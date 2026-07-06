# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Async-correctness contract tests for FailurePatternDetector (#10635).

Guards the regression: all ``async def`` methods in FailurePatternDetector
must call ``await redis.<op>`` via the async Redis client, never the sync
client.  A sync ``MagicMock`` would silently accept attribute access
(``mock.get("k")`` returns a ``MagicMock``, not a coroutine), hiding the
bug.  These tests use the canonical ``make_async_redis`` async fake so
that forgetting an ``await`` causes an ``AttributeError`` on the coroutine
object — the same failure mode as production with a real sync client.

Patch target for ``AsyncRedisClientMixin._get_redis``:
``autobot_shared.redis_mixin.get_async_redis_client``
(the mixin resolves through that import, not through the service module).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from services.failure_pattern_detector import (
    KNOWN_PATTERNS_KEY,
    PATTERN_KEY_PREFIX,
    FailurePatternDetector,
)
from tests.fixtures import make_async_redis

_MIXIN_PATH = "autobot_shared.redis_mixin.get_async_redis_client"

# Pattern used by several tests
_CHAIN = "db-down → conn-timeout → request-timeout"
_CHAIN_B = "pool-exhausted → no-connections"
_ERROR_TYPE = "TimeoutError"


def _pattern_key(detector: FailurePatternDetector, chain: str) -> str:
    return f"{PATTERN_KEY_PREFIX}{detector.hash_causal_chain(chain)}"


# ---------------------------------------------------------------------------
# detect_pattern — async path uses await on get()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_pattern_awaits_async_get_on_miss() -> None:
    """detect_pattern() calls await redis.get(...); returns None on miss."""
    redis = make_async_redis(get_returns=None)
    det = FailurePatternDetector()

    with patch(_MIXIN_PATH, new=AsyncMock(return_value=redis)):
        result = await det.detect_pattern(_CHAIN, _ERROR_TYPE)

    assert result is None
    redis.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_detect_pattern_awaits_async_get_on_hit() -> None:
    """detect_pattern() awaits redis.get() and parses the result on a cache hit."""
    det = FailurePatternDetector()
    pattern_hash = det.hash_causal_chain(_CHAIN)
    stored = json.dumps(
        {
            "pattern_id": pattern_hash,
            "causal_chain": _CHAIN,
            "error_types": [_ERROR_TYPE],
            "occurrence_count": 3,
            "successful_resolutions": ["retry"],
            "resolution_success_rate": 0.67,
            "confidence": 0.9,
            "first_seen": "2026-01-01T00:00:00",
            "last_seen": "2026-01-01T00:00:00",
        }
    ).encode()

    redis = make_async_redis(get_returns=stored, smembers_returns=set())
    with patch(_MIXIN_PATH, new=AsyncMock(return_value=redis)):
        result = await det.detect_pattern(_CHAIN, _ERROR_TYPE)

    assert result is not None
    assert result.pattern_id == pattern_hash
    assert result.occurrence_count == 3
    redis.get.assert_awaited()


