"""Templated (question, SQL) pairs over the toy schema for the smoke-test QLoRA run."""
import json
from difflib import SequenceMatcher
from pathlib import Path

import psycopg

from app.pipeline import SYSTEM, run_sql

OUT = Path("training/toy")
CATEGORIES = ["kuliner", "ritel", "transportasi", "hiburan", "jasa"]
CITIES = ["Jakarta", "Bandung", "Surabaya", "Medan", "Makassar"]
METHODS = ["QRIS", "EWALLET", "VA", "CARD"]
STATUSES = {"sukses": "success", "gagal": "failed", "pending": "pending"}
MONTHS = {"Juli": ("2026-07-01", "2026-08-01"), "Agustus": ("2026-08-01", "2026-09-01"),
          "September": ("2026-09-01", "2026-10-01")}
JOIN_M = "FROM transactions t JOIN merchants m ON m.merchant_id = t.merchant_id"


def make_pairs():
    pairs = []
    for c in CATEGORIES:
        pairs.append((f"Berapa jumlah merchant kategori {c}?",
                      f"SELECT COUNT(*) FROM merchants WHERE category = '{c}'"))
        pairs.append((f"Berapa total fee dari merchant kategori {c}?",
                      f"SELECT SUM(t.fee_idr) AS total_fee {JOIN_M} WHERE t.status = 'success' AND m.category = '{c}'"))
        pairs.append((f"Berapa success rate merchant kategori {c}?",
                      "SELECT ROUND(COUNT(*) FILTER (WHERE t.status = 'success')::numeric / "
                      f"COUNT(*) FILTER (WHERE t.status IN ('success','failed')), 4) AS success_rate {JOIN_M} WHERE m.category = '{c}'"))
        for n in (3, 5):
            pairs.append((f"Tampilkan {n} merchant kategori {c} dengan transaksi terbanyak.",
                          f"SELECT m.name, COUNT(*) AS n_txn {JOIN_M} WHERE m.category = '{c}' "
                          f"GROUP BY m.name ORDER BY n_txn DESC, m.name LIMIT {n}"))
    for city in CITIES:
        pairs.append((f"Sebutkan nama merchant di kota {city}.",
                      f"SELECT name FROM merchants WHERE city = '{city}'"))
        pairs.append((f"Berapa rata-rata nilai transaksi sukses di {city}?",
                      f"SELECT ROUND(AVG(t.amount_idr), 2) AS avg_amount {JOIN_M} WHERE t.status = 'success' AND m.city = '{city}'"))
    for method in METHODS:
        pairs.append((f"Berapa jumlah transaksi dengan metode {method}?",
                      f"SELECT COUNT(*) FROM transactions WHERE method = '{method}'"))
        pairs.append((f"Berapa GMV transaksi {method}?",
                      f"SELECT SUM(amount_idr) AS gmv FROM transactions WHERE status = 'success' AND method = '{method}'"))
    for word, status in STATUSES.items():
        pairs.append((f"Berapa jumlah transaksi {word} per metode pembayaran?",
                      f"SELECT method, COUNT(*) AS n_txn FROM transactions WHERE status = '{status}' GROUP BY method"))
    for month, (start, end) in MONTHS.items():
        pairs.append((f"Berapa GMV bulan {month} 2026?",
                      f"SELECT SUM(amount_idr) AS gmv FROM transactions WHERE status = 'success' "
                      f"AND created_at >= '{start}' AND created_at < '{end}'"))
    for kind, label in (("bank", "bank"), ("ewallet", "e-wallet")):
        pairs.append((f"Berapa GMV lewat {label}?",
                      "SELECT SUM(t.amount_idr) AS gmv FROM transactions t JOIN banks b ON b.bank_id = t.bank_id "
                      f"WHERE t.status = 'success' AND b.type = '{kind}'"))
    return pairs


def main():
    smoke = [json.loads(line) for line in open("eval/smoke_questions.jsonl")]
    kept, dropped = [], []
    for question, sql in make_pairs():
        near = max(SequenceMatcher(None, question.lower(), s["question"].lower()).ratio() for s in smoke)
        if near >= 0.8:
            dropped.append((question, f"near-duplicate of a smoke question ({near:.2f})"))
            continue
        try:
            _, rows = run_sql(sql)
        except psycopg.Error as e:
            dropped.append((question, str(e).splitlines()[0]))
            continue
        if not rows or all(v is None for row in rows for v in row):
            dropped.append((question, "empty result"))
            continue
        kept.append((question, sql))

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "train.jsonl", "w") as f:
        for question, sql in kept:
            f.write(json.dumps({
                "prompt": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}],
                "completion": [{"role": "assistant", "content": sql}],
            }, ensure_ascii=False) + "\n")
    # Questions only: gold SQL stays local and is scored by the harness.
    with open(OUT / "smoke_prompts.jsonl", "w") as f:
        for s in smoke:
            f.write(json.dumps({
                "id": s["id"],
                "prompt": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": s["question"]}],
            }, ensure_ascii=False) + "\n")

    print(f"Kept {len(kept)} pairs, dropped {len(dropped)}")
    for question, reason in dropped:
        print(f"  dropped: {question}  ({reason})")


if __name__ == "__main__":
    main()
