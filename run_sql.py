import os
import sys
import time

import psycopg2
from dotenv import load_dotenv

load_dotenv()

if len(sys.argv) < 2:
    sys.exit("usage: python run_sql.py <path to sql file>")

with open(sys.argv[1], encoding="utf-8") as f:
    sql = f.read()

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit("DATABASE_URL not found in .env")

conn = None
for attempt in range(1, 11):
    try:
        conn = psycopg2.connect(url, connect_timeout=30)
        break
    except Exception:
        print(f"attempt {attempt} failed (compute still waking up), retrying in 6 seconds...")
        time.sleep(6)

if conn is None:
    sys.exit("could not connect after 10 attempts. check DATABASE_URL and neonstatus.com")

try:
    with conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    print(f"done: {sys.argv[1]}")
except Exception as e:
    print("SQL error:")
    print(str(e).split("\n")[0])
    sys.exit(1)
finally:
    conn.close()