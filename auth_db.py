"""
Auth data layer — PostgreSQL-backed.
Implements: bcrypt-12, JWT access tokens, refresh token rotation with reuse detection.
"""
import hashlib
import os
import re
import secrets
from contextlib import closing
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
import jwt
import psycopg2
from psycopg2.extras import RealDictCursor
from performance import timed_function

JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))  # stable only if set in .env
JWT_ALGORITHM = "HS256"
ACCESS_TTL = 15 * 60          # 15 min
REFRESH_TTL_DAYS = 30
BCRYPT_ROUNDS = 12

_PASSWORD_RE = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()\-_=+\[\]{};:'\",.<>/?\\|`~]).{8,128}$"
)
_DUMMY_HASH = bcrypt.hashpw(b"timing-guard-dummy", bcrypt.gensalt(BCRYPT_ROUNDS))


# ─── Schema ──────────────────────────────────────────────────────────────────

def _connect():
    return psycopg2.connect(
        os.environ["DATABASE_URL"],
        cursor_factory=RealDictCursor,
    )


def init_auth_db():
    return None


def _execute(connection, query, parameters=()):
    cursor = connection.cursor()
    cursor.execute(query, parameters)
    return cursor


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _issue_access_token(user: dict) -> str:
    uid = str(user["id"])
    email = user["email"]
    name = user["display_name"]
    payload = {
        "sub": uid,
        "email": email,
        "name": name,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=ACCESS_TTL),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


# ─── Register ────────────────────────────────────────────────────────────────

def validate_password(password: str) -> str | None:
    """Returns error message or None if valid."""
    if not _PASSWORD_RE.match(password):
        return "הסיסמה חייבת להכיל 8–128 תווים, אות גדולה, אות קטנה, ספרה וסימן מיוחד."
    return None


def register_user(email: str, password: str, display_name: str) -> tuple[str, str] | str:
    """Returns (access_token, refresh_token) or error string."""
    err = validate_password(password)
    if err:
        return err
    with closing(_connect()) as conn:
        existing = _execute(
            conn,
            "SELECT id FROM users WHERE LOWER(email) = LOWER(%s)",
            (email,),
        ).fetchone()
        if existing:
            return "כתובת האימייל כבר רשומה במערכת."
        uid = str(uuid4())
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()
        with conn:
            _execute(
                conn,
                "INSERT INTO users (id, email, password_hash, display_name) VALUES (%s,%s,%s,%s)",
                (uid, email.lower().strip(), pw_hash, display_name.strip()),
            )
            _execute(conn, "INSERT INTO user_preferences (user_id) VALUES (%s)", (uid,))
        conn.commit()
    return _create_session(uid)


# ─── Login ───────────────────────────────────────────────────────────────────

def login_user(email: str, password: str) -> tuple[str, str] | str:
    """Returns (access_token, refresh_token) or generic error string."""
    with closing(_connect()) as conn:
        row = _execute(
            conn,
            "SELECT * FROM users WHERE LOWER(email) = LOWER(%s)",
            (email,),
        ).fetchone()
    if row is None:
        bcrypt.checkpw(password.encode(), _DUMMY_HASH)  # timing-safe
        return "אימייל או סיסמה שגויים."
    stored = row["password_hash"]
    if not stored or not bcrypt.checkpw(password.encode(), stored.encode()):
        return "אימייל או סיסמה שגויים."
    return _create_session(str(row["id"]))


# ─── Session helpers ─────────────────────────────────────────────────────────

