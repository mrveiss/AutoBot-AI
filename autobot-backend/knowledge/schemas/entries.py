# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
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
