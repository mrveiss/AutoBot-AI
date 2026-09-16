# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Multi-Source Knowledge API - Single Entry Point for All Knowledge Retrieval

This API provides a multi-source interface for searching across:
- Knowledge Base facts (ChromaDB vectors in autobot_kb collection)
- Fact relations (graph-based connections between facts)
- Documentation (ChromaDB vectors in autobot_docs collection)

Issue #250 Integration: Combines documentation search with RAG and graph search.

Endpoints:
- POST /multi-source/search - Search across all knowledge sources
- GET /multi-source/stats - Statistics from all sources
- POST /multi-source/context - Get context for LLM prompts
"""

import asyncio
import json
from typing import Any, Dict, List, Set

from fastapi import APIRouter, Depends, Query, Request

from api.schemas_knowledge import (
    ContextRequest,
    GraphRequest,
    KnowledgeMultiSourceContextResponse,
    KnowledgeMultiSourceGraphResponse,
    KnowledgeMultiSourceSearchResponse,
    KnowledgeMultiSourceStatsResponse,
    SearchRequest,
)
from auth_middleware import get_current_user
from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import CategoryDefaults
from knowledge.quarantine import RESEARCH_QUARANTINE_FILTER
from knowledge.search_filters import (
    extract_user_context_from_request,
    filter_search_results_by_permission,
)
from knowledge_factory import get_or_create_knowledge_base

logger = get_logger(__name__)


# Issue #336: Extracted helper for processing relation results
def _process_outgoing_relation(rel: Dict[str, Any], fact_id: str, related_ids: Set[str], results: List[Dict]) -> None:
    """Process a single outgoing relation (Issue #336 - extracted helper).

    #16708: a relation item carries "to"/"type", never "target_id"/
    "relation_type" -- those keys never existed on the real shape
    RelationsMixin.get_fact_relations() returns, so every dedup check here
    always missed too.
    """
    if rel.get("target_fact"):
        target = rel["target_fact"]
        target["source"] = "graph_relation"
        target["relation_type"] = rel.get("type")
        target["from_fact"] = fact_id
        if rel.get("to") not in related_ids:
            results.append(target)
            related_ids.add(rel.get("to"))


def _process_incoming_relation(rel: Dict[str, Any], fact_id: str, related_ids: Set[str], results: List[Dict]) -> None:
    """Process a single incoming relation (Issue #336 - extracted helper). See #16708 note above."""
    if rel.get("source_fact"):
        source = rel["source_fact"]
        source["source"] = "graph_relation"
        source["relation_type"] = rel.get("type")
        source["to_fact"] = fact_id
        if rel.get("from") not in related_ids:
            results.append(source)
            related_ids.add(rel.get("from"))


def _relations_by_direction(relations: List[Dict[str, Any]], direction: str) -> List[Dict[str, Any]]:
    """Filter a flat relations list to one direction (#16708).

    RelationsMixin.get_fact_relations() has always returned one flat
    "relations" list with each item's own "direction" field -- never
    separate "outgoing"/"incoming" keys, which every caller below assumed.
    """
    return [rel for rel in relations if rel.get("direction") == direction]


async def _expand_fact_relations(
    kb: Any,
    fact_id: str,
    related_ids: Set[str],
    results: List[Dict],
    user_id: str,
    user_org_id: str | None,
    user_group_ids: List[str],
    is_admin: bool,
) -> None:
    """Expand relations for a single fact (Issue #336 - extracted helper).

    #16665: a related fact (target_fact/source_fact) is a KB fact like any
    other and is only included if *user_id* may see it.
    """
    if not fact_id:
        return
    relations = await kb.get_fact_relations(fact_id, direction="both", include_fact_details=True)
    if not relations.get("success"):
        return
    # #16708: the flat list, partitioned by each item's own "direction" --
    # "outgoing"/"incoming" were never top-level keys on this result.
    flat = relations.get("relations", [])
    ownership_manager = getattr(kb, "ownership_manager", None)
    for rel in _relations_by_direction(flat, "outgoing"):
        if await _related_fact_is_accessible(
            rel.get("target_fact"), ownership_manager, user_id, user_org_id, user_group_ids, is_admin
        ):
            _process_outgoing_relation(rel, fact_id, related_ids, results)
    for rel in _relations_by_direction(flat, "incoming"):
        if await _related_fact_is_accessible(
            rel.get("source_fact"), ownership_manager, user_id, user_org_id, user_group_ids, is_admin
        ):
            _process_incoming_relation(rel, fact_id, related_ids, results)


def _decode_fact_metadata(raw_fact: Dict[str, Any]) -> Dict[str, Any]:
    """knowledge/facts.py hset()s "metadata" as a JSON *string* (#16665 review:
    wrapping it un-decoded read every fact as owner_id=None, denying everyone
    including the owner)."""
    raw = raw_fact.get("metadata")
    if not isinstance(raw, str):
        return raw if isinstance(raw, dict) else {}
    try:
        decoded = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


async def _related_fact_is_accessible(
    related_fact: Dict[str, Any] | None,
    ownership_manager,
    user_id: str,
    user_org_id: str | None,
    user_group_ids: List[str],
    is_admin: bool,
) -> bool:
    """#16665: a related fact reached via the relation graph is filtered the
    same as a direct search result -- a relation is not an access grant."""
    if not related_fact:
        return False
    filtered = await filter_search_results_by_permission(
        [{"id": related_fact.get("id"), "metadata": _decode_fact_metadata(related_fact)}],
        user_id=user_id,
        user_org_id=user_org_id,
        user_group_ids=user_group_ids,
        ownership_manager=ownership_manager,
        is_admin=is_admin,
    )
    return bool(filtered)


def _build_relation_context(rel: Dict[str, Any], total_length: int, max_length: int, context_parts: List[str]) -> int:
    """Build context string from a single relation (Issue #336 - extracted helper)."""
    if not rel.get("target_fact"):
        return total_length
    content = rel["target_fact"].get("content", "")[:300]
    if total_length + len(content) > max_length:
        return total_length
    rel_type = rel.get("type", "related_to")  # #16708: real key is "type"
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
    user_id: str,
    user_org_id: str | None,
    user_group_ids: List[str],
    is_admin: bool,
) -> int:
    """Process relations for citations. (Issue #315 - extracted)

    #16665: a related fact's content only enters the LLM context if
    *user_id* may see it -- a relation is not an access grant.
    """
    ownership_manager = getattr(kb, "ownership_manager", None)
    for citation in citations[:2]:
        if total_length >= max_length:
            break
        fact_id = citation.get("id")
        if not fact_id:
            continue

        relations = await kb.get_fact_relations(fact_id, direction="outgoing", include_fact_details=True)
        # #16708: the result has always been a flat "relations" list -- the
        # direction="outgoing" call already scoped it to outgoing items,
        # there is no separate "outgoing" key to read.
        outgoing = relations.get("relations", []) if relations.get("success") else []
        if not outgoing:
            continue

        context_parts.append("## Related Information\n")
        for rel in outgoing[:2]:
            if await _related_fact_is_accessible(
                rel.get("target_fact"), ownership_manager, user_id, user_org_id, user_group_ids, is_admin
            ):
                total_length = _build_relation_context(rel, total_length, max_length, context_parts)
        context_parts.append("\n")
    return total_length


# Documentation-searcher state, its two standalone routes, and the LLM-context
# doc-processing helpers moved to api/knowledge_search_documentation.py
# (#16665, #14236 file-size ceiling) -- indexed documentation carries no
# per-user ownership/visibility, so it has no fact-visibility concern.
from api.knowledge_search_documentation import (
    get_documentation_searcher,
)
from api.knowledge_search_documentation import process_documentation_context as _process_documentation_context

# #15745: no route here had any auth dependency; anonymous callers could
# search across every knowledge source (facts, graph relations, docs).
router = APIRouter(prefix="/multi-source", tags=["knowledge-multi-source"], dependencies=[Depends(get_current_user)])


# ============================================================================
# Pydantic Models
# ============================================================================


# ============================================================================
# API Endpoints
# ============================================================================


async def _search_facts(
    kb,
    query: str,
    top_k: int,
    result: dict,
    user_id: str,
    user_org_id: str | None,
    user_group_ids: List[str],
    is_admin: bool,
) -> None:
    """
    Search facts via KnowledgeBase.

    Issue #620: Extracted from multi-source search.

    Args:
        kb: Knowledge base instance
        query: Search query
        top_k: Number of results to return
        result: Result dict to populate

    #16665: results are filtered to what *user_id* may see before storing.
    """
    try:
        # Issue #13009: exclude quarantined research facts (#12622).
        fact_results = await kb.search(query, top_k=top_k, filters=RESEARCH_QUARANTINE_FILTER)
        if fact_results.get("results"):
            filtered = await filter_search_results_by_permission(
                fact_results["results"],
                user_id=user_id,
                user_org_id=user_org_id,
                user_group_ids=user_group_ids,
                ownership_manager=getattr(kb, "ownership_manager", None),
                is_admin=is_admin,
            )
            for fact in filtered:
                fact["source"] = "knowledge_base"
            result["facts"] = filtered
        result["sources_searched"].append("facts")
    except Exception as e:
        logger.warning("Fact search failed: %s", e)


async def _search_relations(
    kb, result: dict, user_id: str, user_org_id: str | None, user_group_ids: List[str], is_admin: bool
) -> None:
    """
    Expand facts with graph relations.

    Issue #620: Extracted from multi-source search.

    Args:
        kb: Knowledge base instance
        result: Result dict with facts to expand
    """
    try:
        related_ids: Set[str] = set()
        fact_ids = [f.get("id") or f.get("fact_id") for f in result["facts"]]

        for fact_id in fact_ids[:5]:  # Limit to top 5 to avoid too many queries
            await _expand_fact_relations(
                kb, fact_id, related_ids, result["related_facts"], user_id, user_org_id, user_group_ids, is_admin
            )

        result["sources_searched"].append("relations")
    except Exception as e:
        logger.warning("Relation expansion failed: %s", e)


def _search_documentation(query: str, doc_results_count: int, score_threshold: float, result: dict) -> None:
    """
    Search documentation collection.

    Issue #620: Extracted from multi-source search.

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


@router.post("/search", response_model=KnowledgeMultiSourceSearchResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search",
    error_code_prefix="KNOWLEDGE_SEARCH_AGGREGATOR",
)
async def search(req: Request, body: SearchRequest, current_user: Dict = Depends(get_current_user)):
    """
    Search across all knowledge sources in a multi-source query.

    Issue #620: Refactored to use extracted helper methods.

    Returns results from all sources with source attribution.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    user_id, user_org_id, user_group_ids = extract_user_context_from_request(current_user)
    is_admin = is_admin_role(current_user.get("role"))

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
        await _search_facts(kb, body.query, body.limit, result, user_id, user_org_id, user_group_ids, is_admin)

    # Expand with relations (Issue #620: uses helper)
    if "relations" in body.include_sources and body.expand_relations and kb is not None:
        await _search_relations(kb, result, user_id, user_org_id, user_group_ids, is_admin)

    # Search documentation (Issue #620: uses helper)
    if "documentation" in body.include_sources and body.doc_results > 0:
        _search_documentation(body.query, body.doc_results, body.min_score, result)

    # Calculate totals
    result["total_results"] = len(result["facts"]) + len(result["related_facts"]) + len(result["documentation"])

    return result


@router.get("/stats", response_model=KnowledgeMultiSourceStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stats",
    error_code_prefix="KNOWLEDGE_SEARCH_AGGREGATOR",
)
async def stats(req: Request):
    """Get statistics from all multi-source knowledge endpoints (KB facts, relations, docs). Ref: #1088."""
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


@router.post("/context", response_model=KnowledgeMultiSourceContextResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_llm_context",
    error_code_prefix="KNOWLEDGE_SEARCH_AGGREGATOR",
)
async def get_llm_context(req: Request, body: ContextRequest, current_user: Dict = Depends(get_current_user)):
    """
    Get formatted context for LLM prompts from multi-source knowledge endpoints.

    Retrieves and formats knowledge from all sources into a context string
    suitable for inclusion in LLM prompts.

    Returns:
    - Formatted context string
    - Source citations
    - Metadata about retrieved content

    #16665: every fact entering the context is filtered to what the calling
    user may see -- this feeds an LLM prompt, not just a display list.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    user_id, user_org_id, user_group_ids = extract_user_context_from_request(current_user)
    is_admin = is_admin_role(current_user.get("role"))

    context_parts: List[str] = []
    citations: List[Dict] = []
    total_length = 0

    # Search facts (Issue #315: use extracted helper)
    if kb is not None:
        try:
            # Issue #13009: exclude quarantined research facts (#12622).
            fact_results = await kb.search(body.query, top_k=5, filters=RESEARCH_QUARANTINE_FILTER)
            fact_results["results"] = await filter_search_results_by_permission(
                fact_results.get("results", []),
                user_id=user_id,
                user_org_id=user_org_id,
                user_group_ids=user_group_ids,
                ownership_manager=getattr(kb, "ownership_manager", None),
                is_admin=is_admin,
            )
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
                kb,
                citations,
                body.max_context_length,
                context_parts,
                total_length,
                user_id,
                user_org_id,
                user_group_ids,
                is_admin,
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


# /documentation/search and /documentation/stats moved to
# api/knowledge_search_documentation.py (#16665, #14236 file-size ceiling).

# ============================================================================
# Multi-Source Knowledge Graph Endpoint (for KnowledgeGraph.vue)
# ============================================================================


def _create_category_node(category: Dict[str, Any]) -> Dict[str, Any]:
    """Create a graph node from a category.

    Issue #707: Extracted helper for multi-source graph building.
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

    Issue #707: Extracted helper for multi-source graph building.
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
            "category": fact.get("category", CategoryDefaults.GENERAL),
            "source": fact.get("source", "knowledge_base"),
            "confidence": fact.get("confidence", 1.0),
        },
        "created_at": int(fact.get("created_at", 0)),
    }


