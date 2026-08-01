# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #12439: batch job scheduling + execution plumbing regression tests.

Covers:
  - run_batch_job: pending -> running -> completed (no-op hook), and
    -> failed on an execution exception; log entries appended.
  - dispatch_due_batch_schedules: due+enabled dispatches and advances
    next_run; disabled/not-yet-due/already-running schedules are skipped;
    a double-tick within the same cron window does not double-fire.
  - Celery-beat registration: both task names resolve on the in-process
    test app that tasks/conftest.py injects.

Uses fakeredis (already a project dependency, see services/queue_integration_test.py
and tests/integration/test_celery_reliability.py for the same pattern) — no live
Redis or Celery worker required.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

try:
    import fakeredis

    _FAKEREDIS_AVAILABLE = True
except ImportError:
    _FAKEREDIS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not _FAKEREDIS_AVAILABLE, reason="fakeredis not installed")

import tasks.batch_job_tasks as bjt  # noqa: E402
from api.schemas_workflows import BatchJob, BatchJobStatus, BatchJobType, BatchSchedule  # noqa: E402


@pytest.fixture
def fake_redis(monkeypatch):
    """Patch the sync Redis seam in batch_job_tasks with fakeredis (bytes mode,
    matching the real redis-py client — the module under test calls
    .decode('utf-8') / relies on services.batch_job_store handling bytes)."""
    client = fakeredis.FakeStrictRedis()
    monkeypatch.setattr(bjt, "get_redis_client", lambda **_kw: client)
    yield client
    client.flushall()


def _seed_job(redis, job_id="job-1", status=BatchJobStatus.pending, job_type=BatchJobType.custom):
    job = BatchJob(
        job_id=job_id,
        name="Test Job",
        job_type=job_type,
        status=status,
        progress=0,
        parameters={},
        created_at=datetime.now(tz=timezone.utc),
    )
    redis.set(bjt.get_job_key(job_id), job.model_dump_json())
    return job


def _seed_schedule(redis, schedule_id="sched-1", job_id="job-1", cron="* * * * *", enabled=True, next_run=None):
    schedule = BatchSchedule(
        schedule_id=schedule_id,
        job_id=job_id,
        cron_expression=cron,
        enabled=enabled,
        next_run=next_run or datetime.now(tz=timezone.utc) - timedelta(minutes=1),
    )
    redis.set(bjt.get_schedule_key(schedule_id), schedule.model_dump_json())
    redis.sadd(bjt.SCHEDULES_ALL_KEY, schedule_id)
    return schedule


# ---------------------------------------------------------------------------
# run_batch_job — executor
# ---------------------------------------------------------------------------


def test_run_batch_job_completes_via_noop_hook(fake_redis):
    _seed_job(fake_redis, job_id="job-1")

    result = bjt.run_batch_job("job-1")

    assert result["status"] == "completed"
    persisted = BatchJob(**json.loads(fake_redis.get(bjt.get_job_key("job-1"))))
    assert persisted.status == BatchJobStatus.completed
    assert persisted.started_at is not None
    assert persisted.completed_at is not None
    assert persisted.progress == 100
    assert persisted.result["status"] == "no_op"

    logs = fake_redis.lrange(bjt.get_logs_key("job-1"), 0, -1)
    assert len(logs) == 2  # started + completed
    assert b"started" in logs[0]
    assert b"completed" in logs[1]


def test_run_batch_job_marks_failed_on_exception(fake_redis, monkeypatch):
    _seed_job(fake_redis, job_id="job-2")
    monkeypatch.setattr(bjt, "_execute_batch_job", lambda job: (_ for _ in ()).throw(RuntimeError("boom")))

    result = bjt.run_batch_job("job-2")

    assert result["status"] == "failed"
    persisted = BatchJob(**json.loads(fake_redis.get(bjt.get_job_key("job-2"))))
    assert persisted.status == BatchJobStatus.failed
    assert persisted.error_message == "boom"
    assert persisted.completed_at is not None

    logs = fake_redis.lrange(bjt.get_logs_key("job-2"), 0, -1)
    assert len(logs) == 2  # started + failed
    assert b"failed" in logs[1]


def test_run_batch_job_missing_job_is_a_safe_noop(fake_redis):
    result = bjt.run_batch_job("does-not-exist")
    assert result == {"status": "error", "reason": "job_not_found"}


# ---------------------------------------------------------------------------
# dispatch_due_batch_schedules — dispatcher
# ---------------------------------------------------------------------------


def test_dispatch_enqueues_due_enabled_schedule_and_advances_next_run(fake_redis, monkeypatch):
    _seed_job(fake_redis, job_id="job-1")
    _seed_schedule(fake_redis, schedule_id="sched-1", job_id="job-1", cron="* * * * *")

    delayed = []
    monkeypatch.setattr(bjt.run_batch_job, "delay", lambda job_id: delayed.append(job_id))

    result = bjt.dispatch_due_batch_schedules()

    assert result["dispatched"] == 1
    assert delayed == ["job-1"]

    persisted = BatchSchedule(**json.loads(fake_redis.get(bjt.get_schedule_key("sched-1"))))
    assert persisted.next_run > datetime.now(tz=timezone.utc)


