# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for knowledge-base fact lifecycle endpoints.

Issue #5317 (follow-up to #5248): the fact ingestion / query / delete
endpoints under ``/api/knowledge_base/*`` all returned plain dicts.
FastAPI therefore could not emit them as OpenAPI component schemas, so
the frontend keeps hand-writing ``KnowledgeFact`` / ``AddFactResponse``
etc. in ``autobot-frontend/src/models/repositories/KnowledgeRepository.ts``.

Declaring these as Pydantic ``BaseModel`` subclasses with
``response_model=`` wires them into ``components.schemas`` in
``/openapi.json`` so ``npm run gen:types`` picks them up.

Every model uses ``model_config = ConfigDict(extra="allow")`` because the
backend dicts carry diagnostic keys (fact IDs, per-fact metadata shapes,
error codes) that rotate between releases. Strict schemas would silently
strip those and break existing UI renderers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AddTextResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/add_text``.

    Legacy text-ingestion endpoint (newer frontend uses /facts — see
    :class:`AddFactResponse`). Returns the fact_id plus ownership
    metadata echo for audit visibility.
    """

    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="'success' on insert")
    message: str = ""
    fact_id: Optional[str] = None
    text_length: int = 0
    title: str = ""
    source: str = ""
    access_level: Optional[str] = None
    visibility: Optional[str] = None


class AddFactResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/facts`` (frontend-compatible).

    Returns a truncated content echo (first 100 chars) — callers that
    need the full content should re-fetch via ``GET /fact/{key}``.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    document_id: Optional[str] = None
    title: str = ""
    content: str = Field("", description="Truncated to first 100 chars + ellipsis")
    message: str = ""


class AddUrlResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/url``.

    Same envelope as :class:`AddFactResponse`; the content field carries
    the truncated fetched page text.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    document_id: Optional[str] = None
    title: str = ""
    content: str = ""
    message: str = ""


class UploadFileResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/upload``.

    Adds ``word_count`` over the base upload envelope.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    document_id: Optional[str] = None
    title: str = ""
    content: str = ""
    word_count: int = 0
    message: str = ""


class AudioIngestResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/audio`` and ``/audio/upload``.

    Returned by the shared ``_ingest_audio_source`` helper after Whisper
    transcription completes.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    document_id: Optional[str] = None
    title: str = ""
    word_count: int = 0
    message: str = ""


class KnowledgeEntry(BaseModel):
    """Single row inside ``KnowledgeEntriesResponse.entries``."""

    model_config = ConfigDict(extra="allow")

    key: str
    title: str = "Untitled"
    content: str = ""
    category: str = ""
    type: str = "unknown"
    created_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeEntriesResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/entries``.

    Cursor-paginated list. ``next_cursor`` is a stringified integer;
    ``has_more`` flips to False when the SCAN cursor wraps to 0.
    Error branches populate ``error`` instead of raising.
    """

    model_config = ConfigDict(extra="allow")

    entries: List[KnowledgeEntry] = Field(default_factory=list)
    next_cursor: str = "0"
    count: int = 0
    has_more: bool = False
    # Degraded-path fields: populated on error / KB-uninit, absent on success.
    message: Optional[str] = None
    error: Optional[str] = None


class FactByCategoryEntry(BaseModel):
    """Single fact row nested under ``FactsByCategoryResponse.categories[cat]``."""

    model_config = ConfigDict(extra="allow")

    key: str
    title: str = "Untitled"
    content: str = Field("", description="Truncated to 500 chars + ellipsis")
    full_content: str = ""
    category: str = ""
    type: str = "unknown"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FactsByCategoryResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/facts/by_category``.

    Grouped facts keyed by category name. ``category_filter`` echoes the
    optional ``?category=`` query param for client-side confirmation.
    """

    model_config = ConfigDict(extra="allow")

    categories: Dict[str, List[FactByCategoryEntry]] = Field(default_factory=dict)
    total_facts: int = 0
    category_filter: Optional[str] = None
    # Error branch returns this + empty categories/total_facts.
    error: Optional[str] = None


class FactByKeyResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/fact/{fact_key}``."""

    model_config = ConfigDict(extra="allow")

    key: str
    content: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""


class ClearAllResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/clear_all``.

    DESTRUCTIVE operation. ``items_removed`` counts fact rows, not
    vectors — vector store is cleared as part of ``kb.clear_all()``.
    """

    model_config = ConfigDict(extra="allow")

    status: str = Field(..., description="'success' | 'error'")
    items_removed: int = 0
    items_before: int = 0
    message: str = ""


class QueryKnowledgeResponse(BaseModel):
    """Shape of legacy ``POST /api/knowledge_base/query``.

    Proxies to :mod:`api.knowledge_search`. The exact payload mirrors
    whatever ``search_knowledge`` returns — declared with ``extra="allow"``
    so search-side additions flow through.
    """

    model_config = ConfigDict(extra="allow")

    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0
    query: Optional[str] = None


class ManPageSearchResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/man_pages/search``."""

    model_config = ConfigDict(extra="allow")

    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0
    query: Optional[str] = None
    limit: Optional[int] = None
