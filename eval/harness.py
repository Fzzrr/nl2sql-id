"""Run a question set through the pipeline and report execution accuracy."""
import json
import sys
import time
from pathlib import Path

import psycopg

from app.pipeline import MODEL, generate_sql, run_sql
from eval.metrics import has_order_by, percentile, results_match, wilson


def evaluate(items):
    records = []
    for item in items:
        start = time.perf_counter()
        sql = generate_sql(item["question"])
        latency_ms = round((time.perf_counter() - start) * 1000)
        try:
            _, pred_rows = run_sql(sql)
            valid, error = True, None
        except psycopg.Error as e:
            pred_rows, valid, error = None, False, str(e).splitlines()[0]
        _, gold_rows = run_sql(item["gold_sql"])
        correct = valid and results_match(pred_rows, gold_rows, has_order_by(item["gold_sql"]))
        records.append({
            "id": item["id"],
            "difficulty": item["difficulty"],
            "pred_sql": sql,
            "valid": valid,
            "correct": correct,
            "error": error,
            "latency_ms": latency_ms,
        })
        print(f"{'PASS' if correct else 'FAIL'}  {item['id']}  {latency_ms} ms")
    return records


def report(records):
    n = len(records)
    k = sum(r["correct"] for r in records)
    lo, hi = wilson(k, n)
    latencies = [r["latency_ms"] for r in records]
    print(f"\nModel: {MODEL}")
    print(f"Execution accuracy: {k}/{n} = {k / n:.0%}  (95% CI {lo:.0%}-{hi:.0%})")
    print(f"Valid SQL: {sum(r['valid'] for r in records)}/{n}")
    print(f"Latency: p50 {percentile(latencies, 0.5)} ms, p95 {percentile(latencies, 0.95)} ms")
    for level in ("easy", "medium", "hard"):
        subset = [r for r in records if r["difficulty"] == level]
        if subset:
            print(f"  {level}: {sum(r['correct'] for r in subset)}/{len(subset)}")


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "eval/smoke_questions.jsonl")
    items = [json.loads(line) for line in path.open()]
    verified = [item for item in items if item["verified"]]
    print(f"{len(verified)} verified of {len(items)} items in {path}\n")
    if not verified:
        sys.exit("Nothing to evaluate: no verified items.")

    records = evaluate(verified)
    report(records)

    out = Path("eval/results") / f"{path.stem}__{MODEL.replace(':', '-')}.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    print(f"\nPredictions saved to {out}")
