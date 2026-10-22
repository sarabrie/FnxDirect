"""Messages of a conversation: loading them for display and saving new ones."""
import json
from contextlib import closing

from fnx_direct.history.database import (
    DATABASE_PATH,
    DEFAULT_TITLE,
    TITLE_MAX_LENGTH,
    connect,
    owner_key,
)


def _follow_ups_from_row(row):
    try:
        follow_up_questions = json.loads(row["follow_up_questions_json"] or "[]")
    except (TypeError, json.JSONDecodeError):
        follow_up_questions = []
    if not isinstance(follow_up_questions, list):
        follow_up_questions = []
    # Older rows stored a single follow-up question.
    if not follow_up_questions and row["follow_up_question"]:
        follow_up_questions = [row["follow_up_question"]]
    return follow_up_questions


def load_messages(conversation_id, database_path=DATABASE_PATH, user_id=None):
    with closing(connect(database_path)) as connection:
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
            (conversation_id, user_id, owner_key(user_id)),
        ).fetchall()
    return [
        {
            "role": row["role"],
            "content": row["content"],
            "sources": json.loads(row["sources_json"]),
            "follow_up_questions": _follow_ups_from_row(row),
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
    follow_up_question=None,
    follow_up_questions=None,
    user_id=None,
):
    """Saves a message (creating the conversation on its first message); returns the message id."""
    sources_json = json.dumps(sources or [], ensure_ascii=False)
    chunk_ids_json = json.dumps(chunk_ids or [], ensure_ascii=False)
    if follow_up_questions is None:
        follow_up_questions = [follow_up_question] if follow_up_question else []
    follow_up_questions_json = json.dumps(
        [item for item in follow_up_questions if isinstance(item, str) and item.strip()],
        ensure_ascii=False,
    )
    title = " ".join((conversation_title or content).split())[:TITLE_MAX_LENGTH]
    with closing(connect(database_path)) as connection:
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
                (conversation_id, owner_key(user_id)),
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
            # The first user message names the conversation (until the user renames it).
            connection.execute(
                """
                UPDATE conversations
                SET title = CASE
                    WHEN title = ? AND ? = 'user' THEN ?
                    ELSE title
                END,
                updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (DEFAULT_TITLE, role, title, conversation_id),
            )
    return cursor.lastrowid
