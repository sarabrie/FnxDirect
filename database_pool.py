import os

import streamlit as st
from psycopg2 import extensions, pool


@st.cache_resource(show_spinner=False)
def get_connection_pool() -> pool.ThreadedConnectionPool:
    return pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=os.environ["DATABASE_URL"],
        connect_timeout=10,
    )


class PooledConnection:
    def __init__(self, connection_pool, connection, cursor_factory=None):
        self._pool = connection_pool
        self._connection = connection
        self._cursor_factory = cursor_factory
        self._returned = False

    def __getattr__(self, name):
        return getattr(self._connection, name)

    def cursor(self, *args, **kwargs):
        if self._cursor_factory is not None:
            kwargs.setdefault("cursor_factory", self._cursor_factory)
        return self._connection.cursor(*args, **kwargs)

    def __enter__(self):
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return self._connection.__exit__(exc_type, exc_value, traceback)

    def close(self):
        if self._returned:
            return
        self._returned = True
        try:
            if not self._connection.closed and (
                self._connection.get_transaction_status()
                != extensions.TRANSACTION_STATUS_IDLE
            ):
                self._connection.rollback()
        except Exception:
            self._pool.putconn(self._connection, close=True)
            raise
        self._pool.putconn(
            self._connection,
            close=bool(self._connection.closed),
        )


def connect(cursor_factory=None) -> PooledConnection:
    connection_pool = get_connection_pool()
    conn = connection_pool.getconn()
    try:
        conn.cursor().execute("SELECT 1")
    except Exception:
        connection_pool.putconn(conn, close=True)
        conn = connection_pool.getconn()
    return PooledConnection(connection_pool, conn, cursor_factory=cursor_factory)
