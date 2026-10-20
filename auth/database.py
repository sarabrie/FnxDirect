from contextlib import contextmanager
from psycopg2 import pool
from auth.config import get_settings

_pool: pool.ThreadedConnectionPool | None = None


def init_pool() -> None:
    global _pool
    s = get_settings()
    _pool = pool.ThreadedConnectionPool(s.DB_POOL_MIN, s.DB_POOL_MAX, s.DATABASE_URL)


def get_pool() -> pool.ThreadedConnectionPool:
    if _pool is None:
        raise RuntimeError("DB pool not initialised — call init_pool() at startup")
    return _pool


@contextmanager
def get_conn():
    conn = get_pool().getconn()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        get_pool().putconn(conn)


@contextmanager
def transaction():
    """Yields a cursor inside an atomic transaction."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            try:
                yield cur
                conn.commit()
            except Exception:
                conn.rollback()
                raise
