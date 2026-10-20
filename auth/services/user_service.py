from auth.repositories import preference_repository as pref_repo
from auth.repositories import user_repository as user_repo


def get_profile(user_id: str) -> dict:
    user = user_repo.get_by_id(user_id)
    if not user:
        raise ValueError("User not found.")
    prefs = pref_repo.get_preferences(user_id) or {}
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "display_name": user["display_name"],
        "auth_provider": user["auth_provider"],
        "theme": prefs.get("theme", "system"),
        "created_at": user["created_at"].isoformat(),
    }


def update_preferences(user_id: str, theme: str | None, settings_json: dict | None) -> dict:
    return pref_repo.upsert_preferences(user_id, theme, settings_json)


def get_history(user_id: str, limit: int, before_id: str | None) -> list[dict]:
    rows = pref_repo.get_history_page(user_id, limit, before_id)
    return [
        {
            "id": str(r["id"]),
            "action_type": r["action_type"],
            "metadata": r["metadata_json"],
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]


def migrate_guest_data(user_id: str, guest_actions: list[dict]) -> int:
    """Atomically persist guest actions to the authenticated user's history."""
    valid = [
        a for a in guest_actions
        if isinstance(a.get("action_type"), str) and a["action_type"].strip()
    ]
    if valid:
        pref_repo.bulk_add_history(user_id, valid)
    return len(valid)
