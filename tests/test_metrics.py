from decimal import Decimal

from eval.metrics import has_order_by, percentile, results_match, wilson


def test_unordered_ignores_row_order():
    assert results_match([("a", 1), ("b", 2)], [("b", 2), ("a", 1)], ordered=False)


def test_ordered_checks_row_order():
    assert not results_match([("a", 1), ("b", 2)], [("b", 2), ("a", 1)], ordered=True)


def test_numbers_compared_at_two_decimals():
    assert results_match([(Decimal("0.8725"),)], [(0.87249,)], ordered=False)
    assert results_match([(85283500,)], [(Decimal("85283500"),)], ordered=False)


def test_percent_is_not_fraction():
    assert not results_match([(87.25,)], [(Decimal("0.8725"),)], ordered=False)


def test_duplicate_rows_matter():
    assert not results_match([(1,), (1,)], [(1,)], ordered=False)


def test_order_by_only_counts_at_top_level():
    assert has_order_by("SELECT a FROM t ORDER BY a")
    assert not has_order_by("SELECT a, ROW_NUMBER() OVER (ORDER BY a) FROM t")
    assert not has_order_by("SELECT * FROM (SELECT a FROM t ORDER BY a LIMIT 3) s")


def test_wilson_interval():
    lo, hi = wilson(5, 10)
    assert round(lo, 3) == 0.237 and round(hi, 3) == 0.763
    assert wilson(10, 10)[1] > 0.999


def test_percentile_nearest_rank():
    assert percentile([5, 1, 3, 2, 4], 0.5) == 3
    assert percentile(list(range(1, 11)), 0.95) == 10
