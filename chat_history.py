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
        if "follow_up_question" not in existing_cols:
            connection.execute("ALTER TABLE messages ADD COLUMN follow_up_question TEXT")
        if "follow_up_questions_json" not in existing_cols:
            connection.execute(
                "ALTER TABLE messages ADD COLUMN follow_up_questions_json TEXT NOT NULL DEFAULT '[]'"
            )
        conv_cols = {row[1] for row in connection.execute("PRAGMA table_info(conversations)").fetchall()}
        if "user_id" not in conv_cols:
            connection.execute("ALTER TABLE conversations ADD COLUMN user_id TEXT")
        connection.execute("CREATE INDEX IF NOT EXISTS conversations_user_id_idx ON conversations(user_id)")
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


def migrate_guest_conversations(guest_id, user_id, database_path=DATABASE_PATH):
    if not guest_id or not user_id:
        raise ValueError("מזהה אורח ומזהה משתמש נדרשים להעברת השיחות.")

    guest_owner_id = f"guest:{guest_id}"
    with closing(_connect(database_path)) as connection:
        with connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM conversations WHERE user_id = ?",
                (guest_owner_id,),
            ).fetchone()[0]
            if not count:
                return 0

            connection.execute(
                """
                UPDATE hidden_conversations
                SET user_id = ?
                WHERE user_id = ?
                  AND conversation_id IN (
                      SELECT id FROM conversations WHERE user_id = ?
                  )
                """,
                (user_id, guest_owner_id, guest_owner_id),
            )
            connection.execute(
                """
                UPDATE message_feedback
                SET user_id = ?
                WHERE user_id IS NULL
                  AND conversation_id IN (
                      SELECT id FROM conversations WHERE user_id = ?
                  )
                """,
                (user_id, guest_owner_id),
            )
            connection.execute(
                "UPDATE conversations SET user_id = ? WHERE user_id = ?",
                (user_id, guest_owner_id),
            )
    return count


def conversation_exists(conversation_id, database_path=DATABASE_PATH, user_id=None):
    owner_key = user_id if user_id is not None else "__guest__"
    with closing(_connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT 1
            FROM conversations c
            WHERE c.id = ? AND c.user_id IS ?
              AND NOT EXISTS (
                  SELECT 1 FROM hidden_conversations h
                  WHERE h.conversation_id = c.id AND h.user_id = ?
              )
            """,
            (conversation_id, user_id, owner_key),
        ).fetchone()
    return row is not None


def conversation_is_hidden(conversation_id, database_path=DATABASE_PATH, user_id=None):
    owner_key = user_id if user_id is not None else "__guest__"
    with closing(_connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT 1 FROM hidden_conversations
            WHERE conversation_id = ? AND user_id = ?
            """,
            (conversation_id, owner_key),
        ).fetchone()
    return row is not None


