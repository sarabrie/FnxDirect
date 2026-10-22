"""Cache of generated answers, so a repeated question is answered without calling Gemini."""
import json
from contextlib import closing

from fnx_direct.history.database import DATABASE_PATH, connect

ANSWER_CACHE_DAYS = 7


def get_cached_answer(cache_key, database_path=DATABASE_PATH):
    with closing(connect(database_path)) as connection:
        row = connection.execute(
            """
            SELECT answer, sources_json, chunk_ids_json, prompt_text, follow_up_questions_json
            FROM answer_cache
            WHERE cache_key = ? AND created_at >= datetime('now', ?)
            """,
            (cache_key, f"-{ANSWER_CACHE_DAYS} days"),
        ).fetchone()
    if row is None:
        return None
    return {
        "answer": row["answer"],
        "sources": json.loads(row["sources_json"] or "[]"),
        "chunk_ids": json.loads(row["chunk_ids_json"] or "[]"),
        "prompt_text": row["prompt_text"] or "",
        "follow_up_questions": json.loads(row["follow_up_questions_json"] or "[]"),
    }


def save_cached_answer(
    cache_key, answer, sources, chunk_ids, prompt_text, follow_up_questions,
    database_path=DATABASE_PATH,
):
    with closing(connect(database_path)) as connection:
        with connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO answer_cache (
                    cache_key, answer, sources_json, chunk_ids_json,
                    prompt_text, follow_up_questions_json
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    cache_key, answer,
                    json.dumps(sources or [], ensure_ascii=False),
                    json.dumps(chunk_ids or [], ensure_ascii=False),
                    prompt_text,
                    json.dumps(follow_up_questions or [], ensure_ascii=False),
                ),
            )
