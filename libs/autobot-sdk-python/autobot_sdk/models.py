# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Typed Pydantic models matching the AutoBot REST API response shapes."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Generic envelope
# ---------------------------------------------------------------------------


class DataResponse(BaseModel, Generic[T]):
    """Mirrors the server-side DataResponse envelope from schemas_common.py."""

    success: bool = True
    data: T | None = None
    message: str | None = None
    timestamp: str | None = None


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: str | None = None


class Session(BaseModel):
    session_id: str
    title: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    message_count: int | None = None
    metadata: dict[str, Any] | None = None


class SessionList(BaseModel):
    sessions: list[Session] = []
    total: int | None = None


class SessionMessages(BaseModel):
    session_id: str
    messages: list[ChatMessage] = []
    total: int | None = None


class SessionCreate(BaseModel):
    session_id: str
    title: str | None = None


class SessionUpdate(BaseModel):
    session_id: str
    success: bool = True


class SessionDelete(BaseModel):
    session_id: str
    success: bool = True


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


class AgentHealth(BaseModel):
    status: str
    version: str | None = None
    uptime: float | None = None
    components: dict[str, Any] | None = None


class AgentConfigHealthCheck(BaseModel):
    """Inline ``health_check`` block of /api/agent_config/agents/{id}.

    Mirrors ``AgentConfigDetailHealthCheck`` in
    ``autobot-backend/api/schemas_agent.py``. It carries ``status`` and
    ``response_time``, which are the only liveness signal on that route, so
    modelling it as an untyped dict cost a consumer every hint about what is
    in there (#15072).
    """

    last_check: str | None = None
    response_time: float | None = None
    status: str | None = None


class AgentConfigOptions(BaseModel):
    """Inline ``configuration_options`` block of /api/agent_config/agents/{id}.

    Mirrors ``AgentConfigDetailOptions`` in
    ``autobot-backend/api/schemas_agent.py`` (#15072).
    """

    available_models: list[str] | None = None
    available_providers: list[str] | None = None
    configurable_settings: list[str] | None = None


class AgentConfig(BaseModel):
    """One agent's configuration, as served flat by /api/agent_config/agents/{id}.

    Not wrapped in a DataResponse envelope — that route returns the document
    itself (#15053).

    Every field the route emits is carried here. Pydantic's default
    ``extra='ignore'`` means a key this model does not declare is dropped in
    silence -- no error, no ``None``, nothing for a consumer to inspect -- so a
    field missing here is indistinguishable from a field the backend never sent
    (#15072). ``repo_tests/sdk_response_model_contract_test.py`` fails when the
    two field sets drift again.

    Every field stays optional so an older backend that omits one does not break
    SDK consumers.
    """

    id: str | None = None
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None
    current_model: str | None = None
    default_model: str | None = None
    provider: str | None = None
    priority: int | None = None
    status: str | None = None
    tasks: list[str] | None = None
    mcp_tools: list[str] | None = None
    config_source: str | None = None
    configuration_options: AgentConfigOptions | None = None
    health_check: AgentConfigHealthCheck | None = None


# ---------------------------------------------------------------------------
# Knowledge
# ---------------------------------------------------------------------------


class KnowledgeEntry(BaseModel):
    id: str | None = None
    content: str | None = None
    source: str | None = None
    category: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] | None = None


class KnowledgeStats(BaseModel):
    total_entries: int | None = None
    categories: dict[str, int] | None = None
    last_updated: str | None = None


class KnowledgeAddResult(BaseModel):
    success: bool = True
    id: str | None = None
    message: str | None = None


class KnowledgeSearchResult(BaseModel):
    results: list[KnowledgeEntry] = []
    total: int | None = None
    query: str | None = None


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class AnalyticsUsage(BaseModel):
    total_requests: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    period: str | None = None


class AnalyticsPerformance(BaseModel):
    avg_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    error_rate: float | None = None
    period: str | None = None
