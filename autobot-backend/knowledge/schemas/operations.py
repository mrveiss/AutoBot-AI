# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for operational / admin knowledge-base endpoints.

Issue #5317 (follow-up to #5248): health, machine-profile, man-pages
integration, import tracking, and per-org model-config endpoints under
``/api/knowledge_base/*`` all returned plain dicts. Declaring them as
Pydantic models wires them into ``components.schemas`` in
``/openapi.json``.

``extra="allow"`` throughout — these responses carry diagnostic fields
that rotate (RAG status strings, per-implementation KB stats) and the
frontend already tolerates pass-through values.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeStatsResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/stats``.

    Two branches: (a) KB uninitialized — emits zero counts + status
    ``"offline"`` + a ``rag_available`` flag; (b) KB initialized — echoes
    ``kb.get_stats()`` output (freeform per-implementation diagnostics)
    plus ``rag_available``. Modelled with ``extra="allow"`` so neither
    branch's fields get stripped.
    """

    model_config = ConfigDict(extra="allow")

    status: str = Field("unknown", description="'online' | 'offline' | 'error' | 'unknown'")
    total_documents: int = 0
    total_chunks: int = 0
    total_facts: int = 0
    total_vectors: int = 0
    categories: List[str] = Field(default_factory=list)
    db_size: int = 0
    last_updated: str | None = None
    redis_db: Any | None = None
    index_name: str | None = None
    initialized: bool | None = None
    rag_available: bool = False
    vectorization_stats: Dict[str, Any] | None = None


class TestCategoriesResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/test_categories_main``.

    Debug probe: confirms the module is loaded and reports the built-in
    category taxonomy keys.
    """

    model_config = ConfigDict(extra="allow")

    status: str = "working"
    categories: List[str] = Field(default_factory=list)


class KnowledgeHealthResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/health``.

    Two branches: (a) KB uninitialized — ``status="unhealthy"``, all
    booleans False; (b) KB initialized — fills in per-implementation
    details plus RAG agent status.
    """

    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="'healthy' | 'unhealthy'")
    initialized: bool = False
    redis_connected: bool = False
    vector_store_available: bool = False
    rag_available: bool = False
    rag_status: str = "unknown"
    total_facts: int = 0
    db_size: int = 0
    kb_implementation: str | None = None
    message: str | None = None


class MachineProfileCapabilities(BaseModel):
    """Capability flags nested under :class:`MachineProfileResponse`."""

    model_config = ConfigDict(extra="allow")

    rag_available: bool = False
    vector_search: bool = False
    man_pages_available: bool = True
    system_knowledge: bool = True


class MachineProfileResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/machine_profile``.

    ``machine_profile`` and ``knowledge_base_stats`` are freeform —
    they echo ``platform`` + ``psutil`` output and ``kb.get_stats()``
    respectively.
    """

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    machine_profile: Dict[str, Any] = Field(default_factory=dict)
    knowledge_base_stats: Dict[str, Any] = Field(default_factory=dict)
    capabilities: MachineProfileCapabilities = Field(default_factory=MachineProfileCapabilities)


class ManPagesSummaryEnvelope(BaseModel):
    """Nested summary under :class:`ManPagesSummaryResponse`."""

    model_config = ConfigDict(extra="allow")

    total_man_pages: int = 0
    system_commands: int = 0
    indexed_count: int = 0
    last_indexed: str | None = None
    integration_active: bool = False


class ManPagesSummaryResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/man_pages/summary``."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="'success' | 'error'")
    message: str | None = None
    man_pages_summary: ManPagesSummaryEnvelope = Field(default_factory=ManPagesSummaryEnvelope)


class MachineKnowledgeInitComponents(BaseModel):
    """Per-component counts nested under :class:`MachineKnowledgeInitResponse`."""

    model_config = ConfigDict(extra="allow")

    system_commands: int = 0
    # ``man_pages`` is a string marker ("background_task") — not a count.
    man_pages: str | None = None


class MachineKnowledgeInitResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/machine_knowledge/initialize``."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="'success' | 'error'")
    message: str = ""
    items_added: int = 0
    components: MachineKnowledgeInitComponents | None = None


class ManPagesIntegrateResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/man_pages/integrate``.

    ``integration_started`` is False on the KB-uninit branch, True when
    a background task has been enqueued.
    """

    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="'success' | 'error'")
    message: str = ""
    integration_started: bool = False
    background: bool | None = None


class ImportStatusResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/import/status``.

    ``imports`` is a freeform list of per-import tracker rows — schema
    owned by :mod:`models.knowledge_import_tracking`.
    """

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    imports: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class ImportStatisticsResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/import/statistics``."""

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    statistics: Dict[str, Any] = Field(default_factory=dict)


class OrgKnowledgeConfigResponse(BaseModel):
    """Shape of ``GET`` and ``PUT`` ``/api/knowledge_base/org-config`` (#4451).

    ``stored`` may be ``None`` on GET when the org has never set a
    preference; ``effective`` is always populated (SSOT fallback).
    """

    model_config = ConfigDict(extra="allow")

    org_id: str = "__default__"
    stored: Dict[str, Any] | None = None
    effective: Dict[str, Any] = Field(default_factory=dict)
