# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Documentation Search API - AutoBot's own indexed documentation (Issue #250).

Extracted from knowledge_search_aggregator.py (#16665) to keep that file's
own growth within its grandfathered line-count ceiling (#14236). Indexed
documentation carries no per-user ownership or visibility -- it is the
product's own docs, not a knowledge-base fact -- so this module has no
fact-visibility concern and is out of #16665's scope.

Endpoints:
- GET /multi-source/documentation/search - Search indexed AutoBot documentation
- GET /multi-source/documentation/stats  - Documentation index statistics
"""

import threading
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException

from api.schemas_knowledge import KnowledgeDocumentationSearchResponse, KnowledgeDocumentationStatsResponse
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/multi-source", tags=["knowledge-multi-source"], dependencies=[Depends(get_current_user)])

# ============================================================================
# Lazy-loaded Documentation Searcher (thread-safe)
# ============================================================================

_documentation_searcher = None
_documentation_searcher_lock = threading.Lock()


def get_documentation_searcher():
    """Get or create the documentation searcher instance (thread-safe)."""
    global _documentation_searcher

    if _documentation_searcher is not None:
        return _documentation_searcher

    with _documentation_searcher_lock:
        # Double-check after acquiring lock
        if _documentation_searcher is not None:
            return _documentation_searcher

        try:
            from services.chat_knowledge_service import DocumentationSearcher

            _documentation_searcher = DocumentationSearcher()
            if _documentation_searcher.initialize():
                logger.info("Documentation searcher initialized for multi-source API")
                return _documentation_searcher
            else:
                logger.warning("Documentation searcher failed to initialize")
                _documentation_searcher = None
                return None
        except Exception as e:
            logger.warning("Could not initialize documentation searcher: %s", e)
            return None


def _process_single_doc_result(
    doc: Dict[str, Any],
    total_length: int,
    max_length: int,
    context_parts: List[str],
    citations: List[Dict],
) -> int:
    """Process a single documentation result (Issue #315: extracted).

    Returns updated total_length.
    """
    content = doc.get("content", "")[:400]
    if total_length + len(content) > max_length:
        return total_length
    source = doc.get("metadata", {}).get("source", "docs")
    context_parts.append(f"[{source}]\n{content}\n\n")
    citations.append(
        {
            "source": "documentation",
            "file": doc.get("metadata", {}).get("source"),
        }
    )
    return total_length + len(content)


def process_documentation_context(
    query: str,
    max_length: int,
    context_parts: List[str],
    citations: List[Dict],
    total_length: int,
) -> int:
    """Process documentation search into context. (Issue #315 - extracted)"""
    doc_searcher = get_documentation_searcher()
    if not doc_searcher or not doc_searcher.is_documentation_query(query):
        return total_length

    doc_results = doc_searcher.search(query=query, n_results=2, score_threshold=0.3)
    if not doc_results:
        return total_length

    context_parts.append("## AutoBot Documentation\n")
    for doc in doc_results[:2]:
        total_length = _process_single_doc_result(doc, total_length, max_length, context_parts, citations)
    return total_length


@router.get("/documentation/search", response_model=KnowledgeDocumentationSearchResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_documentation",
    error_code_prefix="KNOWLEDGE_SEARCH_AGGREGATOR",
)
async def search_documentation(
    query: str,
    n_results: int = 5,
    score_threshold: float = 0.3,
):
    """
    Search indexed AutoBot documentation.

    Issue #250: Direct endpoint for documentation search.

    Args:
        query: Search query
        n_results: Maximum results to return
        score_threshold: Minimum relevance score (0-1)
    """
    doc_searcher = get_documentation_searcher()

    if not doc_searcher:
        return {
            "success": False,
            "message": "Documentation not indexed. " "Run: python tools/index_documentation.py --tier 1",
            "results": [],
        }

    try:
        results = doc_searcher.search(
            query=query,
            n_results=n_results,
            score_threshold=score_threshold,
        )

        return {
            "success": True,
            "query": query,
            "results": results,
            "total_results": len(results),
        }

    except Exception as e:
        logger.error("Documentation search failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Documentation search failed",
        )


@router.get("/documentation/stats", response_model=KnowledgeDocumentationStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="documentation_stats",
    error_code_prefix="KNOWLEDGE_SEARCH_AGGREGATOR",
)
async def documentation_stats():
    """
    Get statistics about indexed documentation.

    Returns document count and indexing status.
    """
    doc_searcher = get_documentation_searcher()

    if not doc_searcher or not doc_searcher._collection:
        return {
            "success": True,
            "indexed": False,
            "message": "Documentation not indexed",
            "how_to_index": "Run: python tools/index_documentation.py --tier 1",
        }

    try:
        doc_count = doc_searcher._collection.count()

        return {
            "success": True,
            "indexed": True,
            "collection_name": doc_searcher.collection_name,
            "document_count": doc_count,
        }

    except Exception as e:
        logger.error("Documentation stats failed: %s", e)
        return {
            "success": False,
            "message": "Internal server error",
        }
