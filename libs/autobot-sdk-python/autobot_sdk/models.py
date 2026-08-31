# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Typed Pydantic models matching the AutoBot REST API response shapes."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict

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
    """One row inside ``SessionMessagesData.messages``.

    The backend declares that list as ``List[Any]``, so nothing on the server
    side describes a row; these names are the literal keys
    ``chat_history/messages.py`` writes. The previous model required ``role``
    and ``content``, which that literal has never contained -- so
    ``sessions.get()`` raised ``ValidationError`` on any session holding at
    least one message (#15114 is the same failure on create/update).

    Every field is optional and ``extra="allow"`` keeps a key this model does
    not name, because the route has no declared contract to hold it to.
    """

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    sender: str | None = None
    text: str | None = None
    messageType: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: str | None = None
    sources: list[dict[str, Any]] | None = None
    toolMarkers: list[Any] | None = None
    authorId: str | None = None


class Session(BaseModel):
    """One row inside ``SessionListData.sessions``.

    As with :class:`ChatMessage`, the backend types the list ``List[Any]`` and
    these names are the literal keys ``chat_history/session_listing.py`` writes.
    ``session_id`` was required here and is emitted by nothing, so
    ``sessions.list()`` raised on every response carrying a session (#15114).
    """

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    chatId: str | None = None
    title: str | None = None
    name: str | None = None
    messages: list[ChatMessage] | None = None
    messageCount: int | None = None
    createdAt: str | None = None
    createdTime: str | None = None
    updatedAt: str | None = None
    lastModified: str | None = None
    updatedAtEpoch: float | None = None
    isActive: bool | None = None
    fileSize: int | None = None
    fast_mode: bool | None = None
    companyId: str | None = None
    sessionKind: str | None = None


class SessionList(BaseModel):
    """``data`` payload of ``GET /chat/sessions``; mirrors ``SessionListData``.

    The row count is ``count``. It was named ``total`` here, which the route
    emits under no circumstances, so the attribute existed and was permanently
    ``None`` (#15118).
    """

    sessions: list[Session] = []
    count: int | None = None
    scope: str | None = None
    org_id: str | None = None
    team_id: str | None = None
    intentional_empty: bool | None = None


class SessionMessages(BaseModel):
    """``data`` payload of ``GET /chat/sessions/{id}``; mirrors ``SessionMessagesData``.

    The count is ``total_count``, not ``total`` (#15118).
    """

    messages: list[ChatMessage] = []
    session_id: str | None = None
    total_count: int | None = None
    page: int | None = None
    per_page: int | None = None


class SessionCreate(BaseModel):
    """``data`` payload of ``POST /chat/sessions``; mirrors ``SessionCreateData``.

    The new session's identifier is ``id``. Declaring it as a **required**
    ``session_id`` meant pydantic could satisfy neither ``SessionCreate`` nor
    the envelope's ``None``, so every successful create raised (#15114).
    """

    id: str | None = None
    title: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
    last_modified: str | None = None


class SessionUpdate(BaseModel):
    """``data`` payload of ``PUT /chat/sessions/{id}``; mirrors ``SessionUpdateData``.

    ``success`` used to live here as well. It duplicated the envelope's own flag,
    appeared in the payload never, and defaulted to ``True`` -- so it reported
    success no matter what happened (#15114).
    """

    id: str | None = None
    title: str | None = None
    metadata: dict[str, Any] | None = None
    created_at: str | None = None
    last_modified: str | None = None


class SessionDeleteFileHandling(BaseModel):
    """Inline ``file_handling`` block; mirrors ``FileHandlingResult``."""

    files_handled: bool | None = None
    action_taken: str | None = None
    files_deleted: int | None = None
    files_transferred: int | None = None
    files_failed: int | None = None
    error: str | None = None


class SessionDeleteTerminalCleanup(BaseModel):
    """Inline ``terminal_cleanup`` block; mirrors ``TerminalCleanupResult``."""

    terminal_sessions_closed: int | None = None
    pending_approvals_cleared: int | None = None
    error: str | None = None


class SessionDeleteKbCleanup(BaseModel):
    """Inline ``kb_cleanup`` block; mirrors ``KbCleanupResult``."""

    facts_deleted: int | None = None
    facts_preserved: int | None = None
    cleanup_error: str | None = None


class SessionDeleteTranscriptCleanup(BaseModel):
    """Inline ``transcript_cleanup`` block; mirrors ``TranscriptCleanupResult``."""

    transcript_deleted: bool | None = None
    error: str | None = None


class SessionDelete(BaseModel):
    """``data`` payload of ``DELETE /chat/sessions/{id}``; mirrors ``SessionDeleteData``.

    The outcome flag is ``deleted``. The model declared ``success: bool = True``
    instead -- a name the payload does not carry -- so a **failed** delete read
    as ``success is True`` (#15118).
    """

    session_id: str | None = None
    deleted: bool | None = None
    file_handling: SessionDeleteFileHandling | None = None
    terminal_cleanup: SessionDeleteTerminalCleanup | None = None
    kb_cleanup: SessionDeleteKbCleanup | None = None
    transcript_cleanup: SessionDeleteTranscriptCleanup | None = None


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


