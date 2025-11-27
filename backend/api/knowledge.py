# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge Base API endpoints for content management and search with RAG integration."""

import json
import logging
from pathlib import Path as PathLib
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query, Request

# Import Pydantic models from dedicated module (Issue #185 - split oversized files)
# NOTE: Tag-related models moved to knowledge_tags.py
# NOTE: Search models (EnhancedSearchRequest) moved to knowledge_search.py
from backend.api.knowledge_models import (
    BulkCategoryUpdateRequest,
    BulkDeleteRequest,
    CleanupRequest,
    DeduplicationRequest,
    ExportRequest,
    ImportRequest,
    ScanHostChangesRequest,
    UpdateFactRequest,
)
from backend.knowledge_factory import get_or_create_knowledge_base
from src.exceptions import InternalError
from src.utils.error_boundaries import ErrorCategory, with_error_handling

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

                # Cache the counts for 60 seconds
                for cat_id, cache_key in cache_keys.items():
                    await kb_to_use.aioredis_client.set(
                        cache_key, category_counts[cat_id], ex=60
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
        ),
        fact_id = result.get("fact_id")
    else:
        # Original KnowledgeBase
        result = await kb_to_use.store_fact(
            text=text,
            metadata={"title": title, "source": source, "category": category},
        ),
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
        if metadata.get("type") in ["manual_page", "system_command"]:
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
    """Get facts grouped by category for browsing with caching"""
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
        f"Cache MISS for facts_by_category - scanning all facts "
        f"(category={category}, limit={limit})"
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
            metadata_str = fact_data.get("metadata") or fact_data.get(
                b"metadata", b"{}"
            ),
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
            ),
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
        categories_dict = {k: v for k, v in categories_dict.items() if k == category}

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="deduplicate_facts",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/deduplicate")
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
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_host_changes",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/scan_host_changes")
async def scan_host_changes(req: Request, request_data: ScanHostChangesRequest):
    """
    ULTRA-FAST document change scanner using file metadata.

    Performance: ~0.5 seconds for 10,000 documents (100x faster than subprocess approach)

    Detects:
    - New documents (software installed)
    - Updated documents (man pages changed via mtime/size)
    - Removed documents (software uninstalled)

    Method:
    - Uses file metadata (mtime, size) instead of content reading
    - Direct filesystem access (no subprocess overhead)
    - Redis caching for incremental scans

    Args:
        request_data: Scan configuration with machine_id, force, and scan_type

    Returns:
        Dictionary with change detection results:
        - added: List of new documents
        - updated: List of changed documents (mtime/size changed)
        - removed: List of removed documents
        - unchanged: Count of unchanged documents
        - scan_duration_seconds: Actual scan time
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

    # Extract parameters from request
    machine_id = request_data.machine_id
    force = request_data.force
    scan_type = request_data.scan_type
    auto_vectorize = request_data.auto_vectorize

    logger.info(
        f"Fast scan starting for {machine_id} (type={scan_type}, auto_vectorize={auto_vectorize})"
    )

    # Use ultra-fast metadata-based scanner
    from backend.services.fast_document_scanner import FastDocumentScanner

    scanner = FastDocumentScanner(kb.redis_client)

    # Perform fast scan (limit to 100 for reasonable response time)
    result = scanner.scan_for_changes(
        machine_id=machine_id,
        scan_type=scan_type,
        limit=100,  # Process first 100 documents
        force=force,
    )

    # Auto-vectorization: Add changed documents to knowledge base
    if auto_vectorize:
        vectorization_results = {
            "attempted": 0,
            "successful": 0,
            "failed": 0,
            "skipped": 0,
            "details": [],
        }

        # Vectorize added and updated documents
        documents_to_vectorize = (
            result["changes"]["added"] + result["changes"]["updated"]
        )

        for doc_change in documents_to_vectorize:
            vectorization_results["attempted"] += 1

            command = doc_change.get("command")
            file_path = doc_change.get("file_path")
            doc_id = doc_change.get("document_id")

            if not file_path or not command:
                vectorization_results["skipped"] += 1
                vectorization_results["details"].append(
                    {
                        "doc_id": doc_id,
                        "command": command,
                        "status": "skipped",
                        "reason": "Missing file_path or command",
                    }
                )
                continue

            try:
                # Read man page content
                content = scanner.read_man_page_content(file_path, command)

                if not content or len(content.strip()) < 10:
                    vectorization_results["failed"] += 1
                    vectorization_results["details"].append(
                        {
                            "doc_id": doc_id,
                            "command": command,
                            "status": "failed",
                            "reason": "Empty or too short content",
                        }
                    )
                    continue

                # Add to knowledge base with metadata
                metadata = {
                    "category": "system/manpages",
                    "title": f"man {command}",
                    "command": command,
                    "machine_id": machine_id,
                    "file_path": file_path,
                    "document_id": doc_id,
                    "change_type": doc_change.get("change_type"),
                    "content_size": len(content),
                }

                kb_result = await kb.add_document(
                    content=content, metadata=metadata, doc_id=doc_id
                )

                if kb_result.get("status") == "success":
                    vectorization_results["successful"] += 1
                    vectorization_results["details"].append(
                        {
                            "doc_id": doc_id,
                            "command": command,
                            "status": "success",
                            "fact_id": kb_result.get("fact_id"),
                        }
                    )
                else:
                    vectorization_results["failed"] += 1
                    vectorization_results["details"].append(
                        {
                            "doc_id": doc_id,
                            "command": command,
                            "status": "failed",
                            "reason": kb_result.get("message", "Unknown error"),
                        }
                    )

            except Exception as e:
                logger.error(f"Vectorization failed for {command}: {e}")
                vectorization_results["failed"] += 1
                vectorization_results["details"].append(
                    {
                        "doc_id": doc_id,
                        "command": command,
                        "status": "error",
                        "reason": str(e),
                    }
                )

        # Add vectorization results to response
        result["vectorization"] = vectorization_results
        logger.info(
            f"Vectorization completed: "
            f"{vectorization_results['successful']}/{vectorization_results['attempted']} successful"
        )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="find_orphaned_facts",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/orphans")
async def find_orphaned_facts(req: Request):
    """
    Find facts whose source files no longer exist.
    Only checks facts with file_path metadata.

    Returns:
        List of orphaned facts
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=500, detail="Knowledge base not initialized")

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
                                        "category": metadata.get("category", "Unknown"),
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_orphaned_facts",
    error_code_prefix="KNOWLEDGE",
)
@router.delete("/orphans")
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="scan_for_unimported_files",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/import/scan")
async def scan_for_unimported_files(req: Request, directory: str = "docs"):
    """Scan directory for files that need to be imported"""
    from backend.models.knowledge_import_tracking import ImportTracker

    tracker = ImportTracker()
    # Use project-relative path instead of absolute path
    base_path = PathLib(__file__).parent.parent.parent
    scan_path = base_path / directory

    if not scan_path.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_fact",
    error_code_prefix="KNOWLEDGE",
)
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

    content_status = 'provided' if request.content else 'unchanged'
    metadata_status = 'provided' if request.metadata else 'unchanged'
    logger.info(
        f"Updating fact {fact_id}: content={content_status}, metadata={metadata_status}"
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_fact",
    error_code_prefix="KNOWLEDGE",
)
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


