import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4


DATABASE_PATH = Path(
    os.getenv("CHAT_HISTORY_DB_PATH", Path(__file__).with_name("chat_history.sqlite3"))
)


def _connect(database_path=DATABASE_PATH):
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_history(database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                user_id TEXT,
                title TEXT NOT NULL DEFAULT 'שיחה חדשה',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS conversations_user_id_idx ON conversations(user_id);

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                sources_json TEXT NOT NULL DEFAULT '[]',
                chunk_ids_json TEXT NOT NULL DEFAULT '[]',
                prompt_text TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS messages_conversation_id_idx
                ON messages(conversation_id, id);

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

            CREATE TABLE IF NOT EXISTS chunk_scores (
                chunk_id TEXT PRIMARY KEY,
                score REAL NOT NULL DEFAULT 1.0,
                dislike_count INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        # Migrate existing DB: add columns if they don't exist yet
        existing_cols = {row[1] for row in connection.execute("PRAGMA table_info(messages)").fetchall()}
        if "chunk_ids_json" not in existing_cols:
            connection.execute("ALTER TABLE messages ADD COLUMN chunk_ids_json TEXT NOT NULL DEFAULT '[]'")
        if "prompt_text" not in existing_cols:
            connection.execute("ALTER TABLE messages ADD COLUMN prompt_text TEXT")
        conv_cols = {row[1] for row in connection.execute("PRAGMA table_info(conversations)").fetchall()}
        if "user_id" not in conv_cols:
            connection.execute("ALTER TABLE conversations ADD COLUMN user_id TEXT")
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


def new_conversation_id():
    return str(uuid4())


def conversation_exists(conversation_id, database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        row = connection.execute(
            "SELECT 1 FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
    return row is not None


def list_conversations(limit=20, database_path=DATABASE_PATH, user_id=None):
    with closing(_connect(database_path)) as connection:
        if user_id:
            rows = connection.execute(
                """
                SELECT id, title, updated_at
                FROM conversations
                WHERE user_id = ?
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, title, updated_at
                FROM conversations
                WHERE user_id IS NULL
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
    return [dict(row) for row in rows]


def load_messages(conversation_id, database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT id, role, content, sources_json
            FROM messages
            WHERE conversation_id = ?
            ORDER BY id
            """,
            (conversation_id,),
        ).fetchall()
    return [
        {
            "role": row["role"],
            "content": row["content"],
            "sources": json.loads(row["sources_json"]),
            "message_id": row["id"] if row["role"] == "assistant" else None,
        }
        for row in rows
    ]


def save_message(
    conversation_id,
    role,
    content,
    sources=None,
    database_path=DATABASE_PATH,
    conversation_title=None,
    chunk_ids=None,
    prompt_text=None,
    user_id=None,
):
    sources_json = json.dumps(sources or [], ensure_ascii=False)
    chunk_ids_json = json.dumps(chunk_ids or [], ensure_ascii=False)
    title = " ".join((conversation_title or content).split())[:48]
    with closing(_connect(database_path)) as connection:
        with connection:
            connection.execute(
                "INSERT INTO conversations (id, user_id) VALUES (?, ?) ON CONFLICT(id) DO NOTHING",
                (conversation_id, user_id),
            )
            cursor = connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content, sources_json, chunk_ids_json, prompt_text)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, role, content, sources_json, chunk_ids_json, prompt_text),
            )
            connection.execute(
                """
                UPDATE conversations
                SET title = CASE
                    WHEN title = 'שיחה חדשה' AND ? = 'user' THEN ?
                    ELSE title
                END,
                updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (role, title, conversation_id),
            )
    return cursor.lastrowid


def delete_conversation(conversation_id, database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        with connection:
            connection.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,),
            )


def get_last_message_id(conversation_id, role="assistant", database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        row = connection.execute(
            "SELECT id FROM messages WHERE conversation_id=? AND role=? ORDER BY id DESC LIMIT 1",
            (conversation_id, role),
        ).fetchone()
    return row["id"] if row else None


def save_feedback(message_id, conversation_id, user_id, rating, reasons, comment, database_path=DATABASE_PATH):
    reasons_json = json.dumps(reasons or [], ensure_ascii=False)
    with closing(_connect(database_path)) as connection:
        with connection:
            # Upsert: one feedback per user per message
            existing = connection.execute(
                "SELECT id FROM message_feedback WHERE message_id=? AND (user_id=? OR (user_id IS NULL AND ?=''))",
                (message_id, user_id, user_id or ""),
            ).fetchone()
            if existing:
                connection.execute(
                    "UPDATE message_feedback SET rating=?, reasons_json=?, comment=?, created_at=CURRENT_TIMESTAMP WHERE id=?",
                    (rating, reasons_json, comment, existing["id"]),
                )
            else:
                connection.execute(
                    "INSERT INTO message_feedback (message_id, conversation_id, user_id, rating, reasons_json, comment) VALUES (?,?,?,?,?,?)",
                    (message_id, conversation_id, user_id, rating, reasons_json, comment),
                )
            # Update chunk scores for dislikes with inaccuracy reason
            if rating == "DISLIKE" and "המידע אינו מדויק או שגוי" in (reasons or []):
                row = connection.execute(
                    "SELECT chunk_ids_json FROM messages WHERE id=?", (message_id,)
                ).fetchone()
                if row:
                    chunk_ids = json.loads(row["chunk_ids_json"] or "[]")
                    for cid in chunk_ids:
                        connection.execute(
                            """
                            INSERT INTO chunk_scores (chunk_id, score, dislike_count)
                            VALUES (?, 0.9, 1)
                            ON CONFLICT(chunk_id) DO UPDATE SET
                                dislike_count = dislike_count + 1,
                                score = MAX(0.1, score - 0.1),
                                updated_at = CURRENT_TIMESTAMP
                            """,
                            (cid,),
                        )


def get_chunk_score(chunk_id, database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        row = connection.execute(
            "SELECT score FROM chunk_scores WHERE chunk_id=?", (chunk_id,)
        ).fetchone()
    return row["score"] if row else 1.0


def get_negative_feedback(limit=50, database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT f.id, f.message_id, f.conversation_id, f.user_id,
                   f.rating, f.reasons_json, f.comment, f.created_at,
                   m.content as message_content
            FROM message_feedback f
            JOIN messages m ON m.id = f.message_id
            WHERE f.rating = 'DISLIKE'
            ORDER BY f.created_at DESC LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]