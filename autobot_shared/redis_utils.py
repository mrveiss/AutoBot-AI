# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared Redis utility helpers: decoding replies, and the atomic release-if-owner."""

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


#: Compare-and-delete in one step. Redis runs a script atomically, so nothing
#: can land between the read and the delete: a GET -> compare -> DEL from the
#: client lets a key expire and be re-taken in the gap, and the DEL then
#: removes the new holder's key instead of the caller's.
COMPARE_AND_DELETE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
"""


async def delete_if_value(redis: Any, key: str, expected: str) -> bool:
    """Delete *key* only while it still holds *expected*; True when it was deleted.

    The release-if-owner for a fence or lock whose value names its holder.
    Redis errors propagate: whether a failed release is fatal is the caller's call.
    """
    return bool(await redis.eval(COMPARE_AND_DELETE_LUA, 1, key, expected))


#: The heartbeat twin of COMPARE_AND_DELETE_LUA: a GET -> compare -> EXPIRE from the client lets the
#: key expire and be re-taken in the gap, and the EXPIRE then extends the new holder's key.
COMPARE_AND_PEXPIRE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
"""


async def expire_if_value(redis: Any, key: str, expected: str, ttl_ms: int) -> bool:
    """Reset *key*'s TTL to *ttl_ms* only while it still holds *expected*; True when it was extended.

    The heartbeat-if-owner for a lock whose value names its holder. False means the caller no
    longer holds it (expired, force-closed or re-taken). Redis errors propagate.
    """
    return bool(await redis.eval(COMPARE_AND_PEXPIRE_LUA, 1, key, expected, int(ttl_ms)))
