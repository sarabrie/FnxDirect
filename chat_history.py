import json
import os
from contextlib import closing
from pathlib import Path
from uuid import uuid4

from psycopg2.extras import RealDictCursor
from database_pool import connect
from performance import timed_function

# Kept for compatibility with existing function signatures; PostgreSQL uses DATABASE_URL.
DATABASE_PATH = Path(
    os.getenv("CHAT_HISTORY_DB_PATH", Path(__file__).with_name("chat_history.sqlite3"))
)


def _connect(database_path=DATABASE_PATH):
    return connect(cursor_factory=RealDictCursor)


def _execute(connection, query, parameters=()):
    cursor = connection.cursor()
    cursor.execute(query, parameters)
    return cursor


def initialize_history(database_path=DATABASE_PATH):
    return None


def new_conversation_id():
    return str(uuid4())


@timed_function("db.conversation_exists")
def conversation_exists(conversation_id, database_path=DATABASE_PATH, user_id=None):
    owner_key = user_id if user_id is not None else "__guest__"
    with closing(_connect(database_path)) as connection:
        row = _execute(connection,
            """
            SELECT 1
            FROM conversations c
            WHERE c.id = %s AND c.user_id IS NOT DISTINCT FROM %s
              AND NOT EXISTS (
                  SELECT 1 FROM hidden_conversations h
                  WHERE h.conversation_id = c.id AND h.user_id = %s
              )
            """,
            (conversation_id, user_id, owner_key),
        ).fetchone()
    return row is not None


@timed_function("db.conversation_is_hidden")
def conversation_is_hidden(conversation_id, database_path=DATABASE_PATH, user_id=None):
    owner_key = user_id if user_id is not None else "__guest__"
    with closing(_connect(database_path)) as connection:
        row = _execute(connection,
            """
            SELECT 1 FROM hidden_conversations
            WHERE conversation_id = %s AND user_id = %s
            """,
            (conversation_id, owner_key),
        ).fetchone()
    return row is not None


