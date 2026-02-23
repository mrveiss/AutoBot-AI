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

import asyncio
import logging
from typing import Any, Dict, List, Optional, Set

from backend.knowledge_factory import get_or_create_knowledge_base
from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)


# Issue #336: Extracted helper for processing relation results
def _process_outgoing_relation(
    rel: Dict[str, Any], fact_id: str, related_ids: Set[str], results: List[Dict]
) -> None:
    """Process a single outgoing relation (Issue #336 - extracted helper)."""
    if rel.get("target_fact"):
        target = rel["target_fact"]
        target["source"] = "graph_relation"
        target["relation_type"] = rel.get("relation_type")
        target["from_fact"] = fact_id
        if rel.get("target_id") not in related_ids:
            results.append(target)
            related_ids.add(rel.get("target_id"))


def _process_incoming_relation(
    rel: Dict[str, Any], fact_id: str, related_ids: Set[str], results: List[Dict]
) -> None:
    """Process a single incoming relation (Issue #336 - extracted helper)."""
    if rel.get("source_fact"):
        source = rel["source_fact"]
        source["source"] = "graph_relation"
        source["relation_type"] = rel.get("relation_type")
        source["to_fact"] = fact_id
        if rel.get("source_id") not in related_ids:
            results.append(source)
            related_ids.add(rel.get("source_id"))


async def _expand_fact_relations(
    kb: Any, fact_id: str, related_ids: Set[str], results: List[Dict]
) -> None:
    """Expand relations for a single fact (Issue #336 - extracted helper)."""
    if not fact_id:
        return
    relations = await kb.get_fact_relations(
        fact_id, direction="both", include_fact_details=True
    )
    if relations.get("success"):
        for rel in relations.get("outgoing", []):
            _process_outgoing_relation(rel, fact_id, related_ids, results)
        for rel in relations.get("incoming", []):
            _process_incoming_relation(rel, fact_id, related_ids, results)


def _build_relation_context(
    rel: Dict[str, Any], total_length: int, max_length: int, context_parts: List[str]
) -> int:
    """Build context string from a single relation (Issue #336 - extracted helper)."""
    if not rel.get("target_fact"):
        return total_length
    content = rel["target_fact"].get("content", "")[:300]
    if total_length + len(content) > max_length:
        return total_length
    rel_type = rel.get("relation_type", "relates_to")
    context_parts.append(f"- [{rel_type}] {content}\n")
    return total_length + len(content)


def _process_fact_results(
    fact_results: Dict[str, Any],
    max_length: int,
    context_parts: List[str],
    citations: List[Dict],
    total_length: int,
) -> int:
    """Process fact search results into context. (Issue #315 - extracted)"""
    results = fact_results.get("results")
    if not results:
        return total_length

    context_parts.append("## Knowledge Base Facts\n")
    for i, fact in enumerate(results[:3], 1):
        content = fact.get("content", "")[:500]
        if total_length + len(content) > max_length:
            break
        context_parts.append(f"{i}. {content}\n")
        total_length += len(content)
        citations.append(
            {
                "source": "knowledge_base",
                "id": fact.get("id") or fact.get("fact_id"),
                "category": fact.get("category"),
            }
        )
    context_parts.append("\n")
    return total_length


async def _process_relations_for_citations(
    kb,
    citations: List[Dict],
    max_length: int,
    context_parts: List[str],
    total_length: int,
) -> int:
    """Process relations for citations. (Issue #315 - extracted)"""
    for citation in citations[:2]:
        if total_length >= max_length:
            break
        fact_id = citation.get("id")
        if not fact_id:
            continue

        relations = await kb.get_fact_relations(
            fact_id, direction="outgoing", include_fact_details=True
        )
        if not (relations.get("success") and relations.get("outgoing")):
            continue

        context_parts.append("## Related Information\n")
        for rel in relations["outgoing"][:2]:
            total_length = _build_relation_context(
                rel, total_length, max_length, context_parts
            )
        context_parts.append("\n")
    return total_length


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


