import hashlib
import hmac
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests

from auth.config import get_settings
from auth.repositories import user_repository as user_repo
from auth.repositories import token_repository as token_repo

_DUMMY_HASH = bcrypt.hashpw(b"dummy-timing-guard", bcrypt.gensalt(12))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _issue_access_token(user: dict) -> str:
    s = get_settings()
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "name": user["display_name"],
        "iat": _now(),
        "exp": _now() + timedelta(seconds=s.ACCESS_TOKEN_TTL_SECONDS),
    }
    return jwt.encode(payload, s.JWT_SECRET, algorithm=s.JWT_ALGORITHM)


def _issue_refresh_token(user_id: str, family_id: str | None = None) -> tuple[str, dict]:
    """Returns (raw_token, db_record). family_id=None starts a new family."""
    s = get_settings()
    raw = secrets.token_urlsafe(48)
    fid = family_id or str(uuid.uuid4())
    expires_at = _now() + timedelta(days=s.REFRESH_TOKEN_TTL_DAYS)
    record = token_repo.create_token(_hash_token(raw), user_id, fid, expires_at)
    return raw, record


# ─── Register ────────────────────────────────────────────────────────────────

def register(email: str, password: str, display_name: str) -> tuple[str, str]:
    if user_repo.get_by_email(email):
        raise ValueError("Email already registered.")
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(get_settings().BCRYPT_ROUNDS)).decode()
    user = user_repo.create_user(email, pw_hash, display_name)
    access = _issue_access_token(user)
    refresh, _ = _issue_refresh_token(str(user["id"]))
    return access, refresh


# ─── Login ───────────────────────────────────────────────────────────────────

_GENERIC_AUTH_ERROR = "Invalid email or password."


def login(email: str, password: str) -> tuple[str, str]:
    user = user_repo.get_by_email(email)
    if user is None:
        # Timing-safe: always run bcrypt even for non-existent accounts
        bcrypt.checkpw(password.encode(), _DUMMY_HASH)
        raise ValueError(_GENERIC_AUTH_ERROR)

    stored_hash = user.get("password_hash")
    if not stored_hash or not bcrypt.checkpw(password.encode(), stored_hash.encode()):
        raise ValueError(_GENERIC_AUTH_ERROR)

    access = _issue_access_token(user)
    refresh, _ = _issue_refresh_token(str(user["id"]))
    return access, refresh


# ─── Google OAuth / OIDC ─────────────────────────────────────────────────────

def google_auth(id_token_str: str) -> tuple[str, str]:
    s = get_settings()
    try:
        claims = google_id_token.verify_oauth2_token(
            id_token_str, google_requests.Request(), s.GOOGLE_CLIENT_ID
        )
    except Exception:
        raise ValueError("Invalid Google ID token.")

    if not claims.get("email_verified"):
        raise ValueError("Google account email is not verified.")

    google_sub = claims["sub"]
    email = claims["email"]
    display_name = claims.get("name", email.split("@")[0])

    # 1. Existing Google account
    user = user_repo.get_by_provider(google_sub, "google")
    if user:
        return _issue_access_token(user), _issue_refresh_token(str(user["id"]))[0]

    # 2. Existing local account with same verified email → link
    user = user_repo.get_by_email(email)
    if user:
        user_repo.link_google_provider(str(user["id"]), google_sub)
        user = user_repo.get_by_id(str(user["id"]))
        return _issue_access_token(user), _issue_refresh_token(str(user["id"]))[0]

    # 3. New user
    user = user_repo.create_user(email, None, display_name, "google", google_sub)
    return _issue_access_token(user), _issue_refresh_token(str(user["id"]))[0]


# ─── Refresh with Reuse Detection ────────────────────────────────────────────

def refresh_tokens(raw_refresh: str) -> tuple[str, str]:
    record = token_repo.get_by_hash(_hash_token(raw_refresh))

    if record is None:
        raise ValueError("Invalid refresh token.")

    if record["is_revoked"]:
        # Reuse detected — entire family is compromised
        token_repo.revoke_family(str(record["family_id"]))
        raise ValueError("Refresh token reuse detected. All sessions revoked.")

    if record["expires_at"].replace(tzinfo=timezone.utc) < _now():
        token_repo.revoke_token(str(record["id"]))
        raise ValueError("Refresh token expired.")

    # Rotate: revoke old, issue new in same family
    token_repo.revoke_token(str(record["id"]))
    user = user_repo.get_by_id(str(record["user_id"]))
    if not user:
        raise ValueError("User not found.")

    access = _issue_access_token(user)
    new_refresh, _ = _issue_refresh_token(str(user["id"]), str(record["family_id"]))
    return access, new_refresh


# ─── Logout ──────────────────────────────────────────────────────────────────

def logout(raw_refresh: str | None, revoke_all: bool = False, user_id: str | None = None) -> None:
    if revoke_all and user_id:
        token_repo.revoke_all_for_user(user_id)
        return
    if raw_refresh:
        record = token_repo.get_by_hash(_hash_token(raw_refresh))
        if record:
            token_repo.revoke_token(str(record["id"]))


# ─── Token Verification ──────────────────────────────────────────────────────

def verify_access_token(token: str) -> dict:
    s = get_settings()
    try:
        return jwt.decode(token, s.JWT_SECRET, algorithms=[s.JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise ValueError("Access token expired.")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid access token.")
