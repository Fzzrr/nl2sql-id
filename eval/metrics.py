"""Execution-accuracy comparison and summary statistics."""
import math
from collections import Counter
from decimal import Decimal

import sqlglot


def normalize(value):
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return round(float(value), 2)
    return value


def results_match(pred_rows, gold_rows, ordered: bool) -> bool:
    pred = [tuple(normalize(v) for v in row) for row in pred_rows]
    gold = [tuple(normalize(v) for v in row) for row in gold_rows]
    return pred == gold if ordered else Counter(pred) == Counter(gold)


def has_order_by(sql: str) -> bool:
    return sqlglot.parse_one(sql, read="postgres").args.get("order") is not None


def wilson(successes: int, n: int, z: float = 1.96):
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return center - half, center + half


def percentile(values, q: float):
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]
