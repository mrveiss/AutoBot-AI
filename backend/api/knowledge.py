# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge Base API endpoints for content management and search with RAG integration."""

import asyncio
import json
import logging
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query, Request

# NOTE: Pydantic models moved to knowledge_maintenance.py (Issue #185 - split oversized files)
# NOTE: Tag-related models moved to knowledge_tags.py
# NOTE: Search models (EnhancedSearchRequest) moved to knowledge_search.py
from backend.knowledge_factory import get_or_create_knowledge_base
from src.exceptions import InternalError
from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.path_validation import contains_path_traversal

# Import RAG Agent for enhanced search capabilities
try:
    from src.agents.rag_agent import get_rag_agent

    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logging.warning("RAG Agent not available - enhanced search features disabled")

# NOTE: RAGService and ADVANCED_RAG_AVAILABLE moved to knowledge_search.py (Issue #209)

# Set up logging
logger = logging.getLogger(__name__)

# Cache TTL constants (seconds)
CATEGORY_CACHE_TTL = 3600  # 1 hour for category counts (expensive to compute with 5k+ facts)

# Performance optimization: O(1) lookup for metadata types (Issue #326)
MANUAL_PAGE_TYPES = {"manual_page", "system_command"}

router = APIRouter()

# Import vectorization router (extracted from this file - Issue #185)
from backend.api.knowledge_vectorization import router as vectorization_router
router.include_router(vectorization_router)

# Import population functions (extracted from this file - Issue #209)
from backend.api.knowledge_population import (
    populate_system_commands,
    _populate_man_pages_background,
)

# ===== ENDPOINTS =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_stats",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/stats")
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
    # The previous implementation used synchronous redis_client.hgetall() which blocked the event
    # loop

    return stats


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_main_categories",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/test_categories_main")
async def test_main_categories():
    """Test endpoint to verify file is loaded"""
    from backend.knowledge_categories import CATEGORY_METADATA

    return {"status": "working", "categories": list(CATEGORY_METADATA.keys())}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_stats_basic",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/stats/basic")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_main_categories",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/categories/main")
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

    has_redis = kb_to_use.aioredis_client is not None if kb_to_use else False
    logger.info(
        f"get_main_categories - kb_to_use: {kb_to_use is not None}, "
        f"has_redis: {has_redis}"
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
                KnowledgeCategory.AUTOBOT_DOCUMENTATION: (
                    "kb:stats:category:autobot-documentation"
                ),
                KnowledgeCategory.SYSTEM_KNOWLEDGE: (
                    "kb:stats:category:system-knowledge"
                ),
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

                logger.info(f"Categorizing {len(all_facts)} facts into main categories")

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

                # Cache the counts for 1 hour (expensive to compute with 5k+ facts)
                for cat_id, cache_key in cache_keys.items():
                    await kb_to_use.aioredis_client.set(
                        cache_key, category_counts[cat_id], ex=CATEGORY_CACHE_TTL
                    )

        except Exception as e:
            logger.error(f"Error categorizing facts: {e}")
            # Fallback: just show 0 if we can't categorize

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_categories",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/categories")
async def get_knowledge_categories(req: Request):
    """Get all knowledge base categories with fact counts"""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {"categories": [], "total": 0}

    # Get stats - await async method
    stats = await kb_to_use.get_stats() if hasattr(kb_to_use, "get_stats") else {}
    categories_list = stats.get("categories", [])

    # Get all facts to count by category - async redis operation
    try:
        all_facts_data = await asyncio.to_thread(
            kb_to_use.redis_client.hgetall, "knowledge_base:facts"
        )
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_text_to_knowledge",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/add_text")
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



# NOTE: Search endpoints moved to knowledge_search.py (Issue #209)
# Includes: /search, /enhanced_search, /rag_search, /similarity_search

@with_error_handling(
    category=ErrorCategory.SERVICE_UNAVAILABLE,
    operation="get_knowledge_health",
    error_code_prefix="KB",
)
@router.get("/health")
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
            # Verify RAG agent is properly initialized by checking key attributes
            if hasattr(rag_agent, "is_rag_appropriate") and callable(
                rag_agent.is_rag_appropriate
            ):
                rag_status = "healthy"
            else:
                rag_status = "unhealthy: missing required methods"
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


