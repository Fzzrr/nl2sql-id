"""Seeded synthetic data generator: 8 tables, ~300k transactions."""
import os

import numpy as np
import psycopg

SEED = 42
N_MERCHANTS = 500
N_USERS = 20_000
N_TXNS = 300_000
START = np.datetime64("2025-01-01")
END = np.datetime64("2026-10-01")  # exclusive

CATEGORIES = np.array(["kuliner", "ritel", "transportasi", "hiburan", "jasa"])
CATEGORY_P = [0.35, 0.25, 0.15, 0.10, 0.15]
MEDIAN_AMOUNT = np.array([35_000, 150_000, 25_000, 100_000, 200_000])  # per category
REFUND_P = np.array([0.002, 0.03, 0.01, 0.02, 0.008])  # per category, of successful txns
CITIES = np.array(["Jakarta", "Surabaya", "Bandung", "Medan", "Semarang",
                   "Makassar", "Palembang", "Denpasar", "Yogyakarta", "Balikpapan"])
CITY_P = [0.30, 0.13, 0.12, 0.08, 0.07, 0.06, 0.06, 0.06, 0.07, 0.05]
SEGMENTS = np.array(["reguler", "premium", "bisnis"])
SEGMENT_P = [0.80, 0.15, 0.05]
SEGMENT_SPEND = np.array([1.0, 1.8, 3.0])
BANKS = [("Bank Alpha", "bank"), ("Bank Beta", "bank"), ("Bank Gamma", "bank"),
         ("Dompet Satu", "ewallet"), ("Dompet Dua", "ewallet")]
BANK_P = [0.30, 0.20, 0.15, 0.20, 0.15]
HOUR_W = np.array([1, 1, 1, 1, 1, 2, 4, 6, 7, 7, 8, 12,
                   14, 10, 7, 7, 8, 10, 12, 13, 12, 8, 5, 2])  # lunch and evening peaks

# name, start, end (inclusive), discount_type, discount_value
PROMOS = [
    ("Promo Ramadan 2025", "2025-03-01", "2025-03-30", "percent", 10),
    ("Harbolnas 11.11 2025", "2025-11-11", "2025-11-11", "percent", 20),
    ("Harbolnas 12.12 2025", "2025-12-12", "2025-12-12", "fixed", 25_000),
    ("Promo Gajian Januari 2026", "2026-01-25", "2026-02-02", "fixed", 10_000),
    ("Promo Ramadan 2026", "2026-02-19", "2026-03-20", "percent", 10),
    ("Promo Kemerdekaan 2026", "2026-08-17", "2026-08-17", "percent", 17),
    ("Promo 9.9 2026", "2026-09-09", "2026-09-09", "fixed", 9_000),
]
PROMO_TAKE_UP = 0.4
SPIKES = {"2025-09-09": 1.8, "2025-10-10": 1.8, "2025-11-11": 3.0,
          "2025-12-12": 3.0, "2026-09-09": 1.8}
RAMADAN = [("2025-03-01", "2025-03-31"), ("2026-02-19", "2026-03-21")]  # [start, Idul Fitri)
LEBARAN = ["2025-03-31", "2025-04-01", "2026-03-21", "2026-03-22"]
INCIDENTS = [("2025-02-14", 2), ("2025-05-20", 1), ("2025-08-05", 3), ("2025-11-11", 1),
             ("2026-01-12", 2), ("2026-04-07", 3), ("2026-09-23", 2)]  # (date, bank_id)
FAILURE_REASONS = {
    "INSUFFICIENT_BALANCE": "Saldo tidak mencukupi",
    "TIMEOUT": "Waktu transaksi habis",
    "BANK_DOWNTIME": "Layanan bank sedang gangguan",
    "USER_CANCELLED": "Dibatalkan oleh pengguna",
    "FRAUD_BLOCK": "Diblokir sistem anti-fraud",
}
FAILURE_P = [0.40, 0.25, 0.05, 0.25, 0.05]
REFUND_REASONS = np.array(["Barang tidak sesuai", "Pesanan dibatalkan merchant",
                           "Transaksi ganda", "Layanan tidak diterima"])

