# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
API Response Type Definitions for AutoBot

Provides strongly-typed API response structures to replace Dict[str, Any] patterns.
"""

from typing import Generic, List, TypeVar

from pydantic import BaseModel, Field

from type_defs.common import Metadata, MetricsDict, TimestampStr

# Generic type variable for response data
T = TypeVar("T")


class APISuccessResponse(BaseModel, Generic[T]):
    """Standard success response structure."""

    success: bool = True
    data: T
    message: str | None = None
    timestamp: TimestampStr | None = None


class APIErrorResponse(BaseModel):
    """Standard error response structure."""

    success: bool = False
    error: str
    error_code: str | None = None
    details: Metadata | None = None
    timestamp: TimestampStr | None = None


# Union type for any API response
APIResponse = APISuccessResponse | APIErrorResponse


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response structure."""

    items: List[T]
    total: int
    page: int
    page_size: int
    has_more: bool = False
    next_cursor: str | None = None


class HealthCheckResponse(BaseModel):
    """Health check response structure."""

    status: str = Field(..., description="Service status: healthy, degraded, unhealthy")
    version: str | None = None
    uptime_seconds: float | None = None
    checks: Metadata | None = None


class ServiceStatusResponse(BaseModel):
    """Service status response structure."""

    service_name: str
    status: str
    healthy: bool
    latency_ms: float | None = None
    last_check: TimestampStr | None = None
    details: Metadata | None = None


class BatchOperationResponse(BaseModel):
    """Batch operation response structure."""

    total_items: int
    successful: int
    failed: int
    results: List[Metadata]
    errors: List[Metadata] | None = None


class SearchResponse(BaseModel, Generic[T]):
    """Search response structure."""

    results: List[T]
    total_matches: int
    query: str
    filters_applied: Metadata | None = None
    search_time_ms: float | None = None
    metrics: MetricsDict | None = None


class ValidationErrorResponse(BaseModel):
    """Validation error response structure."""

    success: bool = False
    error: str = "Validation failed"
    validation_errors: List[Metadata]
    field_errors: Metadata | None = None


class FileOperationResponse(BaseModel):
    """File operation response structure."""

    success: bool
    path: str
    operation: str  # read, write, delete, move, etc.
    size_bytes: int | None = None
    content: str | None = None
    metadata: Metadata | None = None
    error: str | None = None


class ProcessingResponse(BaseModel):
    """Processing/Analysis response structure."""

    success: bool
    processed_items: int
    processing_time_ms: float
    results: List[Metadata]
    metrics: MetricsDict | None = None
    warnings: List[str] | None = None


class ConfigResponse(BaseModel):
    """Configuration response structure."""

    config_name: str
    values: Metadata
    source: str | None = None
    last_modified: TimestampStr | None = None
    is_default: bool = False
