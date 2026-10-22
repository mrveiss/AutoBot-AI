# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
The one in-process evaluator of a ChromaDB ``where`` filter (#18874).

Stores that do not delegate filtering to ChromaDB (the in-memory test backend, the FAISS/GPU
index path) evaluate the same filter shape the real store does, here, once. Supported:
implicit equality, ``$eq $ne $gt $gte $lt $lte $in $nin`` and ``$and`` / ``$or``.

Semantics follow ChromaDB: a missing key satisfies ``$ne`` and ``$nin`` (the research-quarantine
filter relies on that to keep facts that predate the ``collection`` field visible) and nothing
else. Anything unrecognised -- an unknown operator, a malformed operand -- fails CLOSED: no match.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

_MISSING = object()


def _ordered(op: Callable[[Any, Any], bool]) -> Callable[[Any, Any], bool]:
    def compare(actual: Any, operand: Any) -> bool:
        if actual is _MISSING or isinstance(actual, bool) or isinstance(operand, bool):
            return False
        try:
            return bool(op(actual, operand))
        except TypeError:
            return False

    return compare


def _in(actual: Any, operand: Any) -> bool:
    return isinstance(operand, (list, tuple, set, frozenset)) and actual is not _MISSING and actual in operand


def _nin(actual: Any, operand: Any) -> bool:
    return isinstance(operand, (list, tuple, set, frozenset)) and (actual is _MISSING or actual not in operand)


_FIELD_OPS: dict[str, Callable[[Any, Any], bool]] = {
    "$eq": lambda a, o: a is not _MISSING and a == o,
    "$ne": lambda a, o: a is _MISSING or a != o,
    "$gt": _ordered(lambda a, o: a > o),
    "$gte": _ordered(lambda a, o: a >= o),
    "$lt": _ordered(lambda a, o: a < o),
    "$lte": _ordered(lambda a, o: a <= o),
    "$in": _in,
    "$nin": _nin,
}


def _match_field(actual: Any, expected: Any) -> bool:
    """One field against a plain value (equality) or an operator dict (every operator must hold)."""
    if not isinstance(expected, dict):
        return actual is not _MISSING and actual == expected
    if not expected:
        return False
    for op, operand in expected.items():
        fn = _FIELD_OPS.get(op)
        if fn is None or not fn(actual, operand):
            return False
    return True


def _match_logical(metadata: Mapping[str, Any], op: str, clauses: Any) -> bool:
    if not isinstance(clauses, (list, tuple)) or not clauses:
        return False
    results = (matches_where(metadata, c) for c in clauses)
    return all(results) if op == "$and" else any(results)


def matches_where(metadata: Mapping[str, Any] | None, where: Mapping[str, Any] | None) -> bool:
    """True when ``metadata`` satisfies the ChromaDB ``where`` filter; an empty filter matches all."""
    if not where:
        return True
    if not isinstance(where, Mapping):
        return False
    meta = metadata or {}
    for key, expected in where.items():
        if key in ("$and", "$or"):
            ok = _match_logical(meta, key, expected)
        elif key.startswith("$"):
            ok = False  # unknown top-level operator
        else:
            ok = _match_field(meta.get(key, _MISSING), expected)
        if not ok:
            return False
    return True
