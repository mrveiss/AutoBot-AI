# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Response schemas for knowledge search endpoints (Issue #5317 batch 2)."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeSearchResponse(BaseModel):
    """Shape returned by POST /search (all three code paths).

    The basic and enhanced paths use _build_search_response (keys: results,
    total_results, query, mode, kb_implementation, rag_enhanced, reranking_applied).
    The RAG path additionally includes status, synthesized_response, original_query,
    reformulated_queries, confidence_score, etc.  extra="allow" admits all extra
    fields so both code paths validate without wrapping returns.
    """

    model_config = ConfigDict(extra="allow")

    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0
    query: str | None = None
    mode: str | None = None
    kb_implementation: str | None = None
    rag_enhanced: bool = False
    reranking_applied: bool = False
    status: str | None = None
    synthesized_response: str | None = None
    original_query: str | None = None
    reformulated_queries: List[str] = Field(default_factory=list)
    message: str | None = None


class KBSearchResponse(BaseModel):
    """Shape returned by deprecated POST /enhanced_search and /enhanced_search_v2 (#10666 B1).

    Consolidates the former enhanced_search (full shape) and enhanced_search_v2
    (V2 was a strict subset: only success/results/total_count/message) response shapes.
    extra="allow" handles KB-specific additions on either code path.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    query_processed: str | None = None
    mode: str | None = None
    tags_applied: List[str] | None = None
    min_score_applied: float = 0.0
    reranking_applied: bool = False
    message: str | None = None


class RagSearchResponse(BaseModel):
    """Shape returned by deprecated POST /rag_search.

    Shares the same RAG synthesis shape as the /search RAG path.
    """

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    synthesized_response: str = ""
    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0
    original_query: str | None = None
    reformulated_queries: List[str] = Field(default_factory=list)
    rag_enhanced: bool = True
    message: str | None = None


class SimilaritySearchResponse(BaseModel):
    """Shape returned by deprecated POST /similarity_search."""

    model_config = ConfigDict(extra="allow")

    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0
    query: str = ""
    threshold: float = 0.7
    kb_implementation: str = ""
    rag_enhanced: bool = False
    rag_analysis: Dict[str, Any] | None = None


# /enhanced_search_v2 response shape folded into KBSearchResponse above (#10666 B1)


class SearchAnalyticsResponse(BaseModel):
    """Shape returned by GET /search_analytics."""

    model_config = ConfigDict(extra="allow")

    success: bool = True
    analytics: Dict[str, Any] = Field(default_factory=dict)
    message: str | None = None


class RecordClickResponse(BaseModel):
    """Shape returned by POST /record_click."""

    model_config = ConfigDict(extra="allow")

    success: bool = True
    message: str = ""


class ExpandQueryResponse(BaseModel):
    """Shape returned by POST /expand_query."""

    model_config = ConfigDict(extra="allow")

    success: bool = True
    original_query: str = ""
    expanded_queries: List[str] = Field(default_factory=list)
    expansion_count: int = 0
    message: str | None = None
