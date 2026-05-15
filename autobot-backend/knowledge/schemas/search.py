# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Response schemas for knowledge search endpoints (Issue #5317 batch 2)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

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
    query: Optional[str] = None
    mode: Optional[str] = None
    kb_implementation: Optional[str] = None
    rag_enhanced: bool = False
    reranking_applied: bool = False
    status: Optional[str] = None
    synthesized_response: Optional[str] = None
    original_query: Optional[str] = None
    reformulated_queries: List[str] = Field(default_factory=list)
    message: Optional[str] = None


class EnhancedSearchResponse(BaseModel):
    """Shape returned by deprecated POST /enhanced_search.

    Mirrors the kb.enhanced_search() contract: success, results, total_count,
    query_processed, mode, tags_applied, min_score_applied, reranking_applied.
    extra="allow" handles KB-specific additions.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    query_processed: Optional[str] = None
    mode: Optional[str] = None
    tags_applied: Optional[List[str]] = None
    min_score_applied: float = 0.0
    reranking_applied: bool = False
    message: Optional[str] = None


class RagSearchResponse(BaseModel):
    """Shape returned by deprecated POST /rag_search.

    Shares the same RAG synthesis shape as the /search RAG path.
    """

    model_config = ConfigDict(extra="allow")

    status: str = "success"
    synthesized_response: str = ""
    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0
    original_query: Optional[str] = None
    reformulated_queries: List[str] = Field(default_factory=list)
    rag_enhanced: bool = True
    message: Optional[str] = None


class SimilaritySearchResponse(BaseModel):
    """Shape returned by deprecated POST /similarity_search."""

    model_config = ConfigDict(extra="allow")

    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_results: int = 0
    query: str = ""
    threshold: float = 0.7
    kb_implementation: str = ""
    rag_enhanced: bool = False
    rag_analysis: Optional[Dict[str, Any]] = None


class EnhancedSearchV2Response(BaseModel):
    """Shape returned by deprecated POST /enhanced_search_v2.

    Delegates to kb.enhanced_search_v2(); mirrors the enhanced_search shape.
    """

    model_config = ConfigDict(extra="allow")

    success: bool = True
    results: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    message: Optional[str] = None


class SearchAnalyticsResponse(BaseModel):
    """Shape returned by GET /search_analytics."""

    model_config = ConfigDict(extra="allow")

    success: bool = True
    analytics: Dict[str, Any] = Field(default_factory=dict)
    message: Optional[str] = None


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
    message: Optional[str] = None
