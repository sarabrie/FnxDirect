import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=30)
cur = conn.cursor()

for t in ("users", "refresh_tokens", "user_preferences",
          "conversations", "messages", "message_feedback"):
    cur.execute(f"SELECT count(*) FROM {t}")
    print(t, cur.fetchone()[0])

conn.close()