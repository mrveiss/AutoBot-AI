"""Knowledge Base API endpoints for content management and search with RAG integration."""

import asyncio
import hashlib
import json
import logging
import re
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path as PathLib
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field, validator

from backend.background_vectorization import get_background_vectorizer
from backend.knowledge_factory import get_or_create_knowledge_base
from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Import RAG Agent for enhanced search capabilities
try:
    from src.agents.rag_agent import get_rag_agent

    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logging.warning("RAG Agent not available - enhanced search features disabled")

# Set up logging
logger = logging.getLogger(__name__)

router = APIRouter()


# ===== PYDANTIC MODELS FOR INPUT VALIDATION =====


class FactIdValidator(BaseModel):
    """Validator for fact ID format and security"""

    fact_id: str = Field(..., min_length=1, max_length=255)

    @validator("fact_id")
    def validate_fact_id(cls, v):
        """Validate fact_id format to prevent injection attacks"""
        # Allow UUID format or safe alphanumeric with underscores/hyphens
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "Invalid fact_id format: only alphanumeric, underscore, and hyphen allowed"
            )
        # Prevent path traversal attempts
        if ".." in v or "/" in v or "\\" in v:
            raise ValueError("Path traversal not allowed in fact_id")
        return v


class SearchRequest(BaseModel):
    """Request model for search endpoints"""

    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=100)
    category: Optional[str] = Field(default=None, max_length=100)

    @validator("category")
    def validate_category(cls, v):
        """Validate category format"""
        if v and not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid category format")
        return v


class PaginationRequest(BaseModel):
    """Request model for pagination"""

    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    cursor: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = Field(default=None, max_length=100)

    @validator("cursor")
    def validate_cursor(cls, v):
        """Validate cursor format"""
        if v and not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid cursor format")
        return v

    @validator("category")
    def validate_category(cls, v):
        """Validate category format"""
        if v and not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Invalid category format")
        return v


class AddTextRequest(BaseModel):
    """Request model for adding text to knowledge base"""

    text: str = Field(..., min_length=1, max_length=1000000)
    metadata: Optional[Dict[str, Any]] = Field(default=None)
    category: Optional[str] = Field(default="general", max_length=100)

    @validator("metadata")
    def validate_metadata(cls, v):
        """Validate metadata structure"""
        if v is not None and not isinstance(v, dict):
            raise ValueError("Metadata must be a dictionary")
        return v


# ===== HELPER FUNCTIONS FOR BATCH VECTORIZATION STATUS =====


def _generate_cache_key(fact_ids: List[str]) -> str:
    """
    Generate deterministic cache key for a list of fact IDs.

    Args:
        fact_ids: List of fact IDs to check

    Returns:
        MD5 hash of sorted fact IDs
    """
    sorted_ids = sorted(fact_ids)
    ids_str = ",".join(sorted_ids)
    return hashlib.md5(ids_str.encode()).hexdigest()


async def _check_vectorization_batch_internal(
    kb_instance, fact_ids: List[str], include_dimensions: bool = False
) -> Dict[str, Any]:
    """
    Internal helper to check vectorization status for multiple facts using Redis pipeline.

    Args:
        kb_instance: KnowledgeBase instance
        fact_ids: List of fact IDs to check
        include_dimensions: Whether to include vector dimensions in response

    Returns:
        Dict with statuses and summary statistics
    """
    start_time = time.time()

    # Build vector keys
    vector_keys = [f"llama_index/vector_{fact_id}" for fact_id in fact_ids]

    # Use Redis pipeline for batch EXISTS checks (single roundtrip)
    try:
        pipeline = kb_instance.redis_client.pipeline()
        for vector_key in vector_keys:
            pipeline.exists(vector_key)

        # Execute pipeline (wrap in to_thread to avoid blocking event loop)
        results = await asyncio.to_thread(pipeline.execute)

        # Build status map
        statuses = {}
        vectorized_count = 0

        for i, fact_id in enumerate(fact_ids):
            exists = bool(results[i])

            if exists:
                vectorized_count += 1
                status_entry = {"vectorized": True}

                # Optionally include dimensions
                if include_dimensions:
                    # Get embedding dimensions from knowledge base config
                    # Default to 768 for nomic-embed-text
                    dimensions = getattr(kb_instance, "embedding_dimensions", 768)
                    status_entry["dimensions"] = dimensions

                statuses[fact_id] = status_entry
            else:
                statuses[fact_id] = {"vectorized": False}

        # Calculate summary statistics
        total_checked = len(fact_ids)
        not_vectorized_count = total_checked - vectorized_count
        vectorization_percentage = (
            (vectorized_count / total_checked * 100) if total_checked > 0 else 0.0
        )

        check_time_ms = (time.time() - start_time) * 1000

        return {
            "statuses": statuses,
            "summary": {
                "total_checked": total_checked,
                "vectorized": vectorized_count,
                "not_vectorized": not_vectorized_count,
                "vectorization_percentage": round(vectorization_percentage, 2),
            },
            "check_time_ms": round(check_time_ms, 2),
        }

    except Exception as e:
        logger.error(f"Error checking vectorization batch: {e}")
        raise


# ===== ENDPOINTS =====


@router.get("/stats")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_stats",
    error_code_prefix="KNOWLEDGE",
)
async def get_knowledge_stats(req: Request):
    """Get knowledge base statistics - FIXED to use proper instance"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "total_documents": 0,
            "total_chunks": 0,
            "total_facts": 0,
            "total_vectors": 0,
            "categories": [],
            "db_size": 0,
            "status": "offline",
            "last_updated": None,
            "redis_db": None,
            "index_name": None,
            "initialized": False,
            "rag_available": RAG_AVAILABLE,
            "vectorization_stats": {
                "total_facts": 0,
                "vectorized_count": 0,
                "not_vectorized_count": 0,
                "vectorization_percentage": 0.0,
            },
        }

    stats = await kb_to_use.get_stats()
    stats["rag_available"] = RAG_AVAILABLE

    # Vectorization stats removed - get_stats() already provides fact counts using async operations
    # The previous implementation used synchronous redis_client.hgetall() which blocked the event loop

    return stats


@router.get("/test_categories_main")
async def test_main_categories():
    """Test endpoint to verify file is loaded"""
    from backend.knowledge_categories import CATEGORY_METADATA

    return {"status": "working", "categories": list(CATEGORY_METADATA.keys())}


@router.get("/stats/basic")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_stats_basic",
    error_code_prefix="KNOWLEDGE",
)
async def get_knowledge_stats_basic(req: Request):
    """Get basic knowledge base statistics for quick display"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {"total_facts": 0, "total_vectors": 0, "status": "offline"}

    stats = await kb_to_use.get_stats()

    # Return lightweight basic stats
    return {
        "total_facts": stats.get("total_facts", 0),
        "total_vectors": stats.get("total_vectors", 0),
        "categories": stats.get("categories", []),
        "status": "online" if stats.get("initialized", False) else "offline",
    }


@router.get("/categories/main")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_main_categories",
    error_code_prefix="KNOWLEDGE",
)
async def get_main_categories(req: Request):
    """
    Get the 3 main knowledge base categories with their metadata and stats.
    OPTIMIZED: Uses cached category counts for fast response (<50ms).

    Returns:
        {
            "categories": [
                {
                    "id": "autobot-documentation",
                    "name": "AutoBot Documentation",
                    "description": "AutoBot's documentation, guides, and technical references",
                    "icon": "fas fa-book",
                    "color": "#3b82f6",
                    "count": 150
                },
                ...
            ]
        }
    """
    from backend.knowledge_categories import (
        CATEGORY_METADATA,
        KnowledgeCategory,
        get_category_for_source,
    )

    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    logger.info(
        f"get_main_categories - kb_to_use: {kb_to_use is not None}, has_redis: {kb_to_use.aioredis_client is not None if kb_to_use else False}"
    )

    # Initialize category counts
    category_counts = {
        KnowledgeCategory.AUTOBOT_DOCUMENTATION: 0,
        KnowledgeCategory.SYSTEM_KNOWLEDGE: 0,
        KnowledgeCategory.USER_KNOWLEDGE: 0,
    }

    # PERFORMANCE FIX: Use cached category counts instead of scanning all facts
    # Scanning 393 facts and parsing JSON metadata takes seconds
    # Use pre-computed counts stored in Redis for instant lookups (<50ms)
    if kb_to_use and kb_to_use.aioredis_client:
        logger.info("Attempting to get cached category counts...")
        try:
            # Try to get cached counts first (instant lookup)
            cache_keys = {
                KnowledgeCategory.AUTOBOT_DOCUMENTATION: "kb:stats:category:autobot-documentation",
                KnowledgeCategory.SYSTEM_KNOWLEDGE: "kb:stats:category:system-knowledge",
                KnowledgeCategory.USER_KNOWLEDGE: "kb:stats:category:user-knowledge",
            }

            cached_values = await kb_to_use.aioredis_client.mget(
                list(cache_keys.values())
            )

            # Check if all cache values exist
            if all(v is not None for v in cached_values):
                # Use cached values
                for i, cat_id in enumerate(cache_keys.keys()):
                    category_counts[cat_id] = int(cached_values[i])
                logger.debug(f"Using cached category counts: {category_counts}")
            else:
                # Cache miss - compute counts the slow way
                logger.info("Cache miss - computing category counts from all facts")

                # Get all facts from knowledge base
                all_facts = await kb_to_use.get_all_facts()

                logger.info(
                    f"Categorizing {len(all_facts)} facts into main categories"
                )

                # Categorize each fact based on its source/metadata
                for fact in all_facts:
                    # Get source from fact metadata
                    source = fact.get("metadata", {}).get("source", "") or fact.get(
                        "source", ""
                    )
                    if not source:
                        # Try to get filename or title as fallback
                        source = fact.get("metadata", {}).get(
                            "filename", ""
                        ) or fact.get("title", "")

                    # Map to main category
                    main_category = get_category_for_source(source)
                    if main_category in category_counts:
                        category_counts[main_category] += 1

                logger.info(f"Category counts: {category_counts}")

                # Cache the counts for 60 seconds
                for cat_id, cache_key in cache_keys.items():
                    await kb_to_use.aioredis_client.set(
                        cache_key, category_counts[cat_id], ex=60
                    )

        except Exception as e:
            logger.error(f"Error categorizing facts: {e}")
            # Fallback: just show 0 if we can't categorize
            pass

    # Build main categories with counts
    main_categories = []
    for cat_id, meta in CATEGORY_METADATA.items():
        count = category_counts.get(cat_id, 0)

        main_categories.append(
            {
                "id": cat_id,
                "name": meta["name"],
                "description": meta["description"],
                "icon": meta["icon"],
                "color": meta["color"],
                "examples": meta["examples"],
                "count": count,
            }
        )

    return {"categories": main_categories, "total": len(main_categories)}