@router.get("/entries")
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
                    "id": fact_id.decode() if isinstance(fact_id, bytes) else fact_id,
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_detailed_stats",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/detailed_stats")
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

    # Get all facts for detailed analysis - async operation
    try:
        all_facts_data = await asyncio.to_thread(
            kb_to_use.redis_client.hgetall, "knowledge_base:facts"
        )
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_machine_profile",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/machine_profile")
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
        "memory_available_gb": round(psutil.virtual_memory().available / (1024**3), 2),
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_man_pages_summary",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/man_pages/summary")
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

    # Get all facts and count man pages - async operation
    try:
        all_facts_data = await asyncio.to_thread(
            kb_to_use.redis_client.hgetall, "knowledge_base:facts"
        )

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
                if created_at and (last_indexed is None or created_at > last_indexed):
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="initialize_machine_knowledge",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/machine_knowledge/initialize")
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
        "message": (
            f"Machine knowledge initialized. Added {commands_added} system commands."
        ),
        "items_added": commands_added,
        "components": {
            "system_commands": commands_added,
            "man_pages": "background_task",  # Man pages run in background
        },
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="integrate_man_pages",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/man_pages/integrate")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_man_pages",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/man_pages/search")
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
        if metadata.get("type") in MANUAL_PAGE_TYPES:  # Issue #326
            man_page_results.append(result)

    return {
        "results": man_page_results,
        "total_results": len(man_page_results),
        "query": query,
        "limit": limit,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_all_knowledge",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/clear_all")
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
        "message": (
            f"Successfully cleared knowledge base. Removed {items_removed} entries."
        ),
        "items_removed": items_removed,
        "items_before": items_before,
    }


# Legacy endpoints for backward compatibility
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_document_to_knowledge",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/add_document")
async def add_document_to_knowledge(request: dict, req: Request):
    """Legacy endpoint - redirects to add_text"""
    return await add_text_to_knowledge(request, req)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="query_knowledge",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/query")
async def query_knowledge(request: dict, req: Request):
    """Legacy endpoint - redirects to search (now in knowledge_search.py)"""
    # Import search function from knowledge_search module
    from backend.api.knowledge_search import search_knowledge
    return await search_knowledge(request, req)


