"""Auth SQLite database: connection, schema and migrations."""
from contextlib import closing
from uuid import uuid4

from fnx_direct import db
from fnx_direct.config import AUTH_DB_PATH

_SCHEMA = """
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

CREATE TABLE IF NOT EXISTS google_oauth_states (
    state_hash TEXT PRIMARY KEY,
    expires_at INTEGER NOT NULL
);
"""


def connect():
    return db.connect(AUTH_DB_PATH)


_initialized = False


def init_auth_db():
    # Called on every rerun — run the DDL only once per process.
    global _initialized
    if _initialized:
        return
    _initialized = True
    db.ensure_parent_dir(AUTH_DB_PATH)
    with closing(connect()) as conn:
        conn.execute("PRAGMA journal_mode=WAL")  # persistent on the DB file
        conn.executescript(_SCHEMA)
        db.add_missing_columns(conn, "user_preferences", {
            "preferred_name": "ALTER TABLE user_preferences ADD COLUMN preferred_name TEXT",
            "response_length":
                "ALTER TABLE user_preferences ADD COLUMN response_length TEXT NOT NULL DEFAULT 'standard'",
            "tone": "ALTER TABLE user_preferences ADD COLUMN tone TEXT NOT NULL DEFAULT 'simple'",
        })
        conn.commit()


def create_user(conn, email, display_name, password_hash=None, provider="local", provider_id=None):
    """Inserts a user with default preferences (inside the caller's transaction); returns the id."""
    user_id = str(uuid4())
    conn.execute(
        "INSERT INTO users (id, email, password_hash, auth_provider, provider_id, display_name) VALUES (?,?,?,?,?,?)",
        (user_id, email, password_hash, provider, provider_id, display_name),
    )
    conn.execute("INSERT INTO user_preferences (user_id) VALUES (?)", (user_id,))
    return user_id
