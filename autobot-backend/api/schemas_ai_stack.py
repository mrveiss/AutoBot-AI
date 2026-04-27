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

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# /health — structure known from AIStackClient.health_check()
# ---------------------------------------------------------------------------


class AIStackHealthData(BaseModel):
    """Data payload for GET /ai-stack/health."""

    status: str  # "healthy" or "unhealthy"
    timestamp: str
    ai_stack_response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# /agents — structure known from AIStackClient.list_available_agents()
# ---------------------------------------------------------------------------


class AIStackAgentsData(BaseModel):
    """Data payload for GET /ai-stack/agents."""

    agents: List[str]
    total: Optional[int] = None
    source: Optional[str] = None  # "fallback_config" when stack unavailable


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
