# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#13344 — a negative task duration must not abort the tracked operation.

``MemoryManager.complete_task`` computed
``(completed_at - task.started_at).total_seconds()`` and handed it to
``update_task_status``, which raises ``ValueError("duration_seconds cannot be
negative")``. That exception escaped through ``TaskExecutionTracker.track_task``
(which re-raises after ``afail_task``), so a *bookkeeping* inconsistency failed
the caller's real work — one observed run logged "Contextual decision making
failed" for a decision that had succeeded.

**What is NOT claimed here.** The cause of ``started_at > completed_at`` is not
established. Both hypotheses on #13344 were checked against the code and
neither is demonstrable:

- naive/aware skew on the round-trip — every production writer of
  ``started_at`` stores an aware UTC value (``manager.py`` ``start_task``), and
  ``test_started_at_round_trips_tz_aware`` below pins the round-trip as
  lossless under a non-UTC process timezone;
- read-before-commit — ``astart_task`` awaits ``asyncio.to_thread(start_task)``
  and ``start_task``'s ``run_or_schedule`` blocks for the result, so the commit
  has landed before ``complete_task`` reads.

A wall-clock step, or a caller passing a naive datetime through the untyped
``update_task_status(**kwargs)``, both remain possible and neither can be shown
from the tree. So these tests pin the cause-**independent** half: an unknowable
duration is recorded as ``None`` and logged loudly, never clamped to ``0`` and
never allowed to abort the task. #13344 stays open for the cause.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

import pytest

from memory import MemoryManager, TaskExecutionRecord, TaskPriority, TaskStatus

_NON_UTC_ZONE = "Pacific/Kiritimati"  # UTC+14


@pytest.fixture()
def non_utc_tz(monkeypatch):
    monkeypatch.setenv("TZ", _NON_UTC_ZONE)
    time.tzset()
    yield
    monkeypatch.undo()
    time.tzset()


def _record(task_id: str, *, started_at=None, created_at=None) -> TaskExecutionRecord:
    return TaskExecutionRecord(
        task_id=task_id,
        task_name="t",
        description="d",
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.MEDIUM,
        created_at=created_at or datetime.now(tz=timezone.utc),
        started_at=started_at,
    )


class TestElapsedSeconds:
    """``TaskExecutionRecord.elapsed_seconds`` is where the value is decided."""

    def test_normal_elapsed_is_the_delta(self) -> None:
        started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert _record("t", started_at=started).elapsed_seconds(started + timedelta(seconds=2.5)) == 2.5

    def test_no_started_at_is_unknowable(self) -> None:
        assert _record("t").elapsed_seconds(datetime.now(tz=timezone.utc)) is None

    def test_future_started_at_records_none_not_a_clamped_zero(self, caplog) -> None:
        started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        completed = started - timedelta(seconds=7200)

        with caplog.at_level(logging.ERROR, logger="memory.models"):
            duration = _record("task-skewed", started_at=started).elapsed_seconds(completed)

        assert duration is None, "a skewed duration must be unknowable, not 0 and not negative"
        assert duration != 0, "clamping to zero hides the skew behind a plausible measurement"

    def test_the_skew_is_logged_with_both_instants(self, caplog) -> None:
        """A silent ``None`` would make the next occurrence as undiagnosable as this one."""
        started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        completed = started - timedelta(seconds=7200)

        with caplog.at_level(logging.ERROR, logger="memory.models"):
            _record("task-skewed", started_at=started).elapsed_seconds(completed)

        [record] = [r for r in caplog.records if r.levelno >= logging.ERROR]
        message = record.getMessage()
        assert "task-skewed" in message
        assert started.isoformat() in message and completed.isoformat() in message
        assert "7200" in message, "the magnitude of the skew is what identifies its cause"

    def test_a_healthy_duration_logs_nothing(self, caplog) -> None:
        """Contrast fixture — the error must not fire on the ordinary path."""
        started = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        with caplog.at_level(logging.ERROR, logger="memory.models"):
            _record("task-ok", started_at=started).elapsed_seconds(started + timedelta(seconds=1))

        assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []

    def test_mixed_timezone_awareness_is_unknowable_not_a_crash(self, caplog) -> None:
        """Review on #18097: the subtraction is what raises, so the guard must precede it.

        ``datetime - datetime`` across the naive/aware boundary raises
        ``TypeError``, and it sat *above* the negative-duration fallback — so the
        fallback could never run and a bookkeeping mismatch would abort the
        tracked operation. That is the exact failure #13344 exists to stop,
        reachable through a different door. Before the fix this raised rather
        than returning ``None``.
        """
        naive = datetime(2026, 1, 1, 12, 0, 0)
        aware = datetime(2026, 1, 1, 12, 0, 5, tzinfo=timezone.utc)

        with caplog.at_level(logging.ERROR, logger="memory.models"):
            duration = _record("task-mixed", started_at=naive).elapsed_seconds(aware)

        assert duration is None, "an unmeasurable duration is None, never a raise and never a 0"
        [record] = [r for r in caplog.records if r.levelno >= logging.ERROR]
        message = record.getMessage()
        assert "timezone-naive" in message, "the log must name why it could not measure"
        assert "task-mixed" in message

    def test_mixed_awareness_in_the_other_direction_is_also_unknowable(self) -> None:
        """An aware ``started_at`` against a naive ``completed_at`` raises the same way."""
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        naive = datetime(2026, 1, 1, 12, 0, 5)

        assert _record("t", started_at=aware).elapsed_seconds(naive) is None

    def test_a_consistently_naive_pair_still_measures(self) -> None:
        """The guard is about the *mismatch*, not about naive values.

        Pinned so a later broadening to "reject every naive instant" fails here:
        two naive instants are mutually consistent and their delta is a real
        measurement, so refusing it would discard a duration we actually know.
        """
        started = datetime(2026, 1, 1, 12, 0, 0)

        assert _record("t", started_at=started).elapsed_seconds(started + timedelta(seconds=3)) == 3.0


class TestCompleteTaskDoesNotAbort:
    """The blast radius: ``complete_task`` must not raise at its caller."""

    @pytest.mark.asyncio
    async def test_completion_succeeds_despite_a_future_started_at(self, tmp_path, caplog) -> None:
        manager = MemoryManager(str(tmp_path / "tasks.db"))
        future = datetime.now(tz=timezone.utc) + timedelta(hours=3)
        await manager.log_task(_record("task-future", started_at=future))

        with caplog.at_level(logging.ERROR, logger="memory.models"):
            # Before the fix this raised ValueError("duration_seconds cannot be
            # negative") out of update_task_status, through track_task, into the
            # caller's own work.
            completed = await manager.acomplete_task("task-future")

        assert completed is True
        stored = await manager.get_task("task-future")
        assert stored.status is TaskStatus.COMPLETED
        assert stored.duration_seconds is None
        assert any("13344" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_the_negative_guard_itself_is_untouched(self, tmp_path) -> None:
        """``update_task_status`` still rejects a negative value it is handed
        directly — the fix is at the producer, not by weakening validation."""
        manager = MemoryManager(str(tmp_path / "tasks.db"))
        await manager.log_task(_record("task-direct"))

        with pytest.raises(ValueError, match="duration_seconds cannot be negative"):
            await manager.update_task_status("task-direct", TaskStatus.COMPLETED, duration_seconds=-1.0)


class TestStartedAtRoundTrip:
    """#13344 acceptance item 1 — and the evidence that ruled hypothesis 1 out."""

    @pytest.mark.asyncio
    async def test_started_at_round_trips_tz_aware(self, non_utc_tz, tmp_path) -> None:
        manager = MemoryManager(str(tmp_path / "tasks.db"))
        started = datetime(2026, 3, 4, 5, 6, 7, 891011, tzinfo=timezone.utc)
        await manager.log_task(_record("task-rt", started_at=started))

        stored = await manager.get_task("task-rt")

        assert stored.started_at.tzinfo is not None, "started_at came back naive — hypothesis 1 of #13344"
        assert stored.started_at == started

    @pytest.mark.asyncio
    async def test_start_then_complete_yields_a_non_negative_duration(self, non_utc_tz, tmp_path) -> None:
        """The real lifecycle under a UTC+14 process clock."""
        manager = MemoryManager(str(tmp_path / "tasks.db"))
        await manager.log_task(_record("task-life"))

        await manager.astart_task("task-life")
        await manager.acomplete_task("task-life")

        stored = await manager.get_task("task-life")
        assert stored.duration_seconds is not None, "the lifecycle lost its duration"
        assert stored.duration_seconds >= 0
