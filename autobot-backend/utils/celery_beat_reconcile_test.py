# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the Beat schedule reconciliation guard (#12354).

Pure/testable: uses simple stand-in entries (any object exposing ``.task``)
instead of real ``celery.beat.ScheduleEntry``/scheduler objects, so it runs
without importing the heavy, pytest-stubbed ``celery_app`` module (#7766),
the same approach as ``utils/celery_schedules.py``'s extraction (#11606).
"""

from __future__ import annotations

from dataclasses import dataclass

from utils.celery_beat_reconcile import reconcile_schedule


@dataclass
class _FakeEntry:
    task: str


def test_stale_entry_is_pruned():
    """A persisted entry whose task is not in beat_schedule is removed."""
    schedule = {
        "reconcile-unified-credentials-hourly": _FakeEntry(task="tasks.reconcile_unified_credentials"),
        "reconcile-credentials-hourly": _FakeEntry(task="tasks.reconcile_credentials"),
    }
    valid_tasks = {"tasks.reconcile_credentials"}

    pruned = reconcile_schedule(schedule, valid_tasks)

    assert pruned == ["reconcile-unified-credentials-hourly"]
    assert "reconcile-unified-credentials-hourly" not in schedule
    assert "reconcile-credentials-hourly" in schedule


def test_valid_entries_are_kept_untouched():
    """When every persisted entry matches beat_schedule, nothing is pruned."""
    schedule = {
        "knowledge-cleanup-orphan-documents": _FakeEntry(task="tasks.cleanup_orphan_documents"),
        "pricing-refresh-daily": _FakeEntry(task="pricing.refresh_daily"),
    }
    valid_tasks = {"tasks.cleanup_orphan_documents", "pricing.refresh_daily"}

    pruned = reconcile_schedule(schedule, valid_tasks)

    assert pruned == []
    assert set(schedule) == {"knowledge-cleanup-orphan-documents", "pricing-refresh-daily"}


def test_multiple_stale_entries_pruned_sorted():
    """Several stale entries are all removed and returned in sorted order."""
    schedule = {
        "z-stale-task": _FakeEntry(task="tasks.long_gone_z"),
        "a-stale-task": _FakeEntry(task="tasks.long_gone_a"),
        "current-task": _FakeEntry(task="tasks.current"),
    }
    valid_tasks = {"tasks.current"}

    pruned = reconcile_schedule(schedule, valid_tasks)

    assert pruned == ["a-stale-task", "z-stale-task"]
    assert set(schedule) == {"current-task"}


def test_empty_schedule_is_a_no_op():
    """An empty persisted schedule reconciles cleanly with no pruning."""
    schedule: dict = {}

    pruned = reconcile_schedule(schedule, {"tasks.anything"})

    assert pruned == []
    assert schedule == {}
