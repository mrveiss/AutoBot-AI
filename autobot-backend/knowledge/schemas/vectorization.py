# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for the knowledge vectorization API endpoints (#5317)."""

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field, field_validator

_REINDEX_DEFAULT_BATCH_SIZE = 20
_REINDEX_COLLECTION_PATTERN = r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,61}[a-zA-Z0-9]$"


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
    last_run: str | None
    is_running: bool


class VectorizationStatusPollResponse(BaseModel):
    """Response for GET /vectorize_facts/status."""

    model_config = ConfigDict(extra="allow")

    is_running: bool
    last_run: str | None
    check_interval: int
    batch_size: int


class ReindexWithContextResponse(BaseModel):
    """Response for POST /reindex_with_context (#1513)."""

    model_config = ConfigDict(extra="allow")

    status: str
    message: str


class ReindexWithContextStatusResponse(BaseModel):
    """Response for GET /reindex_with_context/status (#1761)."""

    model_config = ConfigDict(extra="allow")

    is_running: bool
    enriched_count: int
    total_count: int
    started_at: str | None
    completed_at: str | None
    error: str | None


class BatchVectorizeRequest(BaseModel):
    """Request model for POST /vectorize_documents (#2077)."""

    document_ids: List[str] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="List of document IDs to vectorize (max 100 per request)",
    )

    @field_validator("document_ids")
    @classmethod
    def validate_document_ids(cls, v: List[str]) -> List[str]:
        """Deduplicate and validate individual document IDs."""
        seen: dict[str, None] = {}
        for item in v:
            if not isinstance(item, str) or not item.strip() or len(item) > 255:
                raise ValueError(f"Invalid document ID: {item!r}")
            seen[item] = None
        return list(seen)


class ReindexWithContextRequest(BaseModel):
    """Request model for POST /reindex_with_context (#1513)."""

    collection_name: str | None = Field(
        default=None,
        max_length=200,
        pattern=_REINDEX_COLLECTION_PATTERN,
        description="ChromaDB collection (defaults to knowledge_vectors)",
    )
    batch_size: int = Field(
        default=_REINDEX_DEFAULT_BATCH_SIZE,
        ge=1,
        le=500,
        description="Chunks to process per batch",
    )
