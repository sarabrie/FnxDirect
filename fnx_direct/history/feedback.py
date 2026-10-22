"""
Like / dislike feedback on answers. A dislike drops the answer from the cache; a dislike for
inaccuracy also lowers the score of the chunks behind the answer, so retrieval ranks them lower.
"""
import json
from contextlib import closing

from fnx_direct.history.database import DATABASE_PATH, connect

LIKE = "LIKE"
DISLIKE = "DISLIKE"
INACCURATE_REASON = "המידע אינו מדויק או שגוי"


def save_feedback(message_id, conversation_id, user_id, rating, reasons, comment, database_path=DATABASE_PATH):
    reasons_json = json.dumps(reasons or [], ensure_ascii=False)
    with closing(connect(database_path)) as connection:
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
            if rating != DISLIKE:
                return
            # Don't keep serving a cached answer that a user marked as bad.
            connection.execute(
                "DELETE FROM answer_cache WHERE answer = (SELECT content FROM messages WHERE id=?)",
                (message_id,),
            )
            if INACCURATE_REASON in (reasons or []):
                _penalize_chunks(connection, message_id)


def _penalize_chunks(connection, message_id):
    row = connection.execute("SELECT chunk_ids_json FROM messages WHERE id=?", (message_id,)).fetchone()
    if not row:
        return
    for chunk_id in json.loads(row["chunk_ids_json"] or "[]"):
        connection.execute(
            """
            INSERT INTO chunk_scores (chunk_id, score, dislike_count)
            VALUES (?, 0.9, 1)
            ON CONFLICT(chunk_id) DO UPDATE SET
                dislike_count = dislike_count + 1,
                score = MAX(0.1, score - 0.1),
                updated_at = CURRENT_TIMESTAMP
            """,
            (chunk_id,),
        )


def get_chunk_scores(chunk_ids, database_path=DATABASE_PATH):
    """Scores for many chunks in a single query; missing chunks default to 1.0."""
    if not chunk_ids:
        return {}
    placeholders = ",".join("?" * len(chunk_ids))
    with closing(connect(database_path)) as connection:
        rows = connection.execute(
            f"SELECT chunk_id, score FROM chunk_scores WHERE chunk_id IN ({placeholders})",
            list(chunk_ids),
        ).fetchall()
    scores = {row["chunk_id"]: row["score"] for row in rows}
    return {chunk_id: scores.get(chunk_id, 1.0) for chunk_id in chunk_ids}


def get_negative_feedback(limit=50, database_path=DATABASE_PATH):
    """Latest dislikes with the answer they refer to (for the admin page)."""
    with closing(connect(database_path)) as connection:
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