def _process_documentation_context(
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

    doc_results = doc_searcher.search(query=query, n_results=2, score_threshold=0.6)
    if not doc_results:
        return total_length

    context_parts.append("## AutoBot Documentation\n")
    for doc in doc_results[:2]:
        total_length = _process_single_doc_result(
            doc, total_length, max_length, context_parts, citations
        )
    return total_length


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
            from backend.services.chat_knowledge_service import DocumentationSearcher

            _documentation_searcher = DocumentationSearcher()
            if _documentation_searcher.initialize():
                logger.info("Documentation searcher initialized for unified API")
                return _documentation_searcher
            else:
                logger.warning("Documentation searcher failed to initialize")
                _documentation_searcher = None
                return None
        except Exception as e:
            logger.warning("Could not initialize documentation searcher: %s", e)
            return None


# ============================================================================
# Pydantic Models
# ============================================================================


class UnifiedSearchRequest(BaseModel):
    """Request model for unified knowledge search."""

    query: str = Field(..., description="Search query text")
    top_k: int = Field(10, ge=1, le=50, description="Max results from fact search")
    doc_results: int = Field(3, ge=0, le=10, description="Max documentation results")
    expand_relations: bool = Field(True, description="Include related facts via graph")
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


async def _search_facts(kb, query: str, top_k: int, result: dict) -> None:
    """
    Search facts via KnowledgeBase.

    Issue #620: Extracted from unified_search.

    Args:
        kb: Knowledge base instance
        query: Search query
        top_k: Number of results to return
        result: Result dict to populate
    """
    try:
        fact_results = await kb.search(query, top_k=top_k)
        if fact_results.get("results"):
            for fact in fact_results["results"]:
                fact["source"] = "knowledge_base"
            result["facts"] = fact_results.get("results", [])
        result["sources_searched"].append("facts")
    except Exception as e:
        logger.warning("Fact search failed: %s", e)


async def _search_relations(kb, result: dict) -> None:
    """
    Expand facts with graph relations.

    Issue #620: Extracted from unified_search.

    Args:
        kb: Knowledge base instance
        result: Result dict with facts to expand
    """
    try:
        related_ids: Set[str] = set()
        fact_ids = [f.get("id") or f.get("fact_id") for f in result["facts"]]

        for fact_id in fact_ids[:5]:  # Limit to top 5 to avoid too many queries
            await _expand_fact_relations(
                kb, fact_id, related_ids, result["related_facts"]
            )

        result["sources_searched"].append("relations")
    except Exception as e:
        logger.warning("Relation expansion failed: %s", e)


def _search_documentation(
    query: str, doc_results_count: int, score_threshold: float, result: dict
) -> None:
    """
    Search documentation collection.

    Issue #620: Extracted from unified_search.

    Args:
        query: Search query
        doc_results_count: Number of doc results to return
        score_threshold: Minimum score threshold
        result: Result dict to populate
    """
    try:
        doc_searcher = get_documentation_searcher()
        if doc_searcher:
            doc_results = doc_searcher.search(
                query=query,
                n_results=doc_results_count,
                score_threshold=score_threshold,
            )
            for doc in doc_results:
                doc["source"] = "documentation"
            result["documentation"] = doc_results
            result["sources_searched"].append("documentation")
    except Exception as e:
        logger.warning("Documentation search failed: %s", e)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="unified_search",
    error_code_prefix="KNOWLEDGE_UNIFIED",
)
@router.post("/search")
async def unified_search(req: Request, body: UnifiedSearchRequest):
    """
    Search across all knowledge sources in a unified query.

    Issue #620: Refactored to use extracted helper methods.

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

    # Search facts (Issue #620: uses helper)
    if "facts" in body.include_sources and kb is not None:
        await _search_facts(kb, body.query, body.top_k, result)

    # Expand with relations (Issue #620: uses helper)
    if "relations" in body.include_sources and body.expand_relations and kb is not None:
        await _search_relations(kb, result)

    # Search documentation (Issue #620: uses helper)
    if "documentation" in body.include_sources and body.doc_results > 0:
        _search_documentation(
            body.query, body.doc_results, body.score_threshold, result
        )

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
    """Get statistics from all unified knowledge sources (KB facts, relations, docs). Ref: #1088."""
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
    # Issue #379: Parallelize independent KB stats calls with asyncio.gather()
    if kb is not None:
        try:
            kb_stats, rel_stats = await asyncio.gather(
                kb.get_stats(),
                kb.get_relation_stats(),
            )

            stats["knowledge_base"] = {
                "available": True,
                "total_facts": kb_stats.get("total_facts", 0),
                "vectorized_count": kb_stats.get("vectorized_count", 0),
                "categories": kb_stats.get("categories", []),
            }

            if rel_stats.get("success"):
                stats["relations"] = {
                    "total_relations": rel_stats.get("total_relations", 0),
                    "facts_with_relations": rel_stats.get("facts_with_relations", 0),
                    "relations_by_type": rel_stats.get("relations_by_type", {}),
                }
        except Exception as e:
            logger.warning("KB stats failed: %s", e)

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
        logger.warning("Doc stats failed: %s", e)

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

    context_parts: List[str] = []
    citations: List[Dict] = []
    total_length = 0

    # Search facts (Issue #315: use extracted helper)
    if kb is not None:
        try:
            fact_results = await kb.search(body.query, top_k=5)
            total_length = _process_fact_results(
                fact_results,
                body.max_context_length,
                context_parts,
                citations,
                total_length,
            )
        except Exception as e:
            logger.warning("Fact context failed: %s", e)

    # Get related facts (Issue #315: use extracted helper)
    if body.include_relations and kb is not None and citations:
        try:
            total_length = await _process_relations_for_citations(
                kb, citations, body.max_context_length, context_parts, total_length
            )
        except Exception as e:
            logger.warning("Relation context failed: %s", e)

    # Get documentation (Issue #315: uses helper for reduced nesting)
    if body.include_documentation:
        try:
            total_length = _process_documentation_context(
                body.query,
                body.max_context_length,
                context_parts,
                citations,
                total_length,
            )
        except Exception as e:
            logger.warning("Doc context failed: %s", e)

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
        logger.error("Documentation search failed: %s", e)
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
        logger.error("Documentation stats failed: %s", e)
        return {
            "success": False,
            "message": str(e),
        }


