# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for the knowledge vectorization API endpoints (#5317)."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class VectorizationSummary(BaseModel):
    """Summary statistics returned inside vectorization-status responses."""

    model_config = ConfigDict(extra="allow")

    total_checked: int
    vectorized: int
    not_vectorized: int
    vectorization_percentage: float


class VectorizationStatusResponse(BaseModel):
    """Response for POST /vectorization_status."""

    model_config = ConfigDict(extra="allow")

    statuses: Dict[str, Any]
    summary: VectorizationSummary
    cached: bool
    check_time_ms: float


class VectorizeFactsResponse(BaseModel):
    """Response for POST /vectorize_facts."""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    processed: int
    success: int
    failed: int
    skipped: int


class VectorizeFactJobResponse(BaseModel):
    """Response for POST /vectorize_fact/{fact_id}."""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    job_id: str
    fact_id: str
    force: bool


class DocumentResult(BaseModel):
    """Per-document result entry in batch vectorization."""

    model_config = ConfigDict(extra="allow")

    id: str
    status: str


class VectorizeDocumentsResponse(BaseModel):
    """Response for POST /vectorize_documents."""

    model_config = ConfigDict(extra="allow")

    results: List[DocumentResult]
    total: int
    succeeded: int


class VectorizeJobStatusResponse(BaseModel):
    """Response for GET /vectorize_job/{job_id}."""

    model_config = ConfigDict(extra="allow")

    status: str
    job: Dict[str, Any]


class FailedJobsResponse(BaseModel):
    """Response for GET /vectorize_jobs/failed."""

    model_config = ConfigDict(extra="allow")

    status: str
    failed_jobs: List[Dict[str, Any]]
    total_failed: int


class RetryJobResponse(BaseModel):
    """Response for POST /vectorize_jobs/{job_id}/retry."""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    new_job_id: str
    fact_id: str
    original_job_id: str


class DeleteJobResponse(BaseModel):
    """Response for DELETE /vectorize_jobs/{job_id}."""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    job_id: str


class ClearFailedJobsResponse(BaseModel):
    """Response for DELETE /vectorize_jobs/failed/clear."""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    deleted_count: int


class BackgroundVectorizationResponse(BaseModel):
    """Response for POST /vectorize_facts/background."""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str
    last_run: Optional[str]
    is_running: bool


class VectorizationStatusPollResponse(BaseModel):
    """Response for GET /vectorize_facts/status."""

    model_config = ConfigDict(extra="allow")

    is_running: bool
    last_run: Optional[str]
    check_interval: int
    batch_size: int


class ReindexWithContextStatusResponse(BaseModel):
    """Response for GET /reindex_with_context/status (#1761)."""

    model_config = ConfigDict(extra="allow")

    is_running: bool
    enriched_count: int
    total_count: int
    started_at: Optional[str]
    completed_at: Optional[str]
    error: Optional[str]
