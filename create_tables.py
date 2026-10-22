import os
import time
import psycopg2
from dotenv import load_dotenv

load_dotenv()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    sub TEXT PRIMARY KEY,
    email TEXT UNIQUE,
    name TEXT,
    bot_prefs_json TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversations (
    id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    title TEXT,
    hidden BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (id, user_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id SERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources_json TEXT,
    chunk_ids_json TEXT,
    prompt_text TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feedback (
    id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL,
    conversation_id TEXT,
    user_id TEXT,
    rating TEXT,
    reasons_json TEXT,
    comment TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id);
"""

conn = None
for attempt in range(1, 6):
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=30)
        break
    except psycopg2.OperationalError as e:
        print(f"ניסיון {attempt} נכשל: {e}")
        time.sleep(5)

if conn is None:
    raise SystemExit("לא הצלחתי להתחבר. בדקי את DATABASE_URL.")

with conn, conn.cursor() as cur:
    cur.execute(SCHEMA)
    cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public';")
    print("טבלאות במסד:", [r[0] for r in cur.fetchall()])
conn.close()