# ============================================================================
# Unified Knowledge Graph Endpoint (for KnowledgeGraph.vue)
# ============================================================================


class GraphRequest(BaseModel):
    """Request model for unified knowledge graph."""

    max_facts: int = Field(50, ge=1, le=200, description="Maximum facts to include")
    max_depth: int = Field(2, ge=1, le=3, description="Maximum relation depth")
    include_categories: bool = Field(True, description="Include category nodes")
    include_relations: bool = Field(True, description="Include fact relations")
    category_filter: Optional[str] = Field(None, description="Filter by category path")


def _create_category_node(category: Dict[str, Any]) -> Dict[str, Any]:
    """Create a graph node from a category.

    Issue #707: Extracted helper for unified graph building.
    """
    return {
        "id": f"cat_{category.get('id', category.get('name', 'unknown'))}",
        "name": category.get("name", "Unknown"),
        "type": "category",
        "observations": [category.get("description", "Knowledge category")],
        "metadata": {
            "path": category.get("path", ""),
            "fact_count": category.get("fact_count", 0),
            "icon": category.get("icon", "folder"),
            "color": category.get("color", "#6366f1"),
        },
        "created_at": int(category.get("created_at", 0)),
    }


def _create_fact_node(fact: Dict[str, Any]) -> Dict[str, Any]:
    """Create a graph node from a fact.

    Issue #707: Extracted helper for unified graph building.
    """
    content = fact.get("content", "")
    # Truncate long content for node label
    label = content[:100] + "..." if len(content) > 100 else content

    return {
        "id": fact.get("id") or fact.get("fact_id", f"fact_{hash(content)}"),
        "name": label,
        "type": "fact",
        "observations": [content],
        "metadata": {
            "category": fact.get("category", "general"),
            "source": fact.get("source", "knowledge_base"),
            "confidence": fact.get("confidence", 1.0),
        },
        "created_at": int(fact.get("created_at", 0)),
    }


def _process_category_tree(
    tree: List[Dict[str, Any]],
    nodes: List[Dict],
    edges: List[Dict],
    parent_id: Optional[str] = None,
) -> None:
    """Recursively process category tree into nodes and edges.

    Issue #707: Extracted helper for unified graph building.
    """
    for category in tree:
        node = _create_category_node(category)
        nodes.append(node)

        # Add edge from parent category if exists
        if parent_id:
            edges.append(
                {
                    "from": parent_id,
                    "to": node["id"],
                    "type": "contains",
                    "strength": 1.0,
                }
            )

        # Process children recursively
        children = category.get("children", [])
        if children:
            _process_category_tree(children, nodes, edges, node["id"])


