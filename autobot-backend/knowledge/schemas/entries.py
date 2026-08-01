# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Stored knowledge entry schemas.

Covers response shapes for endpoints that retrieve existing knowledge
base entries: ``GET /entries``, ``GET /facts/by_category``, and
``GET /fact/{key}``.

Split from ``facts.py`` per Issue #5486.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeEntry(BaseModel):
    """Single row inside ``KnowledgeEntriesResponse.entries``."""

    model_config = ConfigDict(extra="allow")

    key: str
    title: str = "Untitled"
    content: str = ""
    category: str = ""
    type: str = "unknown"
    created_at: str | None = None
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
    message: str | None = None
    error: str | None = None


class FactByCategoryEntry(BaseModel):
    """Single fact row nested under ``FactsByCategoryResponse.categories[cat]``."""

    model_config = ConfigDict(extra="allow")

    key: str
    title: str = "Untitled"
    content: str = Field("", description="Truncated to 500 chars + ellipsis")
    # Issue #12370: full_content intentionally omitted from the browse list —
    # the entire document is lazy-loaded per fact via GET /fact/{fact_key}.
    category: str = ""
    type: str = "unknown"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class FactsByCategoryResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/facts/by_category``.

    Grouped facts keyed by category name. ``category_filter`` echoes the
    optional ``?category=`` query param for client-side confirmation.

    Issue #12394: ``limit``/``offset`` are applied per category (each
    category's fact index is paginated independently). ``total_facts`` is
    the count actually returned in this page (sum across categories);
    ``total_count`` is the true sum across all matching categories,
    independent of pagination. ``has_more`` is True when at least one
    category has additional facts beyond this page.
    """

    model_config = ConfigDict(extra="allow")

    categories: Dict[str, List[FactByCategoryEntry]] = Field(default_factory=dict)
    total_facts: int = 0
    total_count: int = 0
    limit: int = 0
    offset: int = 0
    has_more: bool = False
    category_filter: str | None = None
    # Error branch returns this + empty categories/total_facts.
    error: str | None = None


class FactByKeyResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/fact/{fact_key}``."""

    model_config = ConfigDict(extra="allow")

    key: str
    content: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = ""
