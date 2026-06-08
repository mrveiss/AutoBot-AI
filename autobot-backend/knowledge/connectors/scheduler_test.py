# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Tests for ConnectorScheduler multi-worker safety (Issue #6556).

Covers:
  - _parse_interval_seconds: named schedules and */N and plain-int formats
  - is_running: reads Redis, not local asyncio tasks
  - start/stop persist to / delete from Redis
  - Worker restart simulation: new scheduler instance rehydrates from Redis
  - Single-flight: only one worker runs the leader loop (via mocked Redis)
  - stop_all: cancels local tasks without deleting Redis keys
"""

import asyncio
import json
import os
import sys
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure autobot-backend is on sys.path
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from knowledge.connectors.scheduler import (
    _LEADER_KEY,
    _SCHEDULE_PREFIX,
    ConnectorScheduler,
    _parse_interval_seconds,
)

# ---------------------------------------------------------------------------
# _parse_interval_seconds
# ---------------------------------------------------------------------------


class TestParseIntervalSeconds:
    def test_named_minutely(self):
        assert _parse_interval_seconds("@minutely") == 60

    def test_named_hourly(self):
        assert _parse_interval_seconds("@hourly") == 3600

    def test_named_daily(self):
        assert _parse_interval_seconds("@daily") == 86400

    def test_named_weekly(self):
        assert _parse_interval_seconds("@weekly") == 604800

    def test_slash_n(self):
        assert _parse_interval_seconds("*/15") == 900
        assert _parse_interval_seconds("*/5") == 300

    def test_slash_n_min_one(self):
        assert _parse_interval_seconds("*/0") == 60

    def test_plain_int(self):
        assert _parse_interval_seconds("30") == 1800

    def test_plain_int_zero(self):
        assert _parse_interval_seconds("0") == 60

    def test_unrecognised(self):
        assert _parse_interval_seconds("cron(0 * * * *)") is None

    def test_case_insensitive(self):
        assert _parse_interval_seconds("@HOURLY") == 3600


# ---------------------------------------------------------------------------
# Helper: mock async Redis client
# ---------------------------------------------------------------------------


def _make_redis_mock(store: dict | None = None):
    """Return an async mock Redis client backed by an in-memory dict."""
    if store is None:
        store = {}

    mock = AsyncMock()

    async def _get(key):
        key_str = key.decode() if isinstance(key, bytes) else key
        v = store.get(key_str)
        return v.encode() if isinstance(v, str) else v

    async def _set(key, value, nx=False, px=None):
        if nx and key in store:
            return None
        store[key] = value.decode() if isinstance(value, bytes) else value
        return True

    async def _exists(key):
        return 1 if key in store else 0

    async def _delete(key):
        store.pop(key, None)
        return 1

    async def _pexpire(key, ms):
        return 1 if key in store else 0

    async def _scan_iter(match="*"):
        import fnmatch

        for k in list(store):
            if fnmatch.fnmatch(k, match):
                yield k.encode()

    async def _redis_eval(script, numkeys, *args):
        # Implements the _REFRESH_LUA contract: GET==ARGV[1] -> PEXPIRE 1
        key = args[0].decode() if isinstance(args[0], bytes) else args[0]
        expected = args[1].decode() if isinstance(args[1], bytes) else args[1]
        current = store.get(key)
        current_s = current.decode() if isinstance(current, bytes) else current
        if current_s == expected:
            return 1
        return 0

    mock.get = _get
    mock.set = _set
    mock.exists = _exists
    mock.delete = _delete
    mock.pexpire = _pexpire
    mock.scan_iter = _scan_iter
    mock.eval = _redis_eval
    return mock, store


# ---------------------------------------------------------------------------
# ConnectorScheduler unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConnectorSchedulerRedis:
    """Tests that use a mocked Redis client."""

    async def test_start_persists_to_redis(self):
        _, store = _make_redis_mock()
        mock_redis, _ = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            scheduler = ConnectorScheduler()
            result = await scheduler.start("c1", "*/5")

        assert result is True
        key = _SCHEDULE_PREFIX + "c1"
        assert key in store
        data = json.loads(store[key])
        assert data["connector_id"] == "c1"
        assert data["interval_seconds"] == 300

    async def test_start_unknown_schedule_returns_false(self):
        mock_redis, store = _make_redis_mock()
        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            scheduler = ConnectorScheduler()
            result = await scheduler.start("c1", "bad-cron-expr")

        assert result is False
        assert _SCHEDULE_PREFIX + "c1" not in store

    async def test_stop_removes_redis_key(self):
        store = {
            _SCHEDULE_PREFIX + "c1": json.dumps({"connector_id": "c1", "schedule": "*/5", "interval_seconds": 300})
        }
        mock_redis, store = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            scheduler = ConnectorScheduler()
            await scheduler.stop("c1")

        assert _SCHEDULE_PREFIX + "c1" not in store

    async def test_is_running_reads_redis(self):
        """is_running True when Redis key exists, False when absent."""
        store = {_SCHEDULE_PREFIX + "c1": "present"}
        mock_redis, store = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            scheduler = ConnectorScheduler()
            # c1 is in Redis → running
            assert await scheduler.is_running("c1") is True
            # c2 is not in Redis → not running
            assert await scheduler.is_running("c2") is False

    async def test_is_running_consistent_across_workers(self):
        """Two independent scheduler instances share the same Redis view."""
        store = {}
        mock_redis_a, _ = _make_redis_mock(store)
        mock_redis_b, _ = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            side_effect=[mock_redis_a, mock_redis_b, mock_redis_a, mock_redis_b],
        ):
            worker_a = ConnectorScheduler()
            worker_b = ConnectorScheduler()

            # Worker A writes the schedule
            await worker_a.start("c1", "*/5")

            # Worker B reads it (consistent)
            assert await worker_b.is_running("c1") is True

    async def test_stop_all_does_not_delete_redis_keys(self):
        """stop_all cancels local asyncio tasks but leaves Redis schedules intact."""
        store = {
            _SCHEDULE_PREFIX + "c1": json.dumps({"connector_id": "c1", "schedule": "*/5", "interval_seconds": 300})
        }
        mock_redis, _ = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            scheduler = ConnectorScheduler()
            scheduler._is_leader = True
            await scheduler.start("c1", "*/5")
            assert "c1" in scheduler._tasks

            await scheduler.stop_all()

        # Local task was cancelled
        assert "c1" not in scheduler._tasks
        # But Redis key survives (next leader will rehydrate)
        assert _SCHEDULE_PREFIX + "c1" in store

    async def test_restart_simulation_rehydrate(self):
        """Simulates worker restart: new scheduler leader picks up existing Redis schedules."""
        store = {
            _SCHEDULE_PREFIX + "c1": json.dumps({"connector_id": "c1", "schedule": "*/5", "interval_seconds": 300}),
            _SCHEDULE_PREFIX
            + "c2": json.dumps({"connector_id": "c2", "schedule": "@hourly", "interval_seconds": 3600}),
        }
        mock_redis, _ = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            new_scheduler = ConnectorScheduler()
            new_scheduler._is_leader = True
            await new_scheduler._reconcile_schedules()

        # After rehydration both connectors have local asyncio tasks
        assert "c1" in new_scheduler._tasks
        assert "c2" in new_scheduler._tasks

    async def test_reconcile_cancels_orphaned_tasks(self):
        """Tasks for connectors removed from Redis are cancelled during reconciliation."""
        store = {}
        mock_redis, _ = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            scheduler = ConnectorScheduler()
            scheduler._is_leader = True

            # Manually plant an orphaned task (was never persisted to Redis)
            done_event = asyncio.Event()
            orphan = asyncio.create_task(_sleeper(done_event))
            scheduler._tasks["orphan"] = orphan

            await scheduler._reconcile_schedules()

        # Orphaned task was cancelled
        assert "orphan" not in scheduler._tasks

    async def test_leader_election_new_worker_wins(self):
        """A new worker acquires the leader key when it does not yet exist."""
        store = {}
        mock_redis, _ = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            scheduler = ConnectorScheduler()
            won = await scheduler._try_acquire_or_refresh()

        assert won is True
        assert _LEADER_KEY in store

    async def test_leader_election_second_worker_loses(self):
        """A second worker cannot acquire the key while the first holds it."""
        store = {}
        mock_redis, _ = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            a = ConnectorScheduler()
            b = ConnectorScheduler()
            assert await a._try_acquire_or_refresh() is True
            assert await b._try_acquire_or_refresh() is False

    async def test_leader_refresh_succeeds(self):
        """The current leader can refresh its own key."""
        store = {}
        mock_redis, _ = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            scheduler = ConnectorScheduler()
            # Acquire
            await scheduler._try_acquire_or_refresh()
            scheduler._is_leader = True
            # Refresh
            refreshed = await scheduler._try_acquire_or_refresh()

        assert refreshed is True

    async def test_leader_yields_when_key_taken_by_other(self):
        """A worker that thinks it is the leader yields when its key was replaced."""
        store = {}
        mock_redis, _ = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            scheduler = ConnectorScheduler()
            scheduler._is_leader = True
            # Plant another worker's ID in the key
            store[_LEADER_KEY] = "other-worker-9999"
            result = await scheduler._try_acquire_or_refresh()

        assert result is False

    async def test_no_dual_leader_after_atomic_race(self):
        """Atomic Lua refresh prevents dual-leader when a rival re-acquires between cycles.

        Scenario: worker A holds the lock, it expires, worker B re-acquires atomically.
        Worker A tries to refresh — must fail because it no longer holds the key.
        """
        store = {}
        mock_redis, _ = _make_redis_mock(store)

        with patch(
            "knowledge.connectors.scheduler.get_async_redis_client",
            return_value=mock_redis,
        ):
            worker_a = ConnectorScheduler()
            worker_b = ConnectorScheduler()
            # Give distinct IDs so they behave as separate workers
            worker_a._worker_id = "host-a-1"
            worker_b._worker_id = "host-b-2"

            # Worker A acquires leadership
            assert await worker_a._try_acquire_or_refresh() is True
            worker_a._is_leader = True

            # Simulate GC pause: lock expires then worker B re-acquires atomically
            del store[_LEADER_KEY]
            assert await worker_b._try_acquire_or_refresh() is True
            worker_b._is_leader = True

            # Worker A refresh MUST fail — it no longer holds the key
            assert await worker_a._try_acquire_or_refresh() is False
            # Worker B refresh MUST succeed — it is the rightful leader
            assert await worker_b._try_acquire_or_refresh() is True


async def _sleeper(done: asyncio.Event) -> None:
    """Long-running stub used in orphan-task tests."""
    await done.wait()
