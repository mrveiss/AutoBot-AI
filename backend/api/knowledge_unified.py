# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unified Knowledge API - Single Entry Point for All Knowledge Retrieval

This API provides a unified interface for searching across:
- Knowledge Base facts (ChromaDB vectors in autobot_kb collection)
- Fact relations (graph-based connections between facts)
- Documentation (ChromaDB vectors in autobot_docs collection)

Issue #250 Integration: Combines documentation search with RAG and graph search.

Endpoints:
- POST /unified/search - Search across all knowledge sources
- GET /unified/stats - Statistics from all sources
- POST /unified/context - Get context for LLM prompts
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.knowledge_factory import get_or_create_knowledge_base
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/unified", tags=["knowledge-unified"])


# ============================================================================
# Lazy-loaded Documentation Searcher (thread-safe)
# ============================================================================

import threading

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
            from src.services.chat_knowledge_service import DocumentationSearcher

            _documentation_searcher = DocumentationSearcher()
            if _documentation_searcher.initialize():
                logger.info("Documentation searcher initialized for unified API")
                return _documentation_searcher
            else:
                logger.warning("Documentation searcher failed to initialize")
                _documentation_searcher = None
                return None
        except Exception as e:
            logger.warning(f"Could not initialize documentation searcher: {e}")
            return None


# ============================================================================
# Pydantic Models
# ============================================================================


class UnifiedSearchRequest(BaseModel):
    """Request model for unified knowledge search."""

    query: str = Field(..., description="Search query text")
    top_k: int = Field(10, ge=1, le=50, description="Max results from fact search")
    doc_results: int = Field(3, ge=0, le=10, description="Max documentation results")
    expand_relations: bool = Field(
        True, description="Include related facts via graph"
    )
    score_threshold: float = Field(
        0.6, ge=0.0, le=1.0, description="Minimum relevance score"
    )
    include_sources: List[str] = Field(
        default=["facts", "relations", "documentation"],
        description="Which sources to search: facts, relations, documentation",
    )


class ContextRequest(BaseModel):
    """Request model for getting LLM context."""

    query: str = Field(..., description="User query for context retrieval")
    max_context_length: int = Field(
        4000, ge=500, le=16000, description="Maximum context length in characters"
    )
    include_documentation: bool = Field(
        True, description="Include documentation in context"
    )
    include_relations: bool = Field(
        True, description="Include related facts in context"
    )


