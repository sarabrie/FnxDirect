"""Chat-history SQLite database: connection, schema and migrations."""
from contextlib import closing

from fnx_direct import db
from fnx_direct.config import CHAT_HISTORY_DB_PATH

DATABASE_PATH = CHAT_HISTORY_DB_PATH
DEFAULT_TITLE = "שיחה חדשה"
TITLE_MAX_LENGTH = 48
# Owner key used in hidden_conversations when a conversation has no user (legacy rows).
_ANONYMOUS_OWNER = "__guest__"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'שיחה חדשה',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    prompt_text TEXT,
    follow_up_question TEXT,
    follow_up_questions_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS messages_conversation_id_idx
    ON messages(conversation_id, id);

CREATE TABLE IF NOT EXISTS hidden_conversations (
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    hidden_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (conversation_id, user_id)
);

CREATE TABLE IF NOT EXISTS message_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL,
    user_id TEXT,
    rating TEXT NOT NULL CHECK (rating IN ('LIKE', 'DISLIKE')),
    reasons_json TEXT NOT NULL DEFAULT '[]',
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS feedback_message_idx ON message_feedback(message_id);

CREATE TABLE IF NOT EXISTS answer_cache (
    cache_key TEXT PRIMARY KEY,
    answer TEXT NOT NULL,
    sources_json TEXT NOT NULL DEFAULT '[]',
    chunk_ids_json TEXT NOT NULL DEFAULT '[]',
    prompt_text TEXT,
    follow_up_questions_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chunk_scores (
    chunk_id TEXT PRIMARY KEY,
    score REAL NOT NULL DEFAULT 1.0,
    dislike_count INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def connect(database_path=DATABASE_PATH):
    return db.connect(database_path)


def owner_key(user_id):
    """Key for hidden_conversations.user_id (NOT NULL), also for conversations without an owner."""
    return user_id if user_id is not None else _ANONYMOUS_OWNER


_initialized_paths = set()


def initialize_history(database_path=DATABASE_PATH):
    # Schema setup + cleanup scan only once per process, not on every Streamlit rerun.
    if str(database_path) in _initialized_paths:
        return
    _initialized_paths.add(str(database_path))
    db.ensure_parent_dir(database_path)
    with closing(connect(database_path)) as connection:
        connection.executescript(_SCHEMA)
        db.add_missing_columns(connection, "messages", {
            "chunk_ids_json": "ALTER TABLE messages ADD COLUMN chunk_ids_json TEXT NOT NULL DEFAULT '[]'",
            "prompt_text": "ALTER TABLE messages ADD COLUMN prompt_text TEXT",
            "follow_up_question": "ALTER TABLE messages ADD COLUMN follow_up_question TEXT",
            "follow_up_questions_json":
                "ALTER TABLE messages ADD COLUMN follow_up_questions_json TEXT NOT NULL DEFAULT '[]'",
        })
        db.add_missing_columns(connection, "conversations", {
            "user_id": "ALTER TABLE conversations ADD COLUMN user_id TEXT",
        })
        connection.execute("CREATE INDEX IF NOT EXISTS conversations_user_id_idx ON conversations(user_id)")
        # Conversations are created with their first message; drop any left empty.
        connection.execute(
            """
            DELETE FROM conversations
            WHERE NOT EXISTS (
                SELECT 1 FROM messages
                WHERE messages.conversation_id = conversations.id
            )
            """
        )
        connection.commit()
