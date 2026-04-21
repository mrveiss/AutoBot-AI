# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Regression tests for background_task_manager.py datetime arithmetic (#5419 P0).

Pre-fix, three sites did ``(now_aware - datetime.fromisoformat(started))`` where
``started`` from Redis could be naive ISO. ``aware - naive`` raised TypeError,
caught by ``except (ValueError, TypeError): pass`` — silently skipping timeout
detection on every tick. Timed-out tasks never got marked failed; orphaned
tasks never got cleaned up.

After fix, ``parse_utc_iso(started)`` always returns aware UTC regardless of
input format, so the subtraction works cleanly.

These tests exercise the in-memory cleanup path (_cleanup_stuck) which is the
simplest to reach without Redis mocking. The other two sites (_clear_orphaned,
_load_from_redis-based get_task) share the same bug class and the same fix.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from utils.background_task_manager import BackgroundTaskManager


@pytest.fixture
def manager() -> BackgroundTaskManager:
    return BackgroundTaskManager(redis_prefix="test_task:", task_timeout=60)


def _add_running_task(
    manager: BackgroundTaskManager, task_id: str, started_at: str
) -> None:
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
        (datetime.now(tz=timezone.utc) - timedelta(seconds=120))
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
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
    past_naive = (datetime.now(timezone.utc) - timedelta(seconds=120)).replace(
        tzinfo=None
    ).isoformat()
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
    recent_naive = (
        datetime.now(timezone.utc) - timedelta(seconds=10)
    ).replace(tzinfo=None).isoformat()
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
    past_naive = (
        datetime.now(timezone.utc) - timedelta(seconds=120)
    ).replace(tzinfo=None).isoformat()
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
