# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared Redis key helpers + serializers for BatchJob / BatchSchedule (#12439).

Factored out of ``api/batch_jobs.py`` (which previously kept these helpers
private) so the API layer and the Celery executor/dispatcher tasks
(``tasks/batch_job_tasks.py``) read and write the exact same Redis records
through ONE canonical serializer instead of two copies that could drift.

Key layout (unchanged from the original api/batch_jobs.py implementation):
    batch:job:{job_id}        -> BatchJob JSON
    batch:jobs:all            -> set of job_id
    batch:logs:{job_id}       -> list of BatchLogEntry JSON (RPUSH order)
    batch:schedule:{id}       -> BatchSchedule JSON
    batch:schedules:all       -> set of schedule_id
"""

import json

from api.schemas_workflows import BatchJob, BatchSchedule

JOBS_ALL_KEY = "batch:jobs:all"
SCHEDULES_ALL_KEY = "batch:schedules:all"


def get_job_key(job_id: str) -> str:
    """Redis key for a single job's record."""
    return f"batch:job:{job_id}"


def get_schedule_key(schedule_id: str) -> str:
    """Redis key for a single schedule's record."""
    return f"batch:schedule:{schedule_id}"


def get_logs_key(job_id: str) -> str:
    """Redis key for a job's execution log list."""
    return f"batch:logs:{job_id}"


def serialize_job(job: BatchJob) -> str:
    """Serialize a BatchJob to JSON string."""
    return job.model_dump_json()


def deserialize_job(data: str | bytes) -> BatchJob:
    """Deserialize a BatchJob from a JSON string or bytes (raw Redis GET)."""
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return BatchJob(**json.loads(data))


def serialize_schedule(schedule: BatchSchedule) -> str:
    """Serialize a BatchSchedule to JSON string."""
    return schedule.model_dump_json()


def deserialize_schedule(data: str | bytes) -> BatchSchedule:
    """Deserialize a BatchSchedule from a JSON string or bytes (raw Redis GET)."""
    if isinstance(data, bytes):
        data = data.decode("utf-8")
    return BatchSchedule(**json.loads(data))
