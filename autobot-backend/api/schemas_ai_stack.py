# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
AI Stack integration Pydantic response schemas.

Typed data payloads for the endpoints in api/ai_stack_integration.py.
Where the external AI Stack service returns opaque JSON, models use
``model_config = {"extra": "allow"}`` so any fields are accepted while
still giving the OpenAPI schema a meaningful name.

Issue #6387: replaced the single AIStackAgentPayload catch-all with
per-endpoint models so each endpoint gets a distinct OpenAPI schema.
AIStackAgentPayload is retained as the base class and for legacy endpoints.
"""

from typing import Any, Dict, List

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# /health — structure known from AIStackClient.health_check()
# ---------------------------------------------------------------------------


class AIStackHealthData(BaseModel):
    """Data payload for GET /ai-stack/health."""

    status: str  # "healthy" or "unhealthy"
    timestamp: str
    ai_stack_response: Dict[str, Any] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# /agents — structure known from AIStackClient.list_available_agents()
# ---------------------------------------------------------------------------


class AIStackAgentsData(BaseModel):
    """Data payload for GET /ai-stack/agents."""

    agents: List[str]
    total: int | None = None
    source: str | None = None  # "fallback_config" when stack unavailable


# ---------------------------------------------------------------------------
# External AI Stack agent endpoints — per-endpoint typed models (Issue #6387)
# All extend AIStackAgentPayload (extra='allow') to stay backward-compatible
# while exposing meaningful field names in the OpenAPI schema.
# ---------------------------------------------------------------------------


class AIStackAgentPayload(BaseModel):
    """Generic payload base for AI Stack agent endpoints.

    extra='allow' accepts any fields from the external AI Stack service.
    Concrete subclasses declare the expected fields for each endpoint group.
    """

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# multimodal.py response schemas (#6509c)
# ---------------------------------------------------------------------------


class MultimodalEmbeddingData(BaseModel):
    """data payload for POST /embeddings/generate."""

    model_config = {"extra": "allow"}


class MultimodalStatsData(BaseModel):
    """data payload for GET /stats."""

    model_config = {"extra": "allow"}


class MultimodalFusionData(BaseModel):
    """data payload for POST /combine."""

    model_config = {"extra": "allow"}


class MultimodalPerfStatsData(BaseModel):
    """data payload for GET /performance/stats."""

    model_config = {"extra": "allow"}


class MultimodalOptimizeData(BaseModel):
    """data payload for POST /performance/optimize."""

    model_config = {"extra": "allow"}


class MultimodalPerfSummaryData(BaseModel):
    """data payload for GET /performance/summary."""

    model_config = {"extra": "allow"}


class MultimodalBatchSizeData(BaseModel):
    """data payload for PUT /performance/batch-size."""

    model_config = {"extra": "allow"}


class RAGQueryResult(AIStackAgentPayload):
    """Data payload for POST /ai-stack/rag/query and /ai-stack/legacy/rag-search."""

    response: str | None = None
    documents: List[Any] | None = None
    sources: List[str] | None = None
    confidence: float | None = None
    query: str | None = None


class QueryReformulationResult(AIStackAgentPayload):
    """Data payload for POST /ai-stack/rag/reformulate."""

    reformulated_query: str | None = None
    original_query: str | None = None
    improvements: List[str] | None = None


class DocumentAnalysisResult(AIStackAgentPayload):
    """Data payload for POST /ai-stack/rag/analyze-documents."""

    analysis: str | None = None
    key_points: List[str] | None = None
    document_count: int | None = None
    synthesis: str | None = None


class EnhancedChatResult(AIStackAgentPayload):
    """Data payload for POST /ai-stack/chat/enhanced and /ai-stack/legacy/enhanced-chat."""

    message: str | None = None
    context_used: List[Any] | None = None
    knowledge_sources: List[str] | None = None
    reasoning: str | None = None


class KnowledgeExtractionResult(AIStackAgentPayload):
    """Data payload for POST /ai-stack/knowledge/extract."""

    extracted_facts: List[Any] | None = None
    entities: List[Any] | None = None
    relationships: List[Any] | None = None
    confidence: float | None = None


class SystemKnowledgeResult(AIStackAgentPayload):
    """Data payload for GET /ai-stack/knowledge/system."""

    system_facts: List[Any] | None = None
    categories: List[str] | None = None
    last_updated: str | None = None


class WebResearchResult(AIStackAgentPayload):
    """Data payload for POST /ai-stack/research/web."""

    findings: List[Any] | None = None
    sources: List[str] | None = None
    summary: str | None = None
    pages_analyzed: int | None = None


class CodeSearchResult(AIStackAgentPayload):
    """Data payload for POST /ai-stack/development/search-code."""

    matches: List[Any] | None = None
    total_results: int | None = None
    search_scope: str | None = None


class DevelopmentSpeedupResult(AIStackAgentPayload):
    """Data payload for POST /ai-stack/development/analyze-speedup."""

    recommendations: List[Any] | None = None
    speedup_opportunities: List[Any] | None = None
    analysis_type: str | None = None
    summary: str | None = None


class ClassificationResult(AIStackAgentPayload):
    """Data payload for POST /ai-stack/classification/classify."""

    classifications: List[Any] | None = None
    primary_category: str | None = None
    confidence: float | None = None
    scores: Dict[str, float] | None = None
