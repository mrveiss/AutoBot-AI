"""Shared Redis utility helpers."""

from typing import Any


def decode_redis_value(value: Any) -> str | None:
    """Decode a Redis value from bytes to str, passing through other types.

    Returns None if input is None (null-safe).
    """
    if value is None:
        return None
    return value.decode("utf-8") if isinstance(value, bytes) else value