@router.post("/vectorization_status")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_vectorization_status_batch",
    error_code_prefix="KNOWLEDGE",
)
async def check_vectorization_status_batch(request: dict, req: Request):
    """
    Check vectorization status for multiple facts in a single efficient batch operation.

    This endpoint uses Redis pipeline for optimal performance, checking 100-1000 facts
    with a single Redis roundtrip. Results are cached with TTL to reduce Redis load.

    Args:
        request: {
            "fact_ids": ["id1", "id2", ...],  # Required: List of fact IDs to check
            "include_dimensions": bool,        # Optional: Include vector dimensions (default: false)
            "use_cache": bool                  # Optional: Use cached results (default: true)
        }

    Returns:
        {
            "statuses": {
                "fact-id-1": {"vectorized": true, "dimensions": 768},
                "fact-id-2": {"vectorized": false}
            },
            "summary": {
                "total_checked": 1000,
                "vectorized": 750,
                "not_vectorized": 250,
                "vectorization_percentage": 75.0
            },
            "cached": false,
            "check_time_ms": 45.2
        }

    Performance:
        - Batch size: Up to 1000 facts per request
        - Single Redis roundtrip using pipeline
        - Cache TTL: 60 seconds (configurable)
        - Typical response time: <50ms for 1000 facts
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        raise InternalError(
            "Knowledge base not initialized - please check logs for errors"
        )

    # Extract parameters
    fact_ids = request.get("fact_ids", [])
    include_dimensions = request.get("include_dimensions", False)
    use_cache = request.get("use_cache", True)

    # Validate input
    if not fact_ids:
        return {
            "statuses": {},
            "summary": {
                "total_checked": 0,
                "vectorized": 0,
                "not_vectorized": 0,
                "vectorization_percentage": 0.0,
            },
            "cached": False,
            "check_time_ms": 0.0,
            "message": "No fact IDs provided",
        }

    if len(fact_ids) > 1000:
        raise ValueError(
            f"Too many fact IDs ({len(fact_ids)}). Maximum 1000 per request."
        )

    # Generate cache key
    cache_key = f"cache:vectorization_status:{_generate_cache_key(fact_ids)}"
    cached_result = None

    # Try cache if enabled
    if use_cache:
        try:
            cached_json = kb_to_use.redis_client.get(cache_key)
            if cached_json:
                cached_result = json.loads(cached_json)
                cached_result["cached"] = True
                logger.debug(
                    f"Cache hit for vectorization status ({len(fact_ids)} facts)"
                )
                return cached_result
        except Exception as cache_err:
            logger.debug(
                f"Cache read failed (continuing without cache): {cache_err}"
            )

    # Cache miss - perform batch check
    logger.info(
        f"Checking vectorization status for {len(fact_ids)} facts (batch operation)"
    )

    result = await _check_vectorization_batch_internal(
        kb_to_use, fact_ids, include_dimensions
    )

    result["cached"] = False

    # Cache the result (TTL: 60 seconds)
    if use_cache:
        try:
            kb_to_use.redis_client.setex(
                cache_key, 60, json.dumps(result)  # 60 second TTL
            )
            logger.debug(f"Cached vectorization status for {len(fact_ids)} facts")
        except Exception as cache_err:
            logger.warning(f"Failed to cache vectorization status: {cache_err}")

    return result


@router.get("/categories")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_categories",
    error_code_prefix="KNOWLEDGE",
)
async def get_knowledge_categories(req: Request):
    """Get all knowledge base categories with fact counts"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {"categories": [], "total": 0}

    # Get stats - await async method
    stats = await kb_to_use.get_stats() if hasattr(kb_to_use, "get_stats") else {}
    categories_list = stats.get("categories", [])

    # Get all facts to count by category - sync redis operation
    try:
        all_facts_data = kb_to_use.redis_client.hgetall("knowledge_base:facts")
    except Exception as redis_err:
        logger.debug(f"Redis error getting facts: {redis_err}")
        all_facts_data = {}

    category_counts = {}
    for fact_json in all_facts_data.values():
        try:
            fact = json.loads(fact_json)
            category = fact.get("metadata", {}).get("category", "uncategorized")
            category_counts[category] = category_counts.get(category, 0) + 1
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Error parsing fact JSON: {e}")
            continue

    # Format for frontend with counts
    categories = [
        {"name": cat, "count": category_counts.get(cat, 0), "id": cat}
        for cat in categories_list
    ]

    return {"categories": categories, "total": len(categories)}


@router.post("/add_text")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_text_to_knowledge",
    error_code_prefix="KNOWLEDGE",
)
async def add_text_to_knowledge(request: dict, req: Request):
    """Add text to knowledge base - FIXED to use proper instance"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        raise InternalError(
            "Knowledge base not initialized - please check logs for errors"
        )

    text = request.get("text", "")
    title = request.get("title", "")
    source = request.get("source", "manual")
    category = request.get("category", "general")

    if not text:
        raise ValueError("Text content is required")

    logger.info(
        f"Adding text to knowledge: title='{title}', source='{source}', length={len(text)}"
    )

    # Use the store_fact method for KnowledgeBaseV2 or add_fact for compatibility
    if hasattr(kb_to_use, "store_fact"):
        # KnowledgeBaseV2
        result = await kb_to_use.store_fact(
            content=text,
            metadata={"title": title, "source": source, "category": category},
        )
        fact_id = result.get("fact_id")
    else:
        # Original KnowledgeBase
        result = await kb_to_use.store_fact(
            text=text,
            metadata={"title": title, "source": source, "category": category},
        )
        fact_id = result.get("fact_id")

    return {
        "status": "success",
        "message": "Fact stored successfully",
        "fact_id": fact_id,
        "text_length": len(text),
        "title": title,
        "source": source,
    }


@router.post("/search")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_knowledge",
    error_code_prefix="KB",
)
async def search_knowledge(request: dict, req: Request):
    """Search knowledge base with optional RAG enhancement - FIXED parameter mismatch between KnowledgeBase and KnowledgeBaseV2"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "results": [],
            "total_results": 0,
            "message": "Knowledge base not initialized - please check logs for errors",
        }

    query = request.get("query", "")
    top_k = request.get("top_k", 10)
    limit = request.get("limit", 10)  # Also accept 'limit' for compatibility
    mode = request.get("mode", "auto")
    use_rag = request.get("use_rag", False)  # New parameter for RAG enhancement

    # Use limit if provided, otherwise use top_k
    search_limit = limit if request.get("limit") is not None else top_k

    logger.info(
        f"Knowledge search request: '{query}' (top_k={search_limit}, mode={mode}, use_rag={use_rag})"
    )

    # Check if knowledge base is empty - fast check to avoid timeout
    try:
        stats = await kb_to_use.get_stats()
        fact_count = stats.get("total_facts", 0)

        if fact_count == 0:
            logger.info(
                "Knowledge base is empty - returning empty results immediately"
            )
            return {
                "results": [],
                "total_results": 0,
                "query": query,
                "mode": mode,
                "kb_implementation": kb_to_use.__class__.__name__,
                "message": "Knowledge base is empty - no documents to search. Add documents in the Manage tab.",
            }
    except Exception as stats_err:
        logger.warning(f"Could not check KB stats: {stats_err}")

    # FIXED: Check which knowledge base implementation we're using and call with correct parameters
    kb_class_name = kb_to_use.__class__.__name__

    if kb_class_name == "KnowledgeBaseV2":
        # KnowledgeBaseV2 uses 'top_k' parameter
        results = await kb_to_use.search(query=query, top_k=search_limit)
    else:
        # Original KnowledgeBase uses 'similarity_top_k' parameter
        results = await kb_to_use.search(
            query=query, similarity_top_k=search_limit, mode=mode
        )

    # Enhanced search with RAG if requested and available
    if use_rag and RAG_AVAILABLE and results:
        try:
            rag_enhancement = await _enhance_search_with_rag(query, results)
            return {
                "results": results,
                "total_results": len(results),
                "query": query,
                "mode": mode,
                "kb_implementation": kb_class_name,
                "rag_enhanced": True,
                "rag_analysis": rag_enhancement,
            }
        except Exception as e:
            logger.error(f"RAG enhancement failed: {e}")
            # Continue with regular results if RAG fails

    return {
        "results": results,
        "total_results": len(results),
        "query": query,
        "mode": mode,
        "kb_implementation": kb_class_name,
        "rag_enhanced": False,
    }


@router.post("/rag_search")
async def rag_enhanced_search(request: dict, req: Request):
    """RAG-enhanced knowledge search for comprehensive document synthesis"""
    try:
        if not RAG_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="RAG functionality not available - AI Stack may not be running",
            )

        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "status": "error",
                "synthesized_response": "",
                "results": [],
                "message": "Knowledge base not initialized - please check logs for errors",
            }

        query = request.get("query", "")
        top_k = request.get("top_k", 10)
        limit = request.get("limit", 10)
        reformulate_query = request.get("reformulate_query", True)

        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        # Use limit if provided, otherwise use top_k
        search_limit = limit if request.get("limit") is not None else top_k

        logger.info(
            f"RAG-enhanced search request: '{query}' (top_k={search_limit}, reformulate={reformulate_query})"
        )

        # Check if knowledge base is empty - fast check to avoid timeout
        try:
            stats = await kb_to_use.get_stats()
            fact_count = stats.get("total_facts", 0)

            if fact_count == 0:
                logger.info(
                    "Knowledge base is empty - returning empty RAG results immediately"
                )
                return {
                    "status": "success",
                    "synthesized_response": "The knowledge base is currently empty. Please add documents in the Manage tab to enable search functionality.",
                    "results": [],
                    "query": query,
                    "reformulated_query": query,
                    "rag_analysis": {
                        "relevance_score": 0.0,
                        "confidence": 0.0,
                        "sources_used": 0,
                        "synthesis_quality": "empty_kb",
                    },
                    "message": "Knowledge base is empty",
                }
        except Exception as stats_err:
            logger.warning(f"Could not check KB stats: {stats_err}")

        # Step 1: Query reformulation if requested
        original_query = query
        reformulated_queries = [query]

        if reformulate_query:
            try:
                rag_agent = get_rag_agent()
                reformulation_result = await rag_agent.reformulate_query(query)

                if reformulation_result.get("status") == "success":
                    additional_queries = reformulation_result.get(
                        "reformulated_queries", []
                    )
                    reformulated_queries.extend(
                        additional_queries[:3]
                    )  # Limit to avoid too many queries

            except Exception as e:
                logger.warning(f"Query reformulation failed: {e}")

        # Step 2: Search with all queries
        all_results = []
        seen_content = set()

        for search_query in reformulated_queries:
            try:
                # Get search results
                kb_class_name = kb_to_use.__class__.__name__

                if kb_class_name == "KnowledgeBaseV2":
                    query_results = await kb_to_use.search(
                        query=search_query, top_k=search_limit
                    )
                else:
                    query_results = await kb_to_use.search(
                        query=search_query, similarity_top_k=search_limit
                    )

                # Deduplicate results
                for result in query_results:
                    content = result.get("content", "")
                    if content and content not in seen_content:
                        seen_content.add(content)
                        result["source_query"] = search_query
                        all_results.append(result)

            except Exception as e:
                logger.error(f"Search failed for query '{search_query}': {e}")

        # Step 3: Limit total results
        all_results = all_results[:search_limit]

        # Step 4: RAG processing for synthesis
        if all_results:
            try:
                rag_agent = get_rag_agent()

                # Convert results to RAG-compatible format
                documents = []
                for result in all_results:
                    documents.append(
                        {
                            "content": result.get("content", ""),
                            "metadata": {
                                "filename": result.get("metadata", {}).get(
                                    "title", "Unknown"
                                ),
                                "source": result.get("metadata", {}).get(
                                    "source", "knowledge_base"
                                ),
                                "category": result.get("metadata", {}).get(
                                    "category", "general"
                                ),
                                "score": result.get("score", 0.0),
                                "source_query": result.get(
                                    "source_query", original_query
                                ),
                            },
                        }
                    )

                # Process with RAG agent
                rag_result = await rag_agent.process_document_query(
                    query=original_query,
                    documents=documents,
                    context={"reformulated_queries": reformulated_queries},
                )

                return {
                    "status": "success",
                    "synthesized_response": rag_result.get("synthesized_response", ""),
                    "confidence_score": rag_result.get("confidence_score", 0.0),
                    "document_analysis": rag_result.get("document_analysis", {}),
                    "sources_used": rag_result.get("sources_used", []),
                    "results": all_results,
                    "total_results": len(all_results),
                    "original_query": original_query,
                    "reformulated_queries": (
                        reformulated_queries[1:]
                        if len(reformulated_queries) > 1
                        else []
                    ),
                    "kb_implementation": kb_to_use.__class__.__name__,
                    "agent_metadata": rag_result.get("metadata", {}),
                    "rag_enhanced": True,
                }

            except Exception as e:
                logger.error(f"RAG processing failed: {e}")
                # Return search results without synthesis
                return {
                    "status": "partial_success",
                    "synthesized_response": f"Found {len(all_results)} relevant documents but synthesis failed: {str(e)}",
                    "results": all_results,
                    "total_results": len(all_results),
                    "original_query": original_query,
                    "reformulated_queries": (
                        reformulated_queries[1:]
                        if len(reformulated_queries) > 1
                        else []
                    ),
                    "error": str(e),
                    "rag_enhanced": False,
                }
        else:
            return {
                "status": "success",
                "synthesized_response": f"No relevant documents found for query: '{original_query}'",
                "results": [],
                "total_results": 0,
                "original_query": original_query,
                "reformulated_queries": (
                    reformulated_queries[1:] if len(reformulated_queries) > 1 else []
                ),
                "rag_enhanced": True,
            }

    except Exception as e:
        logger.error(f"Error in RAG-enhanced search: {str(e)}")
        raise HTTPException(status_code=500, detail=f"RAG search failed: {str(e)}")