COLUMNS = {
    "banks": ("name", "type"),
    "promos": ("name", "start_date", "end_date", "discount_type", "discount_value"),
    "merchants": ("name", "category", "city", "joined_at", "mdr_rate"),
    "users": ("city", "registered_at", "segment"),
    "transactions": ("created_at", "merchant_id", "user_id", "bank_id", "amount_idr", "method",
                     "status", "promo_id", "discount_idr", "fee_idr"),
    "failures": ("txn_id", "reason_code", "reason_text"),
    "refunds": ("txn_id", "amount_idr", "reason", "refunded_at"),
}

SETTLEMENTS_SQL = """
INSERT INTO settlements (merchant_id, settle_date, gross_idr, fee_idr, net_idr)
SELECT merchant_id, created_at::date + 1, SUM(amount_idr), SUM(fee_idr), SUM(amount_idr) - SUM(fee_idr)
FROM transactions
WHERE status = 'success'
GROUP BY merchant_id, created_at::date + 1
ORDER BY 2, 1
"""


def day_weights(days):
    dom = (days - days.astype("datetime64[M]")).astype(int) + 1
    dow = (days.astype(int) + 3) % 7  # 0 = Monday; 1970-01-01 was a Thursday
    w = np.linspace(1.0, 2.0, len(days))  # platform growth
    w *= np.where((dom >= 25) | (dom <= 2), 1.3, 1.0)  # gajian
    w *= np.where(dow >= 5, 1.15, 1.0)
    for start, end in RAMADAN:
        w[(days >= np.datetime64(start)) & (days < np.datetime64(end))] *= 1.15
    w[np.isin(days, np.array(LEBARAN, dtype="datetime64[D]"))] *= 0.6
    for day, mult in SPIKES.items():
        w[days == np.datetime64(day)] *= mult
    return w / w.sum()


def pick_joined(rng, k, u_power, n):
    """Index into entities sorted by join date; only those joined by then, older ones favoured."""
    return (k * rng.random(n) ** u_power).astype(int)

