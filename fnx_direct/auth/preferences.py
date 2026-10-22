"""Per-user answer preferences: how to address the user, answer length and tone."""
from contextlib import closing

from fnx_direct.auth.database import connect

RESPONSE_LENGTHS = ("short", "standard", "detailed")
TONES = ("simple", "formal")
DEFAULT_PREFERENCES = {"preferred_name": None, "response_length": "standard", "tone": "simple"}


def get_bot_preferences(user_id):
    with closing(connect()) as conn:
        row = conn.execute(
            "SELECT preferred_name, response_length, tone FROM user_preferences WHERE user_id=?",
            (user_id,),
        ).fetchone()
    return dict(row) if row else dict(DEFAULT_PREFERENCES)


def save_bot_preferences(user_id, preferred_name, response_length, tone):
    with closing(connect()) as conn:
        with conn:
            conn.execute(
                """
                INSERT INTO user_preferences (user_id, preferred_name, response_length, tone)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    preferred_name  = excluded.preferred_name,
                    response_length = excluded.response_length,
                    tone            = excluded.tone,
                    updated_at      = CURRENT_TIMESTAMP
                """,
                (user_id, preferred_name or None, response_length, tone),
            )
