"""
Conversations: ownership, listing/search, renaming and hiding.
Owners are a user id, or "guest:<id>" for a guest session (moved to the account on sign-in).
Hiding removes a conversation from its owner's history; the rows stay in the database.
"""
from contextlib import closing
from uuid import uuid4

from fnx_direct.history.database import DATABASE_PATH, TITLE_MAX_LENGTH, connect, owner_key


def new_conversation_id():
    return str(uuid4())


def guest_owner_id(guest_id):
    return f"guest:{guest_id}"


def migrate_guest_conversations(guest_id, user_id, database_path=DATABASE_PATH):
    if not guest_id or not user_id:
        raise ValueError("מזהה אורח ומזהה משתמש נדרשים להעברת השיחות.")

    guest_owner = guest_owner_id(guest_id)
    with closing(connect(database_path)) as connection:
        with connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM conversations WHERE user_id = ?",
                (guest_owner,),
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
                (user_id, guest_owner, guest_owner),
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
                (user_id, guest_owner),
            )
            connection.execute(
                "UPDATE conversations SET user_id = ? WHERE user_id = ?",
                (user_id, guest_owner),
            )
    return count


def conversation_exists(conversation_id, database_path=DATABASE_PATH, user_id=None):
    with closing(connect(database_path)) as connection:
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
            (conversation_id, user_id, owner_key(user_id)),
        ).fetchone()
    return row is not None


def conversation_is_hidden(conversation_id, database_path=DATABASE_PATH, user_id=None):
    with closing(connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT 1 FROM hidden_conversations
            WHERE conversation_id = ? AND user_id = ?
            """,
            (conversation_id, owner_key(user_id)),
        ).fetchone()
    return row is not None


def list_conversations(limit=20, database_path=DATABASE_PATH, user_id=None, search_query=""):
    """The owner's visible conversations, newest first; `search_query` matches titles and messages."""
    escaped_query = search_query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    search_pattern = f"%{escaped_query}%"
    with closing(connect(database_path)) as connection:
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
            (user_id, owner_key(user_id), search_query.strip(), search_pattern, search_pattern, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def rename_conversation(conversation_id, title, database_path=DATABASE_PATH, user_id=None):
    title = " ".join(title.split())[:TITLE_MAX_LENGTH]
    if not title:
        raise ValueError("כותרת השיחה אינה יכולה להיות ריקה.")

    with closing(connect(database_path)) as connection:
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
                (title, conversation_id, user_id, owner_key(user_id)),
            )
    return cursor.rowcount == 1


def hide_conversation(conversation_id, database_path=DATABASE_PATH, user_id=None):
    with closing(connect(database_path)) as connection:
        with connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO hidden_conversations (conversation_id, user_id)
                SELECT id, ?
                FROM conversations
                WHERE id = ? AND user_id IS ?
                """,
                (owner_key(user_id), conversation_id, user_id),
            )
    return cursor.rowcount == 1