@router.post("/similarity_search")
async def similarity_search(request: dict, req: Request):
    """Perform similarity search with optional RAG enhancement - FIXED parameter mismatch between KnowledgeBase and KnowledgeBaseV2"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "results": [],
                "total_results": 0,
                "message": "Knowledge base not initialized - please check logs for errors",
            }

        query = request.get("query", "")
        top_k = request.get("top_k", 10)
        threshold = request.get("threshold", 0.7)
        use_rag = request.get("use_rag", False)

        logger.info(
            f"Similarity search request: '{query}' (top_k={top_k}, threshold={threshold}, use_rag={use_rag})"
        )

        # FIXED: Check which knowledge base implementation we're using and call with correct parameters
        kb_class_name = kb_to_use.__class__.__name__

        if kb_class_name == "KnowledgeBaseV2":
            # KnowledgeBaseV2 uses 'top_k' parameter
            results = await kb_to_use.search(query=query, top_k=top_k)
        else:
            # Original KnowledgeBase uses 'similarity_top_k' parameter
            results = await kb_to_use.search(query=query, similarity_top_k=top_k)

        # Filter by threshold if specified
        if threshold > 0:
            filtered_results = []
            for result in results:
                if result.get("score", 0) >= threshold:
                    filtered_results.append(result)
            results = filtered_results

        # Enhanced search with RAG if requested and available
        if use_rag and RAG_AVAILABLE and results:
            try:
                rag_enhancement = await _enhance_search_with_rag(query, results)
                return {
                    "results": results,
                    "total_results": len(results),
                    "query": query,
                    "threshold": threshold,
                    "kb_implementation": kb_class_name,
                    "rag_enhanced": True,
                    "rag_analysis": rag_enhancement,
                }
            except Exception as e:
                logger.error(f"RAG enhancement failed: {e}")
                # Continue with regular results if RAG fails

        return {
            "results": results,
            "total_results": len(results),
            "query": query,
            "threshold": threshold,
            "kb_implementation": kb_class_name,
            "rag_enhanced": False,
        }

    except Exception as e:
        logger.error(f"Error in similarity search: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Similarity search failed: {str(e)}"
        )


@router.get("/health")
@with_error_handling(
    category=ErrorCategory.SERVICE_UNAVAILABLE,
    operation="get_knowledge_health",
    error_code_prefix="KB",
)
async def get_knowledge_health(req: Request):
    """Get knowledge base health status with RAG capability status - FIXED to use proper instance"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "status": "unhealthy",
            "initialized": False,
            "redis_connected": False,
            "vector_store_available": False,
            "rag_available": RAG_AVAILABLE,
            "rag_status": "disabled" if not RAG_AVAILABLE else "unknown",
            "message": "Knowledge base not initialized",
        }

    # Try to get stats to verify health
    stats = await kb_to_use.get_stats()

    # Check RAG Agent health if available
    rag_status = "disabled"
    if RAG_AVAILABLE:
        try:
            rag_agent = get_rag_agent()
            # Simple test to verify RAG agent works
            rag_status = "healthy"
        except Exception as e:
            rag_status = f"error: {str(e)}"

    return {
        "status": "healthy",
        "initialized": stats.get("initialized", False),
        "redis_connected": True,
        "vector_store_available": stats.get("index_available", False),
        "total_facts": stats.get("total_facts", 0),
        "db_size": stats.get("db_size", 0),
        "kb_implementation": kb_to_use.__class__.__name__,
        "rag_available": RAG_AVAILABLE,
        "rag_status": rag_status,
    }


# === NEW REPOPULATE ENDPOINTS ===


@router.post("/populate_system_commands")
async def populate_system_commands(request: dict, req: Request):
    """Populate knowledge base with common system commands and usage examples"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "status": "error",
                "message": "Knowledge base not initialized - please check logs for errors",
                "items_added": 0,
            }

        logger.info("Starting system commands population...")

        # Define common system commands with descriptions and examples
        system_commands = [
            {
                "command": "curl",
                "description": "Command line tool for transferring data with URLs",
                "usage": "curl [options] <url>",
                "examples": [
                    "curl https://api.example.com/data",
                    "curl -X POST -d 'data' https://api.example.com",
                    "curl -H 'Authorization: Bearer token' https://api.example.com",
                    "curl -o output.html https://example.com",
                ],
                "options": [
                    "-X: HTTP method (GET, POST, PUT, DELETE)",
                    "-H: Add header",
                    "-d: Data to send",
                    "-o: Output to file",
                    "-v: Verbose output",
                    "--json: Send JSON data",
                ],
            },
            {
                "command": "grep",
                "description": "Search text patterns in files",
                "usage": "grep [options] pattern [file...]",
                "examples": [
                    "grep 'error' /var/log/syslog",
                    "grep -r 'function' /path/to/code/",
                    "grep -i 'warning' *.log",
                    "ps aux | grep python",
                ],
                "options": [
                    "-r: Recursive search",
                    "-i: Case insensitive",
                    "-n: Line numbers",
                    "-v: Invert match",
                    "-l: Files with matches only",
                ],
            },
            {
                "command": "ssh",
                "description": "Secure Shell for remote login and command execution",
                "usage": "ssh [options] [user@]hostname [command]",
                "examples": [
                    "ssh user@remote-server",
                    "ssh -i ~/.ssh/key user@server",
                    "ssh -p 2222 user@server",
                    "ssh user@server 'ls -la'",
                ],
                "options": [
                    "-i: Identity file (private key)",
                    "-p: Port number",
                    "-v: Verbose output",
                    "-X: Enable X11 forwarding",
                    "-L: Local port forwarding",
                ],
            },
            {
                "command": "docker",
                "description": "Container platform for building, running and managing applications",
                "usage": "docker [options] COMMAND",
                "examples": [
                    "docker run -it ubuntu bash",
                    "docker build -t myapp .",
                    "docker ps -a",
                    "docker exec -it container_name bash",
                ],
                "options": [
                    "run: Create and run container",
                    "build: Build image from Dockerfile",
                    "ps: List containers",
                    "exec: Execute command in container",
                    "logs: View container logs",
                ],
            },
            {
                "command": "git",
                "description": "Distributed version control system",
                "usage": "git [options] COMMAND [args]",
                "examples": [
                    "git clone https://github.com/user/repo.git",
                    "git add .",
                    "git commit -m 'message'",
                    "git push origin main",
                ],
                "options": [
                    "clone: Clone repository",
                    "add: Stage changes",
                    "commit: Create commit",
                    "push: Upload changes",
                    "pull: Download changes",
                ],
            },
            {
                "command": "find",
                "description": "Search for files and directories",
                "usage": "find [path] [expression]",
                "examples": [
                    "find /path -name '*.py'",
                    "find . -type f -mtime -7",
                    "find /var -size +100M",
                    "find . -perm 755",
                ],
                "options": [
                    "-name: File name pattern",
                    "-type: File type (f=file, d=directory)",
                    "-size: File size",
                    "-mtime: Modification time",
                    "-exec: Execute command on results",
                ],
            },
            {
                "command": "tar",
                "description": "Archive files and directories",
                "usage": "tar [options] archive-file files...",
                "examples": [
                    "tar -czf archive.tar.gz folder/",
                    "tar -xzf archive.tar.gz",
                    "tar -tzf archive.tar.gz",
                    "tar -xzf archive.tar.gz -C /destination/",
                ],
                "options": [
                    "-c: Create archive",
                    "-x: Extract archive",
                    "-z: Gzip compression",
                    "-f: Archive filename",
                    "-t: List contents",
                ],
            },
            {
                "command": "systemctl",
                "description": "Control systemd services",
                "usage": "systemctl [options] COMMAND [service]",
                "examples": [
                    "systemctl status nginx",
                    "systemctl start redis-server",
                    "systemctl enable docker",
                    "systemctl restart apache2",
                ],
                "options": [
                    "start: Start service",
                    "stop: Stop service",
                    "restart: Restart service",
                    "status: Check status",
                    "enable: Auto-start on boot",
                ],
            },
            {
                "command": "ps",
                "description": "Display running processes",
                "usage": "ps [options]",
                "examples": [
                    "ps aux",
                    "ps -ef",
                    "ps aux | grep python",
                    "ps -u username",
                ],
                "options": [
                    "aux: All processes with details",
                    "-ef: Full format listing",
                    "-u: Processes by user",
                    "-C: Processes by command",
                ],
            },
            {
                "command": "chmod",
                "description": "Change file permissions",
                "usage": "chmod [options] mode file...",
                "examples": [
                    "chmod 755 script.sh",
                    "chmod +x program",
                    "chmod -R 644 /path/to/files/",
                    "chmod u+w,g-w file.txt",
                ],
                "options": [
                    "755: rwxr-xr-x (executable)",
                    "644: rw-r--r-- (readable)",
                    "+x: Add execute permission",
                    "-R: Recursive",
                    "u/g/o: user/group/others",
                ],
            },
        ]

        items_added = 0

        # Process commands in batches to avoid timeouts
        batch_size = 5
        for i in range(0, len(system_commands), batch_size):
            batch = system_commands[i : i + batch_size]

            for cmd_info in batch:
                try:
                    # Create comprehensive content for each command
                    content = f"""Command: {cmd_info['command']}

Description: {cmd_info['description']}

Usage: {cmd_info['usage']}

Examples:
{chr(10).join(f"  {example}" for example in cmd_info['examples'])}

Common Options:
{chr(10).join(f"  {option}" for option in cmd_info['options'])}

Category: System Command
Type: Command Reference
"""

                    # Store in knowledge base
                    if hasattr(kb_to_use, "store_fact"):
                        result = await kb_to_use.store_fact(
                            content=content,
                            metadata={
                                "title": f"{cmd_info['command']} command",
                                "source": "system_commands_population",
                                "category": "commands",
                                "command": cmd_info["command"],
                                "type": "system_command",
                            },
                        )
                    else:
                        result = await kb_to_use.store_fact(
                            text=content,
                            metadata={
                                "title": f"{cmd_info['command']} command",
                                "source": "system_commands_population",
                                "category": "commands",
                                "command": cmd_info["command"],
                                "type": "system_command",
                            },
                        )

                    if result and result.get("fact_id"):
                        items_added += 1
                        logger.info(f"Added command: {cmd_info['command']}")
                    else:
                        logger.warning(f"Failed to add command: {cmd_info['command']}")

                except Exception as e:
                    logger.error(f"Error adding command {cmd_info['command']}: {e}")

            # Small delay between batches to prevent overload
            await asyncio.sleep(0.1)

        logger.info(
            f"System commands population completed. Added {items_added} commands."
        )

        return {
            "status": "success",
            "message": f"Successfully populated {items_added} system commands",
            "items_added": items_added,
            "total_commands": len(system_commands),
        }

    except Exception as e:
        logger.error(f"Error populating system commands: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"System commands population failed: {str(e)}"
        )


async def _populate_man_pages_background(kb_to_use):
    """Background task to populate man pages"""
    try:
        logger.info("Starting manual pages population in background...")

        # Common commands to get man pages for
        common_commands = [
            "ls",
            "cd",
            "cp",
            "mv",
            "rm",
            "mkdir",
            "rmdir",
            "chmod",
            "chown",
            "find",
            "grep",
            "sed",
            "awk",
            "sort",
            "uniq",
            "head",
            "tail",
            "cat",
            "less",
            "more",
            "ps",
            "top",
            "kill",
            "jobs",
            "nohup",
            "crontab",
            "systemctl",
            "service",
            "curl",
            "wget",
            "ssh",
            "scp",
            "rsync",
            "tar",
            "zip",
            "unzip",
            "gzip",
            "gunzip",
            "git",
            "docker",
            "npm",
            "pip",
            "python",
            "node",
            "java",
            "gcc",
            "make",
        ]

        items_added = 0

        # Process man pages in batches
        batch_size = 5
        for i in range(0, len(common_commands), batch_size):
            batch = common_commands[i : i + batch_size]

            for command in batch:
                try:
                    # Try to get the man page with reduced timeout
                    result = subprocess.run(
                        ["man", command],
                        capture_output=True,
                        text=True,
                        timeout=3,  # Reduced from 10 to 3 seconds
                    )

                    if result.returncode == 0 and result.stdout.strip():
                        # Clean up the man page output
                        man_content = result.stdout.strip()

                        # Remove ANSI escape sequences if present
                        import re

                        man_content = re.sub(r"\x1b\[[0-9;]*m", "", man_content)

                        # Create structured content
                        content = f"""Manual Page: {command}