async def _get_facts_for_graph(
    kb: Any, category_filter: Optional[str], max_facts: int
) -> List[Dict[str, Any]]:
    """Get facts for the graph with optional category filtering.

    Issue #707: Extracted helper for unified graph building.
    """
    if category_filter:
        # Get facts from specific category
        result = await kb.get_facts_in_category(
            category_id=category_filter, include_descendants=True, limit=max_facts
        )
        return result.get("facts", []) if result.get("success") else []
    else:
        # Search for recent facts
        result = await kb.search("*", top_k=max_facts)
        return result.get("results", [])


async def _get_fact_relations_for_graph(
    kb: Any, fact_ids: List[str], max_relations: int = 100
) -> List[Dict[str, Any]]:
    """Get relations between facts for the graph.

    Issue #707: Extracted helper for unified graph building.
    """
    relations = []
    relation_set = set()

    for fact_id in fact_ids[:20]:  # Limit to first 20 to avoid too many queries
        try:
            result = await kb.get_fact_relations(
                fact_id, direction="both", include_fact_details=False
            )
            if not result.get("success"):
                continue

            for rel in result.get("outgoing", [])[:5]:  # Limit per fact
                target_id = rel.get("target_id")
                if not target_id or target_id not in fact_ids:
                    continue
                key = f"{fact_id}-{target_id}"
                if key not in relation_set:
                    relation_set.add(key)
                    relations.append(
                        {
                            "from": fact_id,
                            "to": target_id,
                            "type": rel.get("relation_type", "relates_to"),
                            "strength": rel.get("strength", 0.8),
                        }
                    )

            if len(relations) >= max_relations:
                break
        except Exception:  # nosec B112 - continue on single fact failure is intentional
            continue

    return relations


def _create_dynamic_category_nodes(
    facts: List[Dict[str, Any]], nodes: List[Dict], edges: List[Dict]
) -> Dict[str, str]:
    """Create category nodes dynamically from fact categories.

    Issue #707: Creates category nodes based on unique category values in facts.
    Returns mapping of category name to node ID.
    """
    category_colors = {
        "general": "#6b7280",
        "system_commands": "#10b981",
        "developer": "#3b82f6",
        "agents": "#8b5cf6",
        "architecture": "#f59e0b",
        "implementation": "#06b6d4",
        "autobot-documentation": "#3b82f6",
        "system-knowledge": "#10b981",
        "user-knowledge": "#f59e0b",
    }

    category_map: Dict[str, str] = {}
    seen_categories: Set[str] = set()

    for fact in facts:
        category = fact.get("category", "general")
        if category and category not in seen_categories:
            seen_categories.add(category)
            node_id = f"cat_{category}"
            category_map[category] = node_id
            nodes.append(
                {
                    "id": node_id,
                    "name": category.replace("-", " ").replace("_", " ").title(),
                    "type": "category",
                    "observations": [f"Knowledge category: {category}"],
                    "metadata": {
                        "path": category,
                        "fact_count": 0,
                        "icon": "folder",
                        "color": category_colors.get(category, "#6366f1"),
                    },
                    "created_at": 0,
                }
            )

    return category_map


async def _process_category_tree_for_graph(
    kb: Any, body: GraphRequest, nodes: List[Dict], edges: List[Dict]
) -> Dict[str, str]:
    """Process category tree and build category map.

    Issue #665: Extracted from get_unified_graph.

    Args:
        kb: Knowledge base instance
        body: Graph request parameters
        nodes: List to append category nodes to
        edges: List to append category edges to

    Returns:
        Dict mapping category names to node IDs
    """
    category_map: Dict[str, str] = {}

    if not body.include_categories or kb is None:
        return category_map

    try:
        tree_result = await kb.get_category_tree(
            root_id=None, max_depth=body.max_depth, include_fact_counts=True
        )
        if tree_result.get("success") and tree_result.get("tree"):
            _process_category_tree(tree_result.get("tree", []), nodes, edges)
            # Build category map from tree
            for node in nodes:
                if node["type"] == "category":
                    cat_name = node.get("metadata", {}).get("path", "").split("/")[-1]
                    if cat_name:
                        category_map[cat_name] = node["id"]
    except Exception as e:
        logger.warning("Failed to get category tree: %s", e)

    return category_map


