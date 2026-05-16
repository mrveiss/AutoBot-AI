# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Integration test: ConnectorScheduler multi-worker restart recovery (#6556)

Verifies that schedule definitions survive worker restarts by using a shared
in-memory Redis store (FakeRedis) that persists across ConnectorScheduler
instances — simulating the production Redis that outlives any single uvicorn
worker.

Scenario covered:
  Worker A starts two connector schedules → both written to Redis.
  Worker A shuts down (stop_all) → Redis keys remain.
  Worker B starts fresh → is_running() reads Redis and returns True.
  Worker B becomes leader, reconciles → asyncio tasks created without re-POSTing.
"""

import json
from typing import Any, Dict, Iterator
from unittest.mock import patch

import pytest

from knowledge.connectors.scheduler import (
    _LEADER_KEY,
    _SCHEDULE_PREFIX,
    ConnectorScheduler,
)

# ---------------------------------------------------------------------------
# Shared-state FakeRedis
# ---------------------------------------------------------------------------


class SharedFakeRedis:
    """Minimal async Redis substitute backed by a caller-supplied dict.

    The store is shared between instances so two ConnectorScheduler objects
    using the same store share state exactly as they would share a real Redis.
    """

    def __init__(self, store: Dict[str, Any]) -> None:
        self._store = store

    async def set(
        self, key: str, value: Any, nx: bool = False, px: int | None = None, ex: int | None = None
    ) -> bool | None:
        if nx and key in self._store:
            return None
        self._store[key] = value if isinstance(value, str) else value
        return True

    async def get(self, key: str) -> Any | None:
        return self._store.get(key)

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    async def delete(self, key: str) -> int:
        if key in self._store:
            del self._store[key]
            return 1
        return 0

    async def pexpire(self, key: str, ms: int) -> int:
        return 1 if key in self._store else 0

    async def scan_iter(self, match: str = "*") -> Iterator[str]:
        prefix = match.rstrip("*")
        for key in list(self._store.keys()):
            if key.startswith(prefix):
                yield key


def _make_shared_redis() -> tuple[Dict[str, Any], SharedFakeRedis]:
    store: Dict[str, Any] = {}
    return store, SharedFakeRedis(store)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_redis(store: Dict[str, Any]):
    """Return a context manager that patches get_async_redis_client to use *store*."""
    redis = SharedFakeRedis(store)

    async def _get(*args, **kwargs) -> SharedFakeRedis:
        return redis

    return patch("knowledge.connectors.scheduler.get_async_redis_client", side_effect=_get)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestWorkerRestartRecovery:
    """Verify that schedule definitions survive a complete worker restart."""

    @pytest.mark.asyncio
    async def test_is_running_consistent_after_restart(self):
        """New worker sees schedules started by the old worker via Redis."""
        store, _ = _make_shared_redis()

        # --- Old worker (Worker A) ---
        with _patch_redis(store):
            worker_a = ConnectorScheduler()
            worker_a._is_leader = True

            ok_c1 = await worker_a.start("c1", "*/5")
            ok_c2 = await worker_a.start("c2", "@hourly")
            assert ok_c1 and ok_c2, "Worker A failed to schedule connectors"

            # Graceful shutdown — Redis keys survive
            await worker_a.stop_all()

        # Confirm Redis keys still present after Worker A stops
        assert _SCHEDULE_PREFIX + "c1" in store
        assert _SCHEDULE_PREFIX + "c2" in store

        # --- New worker (Worker B) ---
        with _patch_redis(store):
            worker_b = ConnectorScheduler()

            # is_running must read Redis and return True without prior start()
            assert await worker_b.is_running("c1"), "Worker B: c1 should appear running (Redis key present)"
            assert await worker_b.is_running("c2"), "Worker B: c2 should appear running (Redis key present)"

    @pytest.mark.asyncio
    async def test_leader_rehydrates_tasks_after_restart(self):
        """New leader reconciles and spins up asyncio tasks for persisted schedules."""
        store, _ = _make_shared_redis()

        # Seed Redis directly (skipping Worker A) to keep the test focused
        store[_SCHEDULE_PREFIX + "conn-x"] = json.dumps(
            {"connector_id": "conn-x", "schedule": "*/10", "interval_seconds": 600}
        )
        store[_SCHEDULE_PREFIX + "conn-y"] = json.dumps(
            {"connector_id": "conn-y", "schedule": "@daily", "interval_seconds": 86400}
        )

        with _patch_redis(store):
            worker_b = ConnectorScheduler()
            worker_b._is_leader = True

            # _reconcile_schedules is called by the leader loop; invoke directly
            await worker_b._reconcile_schedules()

            assert "conn-x" in worker_b._tasks, "Leader should have an asyncio task for conn-x"
            assert "conn-y" in worker_b._tasks, "Leader should have an asyncio task for conn-y"
            assert not worker_b._tasks["conn-x"].done()
            assert not worker_b._tasks["conn-y"].done()

            # Cleanup
            await worker_b.stop_all()

    @pytest.mark.asyncio
    async def test_stop_removes_schedule_so_new_worker_sees_it_gone(self):
        """stop() on old worker removes Redis key; new worker sees connector as not running."""
        store, _ = _make_shared_redis()

        with _patch_redis(store):
            worker_a = ConnectorScheduler()
            worker_a._is_leader = True
            await worker_a.start("c3", "*/30")

            # Explicit stop (e.g. user deleted the connector)
            await worker_a.stop("c3")

        # Key gone from Redis
        assert _SCHEDULE_PREFIX + "c3" not in store

        with _patch_redis(store):
            worker_b = ConnectorScheduler()
            assert not await worker_b.is_running("c3"), "Worker B: c3 should not be running after stop()"

    @pytest.mark.asyncio
    async def test_single_flight_only_leader_has_local_tasks(self):
        """Only the leader worker runs asyncio tasks; follower workers have none."""
        store, _ = _make_shared_redis()

        # Seed Redis with a schedule
        store[_SCHEDULE_PREFIX + "conn-z"] = json.dumps(
            {"connector_id": "conn-z", "schedule": "@minutely", "interval_seconds": 60}
        )
        # Simulate leader already holding the key
        store[_LEADER_KEY] = "some-other-worker-id"

        with _patch_redis(store):
            follower = ConnectorScheduler()
            # Non-leader: start() persists to Redis but does not create local task
            await follower.start("conn-z", "@minutely")

            assert "conn-z" not in follower._tasks, "Follower must not have local asyncio tasks"
            assert await follower.is_running("conn-z"), "Follower must still report running via Redis"