{man_content}

Source: System Manual Pages
Category: Manual Page
Command: {command}
"""

                        # Store in knowledge base
                        if hasattr(kb_to_use, "store_fact"):
                            store_result = await kb_to_use.store_fact(
                                content=content,
                                metadata={
                                    "title": f"man {command}",
                                    "source": "manual_pages_population",
                                    "category": "manpages",
                                    "command": command,
                                    "type": "manual_page",
                                },
                            )
                        else:
                            store_result = await kb_to_use.store_fact(
                                text=content,
                                metadata={
                                    "title": f"man {command}",
                                    "source": "manual_pages_population",
                                    "category": "manpages",
                                    "command": command,
                                    "type": "manual_page",
                                },
                            )

                        if store_result and store_result.get("fact_id"):
                            items_added += 1
                            logger.info(f"Added man page: {command}")
                        else:
                            logger.warning(f"Failed to store man page: {command}")

                    else:
                        logger.warning(f"No man page found for command: {command}")

                except subprocess.TimeoutExpired:
                    logger.warning(f"Timeout getting man page for: {command}")
                except Exception as e:
                    logger.error(f"Error processing man page for {command}: {e}")

            # Small delay between batches (reduced for faster completion)
            await asyncio.sleep(0.1)

        logger.info(
            f"Manual pages population completed. Added {items_added} man pages."
        )
        return items_added

    except Exception as e:
        logger.error(f"Error populating manual pages in background: {str(e)}")
        return 0


@router.post("/populate_man_pages")
async def populate_man_pages(
    request: dict, req: Request, background_tasks: BackgroundTasks
):
    """Populate knowledge base with common manual pages (runs in background)"""
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "status": "error",
                "message": "Knowledge base not initialized - please check logs for errors",
                "items_added": 0,
            }

        # Start background task
        background_tasks.add_task(_populate_man_pages_background, kb_to_use)

        return {
            "status": "success",
            "message": "Man pages population started in background",
            "items_added": 0,  # Will be updated as background task runs
            "background": True,
        }

    except Exception as e:
        logger.error(f"Error starting man pages population: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Failed to start man pages population: {str(e)}"
        )


@router.post("/refresh_system_knowledge")
async def refresh_system_knowledge(request: dict, req: Request):
    """
    Refresh ALL system knowledge (man pages + AutoBot docs)
    Use this after system updates, package installations, or documentation changes
    """
    try:
        logger.info("Starting comprehensive system knowledge refresh...")

        # Run the comprehensive indexing script
        result = subprocess.run(
            [sys.executable, "scripts/utilities/index_all_man_pages.py"],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout for comprehensive indexing
        )

        if result.returncode == 0:
            # Parse output for statistics
            output_lines = result.stdout.split("\n")
            indexed_count = 0
            total_facts = 0

            for line in output_lines:
                if "Successfully indexed:" in line:
                    indexed_count = int(line.split(":")[1].strip())
                elif "Total facts in KB:" in line:
                    total_facts = int(line.split(":")[1].strip())

            logger.info(
                f"System knowledge refresh complete: {indexed_count} commands indexed"
            )

            return {
                "status": "success",
                "message": f"System knowledge refreshed successfully",
                "commands_indexed": indexed_count,
                "total_facts": total_facts,
            }
        else:
            logger.error(f"System knowledge refresh failed: {result.stderr}")
            raise HTTPException(
                status_code=500,
                detail=f"Knowledge refresh failed: {result.stderr[:500]}",
            )

    except subprocess.TimeoutExpired:
        logger.error("System knowledge refresh timed out")
        raise HTTPException(
            status_code=504, detail="Knowledge refresh timed out (>10 minutes)"
        )
    except Exception as e:
        logger.error(f"Error refreshing system knowledge: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"Knowledge refresh failed: {str(e)}"
        )


def extract_category_from_path(doc_file: str) -> str:
    """Extract category from document file path

    Examples:
        docs/api/file.md -> "api"
        docs/architecture/file.md -> "architecture"
        CLAUDE.md -> "root"
    """
    path_parts = str(doc_file).split("/")
    if len(path_parts) > 1 and path_parts[0] == "docs":
        # docs/api/file.md -> "api"
        return path_parts[1] if len(path_parts) > 2 else "docs"
    # Root files like CLAUDE.md
    return "root"


@router.post("/populate_autobot_docs")
async def populate_autobot_docs(request: dict, req: Request):
    """Populate knowledge base with AutoBot-specific documentation"""
    try:
        from backend.models.knowledge_import_tracking import ImportTracker

        # Check if force reindex is requested
        force_reindex = request.get("force", False) if request else False

        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

        if kb_to_use is None:
            return {
                "status": "error",
                "message": "Knowledge base not initialized - please check logs for errors",
                "items_added": 0,
            }

        logger.info("Starting AutoBot documentation population with import tracking...")

        tracker = ImportTracker()
        # Use project-relative path instead of absolute path
        autobot_base_path = PathLib(__file__).parent.parent.parent

        # Scan for all markdown files recursively in docs/ ONLY
        doc_files = []

        # Initialize counters before any loops
        items_added = 0
        items_skipped = 0
        items_failed = 0

        # Recursively find all .md files in docs/ folder ONLY
        # AutoBot documentation should ONLY include files from docs/ folder
        # Root files like CLAUDE.md, README.md are NOT documentation
        docs_path = autobot_base_path / "docs"
        if docs_path.exists():
            for md_file in docs_path.rglob("*.md"):
                rel_path = md_file.relative_to(autobot_base_path)
                # Skip if already imported and unchanged (unless force reindex)
                if not force_reindex and not tracker.needs_reimport(str(md_file)):
                    logger.info(f"Skipping unchanged file: {rel_path}")
                    items_skipped += 1
                    continue
                doc_files.append(str(rel_path))

        for doc_file in doc_files:
            try:
                file_path = autobot_base_path / doc_file

                if file_path.exists() and file_path.is_file():
                    # Read file content
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()

                    if content.strip():
                        # Extract category from path
                        category = extract_category_from_path(doc_file)

                        # Create structured content
                        structured_content = f"""AutoBot Documentation: {doc_file}

File Path: {file_path}

Content:
{content}

Source: AutoBot Documentation
Category: {category}
Type: Documentation
"""

                        # Store in knowledge base
                        if hasattr(kb_to_use, "store_fact"):
                            result = await kb_to_use.store_fact(
                                content=structured_content,
                                metadata={
                                    "title": f"AutoBot: {doc_file}",
                                    "source": "autobot_docs_population",
                                    "category": category,
                                    "filename": doc_file,
                                    "type": f"{category}_documentation",
                                    "file_path": str(file_path),
                                },
                            )
                        else:
                            result = await kb_to_use.store_fact(
                                text=structured_content,
                                metadata={
                                    "title": f"AutoBot: {doc_file}",
                                    "source": "autobot_docs_population",
                                    "category": category,
                                    "filename": doc_file,
                                    "type": f"{category}_documentation",
                                    "file_path": str(file_path),
                                },
                            )

                        if result and result.get("fact_id"):
                            items_added += 1
                            # Mark as imported with tracker
                            tracker.mark_imported(
                                file_path=str(file_path),
                                category=category,
                                facts_count=1,
                                metadata={
                                    "fact_id": result.get("fact_id"),
                                    "title": f"AutoBot: {doc_file}",
                                    "content_length": len(content),
                                },
                            )
                            logger.info(f"Added AutoBot doc: {doc_file}")
                        else:
                            items_failed += 1
                            tracker.mark_failed(
                                str(file_path), "Failed to store in knowledge base"
                            )
                            logger.warning(f"Failed to store AutoBot doc: {doc_file}")
                    else:
                        items_skipped += 1
                        logger.warning(f"Empty file: {doc_file}")
                else:
                    items_skipped += 1
                    logger.warning(f"File not found: {doc_file}")

            except Exception as e:
                items_failed += 1
                tracker.mark_failed(str(autobot_base_path / doc_file), str(e))
                logger.error(f"Error processing AutoBot doc {doc_file}: {e}")

            # Small delay between files
            await asyncio.sleep(0.1)

        # Add AutoBot configuration information
        try:
            # Import constants for network configuration reference
            from src.constants.network_constants import NetworkConstants
            from src.constants.path_constants import PATH

            config_info = f"""AutoBot System Configuration

Network Layout:
- Main Machine (WSL): {NetworkConstants.MAIN_MACHINE_IP} - Backend API (port {NetworkConstants.BACKEND_PORT}) + NPU Worker (port 8082) + Desktop/Terminal VNC (port 6080)
- VM1 Frontend: {NetworkConstants.FRONTEND_VM_IP}:5173 - Web interface (SINGLE FRONTEND SERVER)
- VM2 NPU Worker: {NetworkConstants.NPU_WORKER_VM_IP}:8081 - Secondary NPU worker (Linux)
- VM3 Redis: {NetworkConstants.REDIS_VM_IP}:{NetworkConstants.REDIS_PORT} - Data layer
- VM4 AI Stack: {NetworkConstants.AI_STACK_VM_IP}:{NetworkConstants.AI_STACK_PORT} - AI processing
- VM5 Browser: {NetworkConstants.BROWSER_VM_IP}:{NetworkConstants.BROWSER_SERVICE_PORT} - Web automation (Playwright)

Key Commands:
- Setup: bash setup.sh [--full|--minimal|--distributed]
- Run: bash run_autobot.sh [--dev|--prod] [--build|--no-build] [--desktop|--no-desktop]

Critical Rules:
- NEVER edit code directly on remote VMs (VM1-VM5)
- ALL code edits MUST be made locally in {PATH.PROJECT_ROOT}/
- Use ./sync-frontend.sh or sync scripts to deploy changes
- Frontend ONLY runs on VM1 ({NetworkConstants.FRONTEND_VM_IP}:5173)
- NO temporary fixes or workarounds allowed

