"""Sign in with Google (OAuth 2.0 authorization-code flow with a one-time `state`)."""
import hashlib
import os
import secrets
import time
from contextlib import closing
from urllib.parse import urlencode

from fnx_direct.auth.database import connect, create_user
from fnx_direct.auth.tokens import create_session

# Streamlit supports single-segment page paths only, hence the underscore.
GOOGLE_CALLBACK_PATH = "/auth_google_callback"
_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
_STATE_TTL_SECONDS = 600


def get_google_redirect_uri():
    configured_uri = os.getenv("GOOGLE_REDIRECT_URI", "").strip()
    if configured_uri:
        return configured_uri
    base_url = os.getenv("BASE_URL", "").strip().rstrip("/")
    return f"{base_url}{GOOGLE_CALLBACK_PATH}" if base_url else None


def _hash_state(state):
    return hashlib.sha256(state.encode()).hexdigest()


def create_google_oauth_state():
    state = secrets.token_urlsafe(32)
    now = int(time.time())
    with closing(connect()) as conn:
        with conn:
            conn.execute("DELETE FROM google_oauth_states WHERE expires_at <= ?", (now,))
            conn.execute(
                "INSERT INTO google_oauth_states (state_hash, expires_at) VALUES (?, ?)",
                (_hash_state(state), now + _STATE_TTL_SECONDS),
            )
    return state


def consume_google_oauth_state(state):
    """True if the state was issued by us and not yet used or expired (single use)."""
    state_hash = _hash_state(state)
    with closing(connect()) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT expires_at FROM google_oauth_states WHERE state_hash = ?",
            (state_hash,),
        ).fetchone()
        conn.execute("DELETE FROM google_oauth_states WHERE state_hash = ?", (state_hash,))
        conn.commit()
    return row is not None and row["expires_at"] > int(time.time())


def build_google_auth_url():
    """The Google sign-in URL, or None when Google OAuth isn't configured."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = get_google_redirect_uri()
    if not client_id or not redirect_uri:
        return None
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
        "state": create_google_oauth_state(),
    }
    return f"{_AUTH_URL}?{urlencode(params)}"


def _upsert_google_user(google_sub, email, display_name):
    with closing(connect()) as conn:
        # Find by provider_id first, then by email
        row = conn.execute(
            "SELECT id FROM users WHERE provider_id=? AND auth_provider='google'", (google_sub,)
        ).fetchone()
        if not row:
            row = conn.execute("SELECT id FROM users WHERE email=? COLLATE NOCASE", (email,)).fetchone()
        with conn:
            if row:
                conn.execute(
                    "UPDATE users SET provider_id=?, auth_provider='google', display_name=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (google_sub, display_name, row["id"]),
                )
                return row["id"]
            return create_user(conn, email, display_name, provider="google", provider_id=google_sub)


def login_or_register_google(code):
    """Exchanges the OAuth code, upserts the user; returns (access, refresh) or an error string."""
    import requests  # only needed here; keeps app start-up fast

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = get_google_redirect_uri()
    if not client_id or not client_secret or not redirect_uri:
        return "חסרות הגדרות Google OAuth בקובץ .env."

    token_data = requests.post(
        _TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    ).json()
    if "error" in token_data:
        return f"שגיאת Google: {token_data.get('error_description', token_data['error'])}"

    info = requests.get(
        _USERINFO_URL,
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
        timeout=10,
    ).json()
    google_sub = info.get("sub")
    email = info.get("email", "").lower().strip()
    display_name = info.get("name") or email.split("@")[0]
    if not google_sub or not email or not info.get("email_verified"):
        return "לא ניתן לקבל פרטי משתמש מאומתים מ-Google."

    return create_session(_upsert_google_user(google_sub, email, display_name))
