import json
import sqlite3
from contextlib import closing
from pathlib import Path
from uuid import uuid4


DATABASE_PATH = Path(__file__).with_name("chat_history.sqlite3")


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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS messages_conversation_id_idx
                ON messages(conversation_id, id);
            """
        )
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


def list_conversations(limit=20, database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT id, title, updated_at
            FROM conversations
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
            SELECT role, content, sources_json
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
):
    sources_json = json.dumps(sources or [], ensure_ascii=False)
    title = " ".join((conversation_title or content).split())[:48]
    with closing(_connect(database_path)) as connection:
        with connection:
            connection.execute(
                "INSERT INTO conversations (id) VALUES (?) ON CONFLICT(id) DO NOTHING",
                (conversation_id,),
            )
            connection.execute(
                """
                INSERT INTO messages (conversation_id, role, content, sources_json)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, role, content, sources_json),
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


def delete_conversation(conversation_id, database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        with connection:
            connection.execute(
                "DELETE FROM conversations WHERE id = ?",
                (conversation_id,),
            )