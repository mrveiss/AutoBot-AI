# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for knowledge-base stats + categories endpoints.

Issue #5248 (found during #5207 audit, follow-up to #5215): the stats and
category endpoints under ``/api/knowledge_base/*`` used to return plain
dicts, which FastAPI cannot emit as OpenAPI component schemas. That left
the frontend hand-writing TypeScript interfaces for ``KnowledgeStats`` /
``DetailedKnowledgeStats`` / ``KnowledgeCategoryEntry`` (see
``autobot-frontend/src/models/repositories/KnowledgeRepository.ts``),
which drifts silently from the backend.

Declaring these as Pydantic ``BaseModel`` subclasses and passing them as
``response_model=`` on the routes makes them appear under
``components.schemas`` in ``/openapi.json`` so the frontend's
``npm run gen:types`` step (#5209) picks them up and eliminates the
hand-written duplicates.

Every model uses ``model_config = ConfigDict(extra="allow")`` because the
backend stat dicts carry diagnostic keys (``embedding_cache``,
``chromadb_path``, driver-specific counters, etc.) that rotate between
releases. Strict schemas would silently strip those and break existing
UI renderers.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeStatsBasic(BaseModel):
    """Shape of ``GET /api/knowledge_base/stats/basic``.

    The backend trims ``kb.get_stats()`` down to these four lightweight
    fields; additional fields are accepted via ``extra="allow"`` for
    forward-compat but aren't part of the declared contract.
    """

    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="'online' | 'offline' | 'error' | 'unknown'")
    total_facts: int = Field(0, description="Total facts in the knowledge base")
    total_vectors: int = Field(0, description="Total vectors in the index")
    categories: List[str] = Field(
        default_factory=list,
        description="Bare list of category names (not counts — see /categories)",
    )


class KnowledgeBasicStatsEnvelope(BaseModel):
    """Full ``kb.get_stats()`` envelope nested under ``DetailedKnowledgeStats.basic_stats``.

    Unlike ``KnowledgeStatsBasic`` (the /stats/basic projection), this
    carries the complete set of diagnostic fields returned by
    ``KnowledgeBase.get_stats()`` — used only inside the /detailed_stats
    response, never as a standalone endpoint.
    """

    model_config = ConfigDict(extra="allow")

    total_documents: int = 0
    total_chunks: int = 0
    total_facts: int = 0
    total_vectors: int = 0
    categories: List[str] = Field(default_factory=list)
    db_size: int = 0
    status: str = "unknown"
    last_updated: str | None = None
    redis_db: Any | None = None
    vector_store: str | None = None
    chromadb_collection: str | None = None
    initialized: bool | None = None
    llama_index_configured: bool | None = None
    embedding_model: str | None = None
    embedding_dimensions: int | None = None
    index_available: bool | None = None
    indexed_documents: int | None = None
    chromadb_path: str | None = None
    embedding_cache: Dict[str, Any] | None = None


class DetailedKnowledgeSizeMetrics(BaseModel):
    """Size-breakdown block inside ``DetailedKnowledgeStats``."""

    model_config = ConfigDict(extra="allow")

    total_content_size: int = 0
    average_fact_size: float = 0
    median_fact_size: int = 0
    largest_fact_size: int = 0
    smallest_fact_size: int = 0


class DetailedKnowledgeStats(BaseModel):
    """Shape of ``GET /api/knowledge_base/detailed_stats``."""

    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="'online' | 'offline' | 'error' | 'unknown'")
    # When kb is offline, backend returns `{"basic_stats": {}}`; we model
    # the field as a full envelope rather than `{} | envelope` because
    # the offline dict is a subset of the populated envelope.
    basic_stats: KnowledgeBasicStatsEnvelope = Field(default_factory=KnowledgeBasicStatsEnvelope)
    category_breakdown: Dict[str, int] = Field(default_factory=dict)
    source_breakdown: Dict[str, int] = Field(default_factory=dict)
    type_breakdown: Dict[str, int] = Field(default_factory=dict)
    size_metrics: DetailedKnowledgeSizeMetrics = Field(default_factory=DetailedKnowledgeSizeMetrics)
    rag_available: bool = False
    # Offline branch adds this; populated branch omits it.
    message: str | None = None


class KnowledgeCategoryEntry(BaseModel):
    """Single row returned by ``GET /api/knowledge_base/categories``."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    count: int = 0


class KnowledgeCategoriesResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/categories``."""

    model_config = ConfigDict(extra="allow")

    categories: List[KnowledgeCategoryEntry] = Field(default_factory=list)
    total: int = 0


class KnowledgeMainCategoryEntry(BaseModel):
    """Row returned by ``GET /api/knowledge_base/categories/main``.

    Differs from :class:`KnowledgeCategoryEntry` by carrying UI-display
    metadata (icon, color, description, examples) sourced from
    ``knowledge_categories.CATEGORY_METADATA``.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    description: str = ""
    icon: str = ""
    color: str = ""
    examples: List[str] = Field(default_factory=list)
    count: int = 0


class KnowledgeMainCategoriesResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/categories/main``.

    ``kb_connected`` (issue #5201) lets the UI distinguish an empty knowledge
    base (counts == 0 because nothing has been indexed yet) from an
    unreachable knowledge base (Redis unavailable) — both otherwise return
    all-zero counts.
    """

    model_config = ConfigDict(extra="allow")

    categories: List[KnowledgeMainCategoryEntry] = Field(default_factory=list)
    total: int = 0
    kb_connected: bool = True