# ---------------------------------------------------------------------------
# learn_pattern — async path uses await on get() + set() + sadd() + expire()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_learn_pattern_awaits_async_write_ops_on_new_pattern() -> None:
    """learn_pattern() on a fresh key awaits get, set, sadd, expire."""
    redis = make_async_redis(get_returns=None)
    det = FailurePatternDetector()

    with patch(_MIXIN_PATH, new=AsyncMock(return_value=redis)):
        result = await det.learn_pattern(_CHAIN, _ERROR_TYPE)

    assert result.causal_chain == _CHAIN
    assert _ERROR_TYPE in result.error_types
    assert result.occurrence_count == 1
    # All writes must have been awaited.
    redis.set.assert_awaited_once()
    redis.sadd.assert_awaited_once_with(KNOWN_PATTERNS_KEY, det.hash_causal_chain(_CHAIN))
    redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_learn_pattern_awaits_async_get_for_existing() -> None:
    """learn_pattern() on an existing key awaits get to read prior state."""
    det = FailurePatternDetector()
    pattern_hash = det.hash_causal_chain(_CHAIN)
    existing = json.dumps(
        {
            "pattern_id": pattern_hash,
            "causal_chain": _CHAIN,
            "error_types": [],
            "occurrence_count": 1,
            "successful_resolutions": [],
            "resolution_success_rate": 0.0,
            "confidence": 0.7,
            "first_seen": "2026-01-01T00:00:00",
            "last_seen": "2026-01-01T00:00:00",
        }
    ).encode()

    redis = make_async_redis(get_returns=existing)
    with patch(_MIXIN_PATH, new=AsyncMock(return_value=redis)):
        result = await det.learn_pattern(_CHAIN, _ERROR_TYPE, successful_action="retry")

    assert result.occurrence_count == 2
    assert "retry" in result.successful_resolutions
    redis.get.assert_awaited_once()
    redis.set.assert_awaited_once()


# ---------------------------------------------------------------------------
# get_pattern_statistics — async path awaits smembers() + get() per hash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_pattern_statistics_awaits_smembers_on_empty() -> None:
    """statistics() returns zero dict when smembers returns empty set."""
    redis = make_async_redis(smembers_returns=set())
    det = FailurePatternDetector()

    with patch(_MIXIN_PATH, new=AsyncMock(return_value=redis)):
        stats = await det.get_pattern_statistics()

    assert stats["total_patterns"] == 0
    redis.smembers.assert_awaited_once_with(KNOWN_PATTERNS_KEY)


@pytest.mark.asyncio
async def test_get_pattern_statistics_awaits_get_for_each_hash() -> None:
    """statistics() awaits redis.get() for each known pattern hash."""
    det = FailurePatternDetector()
    h = det.hash_causal_chain(_CHAIN).encode()
    stored = json.dumps(
        {
            "pattern_id": h.decode(),
            "causal_chain": _CHAIN,
            "error_types": [_ERROR_TYPE],
            "occurrence_count": 4,
            "successful_resolutions": ["retry"],
            "resolution_success_rate": 0.75,
            "confidence": 0.95,
            "first_seen": "2026-01-01T00:00:00",
            "last_seen": "2026-01-01T00:00:00",
        }
    ).encode()

    redis = make_async_redis(get_returns=stored, smembers_returns={h})
    with patch(_MIXIN_PATH, new=AsyncMock(return_value=redis)):
        stats = await det.get_pattern_statistics()

    assert stats["total_patterns"] == 1
    assert stats["total_occurrences"] == 4
    assert stats["high_confidence_patterns"] == 1
    redis.smembers.assert_awaited_once()
    redis.get.assert_awaited()


# ---------------------------------------------------------------------------
# list_known_patterns — async path awaits smembers() + get() per hash
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_known_patterns_awaits_smembers_on_empty() -> None:
    """list_known_patterns() returns [] and awaits smembers when set is empty."""
    redis = make_async_redis(smembers_returns=set())
    det = FailurePatternDetector()

    with patch(_MIXIN_PATH, new=AsyncMock(return_value=redis)):
        patterns = await det.list_known_patterns(limit=10)

    assert patterns == []
    redis.smembers.assert_awaited_once_with(KNOWN_PATTERNS_KEY)


@pytest.mark.asyncio
async def test_list_known_patterns_awaits_get_per_hash() -> None:
    """list_known_patterns() awaits redis.get() for each hash in the set."""
    det = FailurePatternDetector()
    h = det.hash_causal_chain(_CHAIN).encode()
    stored = json.dumps(
        {
            "pattern_id": h.decode(),
            "causal_chain": _CHAIN,
            "error_types": [_ERROR_TYPE],
            "occurrence_count": 2,
            "successful_resolutions": [],
            "resolution_success_rate": 0.0,
            "confidence": 0.7,
            "first_seen": "2026-01-01T00:00:00",
            "last_seen": "2026-01-01T00:00:00",
        }
    ).encode()

    redis = make_async_redis(get_returns=stored, smembers_returns={h})
    with patch(_MIXIN_PATH, new=AsyncMock(return_value=redis)):
        patterns = await det.list_known_patterns(limit=10)

    assert len(patterns) == 1
    assert patterns[0].causal_chain == _CHAIN
    redis.smembers.assert_awaited_once()
    redis.get.assert_awaited()


