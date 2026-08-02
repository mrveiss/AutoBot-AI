# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sandbox stats must report the counters hincrby actually wrote (#13274).

``SecureSandboxExecutor`` increments with
``self.redis_client.hincrby("autobot:sandbox:stats", stat_key, 1)`` — ``str``
field names — and ``self.redis_client`` comes from
``get_redis_client(async_client=False)``. The shared sync pool is
``decode_responses=True`` (``redis_management/connection_manager.py:618`` reading
the same ``config.decode_responses`` that defaults ``True``), so ``hgetall``
returns a ``str``-keyed dict.

``get_sandbox_stats`` probed it with bytes literals::

    "successful_executions": int(stats.get(b"successful_executions", 0)),

The lookup always missed, the ``0`` default was returned, and ``int(0)``
succeeded — so the endpoint reported zero executions forever, no matter how many
sandboxes had actually run, with no exception and no log line.

``SecureSandboxExecutor.__init__`` requires a live Docker SDK, so these tests
build the instance without it and attach only the two attributes
``get_sandbox_stats`` touches.
"""

import pytest

from secure_sandbox_executor import SecureSandboxExecutor

STATS_KEY = "autobot:sandbox:stats"


class _FakeSyncRedis:
    """Dict-backed stand-in with redis-py's sync hincrby/hgetall signatures."""

    def __init__(self, initial=None, decoded=True):
        self._hashes = {STATS_KEY: dict(initial or {})}
        self._decoded = decoded

    def hincrby(self, key, field, amount):
        bucket = self._hashes.setdefault(key, {})
        bucket[field] = int(bucket.get(field, 0)) + amount
        return bucket[field]

    def hgetall(self, key):
        raw = self._hashes.get(key, {})
        if self._decoded:
            return {str(k): str(v) for k, v in raw.items()}
        # Field names stay str; only the values arrive as bytes.
        return {str(k): str(v).encode() for k, v in raw.items()}


def _executor(redis):
    """Build the executor without running __init__ (it demands the Docker SDK)."""
    executor = object.__new__(SecureSandboxExecutor)
    executor.redis_client = redis
    executor.active_containers = {}
    return executor


@pytest.mark.asyncio
async def test_stored_counters_are_reported():
    """The live configuration. Pre-fix both counters read back 0."""
    executor = _executor(_FakeSyncRedis({"successful_executions": 42, "failed_executions": 7}))

    stats = await executor.get_sandbox_stats()

    assert stats["successful_executions"] == 42
    assert stats["failed_executions"] == 7
    assert stats["active_containers"] == 0
    assert stats["security_levels_available"]


@pytest.mark.asyncio
async def test_hincrby_then_read_round_trips():
    """Drive the real write shape, then the real reader, over one shared hash."""
    redis = _FakeSyncRedis()
    executor = _executor(redis)

    # Exactly what _log_metrics does on a successful then a failed execution.
    redis.hincrby(STATS_KEY, "successful_executions", 1)
    redis.hincrby(STATS_KEY, "successful_executions", 1)
    redis.hincrby(STATS_KEY, "failed_executions", 1)

    stats = await executor.get_sandbox_stats()

    assert stats["successful_executions"] == 2, "hincrby wrote str fields the reader could not see"
    assert stats["failed_executions"] == 1


@pytest.mark.asyncio
async def test_bytes_values_still_work():
    """``decode_redis_value`` keeps handling a bytes counter value."""
    executor = _executor(_FakeSyncRedis({"successful_executions": 5, "failed_executions": 2}, decoded=False))

    stats = await executor.get_sandbox_stats()

    assert stats["successful_executions"] == 5
    assert stats["failed_executions"] == 2


@pytest.mark.asyncio
async def test_empty_hash_reports_zeros():
    """The one case that looked correct before the fix must still work."""
    executor = _executor(_FakeSyncRedis())

    stats = await executor.get_sandbox_stats()

    assert stats["successful_executions"] == 0
    assert stats["failed_executions"] == 0