Source: AutoBot System Configuration
Category: AutoBot
Type: System Configuration
"""

            if hasattr(kb_to_use, "store_fact"):
                result = await kb_to_use.store_fact(
                    content=config_info,
                    metadata={
                        "title": "AutoBot System Configuration",
                        "source": "autobot_docs_population",
                        "category": "configuration",
                        "type": "system_configuration",
                    },
                )
            else:
                result = await kb_to_use.store_fact(
                    text=config_info,
                    metadata={
                        "title": "AutoBot System Configuration",
                        "source": "autobot_docs_population",
                        "category": "configuration",
                        "type": "system_configuration",
                    },
                )

            if result and result.get("fact_id"):
                items_added += 1
                logger.info("Added AutoBot system configuration")

        except Exception as e:
            logger.error(f"Error adding AutoBot configuration: {e}")

        logger.info(
            f"AutoBot documentation population completed. Added {items_added} documents ({items_skipped} skipped, {items_failed} failed)."
        )

        mode = "Force reindex" if force_reindex else "Incremental update"
        return {
            "status": "success",
            "message": f"{mode}: Successfully imported {items_added} AutoBot documents ({items_skipped} skipped, {items_failed} failed)",
            "items_added": items_added,
            "items_skipped": items_skipped,
            "items_failed": items_failed,
            "total_files": len(doc_files) + 1,  # +1 for config info
            "force_reindex": force_reindex,
        }

    except Exception as e:
        logger.error(f"Error populating AutoBot docs: {str(e)}")
        raise HTTPException(
            status_code=500, detail=f"AutoBot docs population failed: {str(e)}"
        )


@router.get("/entries")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_entries",
    error_code_prefix="KNOWLEDGE",
)
async def get_knowledge_entries(
    req: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    cursor: Optional[str] = Query(default="0", regex=r"^[0-9]+$"),
    category: Optional[str] = Query(default=None, regex=r"^[a-zA-Z0-9_-]*$"),
):
    """
    Get knowledge base entries with cursor-based pagination.

    Uses Redis SCAN for memory-efficient iteration over large datasets.
    Returns cursor for next page - pass "0" or omit for first page.

    Args:
        limit: Number of entries to return (1-1000)
        cursor: Redis cursor for pagination (default "0" for first page)
        category: Optional category filter

    Returns:
        entries: List of knowledge entries
        next_cursor: Cursor for next page ("0" means no more results)
        count: Number of entries returned
        has_more: Whether more entries are available
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "entries": [],
            "next_cursor": "0",
            "count": 0,
            "has_more": False,
            "message": "Knowledge base not initialized",
        }

    logger.info(
        f"Getting knowledge entries: limit={limit}, cursor={cursor}, category={category}"
    )

    # Use Redis SCAN for memory-efficient cursor-based iteration
    entries = []
    current_cursor = int(cursor) if cursor else 0

    try:
        # HSCAN iterates over hash fields without loading all data into memory
        # match parameter filters keys during scan (server-side filtering)
        next_cursor, items = kb_to_use.redis_client.hscan(
            "knowledge_base:facts",
            cursor=current_cursor,
            count=limit * 2,  # Scan more to account for filtering
        )

        # Parse and filter facts
        for fact_id, fact_json in items.items():
            try:
                fact = json.loads(fact_json)

                # Filter by category if specified
                if (
                    category
                    and fact.get("metadata", {}).get("category", "") != category
                ):
                    continue

                # Format entry for frontend
                entry = {
                    "id": (
                        fact_id.decode() if isinstance(fact_id, bytes) else fact_id
                    ),
                    "content": fact.get("content", ""),
                    "title": fact.get("metadata", {}).get("title", "Untitled"),
                    "source": fact.get("metadata", {}).get("source", "unknown"),
                    "category": fact.get("metadata", {}).get("category", "general"),
                    "type": fact.get("metadata", {}).get("type", "document"),
                    "created_at": fact.get("metadata", {}).get("created_at"),
                    "metadata": fact.get("metadata", {}),
                }
                entries.append(entry)

                # Stop when we have enough entries
                if len(entries) >= limit:
                    break

            except Exception as parse_err:
                logger.warning(f"Error parsing fact {fact_id}: {parse_err}")
                continue

        # Sort by creation date (newest first) - only sorts current page
        entries.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        # Limit to requested size
        entries = entries[:limit]

        return {
            "entries": entries,
            "next_cursor": str(next_cursor),
            "count": len(entries),
            "has_more": next_cursor != 0,
        }

    except Exception as redis_err:
        logger.error(f"Redis error getting facts: {redis_err}")
        return {
            "entries": [],
            "next_cursor": "0",
            "count": 0,
            "has_more": False,
            "error": "Redis connection error",
        }


@router.get("/detailed_stats")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_detailed_stats",
    error_code_prefix="KNOWLEDGE",
)
async def get_detailed_stats(req: Request):
    """Get detailed knowledge base statistics with additional metrics"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "status": "offline",
            "message": "Knowledge base not initialized",
            "basic_stats": {},
            "category_breakdown": {},
            "source_breakdown": {},
            "type_breakdown": {},
            "size_metrics": {},
        }

    # Get basic stats
    basic_stats = await kb_to_use.get_stats()

    # Get all facts for detailed analysis
    try:
        all_facts_data = kb_to_use.redis_client.hgetall("knowledge_base:facts")
    except Exception:
        all_facts_data = {}

    # Analyze facts for detailed breakdowns
    category_counts = {}
    source_counts = {}
    type_counts = {}
    total_content_size = 0
    fact_sizes = []

    for fact_json in all_facts_data.values():
        try:
            fact = json.loads(fact_json)
            metadata = fact.get("metadata", {})

            # Category breakdown
            category = metadata.get("category", "uncategorized")
            category_counts[category] = category_counts.get(category, 0) + 1

            # Source breakdown
            source = metadata.get("source", "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1

            # Type breakdown
            fact_type = metadata.get("type", "document")
            type_counts[fact_type] = type_counts.get(fact_type, 0) + 1

            # Size metrics
            content = fact.get("content", "")
            content_size = len(content)
            total_content_size += content_size
            fact_sizes.append(content_size)
        except (KeyError, TypeError, AttributeError) as e:
            logger.warning(f"Error processing fact for size calculation: {e}")
            continue

    # Calculate size metrics
    avg_size = total_content_size / len(fact_sizes) if fact_sizes else 0
    fact_sizes.sort()
    median_size = fact_sizes[len(fact_sizes) // 2] if fact_sizes else 0

    return {
        "status": "online" if basic_stats.get("initialized") else "offline",
        "basic_stats": basic_stats,
        "category_breakdown": category_counts,
        "source_breakdown": source_counts,
        "type_breakdown": type_counts,
        "size_metrics": {
            "total_content_size": total_content_size,
            "average_fact_size": avg_size,
            "median_fact_size": median_size,
            "largest_fact_size": max(fact_sizes) if fact_sizes else 0,
            "smallest_fact_size": min(fact_sizes) if fact_sizes else 0,
        },
        "rag_available": RAG_AVAILABLE,
    }


@router.get("/machine_profile")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_machine_profile",
    error_code_prefix="KNOWLEDGE",
)
async def get_machine_profile(req: Request):
    """Get machine profile with system information and capabilities"""
    import platform

    import psutil

    # Gather system information
    machine_info = {
        "hostname": platform.node(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "cpu_count": psutil.cpu_count(logical=False),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "memory_total_gb": round(psutil.virtual_memory().total / (1024**3), 2),
        "memory_available_gb": round(
            psutil.virtual_memory().available / (1024**3), 2
        ),
        "disk_total_gb": round(psutil.disk_usage("/").total / (1024**3), 2),
        "disk_free_gb": round(psutil.disk_usage("/").free / (1024**3), 2),
    }

    # Get knowledge base stats
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
    kb_stats = await kb_to_use.get_stats() if kb_to_use else {}

    return {
        "status": "success",
        "machine_profile": machine_info,
        "knowledge_base_stats": kb_stats,
        "capabilities": {
            "rag_available": RAG_AVAILABLE,
            "vector_search": kb_stats.get("initialized", False),
            "man_pages_available": True,  # Always available on Linux
            "system_knowledge": True,
        },
    }


@router.get("/man_pages/summary")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_man_pages_summary",
    error_code_prefix="KNOWLEDGE",
)
async def get_man_pages_summary(req: Request):
    """Get summary of man pages integration status"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "status": "error",
            "message": "Knowledge base not initialized",
            "man_pages_summary": {
                "total_man_pages": 0,
                "indexed_count": 0,
                "last_indexed": None,
            },
        }

    # Get all facts and count man pages
    try:
        all_facts_data = kb_to_use.redis_client.hgetall("knowledge_base:facts")

        man_page_count = 0
        system_command_count = 0
        last_indexed = None

        for fact_json in all_facts_data.values():
            try:
                fact = json.loads(fact_json)
                metadata = fact.get("metadata", {})

                if metadata.get("type") == "manual_page":
                    man_page_count += 1
                elif metadata.get("type") == "system_command":
                    system_command_count += 1

                # Track most recent timestamp
                created_at = metadata.get("created_at")
                if created_at and (
                    last_indexed is None or created_at > last_indexed
                ):
                    last_indexed = created_at
            except (KeyError, TypeError, ValueError) as e:
                logger.warning(f"Error parsing fact metadata: {e}")
                continue

        return {
            "status": "success",
            "man_pages_summary": {
                "total_man_pages": man_page_count,
                "system_commands": system_command_count,
                "indexed_count": man_page_count + system_command_count,
                "last_indexed": last_indexed,
                "integration_active": man_page_count > 0,
            },
        }

    except Exception as redis_err:
        logger.error(f"Redis error getting man pages: {redis_err}")
        return {
            "status": "error",
            "message": "Failed to query knowledge base",
            "man_pages_summary": {
                "total_man_pages": 0,
                "indexed_count": 0,
                "last_indexed": None,
            },
        }


@router.post("/machine_knowledge/initialize")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="initialize_machine_knowledge",
    error_code_prefix="KNOWLEDGE",
)
async def initialize_machine_knowledge(request: dict, req: Request):
    """Initialize machine-specific knowledge including man pages and system commands"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "status": "error",
            "message": "Knowledge base not initialized",
            "items_added": 0,
        }

    logger.info("Initializing machine knowledge...")

    # Initialize system commands first
    commands_result = await populate_system_commands(request, req)
    commands_added = commands_result.get("items_added", 0)

    return {
        "status": "success",
        "message": f"Machine knowledge initialized. Added {commands_added} system commands.",
        "items_added": commands_added,
        "components": {
            "system_commands": commands_added,
            "man_pages": "background_task",  # Man pages run in background
        },
    }


@router.post("/man_pages/integrate")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="integrate_man_pages",
    error_code_prefix="KNOWLEDGE",
)
async def integrate_man_pages(req: Request, background_tasks: BackgroundTasks):
    """Integrate system man pages into knowledge base (background task)"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "status": "error",
            "message": "Knowledge base not initialized",
            "integration_started": False,
        }

    # Start background task for man pages
    background_tasks.add_task(_populate_man_pages_background, kb_to_use)

    return {
        "status": "success",
        "message": "Man pages integration started in background",
        "integration_started": True,
        "background": True,
    }


@router.get("/man_pages/search")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_man_pages",
    error_code_prefix="KNOWLEDGE",
)
async def search_man_pages(req: Request, query: str, limit: int = 10):
    """Search specifically for man pages in knowledge base"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {"results": [], "total_results": 0, "query": query}

    logger.info(f"Searching man pages: '{query}' (limit={limit})")

    # Perform search
    kb_class_name = kb_to_use.__class__.__name__

    if kb_class_name == "KnowledgeBaseV2":
        results = await kb_to_use.search(query=query, top_k=limit)
    else:
        results = await kb_to_use.search(query=query, similarity_top_k=limit)

    # Filter for man pages only
    man_page_results = []
    for result in results:
        metadata = result.get("metadata", {})
        if metadata.get("type") in ["manual_page", "system_command"]:
            man_page_results.append(result)

    return {
        "results": man_page_results,
        "total_results": len(man_page_results),
        "query": query,
        "limit": limit,
    }


@router.post("/clear_all")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_all_knowledge",
    error_code_prefix="KNOWLEDGE",
)
async def clear_all_knowledge(request: dict, req: Request):
    """Clear all entries from the knowledge base - DESTRUCTIVE OPERATION"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "status": "error",
            "message": "Knowledge base not initialized - please check logs for errors",
            "items_removed": 0,
        }

    logger.warning(
        "Starting DESTRUCTIVE operation: clearing all knowledge base entries"
    )

    # Get current stats before clearing
    try:
        stats_before = await kb_to_use.get_stats()
        items_before = stats_before.get("total_facts", 0)
    except Exception:
        items_before = 0

    # Clear the knowledge base
    if hasattr(kb_to_use, "clear_all"):
        # Use specific clear_all method if available
        result = await kb_to_use.clear_all()
        items_removed = result.get("items_removed", items_before)
    else:
        # Fallback: try to clear via Redis if that's the implementation
        try:
            if hasattr(kb_to_use, "redis") and kb_to_use.redis:
                # For Redis-based implementations
                keys = await kb_to_use.redis.keys("fact:*")
                if keys:
                    await kb_to_use.redis.delete(*keys)

                # Clear any indexes
                index_keys = await kb_to_use.redis.keys("index:*")
                if index_keys:
                    await kb_to_use.redis.delete(*index_keys)

                items_removed = len(keys)
            else:
                logger.error(
                    "No clear method available for knowledge base implementation"
                )
                raise HTTPException(
                    status_code=500, detail="Knowledge base clearing not supported"
                )

        except Exception as e:
            logger.error(f"Error during knowledge base clearing: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to clear knowledge base: {str(e)}"
            )

    logger.warning(f"Knowledge base cleared. Removed {items_removed} entries.")

    return {
        "status": "success",
        "message": f"Successfully cleared knowledge base. Removed {items_removed} entries.",
        "items_removed": items_removed,
        "items_before": items_before,
    }


