"""SQLite connection helper shared by the chat-history and auth stores."""
import sqlite3
from pathlib import Path


def connect(database_path):
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def ensure_parent_dir(database_path):
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)


def add_missing_columns(connection, table, columns):
    """Lightweight migration: `columns` maps column name -> ALTER TABLE statement."""
    existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
    for column, ddl in columns.items():
        if column not in existing:
            connection.execute(ddl)
