"""Review unverified eval items one at a time and record your verdict."""
import json
import re
import sys
from pathlib import Path

import psycopg

from app.pipeline import run_sql

BANNED = re.compile(r"CURRENT_DATE|NOW\(\)|BETWEEN", re.IGNORECASE)  # gold SQL conventions


def save(path, items):
    path.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items))


def main(path):
    path = Path(path)
    items = [json.loads(line) for line in path.read_text().splitlines()]
    todo = [item for item in items if not item["verified"]]
    to_fix = []
    for n, item in enumerate(todo, 1):
        print(f"\n[{n}/{len(todo)}] {item['id']} ({item['difficulty']}) {item['tags']}")
        print(f"Q:     {item['question']}")
        print(f"Notes: {item['notes'] or '-'}")
        print(f"SQL:   {item['gold_sql']}")
        if BANNED.search(item["gold_sql"]):
            print("WARNING: uses CURRENT_DATE, NOW() or BETWEEN")
        try:
            columns, rows = run_sql(item["gold_sql"])
        except psycopg.Error as e:
            print(f"ERROR: {str(e).splitlines()[0]}")
            columns, rows = [], []
        print(f"{len(rows)} rows {columns}")
        for row in rows[:10]:
            print("  ", row)
        answer = input("[y] verified  [n] needs fixing  [s] skip  [q] quit > ").strip().lower()
        if answer == "q":
            break
        if answer == "y":
            item["verified"] = True
            save(path, items)  # after every answer, so quitting keeps your progress
        elif answer == "n":
            to_fix.append(item["id"])
    print(f"\n{sum(item['verified'] for item in items)}/{len(items)} verified. "
          f"Needs fixing: {', '.join(to_fix) or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1])
