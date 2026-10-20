"""
Auth data layer — SQLite-backed, consistent with chat_history.py.
Implements: bcrypt-12, JWT access tokens, refresh token rotation with reuse detection.
"""
import hashlib
import json
import os
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import bcrypt
import jwt

DB_PATH = Path(os.getenv("AUTH_DB_PATH", Path(__file__).with_name("auth.sqlite3")))
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
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_auth_db():
    with closing(_connect()) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT,
                auth_provider TEXT NOT NULL DEFAULT 'local',
                provider_id   TEXT,
                display_name  TEXT NOT NULL,
                created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_users_email       ON users(email);
            CREATE INDEX IF NOT EXISTS idx_users_provider_id ON users(provider_id);

            CREATE TABLE IF NOT EXISTS refresh_tokens (
                id         TEXT PRIMARY KEY,
                token_hash TEXT NOT NULL,
                user_id    TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                family_id  TEXT NOT NULL,
                is_revoked INTEGER NOT NULL DEFAULT 0,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_rt_hash      ON refresh_tokens(token_hash);
            CREATE INDEX IF NOT EXISTS idx_rt_family    ON refresh_tokens(family_id);
            CREATE INDEX IF NOT EXISTS idx_rt_user      ON refresh_tokens(user_id);

            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id           TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                theme             TEXT NOT NULL DEFAULT 'system',
                settings_json     TEXT NOT NULL DEFAULT '{}',
                preferred_name    TEXT,
                response_length   TEXT NOT NULL DEFAULT 'standard' CHECK (response_length IN ('short','standard','detailed')),
                tone              TEXT NOT NULL DEFAULT 'simple' CHECK (tone IN ('simple','formal')),
                updated_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_history (
                id            TEXT PRIMARY KEY,
                user_id       TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                action_type   TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_uh_user_created ON user_history(user_id, created_at DESC);
        """)
        conn.commit()
        # Migrate existing user_preferences rows — add columns if missing
        existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(user_preferences)").fetchall()}
        for col, ddl in [
            ("preferred_name",  "ALTER TABLE user_preferences ADD COLUMN preferred_name TEXT"),
            ("response_length", "ALTER TABLE user_preferences ADD COLUMN response_length TEXT NOT NULL DEFAULT 'standard'"),
            ("tone",            "ALTER TABLE user_preferences ADD COLUMN tone TEXT NOT NULL DEFAULT 'simple'"),
        ]:
            if col not in existing_cols:
                conn.execute(ddl)
        conn.commit()


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expires_iso(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


def _issue_access_token(user: sqlite3.Row | dict) -> str:
    uid = user["id"] if hasattr(user, "__getitem__") else user.id
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
        existing = conn.execute("SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email,)).fetchone()
        if existing:
            return "כתובת האימייל כבר רשומה במערכת."
        uid = str(uuid4())
        pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(BCRYPT_ROUNDS)).decode()
        with conn:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, display_name) VALUES (?,?,?,?)",
                (uid, email.lower().strip(), pw_hash, display_name.strip()),
            )
            conn.execute("INSERT INTO user_preferences (user_id) VALUES (?)", (uid,))
    return _create_session(uid)


# ─── Login ───────────────────────────────────────────────────────────────────

def login_user(email: str, password: str) -> tuple[str, str] | str:
    """Returns (access_token, refresh_token) or generic error string."""
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ? COLLATE NOCASE", (email,)).fetchone()
    if row is None:
        bcrypt.checkpw(password.encode(), _DUMMY_HASH)  # timing-safe
        return "אימייל או סיסמה שגויים."
    stored = row["password_hash"]
    if not stored or not bcrypt.checkpw(password.encode(), stored.encode()):
        return "אימייל או סיסמה שגויים."
    return _create_session(row["id"])


# ─── Session helpers ─────────────────────────────────────────────────────────

def _create_session(user_id: str, family_id: str | None = None) -> tuple[str, str]:
    with closing(_connect()) as conn:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    access = _issue_access_token(user)
    raw_refresh = secrets.token_urlsafe(48)
    fid = family_id or str(uuid4())
    with closing(_connect()) as conn:
        with conn:
            conn.execute(
                "INSERT INTO refresh_tokens (id, token_hash, user_id, family_id, expires_at) VALUES (?,?,?,?,?)",
                (str(uuid4()), _hash_token(raw_refresh), user_id, fid, _expires_iso(REFRESH_TTL_DAYS)),
            )
    return access, raw_refresh


def refresh_session(raw_refresh: str) -> tuple[str, str] | str:
    """Rotate refresh token. Returns new (access, refresh) or error string."""
    h = _hash_token(raw_refresh)
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM refresh_tokens WHERE token_hash = ?", (h,)).fetchone()
        if row is None:
            return "טוקן לא תקין."
        if row["is_revoked"]:
            # Reuse detected — revoke entire family
            with conn:
                conn.execute("UPDATE refresh_tokens SET is_revoked=1 WHERE family_id=?", (row["family_id"],))
            return "זוהה שימוש חוזר בטוקן. כל הסשנים בוטלו."
        exp = datetime.fromisoformat(row["expires_at"])
        if exp < datetime.now(timezone.utc):
            with conn:
                conn.execute("UPDATE refresh_tokens SET is_revoked=1 WHERE id=?", (row["id"],))
            return "הסשן פג תוקף. יש להתחבר מחדש."
        with conn:
            conn.execute("UPDATE refresh_tokens SET is_revoked=1 WHERE id=?", (row["id"],))
    return _create_session(row["user_id"], row["family_id"])


def logout_user(raw_refresh: str) -> None:
    h = _hash_token(raw_refresh)
    with closing(_connect()) as conn:
        with conn:
            conn.execute("UPDATE refresh_tokens SET is_revoked=1 WHERE token_hash=?", (h,))


def get_user_by_id(user_id: str) -> dict | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def get_bot_preferences(user_id: str) -> dict:
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT preferred_name, response_length, tone FROM user_preferences WHERE user_id=?",
            (user_id,),
        ).fetchone()
    if row:
        return dict(row)
    return {"preferred_name": None, "response_length": "standard", "tone": "simple"}


def save_bot_preferences(user_id: str, preferred_name: str | None, response_length: str, tone: str) -> None:
    with closing(_connect()) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, preferred_name, response_length, tone)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferred_name  = excluded.preferred_name,
                    response_length = excluded.response_length,
                    tone            = excluded.tone,
                    updated_at      = CURRENT_TIMESTAMP
                """,
                (user_id, preferred_name or None, response_length, tone),
            )
