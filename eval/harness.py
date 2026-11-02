"""Run a question set through the pipeline and report execution accuracy."""
import json
import subprocess
import sys
import time
from pathlib import Path

import mlflow
import psycopg

from app.pipeline import CONFIG, MODEL, generate_sql, run_sql
from eval.metrics import has_order_by, percentile, results_match, wilson


def evaluate(items, preds=None):
    records = []
    for item in items:
        if preds:
            sql, latency_ms = preds[item["id"]]["pred_sql"], preds[item["id"]]["latency_ms"]
        else:
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


def report(records, model):
    n = len(records)
    k = sum(r["correct"] for r in records)
    lo, hi = wilson(k, n)
    latencies = [r["latency_ms"] for r in records]
    metrics = {
        "n": n,
        "accuracy": k / n,
        "ci_low": lo,
        "ci_high": hi,
        "valid_rate": sum(r["valid"] for r in records) / n,
        "latency_p50_ms": percentile(latencies, 0.5),
        "latency_p95_ms": percentile(latencies, 0.95),
    }
    print(f"\nModel: {model}")
    print(f"Execution accuracy: {k}/{n} = {k / n:.0%}  (95% CI {lo:.0%}-{hi:.0%})")
    print(f"Valid SQL: {sum(r['valid'] for r in records)}/{n}")
    print(f"Latency: p50 {metrics['latency_p50_ms']} ms, p95 {metrics['latency_p95_ms']} ms")
    for level in ("easy", "medium", "hard"):
        subset = [r for r in records if r["difficulty"] == level]
        if subset:
            print(f"  {level}: {sum(r['correct'] for r in subset)}/{len(subset)}")
            metrics[f"accuracy_{level}"] = sum(r["correct"] for r in subset) / len(subset)
    return metrics


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True).stdout.strip()


def log_run(question_set, model, config, metrics, results_path):
    mlflow.set_experiment("nl2sql-id")
    with mlflow.start_run(run_name=results_path.stem):
        mlflow.log_params({
            "question_set": question_set,
            "model": model,
            "config": config,
            "git_commit": git("rev-parse", "--short", "HEAD"),
            "git_dirty": bool(git("status", "--porcelain")),  # True: code differed from that commit
        })
        mlflow.log_metrics(metrics)
        mlflow.log_artifact(str(results_path))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Usage: python -m eval.harness eval/<set>.jsonl [predictions.jsonl]")
    path = Path(sys.argv[1])
    # Optional second argument: predictions made elsewhere (e.g. Kaggle), named <model>.jsonl
    preds_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    items = [json.loads(line) for line in path.open()]
    verified = [item for item in items if item["verified"]]
    print(f"{len(verified)} verified of {len(items)} items in {path}\n")
    if not verified:
        sys.exit("Nothing to evaluate: no verified items.")

    preds = {p["id"]: p for p in map(json.loads, preds_path.open())} if preds_path else None
    model = preds_path.stem if preds_path else MODEL.replace(":", "-")
    config = "external" if preds_path else CONFIG
    records = evaluate(verified, preds)
    metrics = report(records, model)

    out = Path("eval/results") / f"{path.stem}__{model}__{config}.jsonl"
    out.parent.mkdir(exist_ok=True)
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    print(f"\nPredictions saved to {out}")
    log_run(path.stem, model, config, metrics, out)
    print("Logged to MLflow (view with: uv run mlflow ui)")