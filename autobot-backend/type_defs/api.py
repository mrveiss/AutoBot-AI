# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
API Response Type Definitions for AutoBot

Provides strongly-typed API response structures to replace Dict[str, Any] patterns.
"""

from typing import Generic, List, Optional, TypeVar, Union

from backend.type_defs.common import Metadata, MetricsDict, TimestampStr
from pydantic import BaseModel, Field

# Generic type variable for response data
T = TypeVar("T")


class APISuccessResponse(BaseModel, Generic[T]):
    """Standard success response structure."""

    success: bool = True
    data: T
    message: Optional[str] = None
    timestamp: Optional[TimestampStr] = None


class APIErrorResponse(BaseModel):
    """Standard error response structure."""

    success: bool = False
    error: str
    error_code: Optional[str] = None
    details: Optional[Metadata] = None
    timestamp: Optional[TimestampStr] = None


# Union type for any API response
APIResponse = Union[APISuccessResponse, APIErrorResponse]


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response structure."""

    items: List[T]
    total: int
    page: int
    page_size: int
    has_more: bool = False
    next_cursor: Optional[str] = None


class HealthCheckResponse(BaseModel):
    """Health check response structure."""

    status: str = Field(..., description="Service status: healthy, degraded, unhealthy")
    version: Optional[str] = None
    uptime_seconds: Optional[float] = None
    checks: Optional[Metadata] = None


class ServiceStatusResponse(BaseModel):
    """Service status response structure."""

    service_name: str
    status: str
    healthy: bool
    latency_ms: Optional[float] = None
    last_check: Optional[TimestampStr] = None
    details: Optional[Metadata] = None


class BatchOperationResponse(BaseModel):
    """Batch operation response structure."""

    total_items: int
    successful: int
    failed: int
    results: List[Metadata]
    errors: Optional[List[Metadata]] = None


class SearchResponse(BaseModel, Generic[T]):
    """Search response structure."""

    results: List[T]
    total_matches: int
    query: str
    filters_applied: Optional[Metadata] = None
    search_time_ms: Optional[float] = None
    metrics: Optional[MetricsDict] = None


class ValidationErrorResponse(BaseModel):
    """Validation error response structure."""

    success: bool = False
    error: str = "Validation failed"
    validation_errors: List[Metadata]
    field_errors: Optional[Metadata] = None


class FileOperationResponse(BaseModel):
    """File operation response structure."""

    success: bool
    path: str
    operation: str  # read, write, delete, move, etc.
    size_bytes: Optional[int] = None
    content: Optional[str] = None
    metadata: Optional[Metadata] = None
    error: Optional[str] = None


class ProcessingResponse(BaseModel):
    """Processing/Analysis response structure."""

    success: bool
    processed_items: int
    processing_time_ms: float
    results: List[Metadata]
    metrics: Optional[MetricsDict] = None
    warnings: Optional[List[str]] = None


class ConfigResponse(BaseModel):
    """Configuration response structure."""

    config_name: str
    values: Metadata
    source: Optional[str] = None
    last_modified: Optional[TimestampStr] = None
    is_default: bool = False
