# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Batch Job Processing Manager API

Issue #584: User-facing batch job processing system for managing long-running
batch operations like data processing, file conversion, report generation, etc.

This is separate from the internal batch optimization in backend/api/batch.py
which handles API request batching for frontend performance.
"""

import json
import logging
import uuid
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["batch-jobs", "management"])


# =============================================================================
# Data Models
# =============================================================================


class BatchJobStatus(str, Enum):
    """Status of a batch job"""

    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class BatchJobType(str, Enum):
    """Type of batch job"""

    data_processing = "data_processing"
    file_conversion = "file_conversion"
    report_generation = "report_generation"
    backup = "backup"
    custom = "custom"


class BatchJobCreate(BaseModel):
    """Request model for creating a batch job"""

    name: str = Field(..., description="Human-readable name for the job")
    job_type: BatchJobType = Field(..., description="Type of batch job")
    parameters: Dict = Field(
        default_factory=dict, description="Job-specific parameters"
    )
    schedule: Optional[str] = Field(
        None, description="Optional cron expression for scheduling"
    )
    template_id: Optional[str] = Field(
        None, description="Optional template ID to use"
    )


class BatchJob(BaseModel):
    """Batch job model"""

    job_id: str
    name: str
    job_type: BatchJobType
    status: BatchJobStatus
    progress: int = Field(0, ge=0, le=100, description="Progress percentage")
    parameters: Dict
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    result: Optional[Dict] = None


class BatchTemplate(BaseModel):
    """Batch job template model"""

    template_id: str
    name: str
    job_type: BatchJobType
    parameters: Dict
    created_at: datetime


class BatchSchedule(BaseModel):
    """Batch job schedule model"""

    schedule_id: str
    job_id: str
    cron_expression: str
    enabled: bool
    next_run: datetime


class BatchJobList(BaseModel):
    """Response model for job list"""

    jobs: List[BatchJob]
    total_count: int
    status_counts: Dict[str, int]


class LogEntry(BaseModel):
    """Log entry model"""

    timestamp: datetime
    level: str
    message: str


# =============================================================================
# Helper Functions
# =============================================================================


def _get_job_key(job_id: str) -> str:
    """Generate Redis key for job data"""
    return f"batch:job:{job_id}"


def _get_template_key(template_id: str) -> str:
    """Generate Redis key for template data"""
    return f"batch:template:{template_id}"


def _get_schedule_key(schedule_id: str) -> str:
    """Generate Redis key for schedule data"""
    return f"batch:schedule:{schedule_id}"


def _get_logs_key(job_id: str) -> str:
    """Generate Redis key for job logs"""
    return f"batch:logs:{job_id}"


def _serialize_job(job: BatchJob) -> str:
    """Serialize job to JSON string"""
    return job.model_dump_json()


def _deserialize_job(data: str) -> BatchJob:
    """Deserialize job from JSON string"""
    job_dict = json.loads(data)
    return BatchJob(**job_dict)


# =============================================================================
# Job Management Endpoints
# =============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_batch_job",
    error_code_prefix="BATCH_JOBS",
)
@router.post("", response_model=BatchJob)
async def create_batch_job(job_data: BatchJobCreate):
    """
    Create a new batch job.

    Args:
        job_data: Job creation request data

    Returns:
        BatchJob: Created job with ID and initial status
    """
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    job_id = str(uuid.uuid4())
    now = datetime.now()

    job = BatchJob(
        job_id=job_id,
        name=job_data.name,
        job_type=job_data.job_type,
        status=BatchJobStatus.pending,
        progress=0,
        parameters=job_data.parameters,
        created_at=now,
    )

    job_key = _get_job_key(job_id)
    redis_client.set(job_key, _serialize_job(job))
    redis_client.sadd("batch:jobs:all", job_id)
    redis_client.zadd("batch:jobs:created", {job_id: now.timestamp()})

    logger.info("Created batch job %s: %s", job_id, job_data.name)
    return job


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_batch_jobs",
    error_code_prefix="BATCH_JOBS",
)
@router.get("", response_model=BatchJobList)
async def list_batch_jobs(
    status: Optional[BatchJobStatus] = Query(None, description="Filter by status"),
    job_type: Optional[BatchJobType] = Query(None, description="Filter by type"),
    limit: int = Query(50, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Results offset"),
):
    """
    List all batch jobs with optional filtering and pagination.

    Args:
        status: Filter by job status
        job_type: Filter by job type
        limit: Maximum number of results
        offset: Results offset for pagination

    Returns:
        BatchJobList: List of jobs with counts
    """
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    job_ids = redis_client.smembers("batch:jobs:all")
    jobs = []
    status_counts: Dict[str, int] = {}

    for job_id_bytes in job_ids:
        job_id = job_id_bytes.decode("utf-8")
        job_key = _get_job_key(job_id)
        job_data = redis_client.get(job_key)

        if not job_data:
            continue

        job = _deserialize_job(job_data.decode("utf-8"))

        status_counts[job.status.value] = status_counts.get(job.status.value, 0) + 1

        if status and job.status != status:
            continue
        if job_type and job.job_type != job_type:
            continue

        jobs.append(job)

    jobs.sort(key=lambda j: j.created_at, reverse=True)
    total_count = len(jobs)
    jobs = jobs[offset : offset + limit]

    return BatchJobList(jobs=jobs, total_count=total_count, status_counts=status_counts)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_batch_job",
    error_code_prefix="BATCH_JOBS",
)
@router.get("/{job_id}", response_model=BatchJob)
async def get_batch_job(job_id: str):
    """
    Get detailed information about a specific job.

    Args:
        job_id: Job ID

    Returns:
        BatchJob: Full job details
    """
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    job_key = _get_job_key(job_id)
    job_data = redis_client.get(job_key)

    if not job_data:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return _deserialize_job(job_data.decode("utf-8"))


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_batch_job",
    error_code_prefix="BATCH_JOBS",
)
@router.delete("/{job_id}")
async def delete_batch_job(job_id: str):
    """
    Cancel and delete a batch job.

    Args:
        job_id: Job ID

    Returns:
        dict: Success status
    """
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    job_key = _get_job_key(job_id)
    job_data = redis_client.get(job_key)

    if not job_data:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    job = _deserialize_job(job_data.decode("utf-8"))

    if job.status == BatchJobStatus.running:
        job.status = BatchJobStatus.cancelled
        redis_client.set(job_key, _serialize_job(job))

    redis_client.delete(job_key)
    redis_client.srem("batch:jobs:all", job_id)
    redis_client.zrem("batch:jobs:created", job_id)

    logs_key = _get_logs_key(job_id)
    redis_client.delete(logs_key)

    logger.info("Deleted batch job %s", job_id)
    return {"status": "success", "job_id": job_id, "message": "Job deleted"}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_job_logs",
    error_code_prefix="BATCH_JOBS",
)
@router.get("/{job_id}/logs", response_model=List[LogEntry])
async def get_job_logs(job_id: str):
    """
    Get execution logs for a specific job.

    Args:
        job_id: Job ID

    Returns:
        List[LogEntry]: Job execution logs
    """
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    job_key = _get_job_key(job_id)
    if not redis_client.exists(job_key):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    logs_key = _get_logs_key(job_id)
    log_entries = redis_client.lrange(logs_key, 0, -1)

    logs = []
    for entry_bytes in log_entries:
        entry = json.loads(entry_bytes.decode("utf-8"))
        logs.append(LogEntry(**entry))

    return logs


# =============================================================================
# Template Management Endpoints
# =============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_batch_templates",
    error_code_prefix="BATCH_JOBS",
)
@router.get("/templates/", response_model=List[BatchTemplate])
async def list_batch_templates():
    """List all batch job templates"""
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    template_ids = redis_client.smembers("batch:templates:all")
    templates = []

    for template_id_bytes in template_ids:
        template_id = template_id_bytes.decode("utf-8")
        template_key = _get_template_key(template_id)
        template_data = redis_client.get(template_key)

        if template_data:
            template_dict = json.loads(template_data.decode("utf-8"))
            templates.append(BatchTemplate(**template_dict))

    return templates


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_batch_template",
    error_code_prefix="BATCH_JOBS",
)
@router.post("/templates/", response_model=BatchTemplate)
async def create_batch_template(
    name: str, job_type: BatchJobType, parameters: Dict
):
    """Create a new batch job template"""
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    template_id = str(uuid.uuid4())
    template = BatchTemplate(
        template_id=template_id,
        name=name,
        job_type=job_type,
        parameters=parameters,
        created_at=datetime.now(),
    )

    template_key = _get_template_key(template_id)
    redis_client.set(template_key, template.model_dump_json())
    redis_client.sadd("batch:templates:all", template_id)

    logger.info("Created batch template %s: %s", template_id, name)
    return template


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_batch_template",
    error_code_prefix="BATCH_JOBS",
)
@router.get("/templates/{template_id}", response_model=BatchTemplate)
async def get_batch_template(template_id: str):
    """Get a specific batch job template"""
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    template_key = _get_template_key(template_id)
    template_data = redis_client.get(template_key)

    if not template_data:
        raise HTTPException(
            status_code=404, detail=f"Template {template_id} not found"
        )

    template_dict = json.loads(template_data.decode("utf-8"))
    return BatchTemplate(**template_dict)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_batch_template",
    error_code_prefix="BATCH_JOBS",
)
@router.delete("/templates/{template_id}")
async def delete_batch_template(template_id: str):
    """Delete a batch job template"""
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    template_key = _get_template_key(template_id)
    if not redis_client.exists(template_key):
        raise HTTPException(
            status_code=404, detail=f"Template {template_id} not found"
        )

    redis_client.delete(template_key)
    redis_client.srem("batch:templates:all", template_id)

    logger.info("Deleted batch template %s", template_id)
    return {"status": "success", "template_id": template_id}


# =============================================================================
# Schedule Management Endpoints
# =============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_batch_schedules",
    error_code_prefix="BATCH_JOBS",
)
@router.get("/schedules/", response_model=List[BatchSchedule])
async def list_batch_schedules():
    """List all batch job schedules"""
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    schedule_ids = redis_client.smembers("batch:schedules:all")
    schedules = []

    for schedule_id_bytes in schedule_ids:
        schedule_id = schedule_id_bytes.decode("utf-8")
        schedule_key = _get_schedule_key(schedule_id)
        schedule_data = redis_client.get(schedule_key)

        if schedule_data:
            schedule_dict = json.loads(schedule_data.decode("utf-8"))
            schedules.append(BatchSchedule(**schedule_dict))

    return schedules


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_batch_schedule",
    error_code_prefix="BATCH_JOBS",
)
@router.post("/schedules/", response_model=BatchSchedule)
async def create_batch_schedule(
    job_id: str, cron_expression: str, enabled: bool = True
):
    """Create a new batch job schedule"""
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    job_key = _get_job_key(job_id)
    if not redis_client.exists(job_key):
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    schedule_id = str(uuid.uuid4())
    schedule = BatchSchedule(
        schedule_id=schedule_id,
        job_id=job_id,
        cron_expression=cron_expression,
        enabled=enabled,
        next_run=datetime.now(),
    )

    schedule_key = _get_schedule_key(schedule_id)
    redis_client.set(schedule_key, schedule.model_dump_json())
    redis_client.sadd("batch:schedules:all", schedule_id)

    logger.info("Created batch schedule %s for job %s", schedule_id, job_id)
    return schedule


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_batch_schedule",
    error_code_prefix="BATCH_JOBS",
)
@router.delete("/schedules/{schedule_id}")
async def delete_batch_schedule(schedule_id: str):
    """Delete a batch job schedule"""
    redis_client = get_redis_client(database="main")
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis service unavailable")

    schedule_key = _get_schedule_key(schedule_id)
    if not redis_client.exists(schedule_key):
        raise HTTPException(
            status_code=404, detail=f"Schedule {schedule_id} not found"
        )

    redis_client.delete(schedule_key)
    redis_client.srem("batch:schedules:all", schedule_id)

    logger.info("Deleted batch schedule %s", schedule_id)
    return {"status": "success", "schedule_id": schedule_id}


# =============================================================================
# Health Check Endpoint
# =============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_batch_jobs_health",
    error_code_prefix="BATCH_JOBS",
)
@router.get("/health")
async def get_batch_jobs_health():
    """
    Get batch jobs service health status.

    Returns:
        dict: Service health information
    """
    redis_client = get_redis_client(database="main")
    redis_healthy = redis_client is not None

    if redis_healthy:
        try:
            redis_client.ping()
        except Exception as e:
            logger.warning("Redis ping failed: %s", e)
            redis_healthy = False

    return {
        "status": "healthy" if redis_healthy else "degraded",
        "service": "batch_jobs_manager",
        "redis_connected": redis_healthy,
        "timestamp": datetime.now().isoformat(),
        "capabilities": [
            "job_management",
            "template_management",
            "schedule_management",
            "log_tracking",
        ],
    }
