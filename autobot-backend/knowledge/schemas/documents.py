# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for documentation browser endpoints (Issue #165 surface).

Issue #5317 (follow-up to #5248): the ``/api/knowledge_base/docs/*``
endpoints power the frontend's documentation browser (filter, paginate,
stats, watcher). They returned plain dicts, so their schemas weren't
emitted in ``/openapi.json`` and the Vue views hand-wrote duplicates.

``extra="allow"`` is used throughout because the doc-index pipeline
(``scripts/utilities/index_documentation.py``) writes freeform metadata
into each ``doc_hash:*`` entry — we don't want to strip diagnostic
fields from API output.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class DocsPagination(BaseModel):
    """Pagination envelope nested under :class:`DocsBrowseResponse`."""

    model_config = ConfigDict(extra="allow")

    page: int = 1
    page_size: int = 20
    total_documents: int = 0
    total_pages: int = 1


class DocsFiltersApplied(BaseModel):
    """Echoes the filter inputs back so the UI can render chips.

    Every field is optional because the endpoint accepts any subset.
    """

    model_config = ConfigDict(extra="allow")

    category: str | None = None
    doc_type: str | None = None
    file_path_pattern: str | None = None
    search_query: str | None = None


class DocsBrowseResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/docs/browse``.

    ``documents`` is a list of doc-hash metadata entries; their schema is
    freeform by design (indexer adds new fields over time), so we leave
    it as ``List[Dict]`` rather than modelling each entry.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    pagination: DocsPagination = Field(default_factory=DocsPagination)
    filters_applied: DocsFiltersApplied = Field(default_factory=DocsFiltersApplied)


class DocsCategoryEntry(BaseModel):
    """Single row in :class:`DocsCategoriesResponse.categories`."""

    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    description: str = ""
    count: int = 0


class DocsCategoriesResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/docs/categories``.

    Sorted descending by ``count``; metadata comes from
    ``scripts.utilities.index_documentation.CATEGORY_TAXONOMY``.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    categories: List[DocsCategoryEntry] = Field(default_factory=list)
    total_documents: int = 0


class DocsStatsEnvelope(BaseModel):
    """Nested stats envelope under :class:`DocsStatsResponse.stats`."""

    model_config = ConfigDict(extra="allow")

    total_documents: int = 0
    total_indexed_entries: int = 0
    total_chunks: int = 0
    latest_indexed: str | None = None
    categories_count: int = 0


class DocsStatsResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/docs/stats``."""

    model_config = ConfigDict(extra="allow")

    success: bool = True
    stats: DocsStatsEnvelope = Field(default_factory=DocsStatsEnvelope)


class DocsWatcherStatusResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/docs/watcher/status`` and the
    status branch of ``POST /api/knowledge_base/docs/watcher/control``.

    ``watcher`` carries the freeform stats dict returned by
    ``DocumentationWatcher.get_stats()`` — schema evolves with the
    watcher implementation.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    watcher: Dict[str, Any] = Field(default_factory=dict)


class DocsWatcherControlResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/docs/watcher/control``.

    The control endpoint has three shapes depending on ``action``:
    ``start``/``stop`` return ``{success, message}``; ``status`` returns
    :class:`DocsWatcherStatusResponse` (``{success, watcher}``). Unknown
    actions and ImportError both return ``{success, message}``. This
    model unions all of them via optional fields.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = False
    message: str | None = None
    watcher: Dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# KB Folder Watcher schemas (GH#9000)
# ---------------------------------------------------------------------------


class KBFolderWatcherStatusResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/folder-watcher/status``."""

    model_config = ConfigDict(extra="allow")

    success: bool = True
    watcher: Dict[str, Any] = Field(default_factory=dict)


class KBFolderWatcherControlResponse(BaseModel):
    """Shape of ``POST /api/knowledge_base/folder-watcher/control``."""

    model_config = ConfigDict(extra="allow")

    success: bool = False
    message: str | None = None
    watcher: Dict[str, Any] | None = None


class KBFolderWatcherAddPathRequest(BaseModel):
    """Request body for ``POST /api/knowledge_base/folder-watcher/paths``."""

    path: str


class KBFolderWatcherRemovePathRequest(BaseModel):
    """Request body for ``DELETE /api/knowledge_base/folder-watcher/paths``."""

    path: str


class KBFolderWatcherPathResponse(BaseModel):
    """Response for add/remove path operations."""

    model_config = ConfigDict(extra="allow")

    success: bool
    message: str
    watch_paths: List[str] = Field(default_factory=list)
