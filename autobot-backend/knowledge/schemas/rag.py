# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for RAG endpoints (Issue #5317 batch 3c)."""

from __future__ import annotations

from typing import Any, Dict, List

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
    context: str | None = None
    context_length: int | None = None


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
    source: str | None = None


class UpdateRagConfigResponse(BaseModel):
    """Shape returned by PUT /config/rag."""

    model_config = ConfigDict(extra="allow")

    message: str = ""
    updated_fields: List[str] | None = None
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
    stream_key: str | None = None
    split_used: str | None = None
    dev_size: int | None = None
    test_size: int | None = None
    tuned_on_dev: bool | None = None
    held_out_score: bool | None = None
    mean_precision_at_k: float | None = None
    reason: str | None = None


class EntityHistoryResponse(BaseModel):
    """Shape returned by GET /entity/{entity_id}/history."""

    model_config = ConfigDict(extra="allow")

    entity_id: str = ""
    versions: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class AdvancedSearchRequest(BaseModel):
    """Request body for POST /rag/advanced_search."""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    max_results: int = Field(default=5, ge=1, le=50, description="Maximum results")
    enable_reranking: bool = Field(default=True, description="Enable cross-encoder reranking")
    return_context: bool = Field(default=False, description="Return optimized context for RAG")
    timeout: float | None = Field(default=None, description="Optional timeout in seconds")


class RerankRequest(BaseModel):
    """Request body for POST /rag/rerank."""

    query: str = Field(..., min_length=1, max_length=1000, description="Original search query")
    results: List[Dict[str, Any]] = Field(..., description="Search results to rerank")


class RAGConfigUpdate(BaseModel):
    """Request body for PUT /rag/config."""

    hybrid_weight_semantic: float | None = Field(default=None, ge=0.0, le=1.0)
    hybrid_weight_keyword: float | None = Field(default=None, ge=0.0, le=1.0)
    enable_reranking: bool | None = Field(default=None)
    diversity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    max_results_per_stage: int | None = Field(default=None, ge=1, le=100)


class RunBenchmarkRequest(BaseModel):
    """Request body for POST /rag/benchmark/run (#5074)."""

    split: str = Field(
        ...,
        description="Which portion to benchmark: 'dev', 'test', or 'all'.",
        pattern="^(dev|test|all)$",
    )
    k: int = Field(default=5, ge=1, le=50, description="Top-k results per query.")