@timed_function("db.list_conversations")
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
        rows = _execute(connection,
            """
            SELECT c.id, c.title, c.updated_at
            FROM conversations c
            WHERE c.user_id IS NOT DISTINCT FROM %s
              AND NOT EXISTS (
                  SELECT 1
                  FROM hidden_conversations h
                  WHERE h.conversation_id = c.id AND h.user_id = %s
              )
              AND (
                  %s = ''
                  OR c.title ILIKE %s ESCAPE E'\\\\'
                  OR EXISTS (
                      SELECT 1
                      FROM messages m
                      WHERE m.conversation_id = c.id
                        AND m.content ILIKE %s ESCAPE E'\\\\'
                  )
              )
            ORDER BY c.updated_at DESC, c.created_at DESC
            LIMIT %s
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


@timed_function("db.load_messages")
def _messages_from_rows(rows, include_db_id=False):
    messages = []
    for row in rows:
        message = {
            "role": row["role"],
            "content": row["content"],
            "sources": json.loads(row["sources_json"]),
            "message_id": row["id"] if row["role"] == "assistant" else None,
        }
        if include_db_id:
            message["_db_id"] = row["id"]
        messages.append(message)
    return messages


@timed_function("db.load_messages")
def load_messages(conversation_id, database_path=DATABASE_PATH, user_id=None):
    owner_key = user_id if user_id is not None else "__guest__"
    with closing(_connect(database_path)) as connection:
        rows = _execute(connection,
            """
            SELECT id, role, content, sources_json
            FROM messages
            WHERE conversation_id = %s
              AND EXISTS (
                  SELECT 1 FROM conversations
                  WHERE conversations.id = messages.conversation_id
                    AND conversations.user_id IS NOT DISTINCT FROM %s
              )
              AND NOT EXISTS (
                  SELECT 1 FROM hidden_conversations
                  WHERE hidden_conversations.conversation_id = messages.conversation_id
                    AND hidden_conversations.user_id = %s
              )
            ORDER BY id
            """,
            (conversation_id, user_id, owner_key),
        ).fetchall()
    return _messages_from_rows(rows)


@timed_function("db.load_messages_page")
def load_messages_page(
    conversation_id,
    database_path=DATABASE_PATH,
    user_id=None,
    limit=50,
    before_id=None,
):
    if limit < 1:
        raise ValueError("limit must be positive")
    owner_key = user_id if user_id is not None else "__guest__"
    before_clause = "" if before_id is None else "AND id < %s"
    parameters = (
        (conversation_id, user_id, owner_key, limit + 1)
        if before_id is None
        else (conversation_id, before_id, user_id, owner_key, limit + 1)
    )
    with closing(_connect(database_path)) as connection:
        rows = _execute(
            connection,
            f"""
            SELECT id, role, content, sources_json
            FROM messages
            WHERE conversation_id = %s
              {before_clause}
              AND EXISTS (
                  SELECT 1 FROM conversations
                  WHERE conversations.id = messages.conversation_id
                    AND conversations.user_id IS NOT DISTINCT FROM %s
              )
              AND NOT EXISTS (
                  SELECT 1 FROM hidden_conversations
                  WHERE hidden_conversations.conversation_id = messages.conversation_id
                    AND hidden_conversations.user_id = %s
              )
            ORDER BY id DESC
            LIMIT %s
            """,
            parameters,
        ).fetchall()
    has_more = len(rows) > limit
    return _messages_from_rows(list(reversed(rows[:limit])), include_db_id=True), has_more


@timed_function("db.save_message")
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
            conversation = _execute(connection,
                "SELECT user_id FROM conversations WHERE id = %s",
                (conversation_id,),
            ).fetchone()
            if conversation is None:
                _execute(connection,
                    "INSERT INTO conversations (id, user_id) VALUES (%s, %s)",
                    (conversation_id, user_id),
                )
            elif conversation["user_id"] != user_id:
                raise ValueError("השיחה אינה שייכת למשתמש הנוכחי.")
            elif _execute(connection,
                """
                SELECT 1 FROM hidden_conversations
                WHERE conversation_id = %s AND user_id = %s
                """,
                (conversation_id, user_id if user_id is not None else "__guest__"),
            ).fetchone():
                raise ValueError("השיחה הוסרה מההיסטוריה.")
            cursor = _execute(connection,
                """
                INSERT INTO messages (conversation_id, role, content, sources_json, chunk_ids_json, prompt_text)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (conversation_id, role, content, sources_json, chunk_ids_json, prompt_text),
            )
            _execute(connection,
                """
                UPDATE conversations
                SET title = CASE
                    WHEN title = 'שיחה חדשה' AND %s = 'user' THEN %s
                    ELSE title
                END,
                updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (role, title, conversation_id),
            )
        message_id = cursor.fetchone()["id"]
        connection.commit()
    return message_id


@timed_function("db.rename_conversation")
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
            cursor = _execute(connection,
                """
                UPDATE conversations
                SET title = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id IS NOT DISTINCT FROM %s
                  AND NOT EXISTS (
                      SELECT 1 FROM hidden_conversations
                      WHERE conversation_id = conversations.id AND user_id = %s
                  )
                """,
                (
                    title,
                    conversation_id,
                    user_id,
                    user_id if user_id is not None else "__guest__",
                ),
            )
        connection.commit()
    return cursor.rowcount == 1


@timed_function("db.hide_conversation")
def hide_conversation(conversation_id, database_path=DATABASE_PATH, user_id=None):
    owner_key = user_id if user_id is not None else "__guest__"
    with closing(_connect(database_path)) as connection:
        with connection:
            cursor = _execute(connection,
                """
                INSERT INTO hidden_conversations (conversation_id, user_id)
                SELECT id, %s
                FROM conversations
                WHERE id = %s AND user_id IS NOT DISTINCT FROM %s
                ON CONFLICT (conversation_id, user_id) DO NOTHING
                """,
                (owner_key, conversation_id, user_id),
            )
        connection.commit()
    return cursor.rowcount == 1


def get_last_message_id(conversation_id, role="assistant", database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        row = _execute(connection,
            "SELECT id FROM messages WHERE conversation_id=%s AND role=%s ORDER BY id DESC LIMIT 1",
            (conversation_id, role),
        ).fetchone()
    return row["id"] if row else None


@timed_function("db.save_feedback")
def save_feedback(message_id, conversation_id, user_id, rating, reasons, comment, database_path=DATABASE_PATH):
    reasons_json = json.dumps(reasons or [], ensure_ascii=False)
    with closing(_connect(database_path)) as connection:
        with connection:
            # Upsert: one feedback per user per message
            existing = _execute(connection,
                "SELECT id FROM message_feedback WHERE message_id=%s AND (user_id=%s OR (user_id IS NULL AND %s=''))",
                (message_id, user_id, user_id or ""),
            ).fetchone()
            if existing:
                _execute(connection,
                    "UPDATE message_feedback SET rating=%s, reasons_json=%s, comment=%s, created_at=CURRENT_TIMESTAMP WHERE id=%s",
                    (rating, reasons_json, comment, existing["id"]),
                )
            else:
                _execute(connection,
                    "INSERT INTO message_feedback (message_id, conversation_id, user_id, rating, reasons_json, comment) VALUES (%s,%s,%s,%s,%s,%s)",
                    (message_id, conversation_id, user_id, rating, reasons_json, comment),
                )
            # Update chunk scores for dislikes with inaccuracy reason
            if rating == "DISLIKE" and "המידע אינו מדויק או שגוי" in (reasons or []):
                row = _execute(connection,
                    "SELECT chunk_ids_json FROM messages WHERE id=%s", (message_id,)
                ).fetchone()
                if row:
                    chunk_ids = json.loads(row["chunk_ids_json"] or "[]")
                    for cid in chunk_ids:
                        _execute(connection,
                            """
                            INSERT INTO chunk_scores (chunk_id, score, dislike_count)
                            VALUES (%s, 0.9, 1)
                            ON CONFLICT(chunk_id) DO UPDATE SET
                                dislike_count = dislike_count + 1,
                                score = GREATEST(0.1, score - 0.1),
                                updated_at = CURRENT_TIMESTAMP
                            """,
                            (cid,),
                        )
        connection.commit()


@timed_function("db.get_chunk_score")
def get_chunk_score(chunk_id, database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        row = _execute(connection,
            "SELECT score FROM chunk_scores WHERE chunk_id=%s", (chunk_id,)
        ).fetchone()
    return row["score"] if row else 1.0


@timed_function("db.get_chunk_scores")
def get_chunk_scores(chunk_ids, database_path=DATABASE_PATH):
    chunk_ids = list(chunk_ids)
    if not chunk_ids:
        return {}
    with closing(_connect(database_path)) as connection:
        rows = _execute(
            connection,
            "SELECT chunk_id, score FROM chunk_scores WHERE chunk_id = ANY(%s)",
            (chunk_ids,),
        ).fetchall()
    return {row["chunk_id"]: row["score"] for row in rows}


@timed_function("db.get_negative_feedback")
def get_negative_feedback(limit=50, database_path=DATABASE_PATH):
    with closing(_connect(database_path)) as connection:
        rows = _execute(connection,
            """
            SELECT f.id, f.message_id, f.conversation_id, f.user_id,
                   f.rating, f.reasons_json, f.comment, f.created_at,
                   m.content as message_content
            FROM message_feedback f
            JOIN messages m ON m.id = f.message_id
            WHERE f.rating = 'DISLIKE'
            ORDER BY f.created_at DESC LIMIT %s
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]