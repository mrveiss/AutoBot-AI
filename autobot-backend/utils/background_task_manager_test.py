# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Regression tests for background_task_manager.py datetime arithmetic
(#5419 P0 + #5463 Redis-path coverage).

Pre-fix, three sites did ``(now_aware - datetime.fromisoformat(started))``
where ``started`` from Redis could be naive ISO. ``aware - naive`` raised
TypeError, caught by ``except (ValueError, TypeError): pass`` — silently
skipping timeout detection on every tick.

After #5462 fix, ``parse_utc_iso(started)`` always returns aware UTC.

This test file covers all three fixed sites:
- ``_cleanup_stuck`` — in-memory dict (8 tests, #5419 P0)
- ``_mark_orphans`` — Redis-backed cleanup (5 tests, #5463)
- ``get_status`` — Redis-backed auto-recovery (3 tests, #5463)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from autobot_shared.time_utils import now_utc
from utils.background_task_manager import BackgroundTaskManager


@pytest.fixture
def manager() -> BackgroundTaskManager:
    return BackgroundTaskManager(redis_prefix="test_task:", task_timeout=60)


def _add_running_task(manager: BackgroundTaskManager, task_id: str, started_at: str) -> None:
    """Seed manager._tasks with a running task carrying a string started_at."""
    manager._tasks[task_id] = {
        "status": "running",
        "started_at": started_at,
        "params": {},
    }


# ---------------------------------------------------------------------------
# _cleanup_stuck — the pure in-memory path (no Redis)
# ---------------------------------------------------------------------------


def test_cleanup_stuck_with_aware_iso_started_marks_timed_out(
    manager: BackgroundTaskManager,
) -> None:
    """Aware +00:00 ISO beyond timeout → task marked failed."""
    past = (datetime.now(tz=timezone.utc) - timedelta(seconds=120)).isoformat()
    _add_running_task(manager, "t1", past)

    cleaned = manager._cleanup_stuck()
    assert cleaned == 1
    assert manager._tasks["t1"]["status"] == "failed"
    assert manager._tasks["t1"]["reason"] == "timeout"


def test_cleanup_stuck_with_z_suffix_started_marks_timed_out(
    manager: BackgroundTaskManager,
) -> None:
    """Z-suffix ISO beyond timeout — parse_utc_iso handles Z natively."""
    past = (
        (datetime.now(tz=timezone.utc) - timedelta(seconds=120)).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    _add_running_task(manager, "t2", past)

    cleaned = manager._cleanup_stuck()
    assert cleaned == 1
    assert manager._tasks["t2"]["status"] == "failed"


def test_cleanup_stuck_with_naive_iso_started_no_typeerror(
    manager: BackgroundTaskManager,
) -> None:
    """The #5419 regression guard: NAIVE ISO input must not TypeError.

    Pre-fix: ``datetime.now(tz=utc) - datetime.fromisoformat(naive)`` raised
    TypeError, silently caught by ``except (ValueError, TypeError): pass``,
    leaving ``stuck = True`` (the default) — which meant the task WOULD be
    marked failed, but for the wrong reason (skipped timeout check, not
    elapsed-beyond-threshold). With the fix, the timeout check actually runs.
    """
    # Naive ISO — what pre-migration code paths wrote to Redis
    past_naive = (now_utc() - timedelta(seconds=120)).replace(tzinfo=None).isoformat()
    _add_running_task(manager, "t3", past_naive)

    # Must not raise
    cleaned = manager._cleanup_stuck()
    assert cleaned == 1
    assert manager._tasks["t3"]["status"] == "failed"
    assert manager._tasks["t3"]["reason"] == "timeout"


def test_cleanup_stuck_within_timeout_keeps_running(
    manager: BackgroundTaskManager,
) -> None:
    """Recent started_at (within timeout) leaves task running."""
    recent = (datetime.now(tz=timezone.utc) - timedelta(seconds=10)).isoformat()
    _add_running_task(manager, "t4", recent)

    cleaned = manager._cleanup_stuck()
    assert cleaned == 0
    assert manager._tasks["t4"]["status"] == "running"


def test_cleanup_stuck_within_timeout_with_naive_iso_keeps_running(
    manager: BackgroundTaskManager,
) -> None:
    """The other half of the #5419 fix: naive-within-timeout should NOT be
    marked failed. Pre-fix, TypeError in the try block silently left
    ``stuck = True`` default, causing false-positive failure marking.
    """
    recent_naive = (now_utc() - timedelta(seconds=10)).replace(tzinfo=None).isoformat()
    _add_running_task(manager, "t5", recent_naive)

    cleaned = manager._cleanup_stuck()
    assert cleaned == 0, (
        "task within timeout must not be marked failed — pre-fix, the "
        "silently-caught TypeError caused false positives"
    )
    assert manager._tasks["t5"]["status"] == "running"


def test_cleanup_stuck_malformed_started_still_marks_stuck(
    manager: BackgroundTaskManager,
) -> None:
    """Existing contract: truly malformed started_at → stuck=True fallback.

    parse_utc_iso raises ValueError on garbage input; the surrounding
    ``except (ValueError, TypeError): pass`` leaves ``stuck = True`` default,
    which is the safe choice (mark as failed rather than leave in-memory).
    """
    _add_running_task(manager, "t6", "not-a-timestamp")

    cleaned = manager._cleanup_stuck()
    assert cleaned == 1
    assert manager._tasks["t6"]["status"] == "failed"


def test_cleanup_stuck_missing_started_still_marks_stuck(
    manager: BackgroundTaskManager,
) -> None:
    """No started_at → stuck=True default, task marked failed."""
    manager._tasks["t7"] = {"status": "running", "params": {}}

    cleaned = manager._cleanup_stuck()
    assert cleaned == 1
    assert manager._tasks["t7"]["status"] == "failed"


def test_cleanup_stuck_non_running_tasks_untouched(
    manager: BackgroundTaskManager,
) -> None:
    """Only ``status == 'running'`` tasks are considered."""
    past_naive = (now_utc() - timedelta(seconds=120)).replace(tzinfo=None).isoformat()
    manager._tasks["t8"] = {
        "status": "pending",
        "started_at": past_naive,
        "params": {},
    }
    manager._tasks["t9"] = {
        "status": "completed",
        "started_at": past_naive,
        "params": {},
    }

    cleaned = manager._cleanup_stuck()
    assert cleaned == 0
    assert manager._tasks["t8"]["status"] == "pending"
    assert manager._tasks["t9"]["status"] == "completed"


# ---------------------------------------------------------------------------
# _mark_orphans — Redis-backed cleanup path (#5463)
#
# RedisCache is patched at the module level to return a fake instance whose
# get_json/set_json methods use an in-memory dict. This mirrors the shape
# the real cache exposes without requiring a running Redis.
# ---------------------------------------------------------------------------


class _FakeCache:
    """Minimal RedisCache stand-in backed by an in-memory dict."""

    def __init__(self, storage: dict[str, dict]):
        self._storage = storage

    async def get_json(self, key: str):
        return self._storage.get(key)

    async def set_json(self, key: str, value: dict):
        self._storage[key] = value


def _make_cache_factory(storage: dict[str, dict]):
    """Return a patch target that always yields _FakeCache(storage)."""

    def _factory(*_args, **_kwargs):
        return _FakeCache(storage)

    return _factory


@pytest.mark.asyncio
async def test_mark_orphans_with_naive_iso_beyond_timeout_marks_failed(
    manager: BackgroundTaskManager,
) -> None:
    """#5463: naive-ISO started_at beyond timeout — orphan cleanup runs cleanly.

    Pre-#5462: aware - naive = TypeError, silently caught → EVERY orphan-check
    skipped the timeout gate and marked the task failed regardless of age.
    Post-#5462: elapsed check actually runs; only truly-expired tasks marked.
    """
    past_naive = (now_utc() - timedelta(seconds=120)).replace(tzinfo=None).isoformat()
    storage = {
        "test_task:orphan1": {
            "status": "running",
            "started_at": past_naive,
        }
    }
    fake_redis = MagicMock()

    with patch(
        "utils.background_task_manager.RedisCache",
        side_effect=_make_cache_factory(storage),
    ):
        marked = await manager._mark_orphans(fake_redis, ["test_task:orphan1"])

    assert marked == 1
    assert storage["test_task:orphan1"]["status"] == "failed"
    assert storage["test_task:orphan1"]["reason"] == "orphaned"


@pytest.mark.asyncio
async def test_mark_orphans_with_naive_iso_within_timeout_keeps_running(
    manager: BackgroundTaskManager,
) -> None:
    """Naive-ISO started_at within timeout — NOT marked orphaned.

    This is the second half of the #5462 fix: pre-fix the TypeError caused
    false-positive orphan marking for recent naive-timestamp tasks.
    """
    recent_naive = (now_utc() - timedelta(seconds=10)).replace(tzinfo=None).isoformat()
    storage = {
        "test_task:orphan2": {
            "status": "running",
            "started_at": recent_naive,
        }
    }
    fake_redis = MagicMock()

    with patch(
        "utils.background_task_manager.RedisCache",
        side_effect=_make_cache_factory(storage),
    ):
        marked = await manager._mark_orphans(fake_redis, ["test_task:orphan2"])

    assert marked == 0, (
        "recent naive-timestamp task must not be marked orphaned — "
        "pre-fix the silent TypeError caused false positives"
    )
    assert storage["test_task:orphan2"]["status"] == "running"


@pytest.mark.asyncio
async def test_mark_orphans_skips_in_memory_tasks(
    manager: BackgroundTaskManager,
) -> None:
    """Tasks currently tracked in self._tasks (any worker) are not orphaned."""
    past_naive = (now_utc() - timedelta(seconds=120)).replace(tzinfo=None).isoformat()
    # Task in self._tasks — another worker might be running it
    manager._tasks["orphan3"] = {"status": "running", "started_at": past_naive}

    storage = {"test_task:orphan3": {"status": "running", "started_at": past_naive}}
    fake_redis = MagicMock()

    with patch(
        "utils.background_task_manager.RedisCache",
        side_effect=_make_cache_factory(storage),
    ):
        marked = await manager._mark_orphans(fake_redis, ["test_task:orphan3"])

    assert marked == 0
    assert storage["test_task:orphan3"]["status"] == "running"


@pytest.mark.asyncio
async def test_mark_orphans_skips_non_running_tasks(
    manager: BackgroundTaskManager,
) -> None:
    """Only ``status == 'running'`` Redis tasks are considered."""
    past_naive = (now_utc() - timedelta(seconds=120)).replace(tzinfo=None).isoformat()
    storage = {
        "test_task:done": {"status": "completed", "started_at": past_naive},
    }
    fake_redis = MagicMock()

    with patch(
        "utils.background_task_manager.RedisCache",
        side_effect=_make_cache_factory(storage),
    ):
        marked = await manager._mark_orphans(fake_redis, ["test_task:done"])

    assert marked == 0
    assert storage["test_task:done"]["status"] == "completed"


@pytest.mark.asyncio
async def test_mark_orphans_with_aware_iso_beyond_timeout_marks_failed(
    manager: BackgroundTaskManager,
) -> None:
    """Sanity: aware +00:00 ISO also works (post-fix behavior unchanged)."""
    past_aware = (datetime.now(tz=timezone.utc) - timedelta(seconds=120)).isoformat()
    storage = {"test_task:aware": {"status": "running", "started_at": past_aware}}
    fake_redis = MagicMock()

    with patch(
        "utils.background_task_manager.RedisCache",
        side_effect=_make_cache_factory(storage),
    ):
        marked = await manager._mark_orphans(fake_redis, ["test_task:aware"])

    assert marked == 1
    assert storage["test_task:aware"]["status"] == "failed"


# ---------------------------------------------------------------------------
# get_status auto-recovery — Redis-backed zombie detection (#5463)
#
# The third fixed site at line 327. When a running-status task is loaded
# from Redis and has exceeded the timeout, auto-mark it failed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_status_auto_recovers_timed_out_naive_task(
    manager: BackgroundTaskManager,
) -> None:
    """Timed-out task with naive started_at → auto-marked failed in Redis.

    Pre-#5462: TypeError silently caught → task kept reporting "running"
    indefinitely. The frontend would see infinite spinner.
    """
    past_naive = (now_utc() - timedelta(seconds=120)).replace(tzinfo=None).isoformat()
    storage = {"test_task:zombie": {"status": "running", "started_at": past_naive}}

    async def _fake_load(task_id: str):
        return storage.get(f"{manager._prefix}{task_id}")

    async def _fake_get_redis():
        return MagicMock()  # truthy so cache.set_json path fires

    manager._load_from_redis = _fake_load  # type: ignore[method-assign]
    manager._get_redis = _fake_get_redis  # type: ignore[method-assign]

    with patch(
        "utils.background_task_manager.RedisCache",
        side_effect=_make_cache_factory(storage),
    ):
        result = await manager.get_status("zombie")

    assert result is not None
    assert result["status"] == "failed"
    assert result["reason"] == "timeout"
    # Verify the fix was persisted back to Redis via set_json
    assert storage["test_task:zombie"]["status"] == "failed"


@pytest.mark.asyncio
async def test_get_status_keeps_recent_naive_task_running(
    manager: BackgroundTaskManager,
) -> None:
    """Recent task (within timeout) with naive started_at stays running."""
    recent_naive = (now_utc() - timedelta(seconds=10)).replace(tzinfo=None).isoformat()
    storage = {"test_task:fresh": {"status": "running", "started_at": recent_naive}}

    async def _fake_load(task_id: str):
        return storage.get(f"{manager._prefix}{task_id}")

    manager._load_from_redis = _fake_load  # type: ignore[method-assign]

    result = await manager.get_status("fresh")

    assert result is not None
    assert result["status"] == "running", (
        "recent task must not be auto-recovered — pre-fix the TypeError "
        "would also have left status=running but for the wrong reason "
        "(elapsed check skipped entirely)"
    )


@pytest.mark.asyncio
async def test_get_status_returns_in_memory_task_without_auto_recovery(
    manager: BackgroundTaskManager,
) -> None:
    """In-memory tasks bypass Redis + auto-recovery entirely."""
    past_naive = (now_utc() - timedelta(seconds=120)).replace(tzinfo=None).isoformat()
    manager._tasks["inmem"] = {
        "status": "running",
        "started_at": past_naive,
        "params": {"secret": "hidden"},
    }

    result = await manager.get_status("inmem")

    # Still "running" (no Redis path taken), params stripped
    assert result is not None
    assert result["status"] == "running"
    assert "params" not in result
