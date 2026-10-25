"""Seeded synthetic data generator (smoke-test scale)."""
import os
from datetime import datetime, timedelta

import numpy as np
import psycopg

SEED = 42
N_MERCHANTS = 50
N_TXNS = 1_000
START = datetime(2026, 7, 1)
END = datetime(2026, 10, 1)  # exclusive

CATEGORIES = ["kuliner", "ritel", "transportasi", "hiburan", "jasa"]
CITIES = ["Jakarta", "Bandung", "Surabaya", "Medan", "Makassar"]
BANKS = [("Bank Alpha", "bank"), ("Bank Beta", "bank"), ("Bank Gamma", "bank"),
         ("Dompet Satu", "ewallet"), ("Dompet Dua", "ewallet")]
METHODS = ["QRIS", "EWALLET", "VA", "CARD"]
STATUSES = ["success", "failed", "pending"]

def make_rows(seed=SEED):
    rng = np.random.default_rng(seed)

    merchants = []
    for i in range(N_MERCHANTS):
        merchants.append((
            f"Merchant {i + 1:03d}",
            str(rng.choice(CATEGORIES, p=[0.35, 0.25, 0.15, 0.10, 0.15])),
            str(rng.choice(CITIES)),
            float(rng.choice([0.003, 0.007], p=[0.4, 0.6])),
        ))

    span = int((END - START).total_seconds())
    txns = []
    for _ in range(N_TXNS):
        merchant_id = int(rng.integers(1, N_MERCHANTS + 1))
        amount = max(1_000, int(round(rng.lognormal(mean=11, sigma=1), -2)))
        status = str(rng.choice(STATUSES, p=[0.85, 0.12, 0.03]))
        mdr = merchants[merchant_id - 1][3]
        fee = round(amount * mdr) if status == "success" else 0
        txns.append((
            START + timedelta(seconds=int(rng.integers(0, span))),
            merchant_id,
            int(rng.integers(1, len(BANKS) + 1)),
            amount,
            str(rng.choice(METHODS, p=[0.45, 0.30, 0.15, 0.10])),
            status,
            fee,
        ))
    return merchants, txns

def main():
    merchants, txns = make_rows()
    dsn = os.environ.get("DATABASE_URL", "postgresql://nl2sql:nl2sql@localhost:5432/payments")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute("TRUNCATE transactions, merchants, banks RESTART IDENTITY CASCADE")
        cur.executemany("INSERT INTO banks (name, type) VALUES (%s, %s)", BANKS)
        cur.executemany(
            "INSERT INTO merchants (name, category, city, mdr_rate) VALUES (%s, %s, %s, %s)",
            merchants,
        )
        cur.executemany(
            "INSERT INTO transactions (created_at, merchant_id, bank_id, amount_idr, method, status, fee_idr) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            txns,
        )
    print(f"Inserted {len(BANKS)} banks, {len(merchants)} merchants, {len(txns)} transactions")


if __name__ == "__main__":
    main()