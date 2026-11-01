from datetime import date, datetime

from data.generate import make_rows

ROWS = make_rows()
TXNS = ROWS["transactions"]  # (created_at, merchant_id, user_id, bank_id, amount_idr, method, status, promo_id, ...)


def test_same_seed_same_data():
    assert make_rows() == ROWS


def test_row_counts():
    assert {t: len(r) for t, r in ROWS.items() if t not in ("failures", "refunds")} == {
        "banks": 5, "promos": 7, "merchants": 500, "users": 20_000, "transactions": 300_000}


def test_transactions_inside_window():
    assert min(t[0] for t in TXNS) >= datetime(2025, 1, 1)
    assert max(t[0] for t in TXNS) < datetime(2026, 10, 1)


def test_no_activity_before_join():
    joined = [m[3] for m in ROWS["merchants"]]
    registered = [u[1] for u in ROWS["users"]]
    for t in TXNS:
        assert joined[t[1] - 1] <= t[0].date()
        assert registered[t[2] - 1] <= t[0].date()


def test_failures_match_failed_transactions():
    failed = {i for i, t in enumerate(TXNS, 1) if t[6] == "failed"}
    assert [f[0] for f in ROWS["failures"]] == sorted(failed)


def test_refunds_follow_successful_transactions():
    for txn_id, amount, _, refunded_at in ROWS["refunds"]:
        created, _, _, _, txn_amount, _, status, *_ = TXNS[txn_id - 1]
        assert status == "success"
        assert 0 < amount <= txn_amount
        assert created < refunded_at < datetime(2026, 10, 1)


def test_promos_used_only_in_their_window():
    for t in TXNS:
        if t[7] is not None:
            _, start, end, _, _ = ROWS["promos"][t[7] - 1]
            assert date.fromisoformat(start) <= t[0].date() <= date.fromisoformat(end)


def test_documented_messiness_present():
    assert any(u[0] is None for u in ROWS["users"])
    assert any(t[6] == "pending" for t in TXNS)