def _process_category_tree(
    tree: List[Dict[str, Any]],
    nodes: List[Dict],
    edges: List[Dict],
    parent_id: str | None = None,
) -> None:
    """Recursively process category tree into nodes and edges.

    Issue #707: Extracted helper for multi-source graph building.
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
    kb: Any,
    category_filter: str | None,
    max_facts: int,
    user_id: str,
    user_org_id: str | None,
    user_group_ids: List[str],
    is_admin: bool,
) -> List[Dict[str, Any]]:
    """Get facts for the graph with optional category filtering.

    Issue #707: Extracted helper for multi-source graph building.

    #16665: the returned facts (and, transitively, every fact_id the graph's
    relation edges reach -- _get_fact_relations_for_graph only ever sees IDs
    this function already returned) are filtered to what *user_id* may see.
    """
    if category_filter:
        # get_facts_in_category's facts carry metadata JSON-encoded, unlike
        # kb.search()'s already-decoded results -- _decode_fact_metadata fixes
        # the shape before filtering (#16665 review).
        result = await kb.get_facts_in_category(category_id=category_filter, include_descendants=True, limit=max_facts)
        raw_facts = result.get("facts", []) if result.get("success") else []
        facts = [{**fact, "metadata": _decode_fact_metadata(fact)} for fact in raw_facts]
    else:
        # Search for recent facts
        # Issue #13009: exclude quarantined research facts (#12622).
        result = await kb.search("*", top_k=max_facts, filters=RESEARCH_QUARANTINE_FILTER)
        facts = result.get("results", [])

    return await filter_search_results_by_permission(
        facts,
        user_id=user_id,
        user_org_id=user_org_id,
        user_group_ids=user_group_ids,
        ownership_manager=getattr(kb, "ownership_manager", None),
        is_admin=is_admin,
    )


async def _get_fact_relations_for_graph(kb: Any, fact_ids: List[str], max_relations: int = 100) -> List[Dict[str, Any]]:
    """Get relations between facts for the graph.

    Issue #707: Extracted helper for multi-source graph building.
    """
    relations = []
    relation_set = set()

    for fact_id in fact_ids[:20]:  # Limit to first 20 to avoid too many queries
        try:
            result = await kb.get_fact_relations(fact_id, direction="both", include_fact_details=False)
            if not result.get("success"):
                continue

            # #16708: flat "relations" list, partitioned by "direction" --
            # "outgoing" was never a top-level key. Per-item keys are
            # "to"/"type" (never "target_id"/"relation_type"); "strength"
            # has never existed on this shape, hence the default only.
            outgoing = _relations_by_direction(result.get("relations", []), "outgoing")
            for rel in outgoing[:5]:  # Limit per fact
                target_id = rel.get("to")
                if not target_id or target_id not in fact_ids:
                    continue
                key = f"{fact_id}-{target_id}"
                if key not in relation_set:
                    relation_set.add(key)
                    relations.append(
                        {
                            "from": fact_id,
                            "to": target_id,
                            "type": rel.get("type", "related_to"),
                            "strength": rel.get("strength", 0.8),
                        }
                    )

            if len(relations) >= max_relations:
                break
        except Exception:  # nosec B112  # continue on single fact failure is intentional
            continue

    return relations


def _create_dynamic_category_nodes(facts: List[Dict[str, Any]], nodes: List[Dict], edges: List[Dict]) -> Dict[str, str]:
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
        category = fact.get("category", CategoryDefaults.GENERAL)
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

    Issue #665: Extracted from get_multi_source_graph.

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
        tree_result = await kb.get_category_tree(root_id=None, max_depth=body.max_depth, include_fact_counts=True)
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

    Issue #665: Extracted from get_multi_source_graph.

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
        category = fact.get("category", CategoryDefaults.GENERAL)
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


def _update_category_fact_counts(nodes: List[Dict], facts: List[Dict[str, Any]]) -> None:
    """Update fact counts in category nodes.

    Issue #665: Extracted from get_multi_source_graph.

    Args:
        nodes: List of graph nodes
        facts: List of facts to count per category
    """
    for node in nodes:
        if node["type"] == "category":
            cat_path = node.get("metadata", {}).get("path", "")
            cat_name = cat_path.split("/")[-1] if cat_path else node["id"].replace("cat_", "")
            count = sum(1 for f in facts if f.get("category") == cat_name)
            node["metadata"]["fact_count"] = count


@router.post("/graph", response_model=KnowledgeMultiSourceGraphResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_multi_source_graph",
    error_code_prefix="KNOWLEDGE_SEARCH_AGGREGATOR",
)
async def get_multi_source_graph(req: Request, body: GraphRequest, current_user: Dict = Depends(get_current_user)):
    """
    Get multi-source knowledge graph combining categories, facts, and relations.

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
    user_id, user_org_id, user_group_ids = extract_user_context_from_request(current_user)
    is_admin = is_admin_role(current_user.get("role"))

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []

    # Process category tree and get category map
    category_map = await _process_category_tree_for_graph(kb, body, nodes, edges)

    # Get facts for the graph
    facts: List[Dict[str, Any]] = []
    if kb is not None:
        try:
            facts = await _get_facts_for_graph(
                kb, body.category_filter, body.max_facts, user_id, user_org_id, user_group_ids, is_admin
            )
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


@router.get("/graph", response_model=KnowledgeMultiSourceGraphResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_multi_source_graph_simple",
    error_code_prefix="KNOWLEDGE_SEARCH_AGGREGATOR",
)
async def get_multi_source_graph_simple(
    req: Request,
    max_facts: int = Query(50, ge=1, le=200, description="Maximum facts to include"),
    include_categories: bool = Query(True, description="Include category nodes"),
    current_user: Dict = Depends(get_current_user),
):
    """
    GET version of multi-source graph for simple requests.

    Returns a multi-source knowledge graph with default settings.
    For more control, use POST /multi-source/graph with GraphRequest body.
    """
    body = GraphRequest(
        max_facts=max_facts,
        include_categories=include_categories,
    )
    return await get_multi_source_graph(req, body, current_user)