# NOTE: _enhance_search_with_rag helper moved to knowledge_search.py (Issue #209)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_facts_by_category",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/facts/by_category")
async def get_facts_by_category(
    req: Request, category: Optional[str] = None, limit: int = 100
):
    """
    Get facts grouped by category for browsing with caching.

    Performance: Uses Redis SET indexes (category:index:{category}) for O(1) lookups.
    Issue #258: Optimized from 5000ms+ to <200ms target.
    """
    kb = await get_or_create_knowledge_base(req.app)
    import json

    # REUSABLE PATTERN: Validate KB exists before use
    if kb is None:
        logger.error("Knowledge base not available for get_facts_by_category")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Knowledge base unavailable",
                "message": (
                    "The knowledge base service failed to initialize. Please check server logs."
                ),
                "code": "KB_INIT_FAILED",
            },
        )

    # Check cache first (60 second TTL) - async operation
    cache_key = f"kb:cache:facts_by_category:{category or 'all'}:{limit}"
    cached_result = await asyncio.to_thread(kb.redis_client.get, cache_key)

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
        f"Cache MISS for facts_by_category - using category index lookup "
        f"(category={category}, limit={limit})"
    )

    from backend.knowledge_categories import (
        KnowledgeCategory,
    )

    categories_dict = {}

    try:
        # OPTIMIZED (Issue #258): Use category indexes for O(1) lookup
        # Instead of scanning all 5000+ facts, we fetch only the fact IDs we need

        # Determine which categories to fetch
        if category:
            # Single category requested - direct index lookup
            categories_to_fetch = [category]
        else:
            # All categories - fetch from all 3 main category indexes
            categories_to_fetch = [cat.value for cat in KnowledgeCategory]

        # Step 1: Get fact IDs from category indexes (O(1) per category)
        # Use SRANDMEMBER to get only 'limit' random IDs - avoids fetching all 5000+ IDs
        category_fact_ids = {}
        for cat in categories_to_fetch:
            index_key = f"category:index:{cat}"
            # SRANDMEMBER with count returns up to 'limit' random members efficiently
            fact_ids = await asyncio.to_thread(
                kb.redis_client.srandmember, index_key, limit
            )
            if fact_ids:
                # Decode bytes to strings
                decoded_ids = [
                    fid.decode("utf-8") if isinstance(fid, bytes) else fid
                    for fid in fact_ids
                ]
                category_fact_ids[cat] = decoded_ids
                logger.debug(
                    f"Category index {cat}: fetched {len(decoded_ids)} fact IDs"
                )

        if not category_fact_ids:
            # No indexed facts found - fallback to legacy SCAN method
            logger.warning(
                "No category indexes found - falling back to SCAN method. "
                "Run category index migration to improve performance."
            )
            return await _get_facts_by_category_legacy(kb, category, limit)

        # Step 2: Batch fetch fact data using pipeline (single roundtrip)
        all_fact_keys = []
        for cat, fact_ids in category_fact_ids.items():
            for fid in fact_ids:
                all_fact_keys.append((cat, f"fact:{fid}"))

        if not all_fact_keys:
            return {"categories": {}, "total_facts": 0}

        # Pipeline fetch all facts at once
        pipeline = kb.redis_client.pipeline()
        for _, fact_key in all_fact_keys:
            pipeline.hgetall(fact_key)
        fact_results = await asyncio.to_thread(pipeline.execute)

        # Step 3: Process facts (pure Python, no I/O)
        for (cat, fact_key), fact_data in zip(all_fact_keys, fact_results):
            try:
                if not fact_data:
                    continue

                # Extract metadata (handle both bytes and string keys)
                metadata_raw = fact_data.get(b"metadata") or fact_data.get(
                    "metadata", b"{}"
                )
                metadata_str = (
                    metadata_raw.decode("utf-8")
                    if isinstance(metadata_raw, bytes)
                    else str(metadata_raw)
                )
                metadata = json.loads(metadata_str) if metadata_str else {}

                # Extract content
                content_raw = fact_data.get(b"content") or fact_data.get("content", b"")
                content = (
                    content_raw.decode("utf-8")
                    if isinstance(content_raw, bytes)
                    else str(content_raw) if content_raw else ""
                )

                fact_title = metadata.get("title", metadata.get("command", "Untitled"))
                fact_type = metadata.get("type", "unknown")

                if cat not in categories_dict:
                    categories_dict[cat] = []

                # Add to category list
                categories_dict[cat].append(
                    {
                        "key": fact_key,
                        "title": fact_title,
                        "content": (
                            content[:500] + "..." if len(content) > 500 else content
                        ),
                        "full_content": content,
                        "category": cat,
                        "type": fact_type,
                        "metadata": metadata,
                    }
                )

            except (json.JSONDecodeError, KeyError, TypeError) as e:
                logger.debug(f"Skipping invalid fact entry: {e}")
                continue

    except Exception as e:
        logger.error(f"Error in indexed fact retrieval: {e}")
        return {"categories": {}, "total_facts": 0, "error": str(e)}

    result = {
        "categories": categories_dict,
        "total_facts": sum(len(v) for v in categories_dict.values()),
        "category_filter": category,
    }

    # Cache the result for 60 seconds - async operation
    try:
        await asyncio.to_thread(
            kb.redis_client.setex, cache_key, 60, json.dumps(result)
        )
        logger.debug(
            f"Cached facts_by_category result (category={category}, limit={limit})"
        )
    except Exception as cache_error:
        logger.warning(f"Failed to cache facts_by_category: {cache_error}")

    return result


