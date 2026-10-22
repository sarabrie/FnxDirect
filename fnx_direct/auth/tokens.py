"""
Sessions: short-lived JWT access tokens plus refresh tokens with rotation and reuse detection
(a reused refresh token revokes its whole family).
"""
import hashlib
import os
import secrets
from contextlib import closing
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from fnx_direct.auth.database import connect

JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))  # stable only if set in .env
JWT_ALGORITHM = "HS256"
ACCESS_TTL_SECONDS = 15 * 60
REFRESH_TTL_DAYS = 30


def hash_token(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def _issue_access_token(user):
    payload = {
        "sub": user["id"],
        "email": user["email"],
        "name": user["display_name"],
        "exp": datetime.now(timezone.utc) + timedelta(seconds=ACCESS_TTL_SECONDS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_access_token(token):
    """Decoded claims ({"sub", "email", "name", "exp"}) or None if invalid / expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def create_session(user_id, family_id=None):
    """Returns (access_token, refresh_token) for the user."""
    with closing(connect()) as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    access = _issue_access_token(user)
    raw_refresh = secrets.token_urlsafe(48)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=REFRESH_TTL_DAYS)).isoformat()
    with closing(connect()) as conn:
        with conn:
            conn.execute(
                "INSERT INTO refresh_tokens (id, token_hash, user_id, family_id, expires_at) VALUES (?,?,?,?,?)",
                (str(uuid4()), hash_token(raw_refresh), user_id, family_id or str(uuid4()), expires_at),
            )
    return access, raw_refresh


def refresh_session(raw_refresh):
    """Rotates the refresh token. Returns a new (access, refresh) or an error string."""
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM refresh_tokens WHERE token_hash = ?", (hash_token(raw_refresh),)).fetchone()
        if row is None:
            return "טוקן לא תקין."
        if row["is_revoked"]:
            # Reuse detected — revoke entire family
            with conn:
                conn.execute("UPDATE refresh_tokens SET is_revoked=1 WHERE family_id=?", (row["family_id"],))
            return "זוהה שימוש חוזר בטוקן. כל הסשנים בוטלו."
        with conn:
            conn.execute("UPDATE refresh_tokens SET is_revoked=1 WHERE id=?", (row["id"],))
        if datetime.fromisoformat(row["expires_at"]) < datetime.now(timezone.utc):
            return "הסשן פג תוקף. יש להתחבר מחדש."
    return create_session(row["user_id"], row["family_id"])


def revoke_refresh_token(raw_refresh):
    with closing(connect()) as conn:
        with conn:
            conn.execute("UPDATE refresh_tokens SET is_revoked=1 WHERE token_hash=?", (hash_token(raw_refresh),))