def _process_facts_into_nodes(
    facts: List[Dict[str, Any]],
    nodes: List[Dict],
    edges: List[Dict],
    category_map: Dict[str, str],
) -> List[str]:
    """Process facts into graph nodes and create category edges.

    Issue #665: Extracted from get_unified_graph.

    Args:
        facts: List of fact dictionaries
        nodes: List to append fact nodes to
        edges: List to append category-fact edges to
        category_map: Mapping of category names to node IDs

    Returns:
        List of fact IDs for relation lookups
    """
    fact_ids: List[str] = []

    for fact in facts:
        node = _create_fact_node(fact)
        nodes.append(node)
        fact_ids.append(node["id"])

        # Create edge from category to fact
        category = fact.get("category", "general")
        cat_node_id = category_map.get(category)
        if cat_node_id:
            edges.append(
                {
                    "from": cat_node_id,
                    "to": node["id"],
                    "type": "contains",
                    "strength": 0.6,
                }
            )

    return fact_ids


def _update_category_fact_counts(
    nodes: List[Dict], facts: List[Dict[str, Any]]
) -> None:
    """Update fact counts in category nodes.

    Issue #665: Extracted from get_unified_graph.

    Args:
        nodes: List of graph nodes
        facts: List of facts to count per category
    """
    for node in nodes:
        if node["type"] == "category":
            cat_path = node.get("metadata", {}).get("path", "")
            cat_name = (
                cat_path.split("/")[-1] if cat_path else node["id"].replace("cat_", "")
            )
            count = sum(1 for f in facts if f.get("category") == cat_name)
            node["metadata"]["fact_count"] = count


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_unified_graph",
    error_code_prefix="KNOWLEDGE_UNIFIED",
)
@router.post("/graph")
async def get_unified_graph(req: Request, body: GraphRequest):
    """
    Get unified knowledge graph combining categories, facts, and relations.

    This endpoint is designed for the KnowledgeGraph.vue component to visualize
    all knowledge sources in a single graph. It returns:

    - Category nodes (from hierarchical tree OR dynamically from facts)
    - Fact nodes (sampled from knowledge base)
    - Edges: category->fact, fact->fact relations

    The response format matches what Cytoscape.js expects:
    - entities: List of nodes with id, name, type, observations
    - relations: List of edges with from, to, type, strength
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    # Process category tree and get category map
    category_map = await _process_category_tree_for_graph(kb, body, nodes, edges)

    # Get facts for the graph
    facts: List[Dict[str, Any]] = []
    if kb is not None:
        try:
            facts = await _get_facts_for_graph(kb, body.category_filter, body.max_facts)
        except Exception as e:
            logger.warning("Failed to get facts: %s", e)

    # If no category nodes from tree, create them dynamically from facts
    if body.include_categories and not category_map and facts:
        category_map = _create_dynamic_category_nodes(facts, nodes, edges)

    # Process facts into nodes and create category-fact edges
    fact_ids = _process_facts_into_nodes(facts, nodes, edges, category_map)

    # Update category fact counts
    _update_category_fact_counts(nodes, facts)

    # Get fact relations if requested
    if body.include_relations and kb is not None and fact_ids:
        try:
            fact_relations = await _get_fact_relations_for_graph(kb, fact_ids)
            edges.extend(fact_relations)
        except Exception as e:
            logger.warning("Failed to get fact relations: %s", e)

    return {
        "success": True,
        "data": {
            "entities": nodes,
            "relations": edges,
        },
        "stats": {
            "total_entities": len(nodes),
            "total_relations": len(edges),
            "categories": len([n for n in nodes if n["type"] == "category"]),
            "facts": len([n for n in nodes if n["type"] == "fact"]),
        },
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_unified_graph_simple",
    error_code_prefix="KNOWLEDGE_UNIFIED",
)
@router.get("/graph")
async def get_unified_graph_simple(
    req: Request,
    max_facts: int = Query(50, ge=1, le=200, description="Maximum facts to include"),
    include_categories: bool = Query(True, description="Include category nodes"),
):
    """
    GET version of unified graph for simple requests.

    Returns a unified knowledge graph with default settings.
    For more control, use POST /unified/graph with GraphRequest body.
    """
    body = GraphRequest(
        max_facts=max_facts,
        include_categories=include_categories,
    )
    return await get_unified_graph(req, body)
