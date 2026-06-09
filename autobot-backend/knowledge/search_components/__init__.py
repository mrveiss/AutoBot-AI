# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base Search Components Package

Issue #381: Extracted from search.py god class refactoring.
Provides comprehensive search capabilities for the knowledge base.
Note: Package is named search_components to avoid conflict with search.py.

- helpers: Utility functions for Redis hash operations
- query_processor: Query preprocessing and expansion
- keyword_search: Keyword-based search using Redis
- hybrid_search: Hybrid search with Reciprocal Rank Fusion
- reranking: Cross-encoder result reranking
- tag_filter: Tag-based result filtering
- analytics: Search analytics tracking
- response_builder: Search response building and clustering
- retrieval_learner: Closed-loop retrieval pattern learning (Issue #2095)
- agentic_search: Agentic RAG — search as LLM tool with query rewriting (Issue #1718)
"""

from .agentic_search import (
    AgenticSearchConfig,
    AgenticSearchTool,
    get_agentic_search_tool,
    knowledge_search_tool,
)
from .analytics import SearchAnalytics, get_analytics
from .bm25 import BM25Scorer
from .helpers import (
    build_search_result,
    decode_redis_hash,
    matches_category,
    score_fact_by_terms,
)
from .hybrid_search import HybridSearcher
from .keyword_search import KeywordSearcher
from .query_processor import QueryProcessor, get_query_processor
from .reranking import ResultReranker, get_reranker
from .response_builder import ResponseBuilder, get_response_builder
from .retrieval_learner import RetrievalLearner, get_retrieval_learner
from .tag_filter import TagFilter

__all__ = [
    # BM25 scoring (#1720)
    "BM25Scorer",
    # Helper functions
    "decode_redis_hash",
    "matches_category",
    "score_fact_by_terms",
    "build_search_result",
    # Query processing
    "QueryProcessor",
    "get_query_processor",
    # Search classes
    "KeywordSearcher",
    "HybridSearcher",
    "ResultReranker",
    "get_reranker",
    # Filtering
    "TagFilter",
    # Analytics
    "SearchAnalytics",
    "get_analytics",
    # Response building
    "ResponseBuilder",
    "get_response_builder",
    # Retrieval pattern learning (#2095)
    "RetrievalLearner",
    "get_retrieval_learner",
    # Agentic RAG search tool (#1718)
    "AgenticSearchConfig",
    "AgenticSearchTool",
    "get_agentic_search_tool",
    "knowledge_search_tool",
]