# NOTE: Tag management endpoints moved to knowledge_tags.py (Issue #209)


# ===== BULK OPERATION ENDPOINTS (Issue #79) =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="export_knowledge",
    error_code_prefix="KB",
)
@router.post("/export")
async def export_knowledge(request: ExportRequest, req: Request):
    """
    Export knowledge base facts to JSON, CSV, or Markdown.

    Issue #79: Bulk Operations - Export functionality

    Request body:
    - format: "json", "csv", or "markdown" (default: "json")
    - filters: Optional filters (categories, tags, date_from, date_to, fact_ids)
    - include_metadata: Include metadata in export (default: True)
    - include_tags: Include tags in export (default: True)
    - include_embeddings: Include vector embeddings (default: False, large file)

    Returns:
    - success: Boolean status
    - format: Export format used
    - total_facts: Number of facts exported
    - data: Export data as string
    - exported_at: ISO timestamp
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    # Extract filters
    filters = request.filters
    categories = filters.categories if filters else None
    tags = filters.tags if filters else None
    fact_ids = filters.fact_ids if filters else None
    date_from = filters.date_from if filters else None
    date_to = filters.date_to if filters else None

    logger.info(
        f"Export request: format={request.format.value}, include_metadata={request.include_metadata}")

    result = await kb.export_facts(
        format=request.format.value,
        categories=categories,
        tags=tags,
        fact_ids=fact_ids,
        date_from=date_from,
        date_to=date_to,
        include_metadata=request.include_metadata,
        include_tags=request.include_tags,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="import_knowledge",
    error_code_prefix="KB",
)
@router.post("/import")
async def import_knowledge(
    request: ImportRequest,
    req: Request,
    data: str = Query(..., description="Import data string"),
):
    """
    Import facts into the knowledge base from JSON or CSV.

    Issue #79: Bulk Operations - Import functionality

    Query parameters:
    - data: The import data as a string

    Request body:
    - format: "json" or "csv" (default: "json")
    - validate_only: Only validate without importing (default: False)
    - skip_duplicates: Skip existing facts (default: True)
    - overwrite_existing: Overwrite existing facts (default: False)
    - default_category: Default category for imported facts (default: "imported")

    Returns:
    - success: Boolean status
    - total_facts: Total facts in import data
    - imported: Number of facts imported
    - skipped: Number of facts skipped
    - overwritten: Number of facts overwritten
    - errors: Any import errors
    - validation_errors: Any validation errors
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(
        f"Import request: format={request.format.value}, validate_only={request.validate_only}"
    )

    result = await kb.import_facts(
        data=data,
        format=request.format.value,
        validate_only=request.validate_only,
        skip_duplicates=request.skip_duplicates,
        overwrite_existing=request.overwrite_existing,
        default_category=request.default_category,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="find_duplicates",
    error_code_prefix="KB",
)
@router.post("/deduplicate")
async def find_duplicates(request: DeduplicationRequest, req: Request):
    """
    Find duplicate or near-duplicate facts in the knowledge base.

    Issue #79: Bulk Operations - Deduplication

    Request body:
    - similarity_threshold: Threshold for near-duplicates (0.5-1.0, default: 0.95)
    - dry_run: Only report duplicates (default: True)
    - keep_strategy: "newest", "oldest", or "longest" (default: "newest")
    - category: Limit to specific category (optional)
    - max_comparisons: Maximum comparisons to prevent timeout (default: 10000)

    Returns:
    - success: Boolean status
    - total_facts_scanned: Number of facts scanned
    - exact_duplicates: Count of exact duplicates
    - near_duplicates: Count of near-duplicates
    - total_duplicates: Total duplicate pairs found
    - duplicates: List of duplicate pairs with similarity scores
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(
        f"Deduplication request: threshold={request.similarity_threshold}, "
        f"dry_run={request.dry_run}, category={request.category}"
    )

    result = await kb.find_duplicates(
        similarity_threshold=request.similarity_threshold,
        category=request.category,
        max_comparisons=request.max_comparisons,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="bulk_delete",
    error_code_prefix="KB",
)
@router.delete("/bulk")
async def bulk_delete_facts(request: BulkDeleteRequest, req: Request):
    """
    Delete multiple facts at once.

    Issue #79: Bulk Operations - Bulk delete

    Request body:
    - fact_ids: List of fact IDs to delete (max 500)
    - confirm: Must be True to actually delete (default: False)

    Returns:
    - success: Boolean status
    - deleted: Number of facts deleted
    - not_found: Number of facts not found
    - errors: Any deletion errors
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(f"Bulk delete request: {len(request.fact_ids)} facts, confirm={request.confirm}")

    result = await kb.bulk_delete(
        fact_ids=request.fact_ids,
        confirm=request.confirm,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="bulk_update_category",
    error_code_prefix="KB",
)
@router.post("/bulk/category")
async def bulk_update_category(request: BulkCategoryUpdateRequest, req: Request):
    """
    Update category for multiple facts at once.

    Issue #79: Bulk Operations - Bulk category update

    Request body:
    - fact_ids: List of fact IDs to update (max 500)
    - new_category: New category to assign

    Returns:
    - success: Boolean status
    - updated: Number of facts updated
    - not_found: Number of facts not found
    - errors: Any update errors
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(
        f"Bulk category update: {len(request.fact_ids)} facts → {request.new_category}"
    )

    result = await kb.bulk_update_category(
        fact_ids=request.fact_ids,
        new_category=request.new_category,
    )

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_knowledge_base",
    error_code_prefix="KB",
)
@router.post("/cleanup")
async def cleanup_knowledge_base(request: CleanupRequest, req: Request):
    """
    Clean up the knowledge base.

    Issue #79: Bulk Operations - Cleanup

    Request body:
    - remove_empty: Remove facts with empty content (default: True)
    - remove_orphaned_tags: Remove tags with no facts (default: True)
    - fix_metadata: Fix malformed metadata JSON (default: True)
    - dry_run: Only report issues without fixing (default: True)

    Returns:
    - success: Boolean status
    - dry_run: Whether this was a dry run
    - issues_found: Count of issues by type
    - issues_details: Details of issues (only in dry_run mode)
    - fixes_applied: Count of fixes applied (only when not dry_run)
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(
            status_code=500,
            detail="Knowledge base not initialized",
        )

    logger.info(
        f"Cleanup request: dry_run={request.dry_run}, "
        f"remove_empty={request.remove_empty}, remove_orphaned_tags={request.remove_orphaned_tags}"
    )

    result = await kb.cleanup(
        remove_empty=request.remove_empty,
        remove_orphaned_tags=request.remove_orphaned_tags,
        fix_metadata=request.fix_metadata,
        dry_run=request.dry_run,
    )

    return result