# ---------------------------------------------------------------------------
# clear_patterns — async path awaits smembers() + delete() per hash + delete(key)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_patterns_awaits_smembers_on_empty() -> None:
    """clear_patterns() awaits smembers and skips delete when set is empty."""
    redis = make_async_redis(smembers_returns=set())
    det = FailurePatternDetector()

    with patch(_MIXIN_PATH, new=AsyncMock(return_value=redis)):
        await det.clear_patterns()

    redis.smembers.assert_awaited_once_with(KNOWN_PATTERNS_KEY)
    redis.delete.assert_awaited_once_with(KNOWN_PATTERNS_KEY)


@pytest.mark.asyncio
async def test_clear_patterns_awaits_delete_per_pattern_and_set() -> None:
    """clear_patterns() awaits redis.delete() for each pattern hash and the set key."""
    det = FailurePatternDetector()
    h = det.hash_causal_chain(_CHAIN).encode()

    redis = make_async_redis(smembers_returns={h})
    with patch(_MIXIN_PATH, new=AsyncMock(return_value=redis)):
        await det.clear_patterns()

    # delete is called once for the pattern key and once for the known-patterns set.
    assert redis.delete.await_count == 2
    all_args = [c.args[0] for c in redis.delete.await_args_list]
    # One call must target the known-patterns set key.
    assert any(KNOWN_PATTERNS_KEY in str(a) for a in all_args)
    # Pattern key must use the decoded string hash — not the bytes repr.
    expected_pattern_key = f"{PATTERN_KEY_PREFIX}{h.decode()}"
    assert any(a == expected_pattern_key for a in all_args), (
        f"Expected delete({expected_pattern_key!r}) but got calls with: {all_args!r}. "
        "smembers bytes were not decoded before building the Redis key."
    )


@pytest.mark.asyncio
async def test_clear_patterns_bytes_smembers_uses_str_key() -> None:
    """Regression (#10906): when smembers returns bytes, clear_patterns must delete
    'failure:pattern:<hex>' not 'failure:pattern:b\"<hex>\"'."""
    det = FailurePatternDetector()
    # Simulate a redis client with decode_responses=False — smembers returns bytes.
    raw_hash = b"abc123"
    redis = make_async_redis(smembers_returns={raw_hash})

    with patch(_MIXIN_PATH, new=AsyncMock(return_value=redis)):
        await det.clear_patterns()

    all_args = [c.args[0] for c in redis.delete.await_args_list]
    expected_pattern_key = f"{PATTERN_KEY_PREFIX}abc123"
    assert expected_pattern_key in all_args, (
        f"Expected delete key {expected_pattern_key!r} but delete was called with: {all_args!r}. "
        "Bytes from smembers must be decoded before building the Redis key."
    )
    # The bytes-repr variant must NOT appear.
    bad_key = f"{PATTERN_KEY_PREFIX}b'abc123'"
    assert bad_key not in all_args, f"delete was called with bytes-repr key {bad_key!r} — bytes were not decoded."


# ---------------------------------------------------------------------------
# Regression guard: sync MagicMock would hide the bug — verify the test
# infrastructure correctly rejects a sync stub when awaited.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_make_async_redis_get_is_awaitable() -> None:
    """Sanity: make_async_redis() fields are AsyncMock — awaitable, not sync."""
    redis = make_async_redis(get_returns=b"x")
    # If this were a sync MagicMock, calling await on it would raise TypeError.
    result = await redis.get("any-key")
    assert result == b"x"
