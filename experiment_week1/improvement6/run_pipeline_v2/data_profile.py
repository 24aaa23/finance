"""Compact statistics from complete relations, not their display samples."""
from collections import Counter

from .relational import _freeze, _null


def column_stats(rows, fields):
    result = {}
    for field in fields:
        counts = Counter(_freeze(row.get(field)) for row in rows if not _null(row.get(field)))
        bound = sum(counts.values())
        result[field] = {"null_count": len(rows) - bound, "distinct_non_null": len(counts),
                         "max_multiplicity": max(counts.values(), default=0)}
    return result
