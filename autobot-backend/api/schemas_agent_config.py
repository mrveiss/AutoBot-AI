# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response models for the endpoints in ``api/agent_config.py``.

Split out of ``schemas_agent.py`` (GH #6509 Batch D), which sits on its file-size
ceiling; the five models moved here verbatim, plus ``tier`` on the specialized
detail response.  Importers use this module directly.
"""

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class AgentConfigListAgentsResponse(BaseModel):
    """Response for GET /agents."""

    agents: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    global_provider_type: str = ""
    timestamp: str = ""


class AgentConfigAllAgentsResponse(BaseModel):
    """Response for GET /agents/all."""

    agents: List[Dict[str, Any]] = Field(default_factory=list)
    specialized_agents: List[Dict[str, Any]] = Field(default_factory=list)
    specialized_available: bool = True
    summary: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""


class AgentConfigSpecializedListResponse(BaseModel):
    """Response for GET /agents/specialized."""

    agents: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    categories: Dict[str, Any] = Field(default_factory=dict)
    available: bool = True
    timestamp: str = ""


class AgentConfigSpecializedDetailResponse(BaseModel):
    """Response for GET /agents/specialized/{agent_id}."""

    id: str = ""
    name: str = ""
    description: str = ""
    tools: List[str] = Field(default_factory=list)
    model: str | None = None
    category: str | None = None
    tier: str | None = None


class AgentConfigUsageResponse(BaseModel):
    """Response for GET /agents/usage."""

    agents: List[Dict[str, Any]] = Field(default_factory=list)
    daily_trend: List[Dict[str, Any]] = Field(default_factory=list)
    total_tasks: int = 0
    timestamp: str = ""