async def _get_facts_by_category_legacy(kb, category: Optional[str], limit: int):
    """
    Legacy fallback: Get facts by scanning all keys.
    Used when category indexes don't exist yet.
    """
    import json
    from backend.knowledge_categories import get_category_for_source

    categories_dict = {}

    # Step 1: Collect all fact keys using SCAN (non-blocking, cursor-based)
    all_fact_keys = []
    cursor = 0
    while True:
        cursor, keys = await asyncio.to_thread(
            kb.redis_client.scan, cursor, match="fact:*", count=1000
        )
        all_fact_keys.extend(keys)
        if cursor == 0:
            break

    if not all_fact_keys:
        return {"categories": {}, "total_facts": 0}

    # Step 2: Batch fetch all fact data using pipeline
    chunk_size = 500
    all_facts_data = []

    for i in range(0, len(all_fact_keys), chunk_size):
        chunk_keys = all_fact_keys[i : i + chunk_size]
        pipeline = kb.redis_client.pipeline()
        for key in chunk_keys:
            pipeline.hgetall(key)
        chunk_results = await asyncio.to_thread(pipeline.execute)
        all_facts_data.extend(zip(chunk_keys, chunk_results))

    # Step 3: Process facts
    for fact_key_bytes, fact_data in all_facts_data:
        try:
            if not fact_data:
                continue

            fact_key = (
                fact_key_bytes.decode("utf-8")
                if isinstance(fact_key_bytes, bytes)
                else str(fact_key_bytes)
            )

            metadata_raw = fact_data.get(b"metadata") or fact_data.get("metadata", b"{}")
            metadata_str = (
                metadata_raw.decode("utf-8")
                if isinstance(metadata_raw, bytes)
                else str(metadata_raw)
            )
            metadata = json.loads(metadata_str) if metadata_str else {}

            content_raw = fact_data.get(b"content") or fact_data.get("content", b"")
            content = (
                content_raw.decode("utf-8")
                if isinstance(content_raw, bytes)
                else str(content_raw) if content_raw else ""
            )

            source = metadata.get("source", "")
            fact_category = (
                get_category_for_source(source).value if source else "general"
            )

            if category and fact_category != category:
                continue

            fact_title = metadata.get("title", metadata.get("command", "Untitled"))
            fact_type = metadata.get("type", "unknown")

            if fact_category not in categories_dict:
                categories_dict[fact_category] = []

            if len(categories_dict[fact_category]) >= limit:
                continue

            categories_dict[fact_category].append(
                {
                    "key": fact_key,
                    "title": fact_title,
                    "content": (
                        content[:500] + "..." if len(content) > 500 else content
                    ),
                    "full_content": content,
                    "category": fact_category,
                    "type": fact_type,
                    "metadata": metadata,
                }
            )

        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    return {
        "categories": categories_dict,
        "total_facts": sum(len(v) for v in categories_dict.values()),
        "category_filter": category,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_fact_by_key",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/fact/{fact_key}")
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
    # Additional security check for path traversal (Issue #328 - uses shared validation)
    if contains_path_traversal(fact_key):
        raise HTTPException(
            status_code=400, detail="Invalid fact_key: path traversal not allowed"
        )

    kb = await get_or_create_knowledge_base(req.app)
    import json

    # Get fact data from Redis hash - async operation
    fact_data = await asyncio.to_thread(kb.redis_client.hgetall, fact_key)

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_import_status",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/import/status")
async def get_import_status(
    req: Request, file_path: Optional[str] = None, category: Optional[str] = None
):
    """Get import status for files"""
    from backend.models.knowledge_import_tracking import ImportTracker

    tracker = ImportTracker()
    results = tracker.get_import_status(file_path=file_path, category=category)

    return {"status": "success", "imports": results, "total": len(results)}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_import_statistics",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/import/statistics")
async def get_import_statistics(req: Request):
    """Get import statistics"""
    from backend.models.knowledge_import_tracking import ImportTracker

    tracker = ImportTracker()
    stats = tracker.get_statistics()

    return {"status": "success", "statistics": stats}


# ===== MAINTENANCE ENDPOINTS =====
# NOTE: Maintenance and bulk operation endpoints moved to knowledge_maintenance.py (Issue #185)
# Includes: deduplication, bulk operations, orphaned facts, export/import, cleanup, host scanning

from backend.api.knowledge_maintenance import router as maintenance_router
router.include_router(maintenance_router)
