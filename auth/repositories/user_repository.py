from uuid import UUID
from auth.database import transaction


def create_user(email: str, password_hash: str | None, display_name: str,
                auth_provider: str = "local", provider_id: str | None = None) -> dict:
    with transaction() as cur:
        cur.execute(
            """
            WITH new_user AS (
                INSERT INTO users (email, password_hash, auth_provider, provider_id, display_name)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING *
            ),
            new_prefs AS (
                INSERT INTO user_preferences (user_id)
                SELECT id FROM new_user
            )
            SELECT * FROM new_user
            """,
            (email, password_hash, auth_provider, provider_id, display_name),
        )
        return _row(cur)


def get_by_email(email: str) -> dict | None:
    with transaction() as cur:
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        return _row(cur)


def get_by_id(user_id: str) -> dict | None:
    with transaction() as cur:
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        return _row(cur)


def get_by_provider(provider_id: str, provider: str) -> dict | None:
    with transaction() as cur:
        cur.execute(
            "SELECT * FROM users WHERE provider_id = %s AND auth_provider = %s",
            (provider_id, provider),
        )
        return _row(cur)


def link_google_provider(user_id: str, provider_id: str) -> None:
    with transaction() as cur:
        cur.execute(
            "UPDATE users SET auth_provider = 'google', provider_id = %s WHERE id = %s",
            (provider_id, user_id),
        )


def _row(cur) -> dict | None:
    if cur.description is None:
        return None
    row = cur.fetchone()
    if row is None:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))
