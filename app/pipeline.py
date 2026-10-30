"""Question -> SQL -> rows. Smoke-test version: full schema, zero-shot."""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

DSN = os.environ.get("DATABASE_URL", "postgresql://nl2sql:nl2sql@localhost:5432/payments")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
REFERENCE_DATE = "2026-09-30"
SCHEMA = (Path(__file__).parent.parent / "data" / "schema.sql").read_text()

SYSTEM = f"""You translate Indonesian business questions into one PostgreSQL SELECT query.
Today's date is {REFERENCE_DATE}.
Return only the SQL, with no explanation and no markdown.

Database schema:
{SCHEMA}"""


def generate_sql(question: str) -> str:
    body = {
        "model": MODEL,
        "stream": False,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": question},
        ],
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return strip_fences(json.load(resp)["message"]["content"])


def strip_fences(text: str) -> str:
    match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip().rstrip(";")


def run_sql(sql: str):
    with psycopg.connect(DSN) as conn:
        conn.read_only = True
        with conn.cursor() as cur:
            cur.execute(sql)
            return [d.name for d in cur.description], cur.fetchall()


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Berapa total GMV?"
    sql = generate_sql(question)
    print(sql)
    columns, rows = run_sql(sql)
    print(columns)
    for row in rows[:20]:
        print(row)
