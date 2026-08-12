# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared Redis utility helpers."""

from typing import Any


def decode_redis_value(value: Any) -> str | None:
    """Decode a Redis value from bytes to str, passing through other types.

    Returns None if input is None (null-safe).
    """
    if value is None:
        return None
    return value.decode("utf-8") if isinstance(value, bytes) else value


def decode_redis_list(value: Any) -> Any:
    """Recursively decode a nested RESP array reply (e.g. ``FT.INFO``).

    Commands like ``FT.INFO`` return a flat/nested list rather than a single
    scalar or a hash, so ``decode_redis_value`` alone only handles one leaf.
    Lists are walked recursively and every leaf goes through
    ``decode_redis_value``, so leaf ``bytes`` are decoded at any depth. Only
    ``list`` is walked: RESP2 returns arrays as lists, and the repo pins no
    ``protocol=3``, so tuples/dicts do not occur here and pass through as-is.
    """
    if isinstance(value, list):
        return [decode_redis_list(item) for item in value]
    return decode_redis_value(value)
