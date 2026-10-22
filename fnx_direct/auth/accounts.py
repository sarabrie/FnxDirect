"""Email + password accounts: registration and login (bcrypt, timing-safe on unknown emails)."""
import re
from contextlib import closing

import bcrypt

from fnx_direct.auth.database import connect, create_user
from fnx_direct.auth.tokens import create_session

BCRYPT_ROUNDS = 12
# 8–128 characters with at least one letter (any language) and one digit.
_PASSWORD_RE = re.compile(r"^(?=.*[^\W\d_])(?=.*\d).{8,128}$", re.DOTALL)
_INVALID_CREDENTIALS = "אימייל או סיסמה שגויים."
_dummy_hash = None


def _get_dummy_hash():
    # Computed on first use (not at import) — bcrypt is slow and imports should stay fast.
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = bcrypt.hashpw(b"timing-guard-dummy", bcrypt.gensalt(BCRYPT_ROUNDS))
    return _dummy_hash


def validate_password(password):
    """Returns an error message, or None if the password is acceptable."""
    if not _PASSWORD_RE.match(password):
        return "הסיסמה חייבת להכיל לפחות 8 תווים, ובהם לפחות אות אחת וספרה אחת."
    return None


def register_user(email, password, display_name):
    """Returns (access_token, refresh_token) or an error string."""
    error = validate_password(password)
    if error:
        return error
    with closing(connect()) as conn:
        if conn.execute("SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email,)).fetchone():
            return "כתובת האימייל כבר רשומה במערכת."
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()
        with conn:
            user_id = create_user(conn, email.lower().strip(), display_name.strip(), password_hash=password_hash)
    return create_session(user_id)


def login_user(email, password):
    """Returns (access_token, refresh_token) or a generic error string."""
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)).fetchone()
    if row is None:
        bcrypt.checkpw(password.encode(), _get_dummy_hash())  # same time as a real check
        return _INVALID_CREDENTIALS
    stored = row["password_hash"]
    if not stored or not bcrypt.checkpw(password.encode(), stored.encode()):
        return _INVALID_CREDENTIALS
    return create_session(row["id"])
