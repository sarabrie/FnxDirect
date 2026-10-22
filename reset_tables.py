import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

OLD_TABLES = ["feedback", "messages", "conversations", "users"]

conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=30)
cur = conn.cursor()

# Safety check: refuse to delete anything that contains rows
for t in OLD_TABLES:
    cur.execute(
        "SELECT to_regclass(%s)", (f"public.{t}",)
    )
    if cur.fetchone()[0] is None:
        continue
    cur.execute(f"SELECT count(*) FROM {t}")
    n = cur.fetchone()[0]
    if n > 0:
        conn.close()
        sys.exit(f"STOPPED: table {t} has {n} rows. Nothing was deleted.")

for t in OLD_TABLES:
    cur.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
    print(f"dropped: {t}")

conn.commit()
conn.close()
print("done. now run the 3 SQL files in order.")