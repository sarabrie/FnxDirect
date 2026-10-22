"""Paths and settings shared by every part of the app. Loads .env once, on first import."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

DATA_DIR = ROOT_DIR / "data"

# ── Knowledge base (ChromaDB index of the website) ───────────────────────────
VECTOR_DB_PATH = DATA_DIR / "fnx_db"
COLLECTION_NAME = "fnx_website_chunks_multilingual"
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# ── SQLite databases (Docker points these at a persistent volume) ────────────
CHAT_HISTORY_DB_PATH = Path(os.getenv("CHAT_HISTORY_DB_PATH", DATA_DIR / "chat_history.sqlite3"))
AUTH_DB_PATH = Path(os.getenv("AUTH_DB_PATH", DATA_DIR / "auth.sqlite3"))

# Learned duration of each search-engine loading stage (see search/engine.py).
WARMUP_TIMES_PATH = DATA_DIR / ".warmup_seconds"

# ── Streamlit page ───────────────────────────────────────────────────────────
PAGE_TITLE = "הפניקס | עוזר אישי"
PAGE_ICON = "✳"