# Legacy endpoints for backward compatibility
@router.post("/add_document")
async def add_document_to_knowledge(request: dict, req: Request):
    """Legacy endpoint - redirects to add_text"""
    return await add_text_to_knowledge(request, req)


@router.post("/query")
async def query_knowledge(request: dict, req: Request):
    """Legacy endpoint - redirects to search"""
    return await search_knowledge(request, req)


# Helper function for RAG enhancement
async def _enhance_search_with_rag(
    query: str, results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Enhance search results with RAG analysis"""
    try:
        rag_agent = get_rag_agent()

        # Convert results to documents for RAG processing
        documents = []
        for result in results:
            documents.append(
                {
                    "content": result.get("content", ""),
                    "metadata": {
                        "filename": result.get("metadata", {}).get("title", "Unknown"),
                        "source": result.get("metadata", {}).get(
                            "source", "knowledge_base"
                        ),
                        "score": result.get("score", 0.0),
                    },
                }
            )

        # Analyze document relevance
        document_analysis = rag_agent._analyze_document_relevance(query, documents)

        # Rank documents
        ranked_documents = await rag_agent.rank_documents(query, documents)

        return {
            "document_analysis": document_analysis,
            "ranked_documents": ranked_documents[:5],  # Top 5 ranked documents
            "analysis_summary": {
                "total_analyzed": len(documents),
                "high_relevance_count": document_analysis.get("high_relevance", 0),
                "medium_relevance_count": document_analysis.get("medium_relevance", 0),
                "low_relevance_count": document_analysis.get("low_relevance", 0),
            },
        }

    except Exception as e:
        logger.error(f"RAG enhancement error: {e}")
        return {
            "error": str(e),
            "analysis_summary": {
                "total_analyzed": len(results),
                "error": "RAG analysis failed",
            },
        }


@router.get("/facts/by_category")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_facts_by_category",
    error_code_prefix="KNOWLEDGE",
)
async def get_facts_by_category(
    req: Request, category: Optional[str] = None, limit: int = 100
):
    """Get facts grouped by category for browsing with caching"""
    kb = await get_or_create_knowledge_base(req.app)
    import json

    # Check cache first (60 second TTL)
    cache_key = f"kb:cache:facts_by_category:{category or 'all'}:{limit}"
    cached_result = kb.redis_client.get(cache_key)

    if cached_result:
        logger.debug(
            f"Cache HIT for facts_by_category (category={category}, limit={limit})"
        )
        return json.loads(
            cached_result.decode("utf-8")
            if isinstance(cached_result, bytes)
            else cached_result
        )

    logger.info(
        f"Cache MISS for facts_by_category - scanning all facts (category={category}, limit={limit})"
    )

    # Get all fact keys from Redis
    fact_keys = kb.redis_client.keys("fact:*")

    if not fact_keys:
        return {"categories": {}, "total_facts": 0}

    # Group facts by category
    categories_dict = {}

    for fact_key in fact_keys:
        try:
            # Get fact data from hash
            fact_data = kb.redis_client.hgetall(fact_key)

            if not fact_data:
                continue

            # Extract metadata (handle both bytes and string keys from Redis)
            metadata_str = fact_data.get("metadata") or fact_data.get(b"metadata", b"{}")
            metadata = json.loads(
                metadata_str.decode("utf-8")
                if isinstance(metadata_str, bytes)
                else metadata_str
            )

            # Extract content (handle both bytes and string keys from Redis)
            content_raw = fact_data.get("content") or fact_data.get(b"content", b"")
            content = (
                content_raw.decode("utf-8")
                if isinstance(content_raw, bytes)
                else str(content_raw) if content_raw else ""
            )

            # Get category based on source field (not metadata.category)
            from backend.knowledge_categories import get_category_for_source

            source = metadata.get("source", "")
            fact_category = (
                get_category_for_source(source).value if source else "general"
            )
            fact_title = metadata.get("title", metadata.get("command", "Untitled"))
            fact_type = metadata.get("type", "unknown")

            if fact_category not in categories_dict:
                categories_dict[fact_category] = []

            # Add to category list
            categories_dict[fact_category].append(
                {
                    "key": (
                        fact_key.decode("utf-8")
                        if isinstance(fact_key, bytes)
                        else str(fact_key)
                    ),
                    "title": fact_title,
                    "content": (
                        content[:500] + "..." if len(content) > 500 else content
                    ),  # Preview
                    "full_content": content,
                    "category": fact_category,
                    "type": fact_type,
                    "metadata": metadata,
                }
            )

        except Exception as e:
            logger.warning(f"Error processing fact {fact_key}: {e}")
            continue

    # Filter by category if specified
    if category:
        categories_dict = {
            k: v for k, v in categories_dict.items() if k == category
        }

    # Limit results per category
    for cat in categories_dict:
        categories_dict[cat] = categories_dict[cat][:limit]

    result = {
        "categories": categories_dict,
        "total_facts": sum(len(v) for v in categories_dict.values()),
        "category_filter": category,
    }

    # Cache the result for 60 seconds
    try:
        kb.redis_client.setex(cache_key, 60, json.dumps(result))
        logger.debug(
            f"Cached facts_by_category result (category={category}, limit={limit})"
        )
    except Exception as cache_error:
        logger.warning(f"Failed to cache facts_by_category: {cache_error}")

    return result


@router.get("/fact/{fact_key}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_fact_by_key",
    error_code_prefix="KNOWLEDGE",
)
async def get_fact_by_key(
    fact_key: str = Path(..., regex=r"^[a-zA-Z0-9_:-]+$", max_length=255),
    req: Request = None,
):
    """
    Get a single fact by its Redis key.

    Args:
        fact_key: Redis key for the fact (validated to prevent injection)

    Security:
        - Key format validated to prevent Redis key enumeration attacks
        - Path traversal attempts blocked
        - Maximum key length enforced
    """
    # Additional security check for path traversal
    if ".." in fact_key or "/" in fact_key or "\\" in fact_key:
        raise HTTPException(
            status_code=400, detail="Invalid fact_key: path traversal not allowed"
        )

    kb = await get_or_create_knowledge_base(req.app)
    import json

    # Get fact data from Redis hash
    fact_data = kb.redis_client.hgetall(fact_key)

    if not fact_data:
        raise HTTPException(status_code=404, detail=f"Fact not found: {fact_key}")

    # Extract metadata (handle both bytes and string keys from Redis)
    metadata_str = fact_data.get("metadata") or fact_data.get(b"metadata", b"{}")
    metadata = json.loads(
        metadata_str.decode("utf-8")
        if isinstance(metadata_str, bytes)
        else metadata_str
    )

    # Extract content (handle both bytes and string keys from Redis)
    content_raw = fact_data.get("content") or fact_data.get(b"content", b"")
    content = (
        content_raw.decode("utf-8")
        if isinstance(content_raw, bytes)
        else str(content_raw) if content_raw else ""
    )

    # Extract created_at (handle both bytes and string keys from Redis)
    created_at_raw = fact_data.get("created_at") or fact_data.get(b"created_at", b"")
    created_at = (
        created_at_raw.decode("utf-8")
        if isinstance(created_at_raw, bytes)
        else str(created_at_raw) if created_at_raw else ""
    )

    return {
        "key": fact_key,
        "content": content,
        "metadata": metadata,
        "created_at": created_at,
    }


@router.post("/vectorize_facts")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="vectorize_existing_facts",
    error_code_prefix="KNOWLEDGE",
)
async def vectorize_existing_facts(
    req: Request,
    batch_size: int = 50,
    batch_delay: float = 0.5,
    skip_existing: bool = True,
):
    """
    Generate vector embeddings for facts in Redis using batched processing.

    Args:
        batch_size: Number of facts to process per batch (default: 50)
        batch_delay: Delay in seconds between batches (default: 0.5)
        skip_existing: Skip facts that already have vectors (default: True)

    This prevents resource lockup by processing facts in manageable batches
    and can be run periodically to vectorize new facts.
    """
    kb = await get_or_create_knowledge_base(req.app)

    if not kb:
        raise HTTPException(
            status_code=500, detail="Knowledge base not initialized"
        )

    # Get all fact keys from Redis
    fact_keys = await kb._scan_redis_keys_async("fact:*")

    if not fact_keys:
        return {
            "status": "success",
            "message": "No facts found to vectorize",
            "processed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
        }

    logger.info(
        f"Starting batched vectorization of {len(fact_keys)} facts (batch_size={batch_size}, delay={batch_delay}s)"
    )

    success_count = 0
    failed_count = 0
    skipped_count = 0
    processed_facts = []

    total_batches = (len(fact_keys) + batch_size - 1) // batch_size

    # Process in batches
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(fact_keys))
        batch = fact_keys[start_idx:end_idx]

        logger.info(
            f"Processing batch {batch_num + 1}/{total_batches} ({len(batch)} facts)"
        )

        for fact_key in batch:
            try:
                # Get fact data
                fact_data = await kb.aioredis_client.hgetall(fact_key)

                if not fact_data:
                    logger.warning(f"No data found for fact key: {fact_key}")
                    failed_count += 1
                    continue

                # Extract content and metadata (handle both bytes and string keys from Redis)
                content_raw = fact_data.get("content") or fact_data.get(b"content", b"")
                content = (
                    content_raw.decode("utf-8")
                    if isinstance(content_raw, bytes)
                    else str(content_raw) if content_raw else ""
                )

                metadata_str = fact_data.get("metadata") or fact_data.get(b"metadata", b"{}")
                metadata = json.loads(
                    metadata_str.decode("utf-8")
                    if isinstance(metadata_str, bytes)
                    else metadata_str
                )

                # Extract fact ID from key (fact:uuid)
                fact_id = fact_key.split(":")[-1] if ":" in fact_key else fact_key

                # Check if already vectorized by checking vector_indexed status
                if skip_existing:
                    # Check if this fact is already in the vector index
                    vector_key = f"llama_index/vector_{fact_id}"
                    has_vector = await kb.aioredis_client.exists(vector_key)
                    if has_vector:
                        skipped_count += 1
                        continue

                # Vectorize existing fact without duplication
                result = await kb.vectorize_existing_fact(
                    fact_id=fact_id, content=content, metadata=metadata
                )

                if result.get("status") == "success" and result.get(
                    "vector_indexed"
                ):
                    success_count += 1
                    processed_facts.append(
                        {"fact_id": fact_id, "status": "vectorized"}
                    )
                else:
                    failed_count += 1
                    logger.warning(
                        f"Failed to vectorize fact {fact_id}: {result.get('message')}"
                    )

            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing fact {fact_key}: {e}")

        # Delay between batches to prevent resource exhaustion
        if batch_num < total_batches - 1:
            await asyncio.sleep(batch_delay)

    # KnowledgeBaseV2 automatically indexes during add_document - no rebuild needed
    logger.info("Batched vectorization complete - index updated automatically")

    return {
        "status": "success",
        "message": f"Vectorization complete: {success_count} successful, {failed_count} failed, {skipped_count} skipped",
        "processed": len(fact_keys),
        "success": success_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "batches": total_batches,
        "details": processed_facts[:10],  # Return first 10 for reference
    }


@router.get("/import/status")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_import_status",
    error_code_prefix="KNOWLEDGE",
)
async def get_import_status(
    req: Request, file_path: Optional[str] = None, category: Optional[str] = None
):
    """Get import status for files"""
    from backend.models.knowledge_import_tracking import ImportTracker

    tracker = ImportTracker()
    results = tracker.get_import_status(file_path=file_path, category=category)

    return {"status": "success", "imports": results, "total": len(results)}


@router.get("/import/statistics")
async def get_import_statistics(req: Request):
    """Get import statistics"""
    try:
        from backend.models.knowledge_import_tracking import ImportTracker

        tracker = ImportTracker()
        stats = tracker.get_statistics()

        return {"status": "success", "statistics": stats}
    except Exception as e:
        logger.error(f"Error getting import statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== INDIVIDUAL DOCUMENT VECTORIZATION =====


async def _vectorize_fact_background(
    kb_instance, fact_id: str, job_id: str, force: bool = False
):
    """
    Background task to vectorize a single fact and track progress in Redis.

    Args:
        kb_instance: KnowledgeBase instance
        fact_id: ID of fact to vectorize
        job_id: Job tracking ID
        force: Force re-vectorization even if already vectorized
    """
    try:
        # Update job status to processing
        job_data = {
            "job_id": job_id,
            "fact_id": fact_id,
            "status": "processing",
            "progress": 10,
            "started_at": datetime.now().isoformat(),
            "completed_at": None,
            "error": None,
            "result": None,
        }
        kb_instance.redis_client.setex(
            f"vectorization_job:{job_id}", 3600, json.dumps(job_data)  # 1 hour TTL
        )
        logger.info(f"Started vectorization job {job_id} for fact {fact_id}")

        # Get fact data from Redis - facts are stored as individual hashes with key "fact:{uuid}"
        fact_key = f"fact:{fact_id}"
        fact_hash = kb_instance.redis_client.hgetall(fact_key)

        if not fact_hash:
            raise ValueError(f"Fact {fact_id} not found in knowledge base")

        # Extract content and metadata from hash
        content = (
            fact_hash.get("content", "")
            if isinstance(fact_hash.get("content"), str)
            else fact_hash.get("content", b"").decode("utf-8")
        )
        metadata_str = fact_hash.get("metadata", "{}")
        metadata = (
            json.loads(metadata_str)
            if isinstance(metadata_str, str)
            else json.loads(metadata_str.decode("utf-8"))
        )

        # Update progress
        job_data["progress"] = 30
        kb_instance.redis_client.setex(
            f"vectorization_job:{job_id}", 3600, json.dumps(job_data)
        )

        # Check if already vectorized (unless force=True)
        if not force:
            vector_key = f"llama_index/vector_{fact_id}"
            if kb_instance.redis_client.exists(vector_key):
                logger.info(
                    f"Fact {fact_id} already vectorized, skipping (use force=true to re-vectorize)"
                )
                job_data["status"] = "completed"
                job_data["progress"] = 100
                job_data["completed_at"] = datetime.now().isoformat()
                job_data["result"] = {
                    "status": "skipped",
                    "message": "Fact already vectorized",
                    "fact_id": fact_id,
                    "vector_indexed": True,
                }
                kb_instance.redis_client.setex(
                    f"vectorization_job:{job_id}", 3600, json.dumps(job_data)
                )
                return

        # Update progress
        job_data["progress"] = 50
        kb_instance.redis_client.setex(
            f"vectorization_job:{job_id}", 3600, json.dumps(job_data)
        )

        # Vectorize the fact
        result = await kb_instance.vectorize_existing_fact(
            fact_id=fact_id, content=content, metadata=metadata
        )

        # Update job with result
        job_data["progress"] = 90
        job_data["result"] = result

        if result.get("status") == "success" and result.get("vector_indexed"):
            job_data["status"] = "completed"
            job_data["progress"] = 100
            logger.info(f"Successfully vectorized fact {fact_id} in job {job_id}")
        else:
            job_data["status"] = "failed"
            job_data["error"] = result.get("message", "Unknown error")
            logger.error(
                f"Failed to vectorize fact {fact_id} in job {job_id}: {job_data['error']}"
            )

        job_data["completed_at"] = datetime.now().isoformat()
        kb_instance.redis_client.setex(
            f"vectorization_job:{job_id}", 3600, json.dumps(job_data)
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(
            f"Error in vectorization job {job_id} for fact {fact_id}: {error_msg}"
        )

        # Update job with error
        job_data = {
            "job_id": job_id,
            "fact_id": fact_id,
            "status": "failed",
            "progress": 0,
            "started_at": job_data.get("started_at", datetime.now().isoformat()),
            "completed_at": datetime.now().isoformat(),
            "error": error_msg,
            "result": None,
        }
        kb_instance.redis_client.setex(
            f"vectorization_job:{job_id}", 3600, json.dumps(job_data)
        )


@router.post("/vectorize_fact/{fact_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="vectorize_individual_fact",
    error_code_prefix="KNOWLEDGE",
)
async def vectorize_individual_fact(
    fact_id: str, req: Request, background_tasks: BackgroundTasks, force: bool = False
):
    """
    Vectorize a single fact by ID with progress tracking.

    Args:
        fact_id: ID of the fact to vectorize
        force: Force re-vectorization even if already vectorized (default: False)

    Returns:
        Job tracking information with job_id for status monitoring
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(
            status_code=500, detail="Knowledge base not initialized"
        )

    # Check if fact exists - facts are stored as individual Redis hashes with key "fact:{uuid}"
    fact_key = f"fact:{fact_id}"
    fact_data = kb.redis_client.hgetall(fact_key)
    if not fact_data:
        raise HTTPException(
            status_code=404, detail=f"Fact {fact_id} not found in knowledge base"
        )

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Create initial job record
    job_data = {
        "job_id": job_id,
        "fact_id": fact_id,
        "status": "pending",
        "progress": 0,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "error": None,
        "result": None,
    }

    kb.redis_client.setex(
        f"vectorization_job:{job_id}", 3600, json.dumps(job_data)  # 1 hour TTL
    )

    # Add background task
    background_tasks.add_task(
        _vectorize_fact_background, kb, fact_id, job_id, force
    )

    logger.info(
        f"Created vectorization job {job_id} for fact {fact_id} (force={force})"
    )

    return {
        "status": "success",
        "message": "Vectorization job started",
        "job_id": job_id,
        "fact_id": fact_id,
        "force": force,
    }


@router.get("/vectorize_job/{job_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vectorization_job_status",
    error_code_prefix="KNOWLEDGE",
)
async def get_vectorization_job_status(job_id: str, req: Request):
    """
    Get the status of a vectorization job.

    Args:
        job_id: Job tracking ID

    Returns:
        Job status information including progress and result
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(
            status_code=500, detail="Knowledge base not initialized"
        )

    # Get job data from Redis
    job_json = kb.redis_client.get(f"vectorization_job:{job_id}")

    if not job_json:
        raise HTTPException(
            status_code=404, detail=f"Vectorization job {job_id} not found"
        )

    job_data = json.loads(job_json)

    return {"status": "success", "job": job_data}


@router.get("/vectorize_jobs/failed")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_failed_vectorization_jobs",
    error_code_prefix="KNOWLEDGE",
)
async def get_failed_vectorization_jobs(req: Request):
    """
    Get all failed vectorization jobs from Redis.

    Returns:
        List of failed jobs with their error details
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(
            status_code=500, detail="Knowledge base not initialized"
        )

    # Use SCAN to iterate through keys efficiently (non-blocking)
    failed_jobs = []
    cursor = 0

    while True:
        cursor, keys = kb.redis_client.scan(
            cursor, match="vectorization_job:*", count=100
        )

        # Use pipeline for batch operations
        if keys:
            pipe = kb.redis_client.pipeline()
            for key in keys:
                pipe.get(key)
            results = pipe.execute()

            for job_json in results:
                if job_json:
                    job_data = json.loads(job_json)
                    if job_data.get("status") == "failed":
                        failed_jobs.append(job_data)

        if cursor == 0:
            break

    return {
        "status": "success",
        "failed_jobs": failed_jobs,
        "total_failed": len(failed_jobs),
    }


@router.post("/vectorize_jobs/{job_id}/retry")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="retry_vectorization_job",
    error_code_prefix="KNOWLEDGE",
)
async def retry_vectorization_job(
    job_id: str, req: Request, background_tasks: BackgroundTasks, force: bool = False
):
    """
    Retry a failed vectorization job.

    Args:
        job_id: ID of the failed job to retry
        force: Force re-vectorization even if already vectorized

    Returns:
        New job tracking information
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(
            status_code=500, detail="Knowledge base not initialized"
        )

    # Get old job data
    old_job_json = kb.redis_client.get(f"vectorization_job:{job_id}")

    if not old_job_json:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    old_job_data = json.loads(old_job_json)
    fact_id = old_job_data.get("fact_id")

    if not fact_id:
        raise HTTPException(status_code=400, detail="Job does not contain fact_id")

    # Create new job
    new_job_id = str(uuid.uuid4())
    job_data = {
        "job_id": new_job_id,
        "fact_id": fact_id,
        "status": "pending",
        "progress": 0,
        "started_at": datetime.now().isoformat(),
        "completed_at": None,
        "error": None,
        "result": None,
        "retry_of": job_id,  # Track that this is a retry
    }

    kb.redis_client.setex(
        f"vectorization_job:{new_job_id}", 3600, json.dumps(job_data)
    )

    # Add background task
    background_tasks.add_task(
        _vectorize_fact_background, kb, fact_id, new_job_id, force
    )

    logger.info(f"Retrying vectorization job {job_id} as {new_job_id}")

    return {
        "status": "success",
        "message": "Retry job started",
        "new_job_id": new_job_id,
        "fact_id": fact_id,
        "original_job_id": job_id,
    }


@router.delete("/vectorize_jobs/{job_id}")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_vectorization_job",
    error_code_prefix="KNOWLEDGE",
)
async def delete_vectorization_job(job_id: str, req: Request):
    """
    Delete a vectorization job record from Redis.

    Args:
        job_id: ID of the job to delete

    Returns:
        Deletion confirmation
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(
            status_code=500, detail="Knowledge base not initialized"
        )

    # Delete job from Redis
    deleted = kb.redis_client.delete(f"vectorization_job:{job_id}")

    if deleted == 0:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    logger.info(f"Deleted vectorization job {job_id}")

    return {
        "status": "success",
        "message": f"Job {job_id} deleted",
        "job_id": job_id,
    }


