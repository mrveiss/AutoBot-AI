# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AI Stack integration Pydantic response schemas.

Typed data payloads for the endpoints in api/ai_stack_integration.py.
Where the external AI Stack service returns opaque JSON, models use
``model_config = {"extra": "allow"}`` so any fields are accepted while
still giving the OpenAPI schema a meaningful name.
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
# External AI Stack agent endpoints — structure opaque (from remote service)
# ---------------------------------------------------------------------------


class AIStackAgentPayload(BaseModel):
    """Generic payload returned by AI Stack agent endpoints.

    Accepts any fields from the external AI Stack service response.
    Used for: /rag/query, /rag/reformulate, /rag/analyze-documents,
    /chat/enhanced, /knowledge/extract, /knowledge/system,
    /research/web, /development/search-code, /development/analyze-speedup,
    /classification/classify, /legacy/rag-search, /legacy/enhanced-chat.
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
