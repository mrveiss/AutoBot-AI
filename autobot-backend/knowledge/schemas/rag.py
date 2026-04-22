# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for RAG endpoints (Issue #5317 batch 3c)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AdvancedSearchResponse(BaseModel):
    """Shape returned by POST /advanced_search.

    Core keys: results, total_results, query, metrics, reranking_enabled.
    Optional context/context_length when return_context=True.
    """

    model_config = ConfigDict(extra="allow")

    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0
    query: str = ""
    metrics: Dict[str, Any] = Field(default_factory=dict)
    reranking_enabled: bool = True
    context: Optional[str] = None
    context_length: Optional[int] = None


class RerankResultsResponse(BaseModel):
    """Shape returned by POST /rerank_results."""

    model_config = ConfigDict(extra="allow")

    reranked_results: List[Any] = Field(default_factory=list)
    original_count: int = 0
    query: str = ""
    reranking_applied: bool = True


class RagConfigResponse(BaseModel):
    """Shape returned by GET /config/rag and as the config sub-object in PUT responses."""

    model_config = ConfigDict(extra="allow")

    config: Dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None


class UpdateRagConfigResponse(BaseModel):
    """Shape returned by PUT /config/rag."""

    model_config = ConfigDict(extra="allow")

    message: str = ""
    updated_fields: Optional[List[str]] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class LoopStatusResponse(BaseModel):
    """Shape returned by GET /loop/status."""

    model_config = ConfigDict(extra="allow")

    loop_status: Dict[str, Any] = Field(default_factory=dict)
    current_config: Dict[str, Any] = Field(default_factory=dict)


class LoopApproveResponse(BaseModel):
    """Shape returned by POST /loop/approve."""

    model_config = ConfigDict(extra="allow")

    message: str = ""
    config: Dict[str, Any] = Field(default_factory=dict)


class LoopRejectResponse(BaseModel):
    """Shape returned by POST /loop/reject."""

    model_config = ConfigDict(extra="allow")

    message: str = ""


class RagStatsResponse(BaseModel):
    """Shape returned by GET /stats/rag."""

    model_config = ConfigDict(extra="allow")

    stats: Dict[str, Any] = Field(default_factory=dict)
    service_available: bool = True


class BenchmarkRunResponse(BaseModel):
    """Shape returned by POST /benchmark/run.

    When Redis is unavailable, reason="redis_unavailable" and stream_key=None.
    """

    model_config = ConfigDict(extra="allow")

    published: int = 0
    total: int = 0
    stream_key: Optional[str] = None
    split_used: Optional[str] = None
    dev_size: Optional[int] = None
    test_size: Optional[int] = None
    tuned_on_dev: Optional[bool] = None
    held_out_score: Optional[bool] = None
    mean_precision_at_k: Optional[float] = None
    reason: Optional[str] = None


class EntityHistoryResponse(BaseModel):
    """Shape returned by GET /entity/{entity_id}/history."""

    model_config = ConfigDict(extra="allow")

    entity_id: str = ""
    versions: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0