@router.delete("/vectorize_jobs/failed/clear")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_failed_vectorization_jobs",
    error_code_prefix="KNOWLEDGE",
)
async def clear_failed_vectorization_jobs(req: Request):
    """
    Clear all failed vectorization jobs from Redis.

    Returns:
        Number of jobs cleared
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(
            status_code=500, detail="Knowledge base not initialized"
        )

    # Use SCAN to iterate through keys efficiently (non-blocking)
    deleted_count = 0
    cursor = 0

    while True:
        cursor, keys = kb.redis_client.scan(
            cursor, match="vectorization_job:*", count=100
        )

        # Use pipeline for batch operations
        if keys:
            pipe = kb.redis_client.pipeline()
            for key in keys:
                pipe.get(key)
            results = pipe.execute()

            # Collect failed job keys
            failed_keys = []
            for key, job_json in zip(keys, results):
                if job_json:
                    job_data = json.loads(job_json)
                    if job_data.get("status") == "failed":
                        failed_keys.append(key)

            # Delete failed jobs in batch
            if failed_keys:
                kb.redis_client.delete(*failed_keys)
                deleted_count += len(failed_keys)

        if cursor == 0:
            break

    logger.info(f"Cleared {deleted_count} failed vectorization jobs")

    return {
        "status": "success",
        "message": f"Cleared {deleted_count} failed jobs",
        "deleted_count": deleted_count,
    }


@router.post("/deduplicate")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="deduplicate_facts",
    error_code_prefix="KNOWLEDGE",
)
async def deduplicate_facts(req: Request, dry_run: bool = True):
    """
    Remove duplicate facts based on category + title.
    Keeps the oldest fact and removes newer duplicates.

    Args:
        dry_run: If True, only report duplicates without deleting (default: True)

    Returns:
        Report of duplicates found and removed
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(
            status_code=500, detail="Knowledge base not initialized"
        )

    logger.info(f"Starting deduplication scan (dry_run={dry_run})...")

    # Use SCAN to iterate through all fact keys
    fact_groups = {}  # category:title -> list of (fact_id, created_at, fact_key)
    cursor = 0
    total_facts = 0

    while True:
        cursor, keys = kb.redis_client.scan(cursor, match="fact:*", count=100)

        if keys:
            # Use pipeline for batch GET operations
            pipe = kb.redis_client.pipeline()
            for key in keys:
                pipe.hget(key, "metadata")
                pipe.hget(key, "created_at")
            results = pipe.execute()

            # Group facts by category+title
            for i in range(0, len(results), 2):
                metadata_str = results[i]
                created_at = results[i + 1]
                fact_key = keys[i // 2]

                # Decode key if it's bytes
                if isinstance(fact_key, bytes):
                    fact_key = fact_key.decode("utf-8")

                if metadata_str:
                    try:
                        metadata = json.loads(metadata_str)
                        category = metadata.get("category", "unknown")
                        title = metadata.get("title", "unknown")
                        fact_id = metadata.get("fact_id", fact_key.split(":")[1])

                        group_key = f"{category}:{title}"

                        if group_key not in fact_groups:
                            fact_groups[group_key] = []

                        fact_groups[group_key].append(
                            {
                                "fact_id": fact_id,
                                "fact_key": fact_key,
                                "created_at": created_at or "1970-01-01T00:00:00",
                                "category": category,
                                "title": title,
                            }
                        )
                        total_facts += 1
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse metadata for {fact_key}")

        if cursor == 0:
            break

    logger.info(
        f"Scanned {total_facts} facts, found {len(fact_groups)} unique category+title combinations"
    )

    # Find duplicates
    duplicates_found = []
    facts_to_delete = []

    for group_key, facts in fact_groups.items():
        if len(facts) > 1:
            # Sort by created_at to keep the oldest
            facts.sort(key=lambda x: x["created_at"])

            # Keep first (oldest), mark rest for deletion
            kept_fact = facts[0]
            duplicate_facts = facts[1:]

            duplicates_found.append(
                {
                    "category": kept_fact["category"],
                    "title": kept_fact["title"],
                    "total_copies": len(facts),
                    "kept_fact_id": kept_fact["fact_id"],
                    "kept_created_at": kept_fact["created_at"],
                    "removed_count": len(duplicate_facts),
                    "removed_fact_ids": [f["fact_id"] for f in duplicate_facts],
                }
            )

            facts_to_delete.extend([f["fact_key"] for f in duplicate_facts])

    # Delete duplicates if not dry run
    deleted_count = 0
    if not dry_run and facts_to_delete:
        logger.info(f"Deleting {len(facts_to_delete)} duplicate facts...")

        # Delete in batches
        batch_size = 100
        for i in range(0, len(facts_to_delete), batch_size):
            batch = facts_to_delete[i : i + batch_size]
            kb.redis_client.delete(*batch)
            deleted_count += len(batch)

        logger.info(f"Deleted {deleted_count} duplicate facts")

    return {
        "status": "success",
        "dry_run": dry_run,
        "total_facts_scanned": total_facts,
        "unique_combinations": len(fact_groups),
        "duplicate_groups_found": len(duplicates_found),
        "total_duplicates": len(facts_to_delete),
        "deleted_count": deleted_count,
        "duplicates": duplicates_found[:50],  # Return first 50 for preview
    }


@router.get("/orphans")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="find_orphaned_facts",
    error_code_prefix="KNOWLEDGE",
)
async def find_orphaned_facts(req: Request):
    """
    Find facts whose source files no longer exist.
    Only checks facts with file_path metadata.

    Returns:
        List of orphaned facts
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(
            status_code=500, detail="Knowledge base not initialized"
        )

    logger.info("Scanning for orphaned facts...")

    orphaned_facts = []
    cursor = 0
    total_checked = 0

    while True:
        cursor, keys = kb.redis_client.scan(cursor, match="fact:*", count=100)

        if keys:
            # Use pipeline for batch operations
            pipe = kb.redis_client.pipeline()
            for key in keys:
                pipe.hget(key, "metadata")
            results = pipe.execute()

            for key, metadata_str in zip(keys, results):
                # Decode key if it's bytes
                if isinstance(key, bytes):
                    key = key.decode("utf-8")

                if metadata_str:
                    try:
                        metadata = json.loads(metadata_str)
                        file_path = metadata.get("file_path")

                        # Only check facts with file_path metadata
                        if file_path:
                            total_checked += 1

                            # Check if file exists
                            if not PathLib(file_path).exists():
                                orphaned_facts.append(
                                    {
                                        "fact_id": metadata.get("fact_id"),
                                        "fact_key": key,
                                        "title": metadata.get("title", "Unknown"),
                                        "category": metadata.get(
                                            "category", "Unknown"
                                        ),
                                        "file_path": file_path,
                                        "source": metadata.get("source", "Unknown"),
                                    }
                                )
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse metadata for {key}")

        if cursor == 0:
            break

    logger.info(
        f"Checked {total_checked} facts with file paths, found {len(orphaned_facts)} orphans"
    )

    return {
        "status": "success",
        "total_facts_checked": total_checked,
        "orphaned_count": len(orphaned_facts),
        "orphaned_facts": orphaned_facts,
    }


@router.delete("/orphans")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_orphaned_facts",
    error_code_prefix="KNOWLEDGE",
)
async def cleanup_orphaned_facts(req: Request, dry_run: bool = True):
    """
    Remove facts whose source files no longer exist.

    Args:
        dry_run: If True, only report orphans without deleting (default: True)

    Returns:
        Report of orphans found and removed
    """
    # First find orphans
    orphans_response = await find_orphaned_facts(req)
    orphaned_facts = orphans_response.get("orphaned_facts", [])

    if not orphaned_facts:
        return {
            "status": "success",
            "message": "No orphaned facts found",
            "deleted_count": 0,
        }

    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    # Delete orphans if not dry run
    deleted_count = 0
    if not dry_run:
        logger.info(f"Deleting {len(orphaned_facts)} orphaned facts...")

        fact_keys = [f["fact_key"] for f in orphaned_facts]

        # Delete in batches
        batch_size = 100
        for i in range(0, len(fact_keys), batch_size):
            batch = fact_keys[i : i + batch_size]
            kb.redis_client.delete(*batch)
            deleted_count += len(batch)

        logger.info(f"Deleted {deleted_count} orphaned facts")

    return {
        "status": "success",
        "dry_run": dry_run,
        "orphaned_count": len(orphaned_facts),
        "deleted_count": deleted_count,
        "orphaned_facts": orphaned_facts[:20],  # Return first 20 for preview
    }


@router.post("/import/scan")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_for_unimported_files",
    error_code_prefix="KNOWLEDGE",
)
async def scan_for_unimported_files(req: Request, directory: str = "docs"):
    """Scan directory for files that need to be imported"""
    from backend.models.knowledge_import_tracking import ImportTracker

    tracker = ImportTracker()
    # Use project-relative path instead of absolute path
    base_path = PathLib(__file__).parent.parent.parent
    scan_path = base_path / directory

    if not scan_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Directory not found: {directory}"
        )

    unimported = []
    needs_reimport = []

    # Scan for markdown files
    for file_path in scan_path.rglob("*.md"):
        if tracker.needs_reimport(str(file_path)):
            if tracker.is_imported(str(file_path)):
                needs_reimport.append(str(file_path.relative_to(base_path)))
            else:
                unimported.append(str(file_path.relative_to(base_path)))

    return {
        "status": "success",
        "directory": directory,
        "unimported_files": unimported,
        "needs_reimport": needs_reimport,
        "total_unimported": len(unimported),
        "total_needs_reimport": len(needs_reimport),
    }


@router.post("/vectorize_facts/background")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_background_vectorization",
    error_code_prefix="KNOWLEDGE",
)
async def start_background_vectorization(
    req: Request, background_tasks: BackgroundTasks
):
    """
    Start background vectorization of all pending facts.
    Returns immediately while vectorization runs in the background.
    """
    kb = await get_or_create_knowledge_base(req.app)
    if not kb:
        raise HTTPException(
            status_code=500, detail="Knowledge base not initialized"
        )

    vectorizer = get_background_vectorizer()

    # Add vectorization to background tasks
    background_tasks.add_task(vectorizer.vectorize_pending_facts, kb)

    return {
        "status": "started",
        "message": "Background vectorization started",
        "last_run": (
            vectorizer.last_run.isoformat() if vectorizer.last_run else None
        ),
        "is_running": vectorizer.is_running,
    }


@router.get("/vectorize_facts/status")
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_vectorization_status",
    error_code_prefix="KNOWLEDGE",
)
async def get_vectorization_status(req: Request):
    """Get the status of background vectorization"""
    vectorizer = get_background_vectorizer()

    return {
        "is_running": vectorizer.is_running,
        "last_run": (
            vectorizer.last_run.isoformat() if vectorizer.last_run else None
        ),
        "check_interval": vectorizer.check_interval,
        "batch_size": vectorizer.batch_size,
    }


# ===== CRUD OPERATIONS FOR FACTS =====


class UpdateFactRequest(BaseModel):
    """Request body for updating a fact"""

    content: Optional[str] = Field(None, description="New content for the fact")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Metadata updates (title, source, category, etc.)"
    )

    @validator("content")
    def validate_content(cls, v):
        """Validate content is not empty if provided"""
        if v is not None and not v.strip():
            raise ValueError("Content cannot be empty")
        return v


@router.put("/fact/{fact_id}")
async def update_fact(
    fact_id: str = Path(..., description="Fact ID to update"),
    request: UpdateFactRequest = ...,
    req: Request = None,
):
    """
    Update an existing knowledge base fact.

    Parameters:
    - fact_id: UUID of the fact to update
    - content (optional): New text content
    - metadata (optional): Metadata updates (title, source, category)

    Returns:
    - status: success or error
    - fact_id: ID of the updated fact
    - updated_fields: List of fields that were updated
    - message: Success or error message
    """
    try:
        # Validate fact_id format
        if not fact_id or not isinstance(fact_id, str):
            raise HTTPException(status_code=400, detail="Invalid fact_id format")

        # Validate at least one field is provided
        if request.content is None and request.metadata is None:
            raise HTTPException(
                status_code=400,
                detail="At least one field (content or metadata) must be provided",
            )

        # Get knowledge base instance
        kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
        if kb is None:
            raise HTTPException(
                status_code=500,
                detail="Knowledge base not initialized - please check logs for errors",
            )

        # Check if update_fact method exists (KnowledgeBaseV2)
        if not hasattr(kb, "update_fact"):
            raise HTTPException(
                status_code=501,
                detail="Update operation not supported by current knowledge base implementation",
            )

        logger.info(
            f"Updating fact {fact_id}: content={'provided' if request.content else 'unchanged'}, metadata={'provided' if request.metadata else 'unchanged'}"
        )

        # Call update_fact method
        result = await kb.update_fact(
            fact_id=fact_id, content=request.content, metadata=request.metadata
        )

        # Check if update was successful
        if result.get("success"):
            return {
                "status": "success",
                "fact_id": fact_id,
                "updated_fields": result.get("updated_fields", []),
                "vector_updated": result.get("vector_updated", False),
                "message": result.get("message", "Fact updated successfully"),
            }
        else:
            # Update failed - return error
            error_message = result.get("message", "Unknown error")
            if "not found" in error_message.lower():
                raise HTTPException(status_code=404, detail=error_message)
            else:
                raise HTTPException(status_code=500, detail=error_message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating fact {fact_id}: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Update fact failed: {str(e)}")


@router.delete("/fact/{fact_id}")
async def delete_fact(
    fact_id: str = Path(..., description="Fact ID to delete"), req: Request = None
):
    """
    Delete a knowledge base fact and its vectorization.

    Parameters:
    - fact_id: UUID of the fact to delete

    Returns:
    - status: success or error
    - fact_id: ID of the deleted fact
    - message: Success or error message
    """
    try:
        # Validate fact_id format
        if not fact_id or not isinstance(fact_id, str):
            raise HTTPException(status_code=400, detail="Invalid fact_id format")

        # Get knowledge base instance
        kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
        if kb is None:
            raise HTTPException(
                status_code=500,
                detail="Knowledge base not initialized - please check logs for errors",
            )

        # Check if delete_fact method exists (KnowledgeBaseV2)
        if not hasattr(kb, "delete_fact"):
            raise HTTPException(
                status_code=501,
                detail="Delete operation not supported by current knowledge base implementation",
            )

        logger.info(f"Deleting fact {fact_id}")

        # Call delete_fact method
        result = await kb.delete_fact(fact_id=fact_id)

        # Check if deletion was successful
        if result.get("success"):
            return {
                "status": "success",
                "fact_id": fact_id,
                "vector_deleted": result.get("vector_deleted", False),
                "message": result.get("message", "Fact deleted successfully"),
            }
        else:
            # Deletion failed - return error
            error_message = result.get("message", "Unknown error")
            if "not found" in error_message.lower():
                raise HTTPException(status_code=404, detail=error_message)
            else:
                raise HTTPException(status_code=500, detail=error_message)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting fact {fact_id}: {str(e)}")
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Delete fact failed: {str(e)}")
