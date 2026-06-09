# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Query and search response schemas for the knowledge base.

Covers ``POST /api/knowledge_base/query`` and
``GET /api/knowledge_base/man_pages/search``.

Split from ``facts.py`` per Issue #5486.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class QueryKnowledgeResponse(BaseModel):
    """Shape of legacy ``POST /api/knowledge_base/query``.

    Proxies to :mod:`api.knowledge_search`. Fields mirror the shape returned
    by ``_build_search_response`` in that module.
    """

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    synthesized_response: str = ""
    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0
    original_query: str | None = None
    reformulated_queries: List[str] = Field(default_factory=list)
    rag_enhanced: bool = False


class ManPageSearchResponse(BaseModel):
    """Shape of ``GET /api/knowledge_base/man_pages/search``."""

    model_config = ConfigDict(extra="allow")

    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0
    query: str | None = None
    limit: int | None = None
