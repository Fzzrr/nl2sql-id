"""Near-duplicate check: for each item in set A, the most similar question in set B."""
import json
import re
import sys
from difflib import SequenceMatcher

THRESHOLD = 0.85  # question similarity at or above this counts as a near-duplicate


def norm_question(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower())


def sql_shape(sql):
    """Gold SQL with literals replaced, so 'same query, different date' compares equal."""
    return re.sub(r"\s+", " ", re.sub(r"'[^']*'|\b\d+(\.\d+)?\b", "?", sql.lower()))


def similarity(a, b):
    return SequenceMatcher(None, norm_question(a), norm_question(b)).ratio()


def main(path_a, path_b):
    a = [json.loads(line) for line in open(path_a)]
    b = [json.loads(line) for line in open(path_b)]
    pairs = sorted(((max(b, key=lambda y: similarity(x["question"], y["question"])), x) for x in a),
                   key=lambda p: -similarity(p[1]["question"], p[0]["question"]))
    for y, x in pairs[:10]:
        score = similarity(x["question"], y["question"])
        print(f"{score:.2f}  {x['id']}: {x['question']}\n      {y['id']}: {y['question']}")
    near = [x["id"] for y, x in pairs if similarity(x["question"], y["question"]) >= THRESHOLD]
    shapes = [(x["id"], y["id"]) for x in a for y in b if sql_shape(x["gold_sql"]) == sql_shape(y["gold_sql"])]
    print(f"\nNear-duplicate questions (>= {THRESHOLD}): {near or 'none'}")
    print(f"Same SQL shape, literals stripped: {shapes or 'none'}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
