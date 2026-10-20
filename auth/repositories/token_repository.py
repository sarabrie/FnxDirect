from auth.database import transaction


def create_token(token_hash: str, user_id: str, family_id: str, expires_at) -> dict:
    with transaction() as cur:
        cur.execute(
            """
            INSERT INTO refresh_tokens (token_hash, user_id, family_id, expires_at)
            VALUES (%s, %s, %s, %s) RETURNING *
            """,
            (token_hash, user_id, family_id, expires_at),
        )
        return _row(cur)


def get_by_hash(token_hash: str) -> dict | None:
    with transaction() as cur:
        cur.execute(
            "SELECT * FROM refresh_tokens WHERE token_hash = %s", (token_hash,)
        )
        return _row(cur)


def revoke_token(token_id: str) -> None:
    with transaction() as cur:
        cur.execute(
            "UPDATE refresh_tokens SET is_revoked = TRUE WHERE id = %s", (token_id,)
        )


def revoke_family(family_id: str) -> None:
    """Revoke all tokens in a family — called on reuse detection (compromised session)."""
    with transaction() as cur:
        cur.execute(
            "UPDATE refresh_tokens SET is_revoked = TRUE WHERE family_id = %s",
            (family_id,),
        )


def revoke_all_for_user(user_id: str) -> None:
    with transaction() as cur:
        cur.execute(
            "UPDATE refresh_tokens SET is_revoked = TRUE WHERE user_id = %s", (user_id,)
        )


def _row(cur) -> dict | None:
    if cur.description is None:
        return None
    row = cur.fetchone()
    if row is None:
        return None
    return dict(zip([d[0] for d in cur.description], row))