def list_conversations(
    limit=20,
    database_path=DATABASE_PATH,
    user_id=None,
    search_query="",
):
    owner_key = user_id if user_id is not None else "__guest__"
    escaped_query = search_query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    search_pattern = f"%{escaped_query}%"
    with closing(_connect(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT c.id, c.title, c.updated_at
            FROM conversations c
            WHERE c.user_id IS ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM hidden_conversations h
                  WHERE h.conversation_id = c.id AND h.user_id = ?
              )
              AND (
                  ? = ''
                  OR c.title LIKE ? ESCAPE '\\'
                  OR EXISTS (
                      SELECT 1
                      FROM messages m
                      WHERE m.conversation_id = c.id
                        AND m.content LIKE ? ESCAPE '\\'
                  )
              )
            ORDER BY c.updated_at DESC, c.created_at DESC
            LIMIT ?
            """,
            (
                user_id,
                owner_key,
                search_query.strip(),
                search_pattern,
                search_pattern,
                limit,
            ),
        ).fetchall()
    return [dict(row) for row in rows]


def load_messages(conversation_id, database_path=DATABASE_PATH, user_id=None):
    owner_key = user_id if user_id is not None else "__guest__"
    with closing(_connect(database_path)) as connection:
        rows = connection.execute(
            """
            SELECT id, role, content, sources_json, follow_up_question, follow_up_questions_json
            FROM messages
            WHERE conversation_id = ?
              AND EXISTS (
                  SELECT 1 FROM conversations
                  WHERE conversations.id = messages.conversation_id
                    AND conversations.user_id IS ?
              )
              AND NOT EXISTS (
                  SELECT 1 FROM hidden_conversations
                  WHERE hidden_conversations.conversation_id = messages.conversation_id
                    AND hidden_conversations.user_id = ?
              )
            ORDER BY id
            """,
            (conversation_id, user_id, owner_key),
        ).fetchall()
    messages = []
    for row in rows:
        try:
            follow_up_questions = json.loads(row["follow_up_questions_json"] or "[]")
        except (TypeError, json.JSONDecodeError):
            follow_up_questions = []
        if not isinstance(follow_up_questions, list):
            follow_up_questions = []
        if not follow_up_questions and row["follow_up_question"]:
            follow_up_questions = [row["follow_up_question"]]
        messages.append({
            "role": row["role"],
            "content": row["content"],
            "sources": json.loads(row["sources_json"]),
            "follow_up_questions": follow_up_questions,
            "message_id": row["id"] if row["role"] == "assistant" else None,
        })
    return messages


def save_message(
    conversation_id,
    role,
    content,
    sources=None,
    database_path=DATABASE_PATH,
    conversation_title=None,
    chunk_ids=None,
    prompt_text=None,
    follow_up_question=None,
    follow_up_questions=None,
    user_id=None,
):
    sources_json = json.dumps(sources or [], ensure_ascii=False)
    chunk_ids_json = json.dumps(chunk_ids or [], ensure_ascii=False)
    if follow_up_questions is None:
        follow_up_questions = [follow_up_question] if follow_up_question else []
    follow_up_questions_json = json.dumps(
        [item for item in follow_up_questions if isinstance(item, str) and item.strip()],
        ensure_ascii=False,
    )
    title = " ".join((conversation_title or content).split())[:48]
    with closing(_connect(database_path)) as connection:
        with connection:
            conversation = connection.execute(
                "SELECT user_id FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
            if conversation is None:
                connection.execute(
                    "INSERT INTO conversations (id, user_id) VALUES (?, ?)",
                    (conversation_id, user_id),
                )
            elif conversation["user_id"] != user_id:
                raise ValueError("השיחה אינה שייכת למשתמש הנוכחי.")
            elif connection.execute(
                """
                SELECT 1 FROM hidden_conversations
                WHERE conversation_id = ? AND user_id = ?
                """,
                (conversation_id, user_id if user_id is not None else "__guest__"),
            ).fetchone():
                raise ValueError("השיחה הוסרה מההיסטוריה.")
            cursor = connection.execute(
                """
                INSERT INTO messages (
                    conversation_id, role, content, sources_json,
                    chunk_ids_json, prompt_text, follow_up_question,
                    follow_up_questions_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conversation_id, role, content, sources_json,
                    chunk_ids_json, prompt_text, follow_up_question,
                    follow_up_questions_json,
                ),
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


def rename_conversation(
    conversation_id,
    title,
    database_path=DATABASE_PATH,
    user_id=None,
):
    title = " ".join(title.split())[:48]
    if not title:
        raise ValueError("כותרת השיחה אינה יכולה להיות ריקה.")

    with closing(_connect(database_path)) as connection:
        with connection:
            cursor = connection.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id IS ?
                  AND NOT EXISTS (
                      SELECT 1 FROM hidden_conversations
                      WHERE conversation_id = conversations.id AND user_id = ?
                  )
                """,
                (
                    title,
                    conversation_id,
                    user_id,
                    user_id if user_id is not None else "__guest__",
                ),
            )
    return cursor.rowcount == 1


def hide_conversation(conversation_id, database_path=DATABASE_PATH, user_id=None):
    owner_key = user_id if user_id is not None else "__guest__"
    with closing(_connect(database_path)) as connection:
        with connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO hidden_conversations (conversation_id, user_id)
                SELECT id, ?
                FROM conversations
                WHERE id = ? AND user_id IS ?
                """,
                (owner_key, conversation_id, user_id),
            )
    return cursor.rowcount == 1


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