class AgentHealth(BaseModel):
    """``GET /agent/health/detailed``; mirrors ``AgentHealthResponse``.

    This model shared exactly one field name with the route it parses.
    ``version``, ``uptime`` and ``components`` are emitted by nothing, so they
    read as "the server did not send it" forever, while the five flags the
    route does send were discarded by pydantic's default ``extra="ignore"``
    (#15118).
    """

    status: str | None = None
    ai_stack_available: bool | None = None
    multi_agent_coordination: bool | None = None
    advanced_capabilities: bool | None = None
    timestamp: str | None = None
    error: str | None = None


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
    """One row inside ``KnowledgeEntries.entries``; mirrors the backend's
    ``knowledge.schemas.entries.KnowledgeEntry``.

    The SDK named this ``id``/``source``; the route emits ``key``/``title``/
    ``type`` and has never emitted either of those two (#15118).
    """

    model_config = ConfigDict(extra="allow")

    key: str | None = None
    title: str | None = None
    content: str | None = None
    category: str | None = None
    type: str | None = None
    created_at: str | None = None
    metadata: dict[str, Any] | None = None


class KnowledgeEntries(BaseModel):
    """``GET /knowledge_base/entries``; mirrors ``KnowledgeEntriesResponse``.

    A distinct model from :class:`KnowledgeSearchResult`, which the SDK used
    for both routes even though the two response bodies share no field at all.
    ``next_cursor`` is the pagination token the route actually issues; without
    it on the model a caller could not page (#15119).
    """

    model_config = ConfigDict(extra="allow")

    entries: list[KnowledgeEntry] = []
    next_cursor: str | None = None
    count: int | None = None
    has_more: bool | None = None
    message: str | None = None
    error: str | None = None


class KnowledgeStats(BaseModel):
    """``GET /knowledge_base/stats``; mirrors ``KnowledgeStatsResponse``.

    ``total_entries`` was emitted by nothing -- the route counts documents,
    chunks, facts and vectors separately -- and ``categories`` is a list of
    names, not a name-to-count mapping (#15118).
    """

    model_config = ConfigDict(extra="allow")

    status: str | None = None
    total_documents: int | None = None
    total_chunks: int | None = None
    total_facts: int | None = None
    total_vectors: int | None = None
    categories: list[str] | None = None
    db_size: int | None = None
    last_updated: str | None = None
    redis_db: Any | None = None
    index_name: str | None = None
    initialized: bool | None = None
    rag_available: bool | None = None
    vectorization_stats: dict[str, Any] | None = None


class KnowledgeAddResult(BaseModel):
    """``POST /knowledge_base/add_text``; mirrors ``AddTextResponse``.

    The new fact's identifier is ``fact_id``; ``id`` was never emitted, and
    ``success`` duplicated a flag that route does not send either -- the
    outcome is in ``status`` (#15118).
    """

    model_config = ConfigDict(extra="allow")

    status: str | None = None
    message: str | None = None
    fact_id: str | None = None
    text_length: int | None = None
    title: str | None = None
    source: str | None = None
    access_level: str | None = None
    visibility: str | None = None


class KnowledgeSearchResult(BaseModel):
    """``POST /knowledge_base/search``; mirrors ``KnowledgeSearchResponse``.

    The result count is ``total_results``. ``results`` rows are freeform on
    this route -- the backend declares ``List[Dict[str, Any]]`` -- so they are
    typed as the route types them rather than as :class:`KnowledgeEntry`,
    which describes a *different* route's rows (#15118).
    """

    model_config = ConfigDict(extra="allow")

    results: list[dict[str, Any]] = []
    total_results: int | None = None
    query: str | None = None
    mode: str | None = None
    kb_implementation: str | None = None
    rag_applied: bool | None = None
    reranking_applied: bool | None = None
    status: str | None = None
    synthesized_response: str | None = None
    original_query: str | None = None
    reformulated_queries: list[str] | None = None
    message: str | None = None


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


class AnalyticsUsage(BaseModel):
    """``GET /analytics/usage/statistics``; mirrors ``AnalyticsUsageStatisticsResponse``.

    ``total_requests``, ``total_tokens``, ``cost_usd`` and ``period`` were all
    invented: the route groups its numbers into per-subject blocks and has
    never emitted any of those four names (#15118). ``period`` was also sent as
    a query parameter the route does not accept (#15119).
    """

    model_config = ConfigDict(extra="allow")

    api_usage: dict[str, Any] | None = None
    websocket_usage: dict[str, Any] | None = None
    system_usage: dict[str, Any] | None = None
    knowledge_base_usage: dict[str, Any] | None = None
    analysis_period: dict[str, Any] | None = None
    error: str | None = None


class AnalyticsPerformance(BaseModel):
    """``GET /analytics/performance/metrics``; mirrors ``AnalyticsPerformanceMetricsResponse``.

    Same story as :class:`AnalyticsUsage`: ``avg_latency_ms``, ``p95_latency_ms``,
    ``error_rate`` and ``period`` are emitted by nothing (#15118).
    """

    model_config = ConfigDict(extra="allow")

    system_performance: dict[str, Any] | None = None
    api_performance: dict[str, Any] | None = None
    advanced_metrics: dict[str, Any] | None = None
    detailed_metrics: dict[str, Any] | None = None
    hardware_performance: dict[str, Any] | None = None
    network_io: dict[str, Any] | None = None
    historical_context: dict[str, Any] | None = None
    error: str | None = None