def make_rows(seed=SEED):
    rng = np.random.default_rng(seed)
    n_days = (END - START).astype(int)

    # Entities get ids 1..N in join order, so "joined by day d" is a prefix of the array.
    m_cat = rng.choice(len(CATEGORIES), N_MERCHANTS, p=CATEGORY_P)
    m_city = rng.choice(CITIES, N_MERCHANTS, p=CITY_P)
    m_joined = np.sort(START - 730 + rng.integers(0, 730 + n_days, N_MERCHANTS))
    m_mdr = rng.choice([0.003, 0.007], N_MERCHANTS, p=[0.4, 0.6])
    merchants = [(f"Merchant {i + 1:04d}", CATEGORIES[c], city, j, mdr) for i, (c, city, j, mdr)
                 in enumerate(zip(m_cat.tolist(), m_city.tolist(), m_joined.tolist(), m_mdr.tolist()))]

    u_city = rng.choice(CITIES, N_USERS, p=CITY_P)
    u_city_null = rng.random(N_USERS) < 0.03
    u_registered = np.sort(START - 730 + rng.integers(0, 730 + n_days, N_USERS))
    u_seg = rng.choice(len(SEGMENTS), N_USERS, p=SEGMENT_P)
    users = [(None if null else city, reg, SEGMENTS[s]) for city, null, reg, s
             in zip(u_city.tolist(), u_city_null.tolist(), u_registered.tolist(), u_seg.tolist())]

    days = np.arange(START, END)
    created = np.sort(days[rng.choice(n_days, N_TXNS, p=day_weights(days))]
                      + rng.choice(24, N_TXNS, p=HOUR_W / HOUR_W.sum()) * np.timedelta64(1, "h")
                      + rng.integers(0, 3600, N_TXNS) * np.timedelta64(1, "s"))
    day = created.astype("datetime64[D]")

    m_idx = pick_joined(rng, np.searchsorted(m_joined, day, side="right"), 2.0, N_TXNS)
    u_idx = pick_joined(rng, np.searchsorted(u_registered, day, side="right"), 1.5, N_TXNS)
    cat = m_cat[m_idx]
    amount = np.maximum(1_000, np.round(
        MEDIAN_AMOUNT[cat] * SEGMENT_SPEND[u_seg[u_idx]] * rng.lognormal(0, 0.8, N_TXNS), -2)).astype(np.int64)

    bank = rng.choice(len(BANKS), N_TXNS, p=BANK_P)
    u = rng.random(N_TXNS)
    method = np.where(bank >= 3, np.where(u < 0.5, "QRIS", "EWALLET"),
                      np.select([u < 0.55, u < 0.80], ["QRIS", "VA"], "CARD"))

    incident = np.zeros(N_TXNS, dtype=bool)
    for d, bank_id in INCIDENTS:
        incident |= (day == np.datetime64(d)) & (bank == bank_id - 1)
    u = rng.random(N_TXNS)
    status = np.where(u < 0.03, "pending",
                      np.where(u < 0.03 + np.where(incident, 0.45, 0.09), "failed", "success"))
    success, failed = status == "success", status == "failed"

    promo_idx = np.full(N_TXNS, -1)
    for i, (_, start, end, _, _) in enumerate(PROMOS):
        promo_idx[(day >= np.datetime64(start)) & (day <= np.datetime64(end))] = i
    used = (promo_idx >= 0) & (rng.random(N_TXNS) < PROMO_TAKE_UP)
    is_pct = np.array([p[3] == "percent" for p in PROMOS])[promo_idx]
    value = np.array([p[4] for p in PROMOS])[promo_idx]
    discount = np.where(used, np.where(is_pct, np.round(amount * value / 100), np.minimum(value, amount)), 0)
    promo_id = [p or None for p in np.where(used, promo_idx + 1, 0).tolist()]
    fee = np.where(success, np.round(amount * m_mdr[m_idx]), 0)

    transactions = list(zip(created.tolist(), (m_idx + 1).tolist(), (u_idx + 1).tolist(),
                            (bank + 1).tolist(), amount.tolist(), method.tolist(), status.tolist(),
                            promo_id, discount.astype(np.int64).tolist(), fee.astype(np.int64).tolist()))

    reason = rng.choice(list(FAILURE_REASONS), N_TXNS, p=FAILURE_P)
    reason = np.where(incident & (rng.random(N_TXNS) < 0.85), "BANK_DOWNTIME", reason)
    failures = [(i + 1, r, FAILURE_REASONS[r]) for i, r
                in zip(np.flatnonzero(failed).tolist(), reason[failed].tolist())]

    refunded = success & (rng.random(N_TXNS) < REFUND_P[cat])
    partial = np.maximum(100, np.round(amount * rng.uniform(0.2, 0.9, N_TXNS), -2)).astype(np.int64)
    refund_amount = np.where(rng.random(N_TXNS) < 0.7, amount, partial)
    refund_reason = rng.choice(REFUND_REASONS, N_TXNS)
    refunded_at = created + rng.integers(3600, 14 * 86400, N_TXNS) * np.timedelta64(1, "s")
    refunded &= refunded_at < END  # data ends at END
    refunds = list(zip((np.flatnonzero(refunded) + 1).tolist(), refund_amount[refunded].tolist(),
                       refund_reason[refunded].tolist(), refunded_at[refunded].tolist()))

    return {
        "banks": BANKS,
        "promos": PROMOS,
        "merchants": merchants,
        "users": users,
        "transactions": transactions,
        "failures": failures,
        "refunds": refunds,
    }


def main():
    tables = make_rows()
    dsn = os.environ.get("DATABASE_URL", "postgresql://nl2sql:nl2sql@localhost:5432/payments")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(tables)}, settlements RESTART IDENTITY CASCADE")
        for table, rows in tables.items():
            with cur.copy(f"COPY {table} ({', '.join(COLUMNS[table])}) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(row)
        cur.execute(SETTLEMENTS_SQL)
    print(", ".join(f"{len(rows)} {table}" for table, rows in tables.items()))


if __name__ == "__main__":
    main()