# ============================================================================
# API Endpoints
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="unified_search",
    error_code_prefix="KNOWLEDGE_UNIFIED",
)
@router.post("/search")
async def unified_search(req: Request, body: UnifiedSearchRequest):
    """
    Search across all knowledge sources in a unified query.

    Combines:
    - Vector similarity search on facts (KnowledgeBase)
    - Graph traversal for related facts (Relations)
    - Documentation search (autobot_docs collection)

    Returns results from all sources with source attribution.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    result = {
        "success": True,
        "query": body.query,
        "facts": [],
        "related_facts": [],
        "documentation": [],
        "sources_searched": [],
    }

    # Search facts via KnowledgeBase
    if "facts" in body.include_sources and kb is not None:
        try:
            fact_results = await kb.search(body.query, top_k=body.top_k)
            if fact_results.get("results"):
                for fact in fact_results["results"]:
                    fact["source"] = "knowledge_base"
                result["facts"] = fact_results.get("results", [])
            result["sources_searched"].append("facts")
        except Exception as e:
            logger.warning(f"Fact search failed: {e}")

    # Expand with relations if enabled
    if "relations" in body.include_sources and body.expand_relations and kb is not None:
        try:
            # Get related facts for each fact result
            related_ids = set()
            fact_ids = [f.get("id") or f.get("fact_id") for f in result["facts"]]

            for fact_id in fact_ids[:5]:  # Limit to top 5 to avoid too many queries
                if not fact_id:
                    continue
                relations = await kb.get_fact_relations(
                    fact_id, direction="both", include_fact_details=True
                )
                if relations.get("success"):
                    for rel in relations.get("outgoing", []):
                        if rel.get("target_fact"):
                            target = rel["target_fact"]
                            target["source"] = "graph_relation"
                            target["relation_type"] = rel.get("relation_type")
                            target["from_fact"] = fact_id
                            if rel.get("target_id") not in related_ids:
                                result["related_facts"].append(target)
                                related_ids.add(rel.get("target_id"))

                    for rel in relations.get("incoming", []):
                        if rel.get("source_fact"):
                            source = rel["source_fact"]
                            source["source"] = "graph_relation"
                            source["relation_type"] = rel.get("relation_type")
                            source["to_fact"] = fact_id
                            if rel.get("source_id") not in related_ids:
                                result["related_facts"].append(source)
                                related_ids.add(rel.get("source_id"))

            result["sources_searched"].append("relations")
        except Exception as e:
            logger.warning(f"Relation expansion failed: {e}")

    # Search documentation
    if "documentation" in body.include_sources and body.doc_results > 0:
        try:
            doc_searcher = get_documentation_searcher()
            if doc_searcher:
                doc_results = doc_searcher.search(
                    query=body.query,
                    n_results=body.doc_results,
                    score_threshold=body.score_threshold,
                )
                for doc in doc_results:
                    doc["source"] = "documentation"
                result["documentation"] = doc_results
                result["sources_searched"].append("documentation")
        except Exception as e:
            logger.warning(f"Documentation search failed: {e}")

    # Calculate totals
    result["total_results"] = (
        len(result["facts"])
        + len(result["related_facts"])
        + len(result["documentation"])
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="unified_stats",
    error_code_prefix="KNOWLEDGE_UNIFIED",
)
@router.get("/stats")
async def unified_stats(req: Request):
    """
    Get statistics from all unified knowledge sources.

    Returns counts and status for:
    - Knowledge base facts
    - Fact relations
    - Indexed documentation
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    stats = {
        "success": True,
        "knowledge_base": {
            "available": False,
            "total_facts": 0,
            "vectorized_count": 0,
        },
        "relations": {
            "total_relations": 0,
            "facts_with_relations": 0,
        },
        "documentation": {
            "available": False,
            "indexed_documents": 0,
        },
    }

    # Knowledge base stats
    if kb is not None:
        try:
            kb_stats = await kb.get_stats()
            stats["knowledge_base"] = {
                "available": True,
                "total_facts": kb_stats.get("total_facts", 0),
                "vectorized_count": kb_stats.get("vectorized_count", 0),
                "categories": kb_stats.get("categories", []),
            }

            # Relation stats
            rel_stats = await kb.get_relation_stats()
            if rel_stats.get("success"):
                stats["relations"] = {
                    "total_relations": rel_stats.get("total_relations", 0),
                    "facts_with_relations": rel_stats.get("facts_with_relations", 0),
                    "relations_by_type": rel_stats.get("relations_by_type", {}),
                }
        except Exception as e:
            logger.warning(f"KB stats failed: {e}")

    # Documentation stats
    try:
        doc_searcher = get_documentation_searcher()
        if doc_searcher and doc_searcher._collection:
            doc_count = doc_searcher._collection.count()
            stats["documentation"] = {
                "available": True,
                "indexed_documents": doc_count,
                "collection_name": doc_searcher.collection_name,
            }
    except Exception as e:
        logger.warning(f"Doc stats failed: {e}")

    return stats


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_llm_context",
    error_code_prefix="KNOWLEDGE_UNIFIED",
)
@router.post("/context")
async def get_llm_context(req: Request, body: ContextRequest):
    """
    Get formatted context for LLM prompts from unified knowledge sources.

    Retrieves and formats knowledge from all sources into a context string
    suitable for inclusion in LLM prompts.

    Returns:
    - Formatted context string
    - Source citations
    - Metadata about retrieved content
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    context_parts = []
    citations = []
    total_length = 0

    # Search facts
    if kb is not None:
        try:
            fact_results = await kb.search(body.query, top_k=5)
            if fact_results.get("results"):
                context_parts.append("## Knowledge Base Facts\n")
                for i, fact in enumerate(fact_results["results"][:3], 1):
                    content = fact.get("content", "")[:500]
                    if total_length + len(content) > body.max_context_length:
                        break
                    context_parts.append(f"{i}. {content}\n")
                    total_length += len(content)
                    citations.append({
                        "source": "knowledge_base",
                        "id": fact.get("id") or fact.get("fact_id"),
                        "category": fact.get("category"),
                    })
                context_parts.append("\n")
        except Exception as e:
            logger.warning(f"Fact context failed: {e}")

    # Get related facts
    if body.include_relations and kb is not None and citations:
        try:
            for citation in citations[:2]:
                if total_length >= body.max_context_length:
                    break
                fact_id = citation.get("id")
                if not fact_id:
                    continue

                relations = await kb.get_fact_relations(
                    fact_id, direction="outgoing", include_fact_details=True
                )
                if relations.get("success") and relations.get("outgoing"):
                    context_parts.append("## Related Information\n")
                    for rel in relations["outgoing"][:2]:
                        if rel.get("target_fact"):
                            content = rel["target_fact"].get("content", "")[:300]
                            if total_length + len(content) > body.max_context_length:
                                break
                            rel_type = rel.get("relation_type", "relates_to")
                            context_parts.append(f"- [{rel_type}] {content}\n")
                            total_length += len(content)
                    context_parts.append("\n")
        except Exception as e:
            logger.warning(f"Relation context failed: {e}")

    # Get documentation
    if body.include_documentation:
        try:
            doc_searcher = get_documentation_searcher()
            if doc_searcher and doc_searcher.is_documentation_query(body.query):
                doc_results = doc_searcher.search(
                    query=body.query,
                    n_results=2,
                    score_threshold=0.6,
                )
                if doc_results:
                    context_parts.append("## AutoBot Documentation\n")
                    for doc in doc_results[:2]:
                        content = doc.get("content", "")[:400]
                        if total_length + len(content) > body.max_context_length:
                            break
                        source = doc.get("metadata", {}).get("source", "docs")
                        context_parts.append(f"[{source}]\n{content}\n\n")
                        total_length += len(content)
                        citations.append({
                            "source": "documentation",
                            "file": doc.get("metadata", {}).get("source"),
                        })
        except Exception as e:
            logger.warning(f"Doc context failed: {e}")

    context_string = "".join(context_parts)

    return {
        "success": True,
        "context": context_string,
        "context_length": len(context_string),
        "citations": citations,
        "sources_used": list(set(c.get("source") for c in citations)),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_documentation",
    error_code_prefix="KNOWLEDGE_UNIFIED",
)
@router.get("/documentation/search")
async def search_documentation(
    query: str,
    n_results: int = 5,
    score_threshold: float = 0.5,
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
            "message": "Documentation not indexed. "
                       "Run: python tools/index_documentation.py --tier 1",
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
        logger.error(f"Documentation search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Documentation search failed: {str(e)}",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="documentation_stats",
    error_code_prefix="KNOWLEDGE_UNIFIED",
)
@router.get("/documentation/stats")
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
        logger.error(f"Documentation stats failed: {e}")
        return {
            "success": False,
            "message": str(e),
        }