def test_dispatch_skips_disabled_schedule(fake_redis, monkeypatch):
    _seed_job(fake_redis, job_id="job-1")
    _seed_schedule(fake_redis, schedule_id="sched-1", job_id="job-1", enabled=False)

    delayed = []
    monkeypatch.setattr(bjt.run_batch_job, "delay", lambda job_id: delayed.append(job_id))

    result = bjt.dispatch_due_batch_schedules()

    assert result["dispatched"] == 0
    assert result["skipped_disabled"] == 1
    assert delayed == []


def test_dispatch_skips_not_yet_due_schedule(fake_redis, monkeypatch):
    _seed_job(fake_redis, job_id="job-1")
    _seed_schedule(
        fake_redis,
        schedule_id="sched-1",
        job_id="job-1",
        next_run=datetime.now(tz=timezone.utc) + timedelta(hours=1),
    )

    delayed = []
    monkeypatch.setattr(bjt.run_batch_job, "delay", lambda job_id: delayed.append(job_id))

    result = bjt.dispatch_due_batch_schedules()

    assert result["dispatched"] == 0
    assert result["not_due"] == 1
    assert delayed == []


def test_dispatch_skips_already_running_job(fake_redis, monkeypatch):
    _seed_job(fake_redis, job_id="job-1", status=BatchJobStatus.running)
    _seed_schedule(fake_redis, schedule_id="sched-1", job_id="job-1")

    delayed = []
    monkeypatch.setattr(bjt.run_batch_job, "delay", lambda job_id: delayed.append(job_id))

    result = bjt.dispatch_due_batch_schedules()

    assert result["dispatched"] == 0
    assert result["skipped_running"] == 1
    assert delayed == []

    # Claim still advances next_run even when the dispatch itself is skipped,
    # so a stuck 'running' job doesn't spam the dispatcher every beat tick.
    persisted = BatchSchedule(**json.loads(fake_redis.get(bjt.get_schedule_key("sched-1"))))
    assert persisted.next_run > datetime.now(tz=timezone.utc)


def test_dispatch_double_tick_does_not_double_fire(fake_redis, monkeypatch):
    """Two dispatcher ticks in the same cron window must dispatch exactly once."""
    _seed_job(fake_redis, job_id="job-1")
    _seed_schedule(fake_redis, schedule_id="sched-1", job_id="job-1", cron="0 0 1 1 *")  # next Jan 1st — far future

    delayed = []
    monkeypatch.setattr(bjt.run_batch_job, "delay", lambda job_id: delayed.append(job_id))

    first = bjt.dispatch_due_batch_schedules()
    second = bjt.dispatch_due_batch_schedules()

    assert first["dispatched"] == 1
    assert second["dispatched"] == 0
    assert second["not_due"] == 1
    assert delayed == ["job-1"]


def test_dispatch_invalid_cron_expression_is_skipped_not_raised(fake_redis, monkeypatch):
    _seed_job(fake_redis, job_id="job-1")
    _seed_schedule(fake_redis, schedule_id="sched-1", job_id="job-1", cron="not a cron expression")

    delayed = []
    monkeypatch.setattr(bjt.run_batch_job, "delay", lambda job_id: delayed.append(job_id))

    result = bjt.dispatch_due_batch_schedules()

    assert result["dispatched"] == 0
    assert delayed == []


def test_dispatch_no_redis_returns_zeroed_summary(monkeypatch):
    monkeypatch.setattr(bjt, "get_redis_client", lambda **_kw: None)
    result = bjt.dispatch_due_batch_schedules()
    assert result == {"dispatched": 0, "skipped_disabled": 0, "skipped_running": 0, "not_due": 0}


# ---------------------------------------------------------------------------
# Celery-beat registration
# ---------------------------------------------------------------------------


def test_tasks_are_registered_on_the_test_celery_app():
    import sys

    celery_app_mod = sys.modules.get("celery_app")
    assert celery_app_mod is not None
    registered = set(celery_app_mod.celery_app.tasks)
    assert "tasks.run_batch_job" in registered
    assert "tasks.dispatch_due_batch_schedules" in registered


def test_beat_schedule_entry_resolves_to_dispatcher_task():
    """celery_app.py's beat_schedule wires tasks.dispatch_due_batch_schedules
    on a distinct entry from the concurrent #12365 beat work (both entries
    coexist in the same beat_schedule dict)."""
    from pathlib import Path

    src = (Path(__file__).resolve().parents[1] / "celery_app.py").read_text(encoding="utf-8")
    assert '"task": "tasks.dispatch_due_batch_schedules"' in src
