from typing import Any
from auth.database import transaction


# ─── Preferences ─────────────────────────────────────────────────────────────

def get_preferences(user_id: str) -> dict | None:
    with transaction() as cur:
        cur.execute("SELECT * FROM user_preferences WHERE user_id = %s", (user_id,))
        return _row(cur)


def upsert_preferences(user_id: str, theme: str | None, settings_json: dict | None) -> dict:
    with transaction() as cur:
        cur.execute(
            """
            INSERT INTO user_preferences (user_id, theme, settings_json)
            VALUES (%s, COALESCE(%s, 'system'), COALESCE(%s::jsonb, '{}'))
            ON CONFLICT (user_id) DO UPDATE SET
                theme         = COALESCE(EXCLUDED.theme, user_preferences.theme),
                settings_json = COALESCE(EXCLUDED.settings_json, user_preferences.settings_json),
                updated_at    = NOW()
            RETURNING *
            """,
            (user_id, theme, _json(settings_json)),
        )
        return _row(cur)


# ─── History ─────────────────────────────────────────────────────────────────

def add_history(user_id: str, action_type: str, metadata: dict) -> None:
    with transaction() as cur:
        cur.execute(
            "INSERT INTO user_history (user_id, action_type, metadata_json) VALUES (%s, %s, %s::jsonb)",
            (user_id, action_type, _json(metadata)),
        )


def bulk_add_history(user_id: str, actions: list[dict[str, Any]]) -> None:
    """Used for guest-to-user migration — inserts all actions atomically."""
    with transaction() as cur:
        cur.executemany(
            "INSERT INTO user_history (user_id, action_type, metadata_json) VALUES (%s, %s, %s::jsonb)",
            [(user_id, a["action_type"], _json(a.get("metadata", {}))) for a in actions],
        )


def get_history_page(user_id: str, limit: int, before_id: str | None) -> list[dict]:
    with transaction() as cur:
        if before_id:
            cur.execute(
                """
                SELECT * FROM user_history
                WHERE user_id = %s AND created_at < (
                    SELECT created_at FROM user_history WHERE id = %s
                )
                ORDER BY created_at DESC LIMIT %s
                """,
                (user_id, before_id, limit),
            )
        else:
            cur.execute(
                "SELECT * FROM user_history WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
                (user_id, limit),
            )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _row(cur) -> dict | None:
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([d[0] for d in cur.description], row))


def _json(v) -> str | None:
    if v is None:
        return None
    import json
    return json.dumps(v, ensure_ascii=False)