def _create_session(user_id: str, family_id: str | None = None) -> tuple[str, str]:
    with closing(_connect()) as conn:
        user = _execute(conn, "SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
    access = _issue_access_token(user)
    raw_refresh = secrets.token_urlsafe(48)
    fid = family_id or str(uuid4())
    with closing(_connect()) as conn:
        with conn:
            _execute(
                conn,
                "INSERT INTO refresh_tokens (id, token_hash, user_id, family_id, expires_at) VALUES (%s,%s,%s,%s,%s)",
                (str(uuid4()), _hash_token(raw_refresh), user_id, fid, _expires_iso(REFRESH_TTL_DAYS)),
            )
        conn.commit()
    return access, raw_refresh


def refresh_session(raw_refresh: str) -> tuple[str, str] | str:
    """Rotate refresh token. Returns new (access, refresh) or error string."""
    h = _hash_token(raw_refresh)
    with closing(_connect()) as conn:
        row = _execute(conn, "SELECT * FROM refresh_tokens WHERE token_hash = %s", (h,)).fetchone()
        if row is None:
            return "טוקן לא תקין."
        if row["is_revoked"]:
            # Reuse detected — revoke entire family
            with conn:
                _execute(
                    conn,
                    "UPDATE refresh_tokens SET is_revoked=TRUE WHERE family_id=%s",
                    (str(row["family_id"]),),
                )
            conn.commit()
            return "זוהה שימוש חוזר בטוקן. כל הסשנים בוטלו."
        exp = row["expires_at"]
        if isinstance(exp, str):
            exp = datetime.fromisoformat(exp)
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            with conn:
                _execute(
                    conn,
                    "UPDATE refresh_tokens SET is_revoked=TRUE WHERE id=%s",
                    (str(row["id"]),),
                )
            conn.commit()
            return "הסשן פג תוקף. יש להתחבר מחדש."
        with conn:
            _execute(
                conn,
                "UPDATE refresh_tokens SET is_revoked=TRUE WHERE id=%s",
                (str(row["id"]),),
            )
        conn.commit()
    return _create_session(str(row["user_id"]), str(row["family_id"]))


def logout_user(raw_refresh: str) -> None:
    h = _hash_token(raw_refresh)
    with closing(_connect()) as conn:
        with conn:
            _execute(
                conn,
                "UPDATE refresh_tokens SET is_revoked=TRUE WHERE token_hash=%s",
                (h,),
            )
        conn.commit()


def get_user_by_id(user_id: str) -> dict | None:
    with closing(_connect()) as conn:
        row = _execute(conn, "SELECT * FROM users WHERE id=%s", (user_id,)).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["id"] = str(result["id"])
    return result


# ─── Google OAuth ──────────────────────────────────────────────────────────────

def build_google_auth_url() -> str | None:
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8501")
    if not client_id:
        return None
    from urllib.parse import urlencode
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)


def login_or_register_google(code: str) -> tuple[str, str] | str:
    """Exchange OAuth code for tokens, upsert user, return (access, refresh) or error string."""
    import requests as _requests
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8501")
    if not client_id or not client_secret:
        return "חסרות הגדרות Google OAuth בקובץ .env."

    # Exchange code for tokens
    token_resp = _requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10,
    )
    token_data = token_resp.json()
    if "error" in token_data:
        return f"שגיאת Google: {token_data.get('error_description', token_data['error'])}"

    # Get user info
    userinfo_resp = _requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {token_data['access_token']}"},
        timeout=10,
    )
    info = userinfo_resp.json()
    google_sub = info.get("sub")
    email = info.get("email", "").lower().strip()
    display_name = info.get("name") or email.split("@")[0]

    if not google_sub or not email:
        return "לא ניתן לקבל פרטי משתמש מ -Google."

    with closing(_connect()) as conn:
        # Find by provider_id first, then by email
        row = _execute(
            conn,
            "SELECT id FROM users WHERE provider_id=%s AND auth_provider='google'",
            (google_sub,),
        ).fetchone()
        if not row:
            row = _execute(
                conn,
                "SELECT id FROM users WHERE LOWER(email)=LOWER(%s)",
                (email,),
            ).fetchone()
        if row:
            uid = str(row["id"])
            with conn:
                _execute(
                    conn,
                    "UPDATE users SET provider_id=%s, auth_provider='google', display_name=%s, updated_at=CURRENT_TIMESTAMP WHERE id=%s",
                    (google_sub, display_name, uid),
                )
        else:
            uid = str(uuid4())
            with conn:
                _execute(
                    conn,
                    "INSERT INTO users (id, email, auth_provider, provider_id, display_name) VALUES (%s,%s,%s,%s,%s)",
                    (uid, email, "google", google_sub, display_name),
                )
                _execute(conn, "INSERT INTO user_preferences (user_id) VALUES (%s)", (uid,))
        conn.commit()

    return _create_session(uid)


@timed_function("db.get_bot_preferences")
def get_bot_preferences(user_id: str) -> dict:
    with closing(_connect()) as conn:
        row = _execute(
            conn,
            "SELECT preferred_name, response_length, tone FROM user_preferences WHERE user_id=%s",
            (user_id,),
        ).fetchone()
    if row:
        return dict(row)
    return {"preferred_name": None, "response_length": "standard", "tone": "simple"}


@timed_function("db.save_bot_preferences")
def save_bot_preferences(user_id: str, preferred_name: str | None, response_length: str, tone: str) -> None:
    with closing(_connect()) as conn:
        with conn:
            _execute(
                conn,
                """
                INSERT INTO user_preferences (user_id, preferred_name, response_length, tone)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferred_name  = EXCLUDED.preferred_name,
                    response_length = EXCLUDED.response_length,
                    tone            = EXCLUDED.tone,
                    updated_at      = CURRENT_TIMESTAMP
                """,
                (user_id, preferred_name or None, response_length, tone),
            )
        conn.commit()
