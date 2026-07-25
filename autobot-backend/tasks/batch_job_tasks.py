# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Batch job scheduling + execution plumbing (#12439).

Background
----------
``api/batch_jobs.py`` has always stored ``BatchJob`` and ``BatchSchedule``
records in Redis, but nothing ever consumed them: schedules (cron_expression
+ enabled) sat as inert metadata, and jobs themselves never transitioned past
``pending`` because nothing ever executed them (#12439 discovery, filed from
#12380).

This module provides the two Celery tasks that close that gap:

``run_batch_job(job_id)``
    The single execution entry point. Loads the job, transitions
    pending -> running -> completed/failed, and dispatches to
    ``_execute_batch_job`` by ``job_type``. Both the manual "run now" route
    (``POST /api/batch-jobs/{job_id}/run``) and the scheduled dispatcher call
    this exact task so on-demand and cron-driven execution share one path.

``dispatch_due_batch_schedules()``
    The Celery-beat single-tick dispatcher (registered in ``celery_app.py``
    on a ``crontab(minute="*")`` beat entry). Scans every ``BatchSchedule``,
    and for each enabled schedule whose ``next_run <= now``: claims it by
    advancing ``next_run`` to the next cron occurrence BEFORE enqueueing
    (double-fire avoidance — mirrors the zrem-before-dispatch pattern in
    ``llc/scheduler/routine_scheduler.py``), then enqueues
    ``run_batch_job`` unless the referenced job is already ``running``
    (skip-if-running, so overlapping runs of a slow job are never queued
    concurrently).

Execution scope (IMPORTANT)
----------------------------
``_execute_batch_job`` is intentionally a documented no-op / 'custom' hook.
This module delivers the scheduling + execution PLUMBING only — it does NOT
fabricate real behavior for any ``BatchJobType`` (data_processing,
file_conversion, report_generation, backup). Implementing real per-job_type
work is tracked in a dedicated follow-up issue referenced from the #12439 PR.
"""

from datetime import datetime, timezone

from celery_app import celery_app

from api.schemas_workflows import BatchJob, BatchJobStatus, BatchLogEntry
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from services.batch_job_store import (
    SCHEDULES_ALL_KEY,
    deserialize_job,
    deserialize_schedule,
    get_job_key,
    get_logs_key,
    get_schedule_key,
    serialize_job,
    serialize_schedule,
)

logger = get_logger(__name__)

_REDIS_DATABASE = "main"


# =============================================================================
# No-op / custom execution hook — see module docstring "Execution scope".
# =============================================================================


def _execute_batch_job(job: BatchJob) -> dict:
    """Dispatch-by-job_type execution hook — currently a documented no-op.

    Reads ``job.job_type`` (the dispatch point real per-type handlers will
    hang off of) but returns a stub result for every type. No per-type
    behavior is fabricated here; see the #12439 follow-up issue for
    implementing data_processing / file_conversion / report_generation /
    backup / custom execution.
    """
    note = (
        f"Execution for job_type={job.job_type.value!r} is not yet implemented "
        "(custom/no-op stub, see #12439 follow-up)."
    )
    logger.info("_execute_batch_job(%s): %s", job.job_id, note)
    return {"job_type": job.job_type.value, "status": "no_op", "note": note}


# =============================================================================
# Executor task
# =============================================================================


def _append_log(redis_client, job_id: str, level: str, message: str) -> None:
    """Append a BatchLogEntry to batch:logs:{job_id} (RPUSH — read in order)."""
    entry = BatchLogEntry(timestamp=datetime.now(tz=timezone.utc), level=level, message=message)
    redis_client.rpush(get_logs_key(job_id), entry.model_dump_json())


@celery_app.task(bind=True, name="tasks.run_batch_job")
def run_batch_job(self, job_id: str) -> dict:
    """Execute a single batch job end-to-end.

    Transitions pending -> running (sets started_at) -> completed (sets
    completed_at + result) or failed (sets completed_at + error_message).
    Appends a log entry at start and at the terminal transition.
    """
    redis_client = get_redis_client(database=_REDIS_DATABASE)
    if not redis_client:
        logger.error("run_batch_job(%s): Redis unavailable", job_id)
        return {"status": "error", "reason": "redis_unavailable"}

    job_key = get_job_key(job_id)
    job_data = redis_client.get(job_key)
    if not job_data:
        logger.error("run_batch_job(%s): job not found", job_id)
        return {"status": "error", "reason": "job_not_found"}

    job = deserialize_job(job_data)

    job.status = BatchJobStatus.running
    job.started_at = datetime.now(tz=timezone.utc)
    redis_client.set(job_key, serialize_job(job))
    _append_log(redis_client, job_id, "info", f"Job {job_id} started (job_type={job.job_type.value})")
    logger.info("run_batch_job(%s): started (job_type=%s)", job_id, job.job_type.value)

    try:
        result = _execute_batch_job(job)
    except Exception as exc:
        job.status = BatchJobStatus.failed
        job.completed_at = datetime.now(tz=timezone.utc)
        job.error_message = str(exc)
        redis_client.set(job_key, serialize_job(job))
        _append_log(redis_client, job_id, "error", f"Job {job_id} failed: {exc}")
        logger.error("run_batch_job(%s): failed: %s", job_id, exc, exc_info=True)
        return {"status": "failed", "error": str(exc)}

    job.status = BatchJobStatus.completed
    job.completed_at = datetime.now(tz=timezone.utc)
    job.progress = 100
    job.result = result
    redis_client.set(job_key, serialize_job(job))
    _append_log(redis_client, job_id, "info", f"Job {job_id} completed")
    logger.info("run_batch_job(%s): completed", job_id)
    return {"status": "completed", "result": result}


# =============================================================================
# Dispatcher task (Celery-beat single-tick — see celery_app.py beat_schedule)
# =============================================================================


def _decode(value) -> str:
    return value.decode("utf-8") if isinstance(value, bytes) else value


@celery_app.task(name="tasks.dispatch_due_batch_schedules")
def dispatch_due_batch_schedules() -> dict:
    """Scan BatchSchedule records and enqueue due ones (#12439).

    Runs every minute via a Celery-beat entry (celery_app.py). For every
    schedule with ``enabled=True`` and ``next_run <= now``: claims it by
    rewriting ``next_run`` to the schedule's next cron occurrence BEFORE
    enqueueing (double-fire avoidance — a second tick within the same
    minute, or a retried beat run, then sees ``next_run > now`` and skips),
    then enqueues ``run_batch_job`` unless the referenced job is already
    ``running`` (skip-if-running for overlaps).
    """
    # #12439: lazy import — mirrors llc/scheduler/routine_scheduler.py's
    # croniter handling. croniter is a hard requirement in requirements.txt,
    # but startup-import-smoke deliberately runs with 29 optional deps
    # (croniter included) NOT installed to verify the app still imports; a
    # module-level `from croniter import croniter` here would be re-exported
    # via tasks/__init__.py (imported at startup for task discovery) and
    # hard-fail that check. Deferring the import to call-time — where
    # croniter IS installed in every real deployment — fixes that without
    # weakening the dependency.
    try:
        from croniter import CroniterError, croniter
    except ImportError:
        logger.warning("dispatch_due_batch_schedules: croniter not installed — schedule dispatch disabled")
        return {"dispatched": 0, "skipped_disabled": 0, "skipped_running": 0, "not_due": 0}

    redis_client = get_redis_client(database=_REDIS_DATABASE)
    if not redis_client:
        logger.warning("dispatch_due_batch_schedules: Redis unavailable")
        return {"dispatched": 0, "skipped_disabled": 0, "skipped_running": 0, "not_due": 0}

    now = datetime.now(tz=timezone.utc)
    schedule_ids = redis_client.smembers(SCHEDULES_ALL_KEY)

    dispatched = skipped_disabled = skipped_running = not_due = 0

    for raw_id in schedule_ids:
        schedule_id = _decode(raw_id)
        schedule_key = get_schedule_key(schedule_id)
        schedule_data = redis_client.get(schedule_key)
        if not schedule_data:
            continue

        schedule = deserialize_schedule(schedule_data)

        if not schedule.enabled:
            skipped_disabled += 1
            continue

        if schedule.next_run > now:
            not_due += 1
            continue

        try:
            schedule.next_run = croniter(schedule.cron_expression, now).get_next(datetime)
        except (CroniterError, ValueError) as exc:
            logger.warning(
                "dispatch_due_batch_schedules: invalid cron_expression %r for schedule %s: %s",
                schedule.cron_expression,
                schedule_id,
                exc,
            )
            continue
        # Claim BEFORE enqueue — persists the advanced next_run so a
        # concurrent/duplicate tick observes it as no-longer-due.
        redis_client.set(schedule_key, serialize_schedule(schedule))

        job_data = redis_client.get(get_job_key(schedule.job_id))
        if job_data:
            job = deserialize_job(job_data)
            if job.status == BatchJobStatus.running:
                logger.info(
                    "dispatch_due_batch_schedules: skipping schedule %s — job %s already running",
                    schedule_id,
                    schedule.job_id,
                )
                skipped_running += 1
                continue

        run_batch_job.delay(schedule.job_id)
        dispatched += 1

    logger.info(
        "dispatch_due_batch_schedules: dispatched=%d skipped_disabled=%d skipped_running=%d not_due=%d",
        dispatched,
        skipped_disabled,
        skipped_running,
        not_due,
    )
    return {
        "dispatched": dispatched,
        "skipped_disabled": skipped_disabled,
        "skipped_running": skipped_running,
        "not_due": not_due,
    }
