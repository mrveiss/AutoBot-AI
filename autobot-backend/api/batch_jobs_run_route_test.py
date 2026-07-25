# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #12439: POST /api/batch-jobs/{job_id}/run on-demand execution route.

Reuses the same stub-then-real-load setup as batch_jobs_schedules_test.py
(same file, same import ordering constraints — see that file's module
docstring) so ``api.batch_jobs`` real-loads with ``api.schemas_workflows``
and ``services.batch_job_store``.
"""

import json
from datetime import datetime, timezone

import pytest

import api.batch_jobs as _bj  # noqa: E402
from api.batch_jobs_schedules_test import _FakeRedis  # noqa: F401  (reuse fixture)
from api.schemas_workflows import BatchJob, BatchJobStatus, BatchJobType, BatchSchedule


def _seed_job(redis, job_id="job-1", status=BatchJobStatus.pending):
    job = BatchJob(
        job_id=job_id,
        name="Test Job",
        job_type=BatchJobType.custom,
        status=status,
        progress=0,
        parameters={},
        created_at=datetime.now(tz=timezone.utc),
    )
    redis.set(_bj._get_job_key(job_id), job.model_dump_json())
    return job


@pytest.mark.asyncio
async def test_run_route_queues_pending_job(monkeypatch):
    redis = _FakeRedis()
    _seed_job(redis, job_id="job-1", status=BatchJobStatus.pending)
    monkeypatch.setattr(_bj, "get_redis_client", lambda database: redis)

    import tasks.batch_job_tasks as bjt

    delayed = []
    monkeypatch.setattr(bjt.run_batch_job, "delay", lambda job_id: delayed.append(job_id))

    result = await _bj.run_batch_job_now("job-1", current_user={"user_id": "test"})

    assert result.job_id == "job-1"
    assert delayed == ["job-1"]


@pytest.mark.asyncio
async def test_run_route_404_for_unknown_job(monkeypatch):
    from fastapi import HTTPException

    redis = _FakeRedis()
    monkeypatch.setattr(_bj, "get_redis_client", lambda database: redis)

    with pytest.raises(HTTPException) as exc_info:
        await _bj.run_batch_job_now("does-not-exist", current_user={"user_id": "test"})

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_run_route_409_when_already_running(monkeypatch):
    from fastapi import HTTPException

    redis = _FakeRedis()
    _seed_job(redis, job_id="job-1", status=BatchJobStatus.running)
    monkeypatch.setattr(_bj, "get_redis_client", lambda database: redis)

    with pytest.raises(HTTPException) as exc_info:
        await _bj.run_batch_job_now("job-1", current_user={"user_id": "test"})

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_next_run_fix_create_schedule_fires_on_cron_not_immediately(monkeypatch):
    """POST /schedules/ must seed next_run from the cron expression, not now()."""
    redis = _FakeRedis()
    _seed_job(redis, job_id="job-1", status=BatchJobStatus.pending)
    monkeypatch.setattr(_bj, "get_redis_client", lambda database: redis)

    schedule = await _bj.create_batch_schedule(
        job_id="job-1",
        cron_expression="0 0 1 1 *",  # next Jan 1st — far future
        enabled=True,
        current_user={"user_id": "test"},
    )

    assert schedule.next_run > datetime.now(tz=timezone.utc)
    persisted = json.loads(redis.get(_bj._get_schedule_key(schedule.schedule_id)))
    assert BatchSchedule(**persisted).next_run == schedule.next_run
