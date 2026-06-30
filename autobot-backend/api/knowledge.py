# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base API — primary document management and general search.

Responsibility (issue #3336):
    This module is the **canonical owner** of all knowledge-base document
    lifecycle operations.  It is mounted at ``/api/knowledge_base/*``.

Scope:
    - Ingesting content: text facts, URLs, file uploads, man-pages,
      machine profiles, and AutoBot documentation.
    - General-purpose semantic search (vector + keyword) across the
      entire knowledge base.
    - Category, tag, collection, and metadata management.
    - Import/export job status and statistics.
    - Admin health and clear-all operations.

What does NOT belong here:
    - Chat-session-scoped operations (temporary facts, file associations,
      session compilation, session-fact preservation) → api/chat_knowledge.py
    - LLM-mediated librarian queries (intent detection, auto-summarise,
      per-request parameter overrides) → api/kb_librarian.py

Related modules:
    - ``api/chat_knowledge.py``  — chat-session knowledge lifecycle
    - ``api/kb_librarian.py``    — librarian agent (unregistered, internal use)
    - ``api/knowledge_search.py``  — search sub-router (included here)
    - ``api/knowledge_tags.py``, ``api/knowledge_categories.py``, etc.
"""

import asyncio
import json
import logging

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Path,
    Query,
    Request,
)

from api.schemas_knowledge import (
    AddFactsRequest,
    AddUrlRequest,
    AudioIngestRequest,
    DocsBrowseRequest,
    OrgKnowledgeConfigPayload,
    WatchFolderControlRequest,
    WatchFolderCreateRequest,
    WatchFolderListResponse,
    WatchFolderResponse,
    WatchFolderStatsResponse,
)
from api.system_health import ComponentHealth, KnownProbes, register_health_probe
from auth_middleware import check_admin_permission, get_auth_middleware, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import QueryDefaults
from exceptions import InternalError
from knowledge.query_sanitizer import sanitize_document as _sanitize_document
from knowledge.schemas.documents import (
    DocsBrowseResponse,
    DocsCategoriesResponse,
    DocsStatsResponse,
    DocsWatcherControlResponse,
    DocsWatcherStatusResponse,
)
from knowledge.schemas.facts import (
    AddFactResponse,
    AddTextResponse,
    AddUrlResponse,
    AudioIngestResponse,
    ClearAllResponse,
    FactByKeyResponse,
    FactsByCategoryResponse,
    KnowledgeEntriesResponse,
    ManPageSearchResponse,
    QueryKnowledgeResponse,
    UploadFileResponse,
)
from knowledge.schemas.operations import (
    ImportStatisticsResponse,
    ImportStatusResponse,
    KnowledgeStatsResponse,
    MachineKnowledgeInitResponse,
    MachineProfileResponse,
    ManPagesIntegrateResponse,
    ManPagesSummaryResponse,
    OrgKnowledgeConfigResponse,
    TestCategoriesResponse,
)
from knowledge.schemas.stats import (
    DetailedKnowledgeStats,
    KnowledgeCategoriesResponse,
    KnowledgeMainCategoriesResponse,
    KnowledgeStatsBasic,
)

# NOTE: Pydantic models moved to knowledge_maintenance.py (Issue #185 - split oversized files)
# NOTE: Tag-related models moved to knowledge_tags.py
# NOTE: Search models (SearchRequest) defined in schemas_knowledge.py (#10666 B1)
from knowledge_factory import get_or_create_knowledge_base
from services.audit.audit import AuditAction, audit_record  # GH#8290 Phase 2
from utils.path_validation import contains_path_traversal

# =============================================================================
# Issue #549: Pydantic Models for Knowledge Ingestion Endpoints
# =============================================================================


# File upload constants (Issue #549 Code Review)
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".json", ".csv", ".html"}

# Import RAG Agent for enhanced search capabilities
try:
    pass

    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logging.warning("RAG Agent not available - enhanced search features disabled")

# NOTE: RAGService and ADVANCED_RAG_AVAILABLE moved to knowledge_search.py (Issue #209)

# Set up logging
logger = get_logger(__name__)

# Cache TTL constants (seconds)
CATEGORY_CACHE_TTL = 3600  # 1 hour for category counts (expensive to compute with 5k+ facts)

# Performance optimization: O(1) lookup for metadata types (Issue #326)
MANUAL_PAGE_TYPES = {"manual_page", "system_command"}


def _get_fact_source(fact: dict) -> str:
    """Extract source identifier from fact for categorization (Issue #315: extracted).

    Args:
        fact: Fact dictionary with metadata

    Returns:
        Source string for category lookup
    """
    source = fact.get("metadata", {}).get("source", "") or fact.get("source", "")
    if not source:
        # Try filename or title as fallback
        source = fact.get("metadata", {}).get("filename", "") or fact.get("title", "")
    return source


async def _compute_category_counts(all_facts: list, get_category_for_source, category_counts: dict) -> None:
    """Compute category counts from facts (Issue #315: extracted).

    Args:
        all_facts: List of fact dictionaries
        get_category_for_source: Function to map source to category
        category_counts: Dict to update with counts (mutated in place)
    """
    for fact in all_facts:
        source = _get_fact_source(fact)
        main_category = get_category_for_source(source)
        if main_category in category_counts:
            category_counts[main_category] += 1


def _format_knowledge_entry(fact_id: bytes | str, fact: dict) -> dict:
    """
    Format a knowledge fact into a frontend-compatible entry.

    Issue #281: Extracted from get_knowledge_entries to reduce function length
    and improve testability.

    Args:
        fact_id: Redis key for the fact (bytes or string)
        fact: Parsed fact dictionary with content and metadata

    Returns:
        Formatted entry dict with id, content, title, source, category,
        type, created_at, and metadata fields
    """
    metadata = fact.get("metadata", {})
    return {
        "id": fact_id.decode() if isinstance(fact_id, bytes) else fact_id,
        "content": fact.get("content", ""),
        "title": metadata.get("title", "Untitled"),
        "source": metadata.get("source", "unknown"),
        "category": metadata.get("category", "general"),
        "type": metadata.get("type", "document"),
        "created_at": metadata.get("created_at"),
        "metadata": metadata,
    }


def _parse_man_page_fact(fact_json: bytes) -> tuple:
    """Parse a man page fact and extract counts (Issue #315: extracted).

    Args:
        fact_json: JSON bytes of fact data

    Returns:
        Tuple of (is_man_page, is_system_command, created_at) or (False, False, None) on error
    """
    try:
        fact = json.loads(fact_json)
        metadata = fact.get("metadata", {})
        fact_type = metadata.get("type")

        is_man_page = fact_type == "manual_page"
        is_system_command = fact_type == "system_command"
        created_at = metadata.get("created_at")

        return is_man_page, is_system_command, created_at
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.warning("Error parsing fact metadata: %s", e)
        return False, False, None


router = APIRouter()

# Import vectorization router (extracted from this file - Issue #185)
from api.knowledge_vectorization import router as vectorization_router

router.include_router(vectorization_router)

# Issue #3242: project-scoped board management endpoints
from api.knowledge_boards import router as boards_router

router.include_router(boards_router)

# Import population functions (extracted from this file - Issue #209)
from api.knowledge_population import (
    _populate_man_pages_background,
    populate_system_commands,
)

# ===== ENDPOINTS =====


@router.get("/stats", response_model=KnowledgeStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_stats",
    error_code_prefix="KNOWLEDGE",
)
async def get_knowledge_stats(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
) -> KnowledgeStatsResponse:
    """Get knowledge base statistics - FIXED to use proper instance

    Issue #744: Requires admin authentication.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        # Issue #5407: KB instance not initialized - emit ops-visible
        # counter + warning so operators see the degradation.
        logger.warning("get_knowledge_stats: KB uninitialized - returning offline stats")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="stats", reason="kb_uninit").inc()
        return KnowledgeStatsResponse(
            total_documents=0,
            total_chunks=0,
            total_facts=0,
            total_vectors=0,
            categories=[],
            db_size=0,
            status="offline",
            last_updated=None,
            redis_db=None,
            index_name=None,
            initialized=False,
            rag_available=RAG_AVAILABLE,
            vectorization_stats={
                "total_facts": 0,
                "vectorized_count": 0,
                "not_vectorized_count": 0,
                "vectorization_percentage": 0.0,
            },
        )

    stats = await kb_to_use.get_stats()
    stats["rag_available"] = RAG_AVAILABLE

    # Vectorization stats removed - get_stats() already provides fact counts using async operations
    # The previous implementation used synchronous redis_client.hgetall() which blocked the event
    # loop

    return KnowledgeStatsResponse(**stats)


@router.get("/test_categories_main", response_model=TestCategoriesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_main_categories",
    error_code_prefix="KNOWLEDGE",
)
async def test_main_categories(
    admin_check: bool = Depends(check_admin_permission),
) -> TestCategoriesResponse:
    """Test endpoint to verify file is loaded

    Issue #744: Requires admin authentication.
    """
    from knowledge_categories import CATEGORY_METADATA

    return TestCategoriesResponse(status="working", categories=list(CATEGORY_METADATA.keys()))


@router.get("/stats/basic", response_model=KnowledgeStatsBasic)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_stats_basic",
    error_code_prefix="KNOWLEDGE",
)
async def get_knowledge_stats_basic(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
) -> KnowledgeStatsBasic:
    """Get basic knowledge base statistics for quick display

    Issue #744: Requires admin authentication.
    Issue #5248: response typed as Pydantic model so OpenAPI captures schema.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        # Issue #5407: KB instance not initialized.
        logger.warning("get_knowledge_stats_basic: KB uninitialized - returning offline stats")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="stats_basic", reason="kb_uninit").inc()
        return KnowledgeStatsBasic(
            status="offline",
            total_facts=0,
            total_vectors=0,
            categories=[],
        )

    stats = await kb_to_use.get_stats()

    # Return lightweight basic stats
    return KnowledgeStatsBasic(
        total_facts=stats.get("total_facts", 0),
        total_vectors=stats.get("total_vectors", 0),
        categories=stats.get("categories", []),
        status="online" if stats.get("initialized", False) else "offline",
    )


def _get_category_cache_keys(KnowledgeCategory) -> dict:
    """Get cache keys for category counts (Issue #398: extracted)."""
    return {
        KnowledgeCategory.AUTOBOT_DOCUMENTATION: "kb:stats:category:autobot-documentation",
        KnowledgeCategory.SYSTEM_KNOWLEDGE: "kb:stats:category:system-knowledge",
        KnowledgeCategory.USER_KNOWLEDGE: "kb:stats:category:user-knowledge",
    }


async def _get_or_compute_category_counts(kb, cache_keys: dict, get_category_for_source, category_counts: dict) -> None:
    """Get cached counts or compute from facts (Issue #398: extracted)."""
    cached_values = await kb.redis().mget(list(cache_keys.values()))
    if all(v is not None for v in cached_values):
        # Use cached values
        for i, cat_id in enumerate(cache_keys.keys()):
            category_counts[cat_id] = int(cached_values[i])
        logger.debug("Using cached category counts: %s", category_counts)
    else:
        # Cache miss - compute counts
        logger.info("Cache miss - computing category counts from all facts")
        all_facts = await kb.get_all_facts()
        logger.info("Categorizing %s facts into main categories", len(all_facts))
        await _compute_category_counts(all_facts, get_category_for_source, category_counts)
        logger.info("Category counts: %s", category_counts)
        # Cache for 1 hour
        for cat_id, cache_key in cache_keys.items():
            await kb.redis().set(cache_key, category_counts[cat_id], ex=CATEGORY_CACHE_TTL)


def _build_main_categories(CATEGORY_METADATA, category_counts: dict) -> list:
    """Build main categories list with counts (Issue #398: extracted)."""
    return [
        {
            "id": cat_id,
            "name": meta["name"],
            "description": meta["description"],
            "icon": meta["icon"],
            "color": meta["color"],
            "examples": meta["examples"],
            "count": category_counts.get(cat_id, 0),
        }
        for cat_id, meta in CATEGORY_METADATA.items()
    ]


@router.get("/categories/main", response_model=KnowledgeMainCategoriesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_main_categories",
    error_code_prefix="KNOWLEDGE",
)
async def get_main_categories(
    current_user: dict = Depends(get_current_user),
    req: Request = None,
) -> KnowledgeMainCategoriesResponse:
    """Get the 3 main knowledge base categories with their metadata and stats.

    Issue #910: Available to all authenticated users (not admin-only).
    The 3 top-level categories are non-sensitive public metadata.
    Issue #5248: response typed as Pydantic model so OpenAPI captures schema.
    """
    from knowledge_categories import (
        CATEGORY_METADATA,
        KnowledgeCategory,
        get_category_for_source,
    )

    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    redis_client = None
    if kb is not None:
        try:
            redis_client = kb.redis()
        except RuntimeError:
            redis_client = None
    logger.info(
        "get_main_categories - kb: %s, has_redis: %s",
        kb is not None,
        redis_client is not None,
    )
    if redis_client is None:
        # Issue #5319 / #5407: surface kb_connected=false as a log line +
        # Prometheus counter so operators see the outage, not just the
        # frontend banner.  reason="redis_down" - KB instance exists but
        # its Redis connection is unreachable (infra page).
        logger.warning("KB categories returning kb_connected=false - Redis unreachable")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="categories_main", reason="redis_down").inc()

    category_counts = {
        KnowledgeCategory.AUTOBOT_DOCUMENTATION: 0,
        KnowledgeCategory.SYSTEM_KNOWLEDGE: 0,
        KnowledgeCategory.USER_KNOWLEDGE: 0,
    }

    if redis_client is not None:
        logger.info("Attempting to get cached category counts...")
        try:
            cache_keys = _get_category_cache_keys(KnowledgeCategory)
            await _get_or_compute_category_counts(kb, cache_keys, get_category_for_source, category_counts)
        except Exception as e:
            logger.error("Error categorizing facts: %s", e)

    main_categories = _build_main_categories(CATEGORY_METADATA, category_counts)
    return KnowledgeMainCategoriesResponse(
        categories=main_categories,
        total=len(main_categories),
        kb_connected=redis_client is not None,
    )


@router.get("/categories", response_model=KnowledgeCategoriesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_categories",
    error_code_prefix="KNOWLEDGE",
)
async def get_knowledge_categories(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
) -> KnowledgeCategoriesResponse:
    """Get all knowledge base categories with fact counts

    Issue #744: Requires admin authentication.
    Issue #5248: response typed as Pydantic model so OpenAPI captures schema.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        # Issue #5407: KB instance not initialized.
        logger.warning("get_knowledge_categories: KB uninitialized - returning empty list")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="categories", reason="kb_uninit").inc()
        return KnowledgeCategoriesResponse(categories=[], total=0)

    # Get stats - await async method
    stats = await kb_to_use.get_stats() if hasattr(kb_to_use, "get_stats") else {}
    categories_list = stats.get("categories", [])

    # Get all facts to count by category - async redis operation
    try:
        all_facts_data = await asyncio.to_thread(kb_to_use.redis_client.hgetall, "knowledge_base:facts")
    except Exception as redis_err:
        logger.debug("Redis error getting facts: %s", redis_err)
        all_facts_data = {}

    category_counts = {}
    for fact_json in all_facts_data.values():
        try:
            fact = json.loads(fact_json)
            category = fact.get("metadata", {}).get("category", "uncategorized")
            category_counts[category] = category_counts.get(category, 0) + 1
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Error parsing fact JSON: %s", e)
            continue

    # Format for frontend with counts
    categories = [{"name": cat, "count": category_counts.get(cat, 0), "id": cat} for cat in categories_list]

    # Also expose the doc_indexer's autobot_docs collection so AutoBot's own
    # indexed documentation always appears as a category, even before any user
    # facts are added to the main KB.
    existing_names = {c["name"] for c in categories}
    try:
        from services.knowledge.doc_indexer import get_doc_indexer_service

        doc_indexer = get_doc_indexer_service()
        if await doc_indexer.initialize():
            doc_stats = await doc_indexer.get_stats()
            doc_count = doc_stats.get("count", 0)
            if doc_count > 0 and "autobot_docs" not in existing_names:
                categories.append({"name": "autobot_docs", "count": doc_count, "id": "autobot_docs"})
    except Exception as doc_idx_err:
        logger.debug("Could not fetch doc_indexer stats (non-critical): %s", doc_idx_err)

    return KnowledgeCategoriesResponse(
        categories=categories,
        total=len(categories),
    )


def _extract_add_text_fields(request: dict) -> tuple:
    """Helper for add_text_to_knowledge. Ref: #1088.

    Extracts and validates all request fields for the add_text endpoint.
    Raises ValueError when the text field is empty.

    Returns:
        Tuple of (text, title, source, category, access_level,
                  visibility, owner_id, organization_id, group_ids, shared_with,
                  board_id)
    """
    text = request.get("text", "")
    title = request.get("title", "")
    source = request.get("source", "manual")
    category = request.get("category", "general")
    # Issue #685: hierarchical access fields
    access_level = request.get("access_level", "user")
    visibility = request.get("visibility", "private")
    owner_id = request.get("owner_id")
    organization_id = request.get("organization_id")
    group_ids = request.get("group_ids", [])
    shared_with = request.get("shared_with", [])
    # Issue #3242: board scoping
    board_id = request.get("board_id")
    if not text:
        raise ValueError("Text content is required")
    logger.info(
        "Adding text to knowledge: title='%s', source='%s', " "access_level='%s', visibility='%s', length=%d",
        title,
        source,
        access_level,
        visibility,
        len(text),
    )
    return (
        text,
        title,
        source,
        category,
        access_level,
        visibility,
        owner_id,
        organization_id,
        group_ids,
        shared_with,
        board_id,
    )


def _build_ownership_metadata(
    title: str,
    source: str,
    category: str,
    access_level: str,
    visibility: str,
    owner_id,
    organization_id,
    group_ids: list,
    shared_with: list,
    board_id: str | None = None,
) -> dict:
    """Helper for add_text_to_knowledge. Ref: #1088.

    Builds the metadata dict including optional ownership fields.
    Only non-empty/non-falsy ownership fields are included.

    Returns:
        Metadata dictionary ready to pass to store_fact.
    """
    metadata = {
        "title": title,
        "source": source,
        "category": category,
        "access_level": access_level,
        "visibility": visibility,
    }
    if owner_id:
        metadata["owner_id"] = owner_id
    if organization_id:
        metadata["organization_id"] = organization_id
    if group_ids:
        metadata["group_ids"] = group_ids
    if shared_with:
        metadata["shared_with"] = shared_with
    # Issue #3242: board scoping — only store when non-global
    if board_id and board_id != "__global__":
        metadata["board_id"] = board_id
    return metadata


@router.post("/add_text", response_model=AddTextResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_text_to_knowledge",
    error_code_prefix="KNOWLEDGE",
)
async def add_text_to_knowledge(
    admin_check: bool = Depends(check_admin_permission),
    request: dict = None,
    req: Request = None,
) -> AddTextResponse:
    """Add text to knowledge base - FIXED to use proper instance

    Issue #744: Requires admin authentication.
    Issue #685: Added hierarchical access level support.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb_to_use is None:
        # Issue #5407: KB instance not initialized - emit counter before 500.
        logger.warning("add_text_to_knowledge: KB uninitialized - raising 500")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="add_text", reason="kb_uninit").inc()
        raise InternalError("Knowledge base not initialized - please check logs for errors")

    (
        text,
        title,
        source,
        category,
        access_level,
        visibility,
        owner_id,
        organization_id,
        group_ids,
        shared_with,
        board_id,
    ) = _extract_add_text_fields(request)

    # GH#8598: block sub-company agents from writing to parent-company KB
    if organization_id:
        from llc.kb.write_guard import assert_not_writing_to_ancestor_kb
        from user_management.database import get_async_session_factory

        _requester = get_auth_middleware().get_user_from_request(req)
        _requester_role = (_requester or {}).get("role", "")
        if _requester_role not in ("platform_admin", "superadmin"):
            _requester_org_id = (_requester or {}).get("org_id")
            _session_factory = get_async_session_factory()
            async with _session_factory() as _session:
                await assert_not_writing_to_ancestor_kb(_requester_org_id, organization_id, _session)

    metadata = _build_ownership_metadata(
        title,
        source,
        category,
        access_level,
        visibility,
        owner_id,
        organization_id,
        group_ids,
        shared_with,
        board_id=board_id,
    )

    fact_id = await _store_fact_in_kb(kb_to_use, text, metadata)

    _user = get_auth_middleware().get_user_from_request(req)
    audit_record(
        user_id=str((_user or {}).get("user_id", "unknown")),
        action=AuditAction.KNOWLEDGE_ADD,
        resource_type="knowledge_doc",
        resource_id=fact_id,
        ip_address=req.client.host if req and req.client else "unknown",
        session_id=None,
        outcome="success",
    )

    return AddTextResponse(
        status="success",
        message="Fact stored successfully",
        fact_id=fact_id,
        text_length=len(text),
        title=title,
        source=source,
        access_level=access_level,
        visibility=visibility,
    )


# =============================================================================
# Issue #549: Frontend-compatible knowledge ingestion endpoints
# These endpoints match what KnowledgeRepository.ts expects
# =============================================================================


async def _store_fact_in_kb(kb, content: str, metadata: dict) -> str:
    """
    Helper to store a fact in the knowledge base (Issue #549 Code Review: Extract duplication).

    Args:
        kb: Knowledge base instance
        content: Text content to store
        metadata: Metadata dict with title, source, category, tags, etc.

    Returns:
        Fact ID of stored content
    """
    if hasattr(kb, "store_fact"):
        result = await kb.store_fact(content=content, metadata=metadata)
    else:
        result = await kb.store_fact(text=content, metadata=metadata)
    return result.get("fact_id")


def _fallback_html_strip(html_content: str) -> tuple:
    """
    Fallback HTML stripping using HTMLParser when _HtmlTextExtractor fails.

    Uses the same _in_script/_in_style suppression pattern as
    _HtmlTextExtractor so script/style content never leaks into output.
    Avoids bare ``<[^>]+>`` regex (CodeQL py/bad-tag-filter).

    Issue #3214.

    Args:
        html_content: Raw HTML content

    Returns:
        Tuple of (plain_text, empty_title)
    """
    import re
    from html import unescape
    from html.parser import HTMLParser

    class _TagStripper(HTMLParser):
        def __init__(self):
            super().__init__()
            self._parts: list[str] = []
            self._in_script = False
            self._in_style = False

        def handle_starttag(self, tag, attrs):
            tag_lower = tag.lower()
            if tag_lower == "script":
                self._in_script = True
            elif tag_lower == "style":
                self._in_style = True

        def handle_endtag(self, tag):
            tag_lower = tag.lower()
            if tag_lower == "script":
                self._in_script = False
            elif tag_lower == "style":
                self._in_style = False

        def handle_data(self, data: str):
            if not self._in_script and not self._in_style:
                self._parts.append(data)

        def get_text(self) -> str:
            return " ".join(self._parts)

    stripper = _TagStripper()
    stripper.feed(html_content)
    text = unescape(stripper.get_text())
    return re.sub(r"\s+", " ", text).strip(), ""


class _HtmlTextExtractor:
    """
    HTML parser that extracts text content and title.

    Skips script and style tag content for safe text extraction.
    Issue #620.
    """

    def __init__(self):
        from html.parser import HTMLParser

        self._parser = HTMLParser()
        self._parser.handle_starttag = self._handle_starttag
        self._parser.handle_endtag = self._handle_endtag
        self._parser.handle_data = self._handle_data
        self.text_parts = []
        self.title = ""
        self._in_script = False
        self._in_style = False
        self._in_title = False

    def _handle_starttag(self, tag, attrs):
        tag_lower = tag.lower()
        if tag_lower == "script":
            self._in_script = True
        elif tag_lower == "style":
            self._in_style = True
        elif tag_lower == "title":
            self._in_title = True

    def _handle_endtag(self, tag):
        tag_lower = tag.lower()
        if tag_lower == "script":
            self._in_script = False
        elif tag_lower == "style":
            self._in_style = False
        elif tag_lower == "title":
            self._in_title = False

    def _handle_data(self, data):
        if self._in_title:
            self.title = data.strip()
        elif not self._in_script and not self._in_style:
            text = data.strip()
            if text:
                self.text_parts.append(text)

    def feed(self, html_content: str):
        """Feed HTML content to the parser. Issue #620."""
        self._parser.feed(html_content)


def _sanitize_html_content(html_content: str) -> tuple:
    """
    Safely extract text and title from HTML content.

    Uses html.parser for safe HTML processing instead of regex.
    Issue #549 Code Review: Security fix.

    Args:
        html_content: Raw HTML content

    Returns:
        Tuple of (plain_text, extracted_title)
    """
    extractor = _HtmlTextExtractor()
    try:
        extractor.feed(html_content)
    except Exception:
        return _fallback_html_strip(html_content)

    plain_text = " ".join(extractor.text_parts)
    return plain_text, extractor.title


def _validate_file_upload(filename: str, file_size: int) -> None:
    """
    Validate file upload for security (Issue #549 Code Review: Security fix).

    Args:
        filename: Original filename
        file_size: Size in bytes

    Raises:
        HTTPException: If validation fails
    """
    import os

    # Check file size
    if file_size > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB",
        )

    # Check extension
    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Check for path traversal
    if contains_path_traversal(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")


@router.post("/facts", response_model=AddFactResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_facts_to_knowledge",
    error_code_prefix="KNOWLEDGE",
)
async def add_facts_to_knowledge(
    admin_check: bool = Depends(check_admin_permission),
    request: AddFactsRequest = None,
    req: Request = None,
) -> AddFactResponse:
    """
    Add text content to knowledge base (frontend-compatible endpoint).

    Issue #549: Created to match KnowledgeRepository.ts POST /api/knowledge_base/facts
    Issue #744: Requires admin authentication.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        # Issue #5407: KB instance not initialized - emit counter before 500.
        logger.warning("add_facts_to_knowledge: KB uninitialized - raising 500")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="facts_add", reason="kb_uninit").inc()
        raise InternalError("Knowledge base not initialized - please check logs for errors")

    logger.info(f"Adding fact: title='{request.title}', source='{request.source}', len={len(request.content)}")

    metadata: dict = {
        "title": request.title,
        "source": request.source,
        "category": request.category,
        "tags": request.tags,
    }
    # Issue #3242: attach board_id when provided
    if request.board_id and request.board_id != "__global__":
        metadata["board_id"] = request.board_id

    fact_id = await _store_fact_in_kb(kb_to_use, request.content, metadata)

    _user = get_auth_middleware().get_user_from_request(req)
    audit_record(
        user_id=str((_user or {}).get("user_id", "unknown")),
        action=AuditAction.KNOWLEDGE_ADD,
        resource_type="knowledge_doc",
        resource_id=fact_id,
        ip_address=req.client.host if req and req.client else "unknown",
        session_id=None,
        outcome="success",
    )

    return AddFactResponse(
        success=True,
        document_id=fact_id,
        title=request.title,
        content=(request.content[:100] + "..." if len(request.content) > 100 else request.content),
        message="Document added successfully",
    )


async def _fetch_and_extract_url(url: str, fallback_title: str) -> "tuple[str, str]":
    """Fetch HTML from a URL and return (content, title). Ref: #2735, #6533.

    Uses fetch_safe_url which enforces: scheme validation, DNS resolution to
    public IPs only, pinned resolver (defeats DNS-rebind), allow_redirects=False.
    Raises HTTPException on SSRF rejection, HTTP error, or connection failure.
    """
    import aiohttp

    from autobot_shared.security.ssrf_guard import SSRFError, fetch_safe_url

    try:
        status, body_bytes, _ = await fetch_safe_url(url, timeout=30.0)
    except SSRFError:
        raise HTTPException(status_code=400, detail="Request failed")
    except aiohttp.ClientError:
        raise HTTPException(status_code=400, detail="Failed to fetch URL")

    if status != 200:
        raise HTTPException(status_code=400, detail=f"HTTP {status}")

    html_content = body_bytes.decode("utf-8", errors="replace")
    # Use safe HTML parser instead of regex (Issue #549 Code Review)
    content, extracted_title = _sanitize_html_content(html_content)
    title = fallback_title or extracted_title or url
    return content, title


@router.post("/url", response_model=AddUrlResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_url_to_knowledge",
    error_code_prefix="KNOWLEDGE",
)
async def add_url_to_knowledge(
    admin_check: bool = Depends(check_admin_permission),
    request: AddUrlRequest = None,
    req: Request = None,
) -> AddUrlResponse:
    """
    Add content from URL to knowledge base.

    Issue #549: Created to match KnowledgeRepository.ts POST /api/knowledge_base/url
    Issue #744: Requires admin authentication.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        # Issue #5407: KB instance not initialized - emit counter before 500.
        logger.warning("add_url_to_knowledge: KB uninitialized - raising 500")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="url_add", reason="kb_uninit").inc()
        raise InternalError("Knowledge base not initialized")

    logger.info("Fetching content from URL: %s", request.url)

    # SSRF validation + fetch handled in _fetch_and_extract_url via fetch_safe_url (#6533)
    content, title = await _fetch_and_extract_url(request.url, request.title or "")

    url_metadata: dict = {
        "title": title,
        "source": request.url,
        "category": request.category,
        "tags": request.tags,
        "type": "url",
    }
    # Issue #3242: attach board_id when provided
    if request.board_id and request.board_id != "__global__":
        url_metadata["board_id"] = request.board_id

    fact_id = await _store_fact_in_kb(kb_to_use, content, url_metadata)

    _user = get_auth_middleware().get_user_from_request(req)
    audit_record(
        user_id=str((_user or {}).get("user_id", "unknown")),
        action=AuditAction.KNOWLEDGE_ADD,
        resource_type="knowledge_doc",
        resource_id=fact_id,
        ip_address=req.client.host if req and req.client else "unknown",
        session_id=None,
        outcome="success",
    )

    return AddUrlResponse(
        success=True,
        document_id=fact_id,
        title=title,
        content=content[:100] + "..." if len(content) > 100 else content,
        message=f"URL content added ({len(content)} chars)",
    )


def _extract_pdf_content(filename: str, file_content: bytes) -> str:
    """
    Extract text content from PDF file.

    Issue #620.

    Args:
        filename: Name of the file for error logging
        file_content: Raw PDF bytes

    Returns:
        Extracted text content

    Raises:
        HTTPException: If pypdf library is missing or parsing fails
    """
    import io

    try:
        import pypdf

        pdf_reader = pypdf.PdfReader(io.BytesIO(file_content))
        return "\n".join(page.extract_text() or "" for page in pdf_reader.pages)
    except ImportError:
        raise HTTPException(status_code=400, detail="PDF support requires pypdf library")
    except Exception as e:
        logger.error("PDF parse error for %s: %s", filename, e)
        raise HTTPException(status_code=400, detail="Failed to parse PDF file")


def _extract_docx_content(filename: str, file_content: bytes) -> str:
    """
    Extract text content from DOCX file.

    Issue #620.

    Args:
        filename: Name of the file for error logging
        file_content: Raw DOCX bytes

    Returns:
        Extracted text content

    Raises:
        HTTPException: If python-docx library is missing or parsing fails
    """
    import io

    try:
        import docx

        doc = docx.Document(io.BytesIO(file_content))
        return "\n".join(para.text for para in doc.paragraphs)
    except ImportError:
        raise HTTPException(status_code=400, detail="DOCX support requires python-docx library")
    except Exception as e:
        logger.error("DOCX parse error for %s: %s", filename, e)
        raise HTTPException(status_code=400, detail="Failed to parse DOCX file")


def _extract_file_content(filename: str, file_content: bytes) -> str:
    """
    Extract text content from uploaded file based on extension.

    Args:
        filename: Name of the file (used to determine extension)
        file_content: Raw file bytes

    Returns:
        Extracted text content

    Raises:
        HTTPException: If file cannot be parsed or library is missing
    """
    import os

    ext = os.path.splitext(filename.lower())[1]

    if ext in {".txt", ".md", ".csv"}:
        return file_content.decode("utf-8", errors="replace")

    if ext == ".html":
        html_text = file_content.decode("utf-8", errors="replace")
        content, _ = _sanitize_html_content(html_text)
        return content

    if ext == ".json":
        try:
            data = json.loads(file_content.decode("utf-8"))
            return json.dumps(data, indent=2)
        except json.JSONDecodeError:
            return file_content.decode("utf-8", errors="replace")

    if ext == ".pdf":
        return _extract_pdf_content(filename, file_content)

    if ext == ".docx":
        return _extract_docx_content(filename, file_content)

    # Default: treat as text
    return file_content.decode("utf-8", errors="replace")


def _parse_upload_tags(tags_str) -> list:
    """Parse and validate tags from upload form."""
    try:
        tags = json.loads(tags_str) if isinstance(tags_str, str) else tags_str
        if not isinstance(tags, list):
            return []
        return [str(t)[:50] for t in tags[:20]]  # Limit tags
    except (json.JSONDecodeError, TypeError):
        return []


@router.post("/upload", response_model=UploadFileResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="upload_file_to_knowledge",
    error_code_prefix="KNOWLEDGE",
)
async def upload_file_to_knowledge(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
) -> UploadFileResponse:
    """
    Upload file to knowledge base.

    Issue #549: Created to match KnowledgeRepository.ts POST /api/knowledge_base/upload
    Supports: .txt, .md, .pdf, .docx, .json, .csv, .html files
    Issue #744: Requires admin authentication.
    """
    import os

    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb_to_use is None:
        # Issue #5407: KB instance not initialized - emit counter before 500.
        logger.warning("upload_file_to_knowledge: KB uninitialized - raising 500")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="upload", reason="kb_uninit").inc()
        raise InternalError("Knowledge base not initialized")

    form = await req.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        raise HTTPException(status_code=400, detail="File is required")

    # Get filename and sanitize (Issue #549 Code Review: Security)
    filename = os.path.basename(getattr(file, "filename", "unknown"))
    file_content = await file.read()

    # Validate file upload BEFORE processing (Issue #549 Code Review: Security)
    _validate_file_upload(filename, len(file_content))

    title = form.get("title", "") or filename
    category = form.get("category", "uploads")
    tags = _parse_upload_tags(form.get("tags", "[]"))

    content = _extract_file_content(filename, file_content)
    if not content.strip():
        raise HTTPException(status_code=400, detail="No text content could be extracted from file")

    # Issue #5064: sanitize uploaded document content against prompt injection
    # before the text reaches the KB / embedding pipeline.
    content = _sanitize_document(content, source="file_upload").sanitized_text

    logger.info("Uploading file: filename='%s', size=%d", filename, len(file_content))

    fact_id = await _store_fact_in_kb(
        kb_to_use,
        content,
        {
            "title": title,
            "source": filename,
            "category": category,
            "tags": tags,
            "type": "file",
            "filename": filename,
        },
    )

    _user = get_auth_middleware().get_user_from_request(req)
    audit_record(
        user_id=str((_user or {}).get("user_id", "unknown")),
        action=AuditAction.KNOWLEDGE_ADD,
        resource_type="knowledge_doc",
        resource_id=fact_id,
        ip_address=req.client.host if req and req.client else "unknown",
        session_id=None,
        outcome="success",
    )

    word_count = len(content.split())
    return UploadFileResponse(
        success=True,
        document_id=fact_id,
        title=title,
        content=content[:100] + "..." if len(content) > 100 else content,
        word_count=word_count,
        message=f"File uploaded ({word_count} words)",
    )


# =============================================================================
# Issue #3243: Audio / Video / YouTube ingestion endpoint
# =============================================================================

# Allowed audio/video extensions for direct upload (mirrors AudioConnector)
_AUDIO_ALLOWED_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".mp4", ".mkv", ".webm"}
# Max audio upload size: 200 MB
_AUDIO_MAX_BYTES = 200 * 1024 * 1024


async def _ingest_audio_source(
    kb_to_use,
    source: str,
    title: str,
    category: str,
    tags: list,
    whisper_model: str,
    language: str | None,
) -> AudioIngestResponse:
    """Run transcription and store result in KB. Helper for audio endpoints.

    Issue #3243: shared by both the URL and file-upload audio routes.
    Returns an :class:`AudioIngestResponse` with success, document_id,
    word_count, and message (Issue #5317).
    """
    import uuid as _uuid

    from knowledge.connectors.models import ConnectorConfig

    # Build a transient connector config for a single source
    connector_config = ConnectorConfig(
        connector_id=_uuid.uuid4().hex,
        connector_type="audio",
        name="api_audio_ingest",
        config={
            "sources": [source],
            "whisper_model": whisper_model,
            "language": language,
        },
    )

    from knowledge.connectors.audio_connector import AudioConnector

    connector = AudioConnector(connector_config)
    sources = await connector.discover_sources()
    if not sources:
        raise HTTPException(status_code=400, detail="Could not locate audio source")

    source_info = sources[0]
    content_result = await connector.fetch_content(source_info.source_id)
    if content_result is None or not content_result.content.strip():
        raise HTTPException(status_code=422, detail="Transcription produced no content")

    transcript = content_result.content
    effective_title = title or content_result.metadata.get("title", "") or source
    metadata = {
        "title": effective_title,
        "source": source,
        "category": category,
        "tags": tags,
        "type": "audio_transcript",
        "audio_source": source,
        **{k: v for k, v in content_result.metadata.items() if k not in {"source", "category", "type"}},
    }

    fact_id = await _store_fact_in_kb(kb_to_use, transcript, metadata)
    word_count = len(transcript.split())
    return AudioIngestResponse(
        success=True,
        document_id=fact_id,
        title=effective_title,
        word_count=word_count,
        message=f"Audio transcribed and indexed ({word_count} words)",
    )


@router.post("/audio", response_model=AudioIngestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="ingest_audio_url",
    error_code_prefix="KNOWLEDGE",
)
async def ingest_audio_url(
    request: AudioIngestRequest,
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
) -> AudioIngestResponse:
    """Transcribe a YouTube URL or direct audio/video URL and index it.

    Issue #3243: Accepts a YouTube or remote audio URL, downloads the audio
    track via yt-dlp, transcribes with Whisper (NPU if available, CPU fallback),
    and stores the transcript in the knowledge base.

    Requires admin authentication.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb_to_use is None:
        # Issue #5407: KB instance not initialized - emit counter before 500.
        logger.warning("ingest_audio_url: KB uninitialized - raising 500")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="audio", reason="kb_uninit").inc()
        raise InternalError("Knowledge base not initialized")

    logger.info(
        "Audio URL ingest requested: url=%s model=%s",
        request.url,
        request.whisper_model,
    )

    return await _ingest_audio_source(
        kb_to_use=kb_to_use,
        source=request.url,
        title=request.title,
        category=request.category,
        tags=request.tags,
        whisper_model=request.whisper_model,
        language=request.language,
    )


@router.post("/audio/upload", response_model=AudioIngestResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="upload_audio_file",
    error_code_prefix="KNOWLEDGE",
)
async def upload_audio_file(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
) -> AudioIngestResponse:
    """Upload a local audio/video file (mp3, wav, m4a, ogg, flac, mp4, mkv, webm).

    Issue #3243: Saves the uploaded file to a temp path, runs Whisper transcription
    (NPU-accelerated if available, CPU fallback), then stores the transcript.

    Requires admin authentication.

    Form fields:
        file:          The audio/video binary.
        title:         Optional display title.
        category:      Knowledge category (default "audio").
        tags:          JSON array of tag strings.
        whisper_model: Whisper model size (default "base").
        language:      ISO-639-1 language hint (optional).
    """
    import json as _json
    import os as _os
    import tempfile as _tmp

    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb_to_use is None:
        # Issue #5407: KB instance not initialized - emit counter before 500.
        logger.warning("upload_audio_file: KB uninitialized - raising 500")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="audio_upload", reason="kb_uninit").inc()
        raise InternalError("Knowledge base not initialized")

    form = await req.form()
    file = form.get("file")
    if not file or not hasattr(file, "read"):
        raise HTTPException(status_code=400, detail="Audio file is required")

    filename = _os.path.basename(getattr(file, "filename", "audio.mp3"))
    if contains_path_traversal(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")

    ext = _os.path.splitext(filename.lower())[1]
    if ext not in _AUDIO_ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format. Allowed: {', '.join(sorted(_AUDIO_ALLOWED_EXTS))}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > _AUDIO_MAX_BYTES:
        raise HTTPException(status_code=400, detail="Audio file exceeds 200 MB limit")

    title = form.get("title", "") or filename
    category = form.get("category", "audio")
    whisper_model = form.get("whisper_model", "base")
    language = form.get("language") or None
    try:
        raw_tags = form.get("tags", "[]")
        tags = _json.loads(raw_tags) if isinstance(raw_tags, str) else raw_tags
        if not isinstance(tags, list):
            tags = []
        tags = [str(t)[:50] for t in tags[:20]]
    except (_json.JSONDecodeError, TypeError):
        tags = []

    # Write to a temp file so AudioConnector can read it by path
    with _tmp.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        logger.info("Audio file upload: filename=%s size=%d", filename, len(file_bytes))
        return await _ingest_audio_source(
            kb_to_use=kb_to_use,
            source=tmp_path,
            title=title,
            category=category,
            tags=tags,
            whisper_model=whisper_model,
            language=language,
        )
    finally:
        try:
            _os.unlink(tmp_path)
        except OSError:
            pass


# NOTE: Search endpoints in knowledge_search.py (Issue #209).
# Canonical: /search only. Deprecated /enhanced_search, /rag_search,
# /similarity_search, /enhanced_search (advanced) removed in #10666.


@register_health_probe(KnownProbes.KNOWLEDGE)
async def probe_knowledge(
    request: Request | None = None,
) -> ComponentHealth:
    """Issue #3333: probe registration for the knowledge base.

    Issue #6905: increments ``autobot_kb_degradation_total`` on every
    degraded/down outcome with ``endpoint="probe"`` so the SLO dashboard
    keeps the kb_uninit signal once the legacy /health route is sunset
    by #6902.
    """
    from knowledge.metrics import autobot_kb_degradation_total

    if request is None or not hasattr(request.app.state, "knowledge_base"):
        autobot_kb_degradation_total.labels(endpoint="probe", reason="kb_uninit").inc()
        return ComponentHealth(
            name="knowledge",
            status="degraded",
            detail="knowledge base not initialized in app state",
        )
    try:
        kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
        if kb is None:
            autobot_kb_degradation_total.labels(endpoint="probe", reason="kb_uninit").inc()
            return ComponentHealth(name="knowledge", status="down", detail="kb instance is None")
        return ComponentHealth(name="knowledge", status="ok")
    except Exception as exc:
        autobot_kb_degradation_total.labels(endpoint="probe", reason="probe_error").inc()
        return ComponentHealth(
            name="knowledge",
            status="down",
            detail=f"probe error: {type(exc).__name__}",
        )


def _empty_entries_response(message: str = "", error: str = "") -> dict:
    """Create empty entries response (Issue #398: extracted)."""
    resp = {"entries": [], "next_cursor": "0", "count": 0, "has_more": False}
    if message:
        resp["message"] = message
    if error:
        resp["error"] = error
    return resp


def _parse_and_filter_facts(items: dict, category: str | None, limit: int) -> list:
    """Parse and filter facts from HSCAN results (Issue #398: extracted)."""
    entries = []
    for fact_id, fact_json in items.items():
        try:
            fact = json.loads(fact_json)
            if category and fact.get("metadata", {}).get("category", "") != category:
                continue
            entries.append(_format_knowledge_entry(fact_id, fact))
            if len(entries) >= limit:
                break
        except Exception as e:
            logger.warning("Error parsing fact %s: %s", fact_id, e)
    return entries


@router.get("/entries", response_model=KnowledgeEntriesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_knowledge_entries",
    error_code_prefix="KNOWLEDGE",
)
async def get_knowledge_entries(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
    limit: int = Query(default=QueryDefaults.KNOWLEDGE_DEFAULT_LIMIT, ge=1, le=1000),
    cursor: str | None = Query(default="0", pattern=r"^[0-9]+$"),
    category: str | None = Query(default=None, pattern=r"^[a-zA-Z0-9_-]*$"),
):
    """Get knowledge base entries with cursor-based pagination.

    Issue #744: Requires admin authentication.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        # Issue #5407: KB instance not initialized.
        logger.warning("get_knowledge_entries: KB uninitialized - returning empty list")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="entries", reason="kb_uninit").inc()
        return _empty_entries_response(message="Knowledge base not initialized")

    logger.info("Getting knowledge entries: limit=%s, cursor=%s", limit, cursor)
    current_cursor = int(cursor) if cursor else 0

    try:

        def _hscan():
            return kb.redis_client.hscan("knowledge_base:facts", cursor=current_cursor, count=limit * 2)

        next_cursor, items = await asyncio.to_thread(_hscan)
        entries = _parse_and_filter_facts(items, category, limit)
        entries.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {
            "entries": entries[:limit],
            "next_cursor": str(next_cursor),
            "count": len(entries[:limit]),
            "has_more": next_cursor != 0,
        }
    except Exception as e:
        logger.error("Redis error getting facts: %s", e)
        return _empty_entries_response(error="Redis connection error")


def _create_offline_stats_response() -> dict:
    """Create offline stats response (Issue #398: extracted)."""
    return {
        "status": "offline",
        "message": "Knowledge base not initialized",
        "basic_stats": {},
        "category_breakdown": {},
        "source_breakdown": {},
        "type_breakdown": {},
        "size_metrics": {},
    }


def _analyze_facts_for_stats(all_facts_data: dict) -> tuple:
    """Analyze facts for detailed breakdowns (Issue #398: extracted).

    Returns:
        Tuple of (category_counts, source_counts, type_counts, fact_sizes)
    """
    category_counts, source_counts, type_counts = {}, {}, {}
    fact_sizes = []
    for fact_json in all_facts_data.values():
        try:
            fact = json.loads(fact_json)
            metadata = fact.get("metadata", {})
            cat = metadata.get("category", "uncategorized")
            category_counts[cat] = category_counts.get(cat, 0) + 1
            src = metadata.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1
            ft = metadata.get("type", "document")
            type_counts[ft] = type_counts.get(ft, 0) + 1
            fact_sizes.append(len(fact.get("content", "")))
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as e:
            logger.warning("Error processing fact for size calculation: %s", e)
    return category_counts, source_counts, type_counts, fact_sizes


def _compute_size_metrics(fact_sizes: list) -> dict:
    """Compute size metrics from fact sizes (Issue #398: extracted)."""
    if not fact_sizes:
        return {
            "total_content_size": 0,
            "average_fact_size": 0,
            "median_fact_size": 0,
            "largest_fact_size": 0,
            "smallest_fact_size": 0,
        }
    total = sum(fact_sizes)
    sorted_sizes = sorted(fact_sizes)
    return {
        "total_content_size": total,
        "average_fact_size": total / len(fact_sizes),
        "median_fact_size": sorted_sizes[len(sorted_sizes) // 2],
        "largest_fact_size": max(fact_sizes),
        "smallest_fact_size": min(fact_sizes),
    }


@router.get("/detailed_stats", response_model=DetailedKnowledgeStats)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_detailed_stats",
    error_code_prefix="KNOWLEDGE",
)
async def get_detailed_stats(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
) -> DetailedKnowledgeStats:
    """Get detailed knowledge base statistics with additional metrics.

    Issue #744: Requires admin authentication.
    Issue #5248: response typed as Pydantic model so OpenAPI captures schema.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        # Issue #5407: KB instance not initialized.
        logger.warning("get_detailed_stats: KB uninitialized - returning offline stats")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="detailed_stats", reason="kb_uninit").inc()
        return DetailedKnowledgeStats(**_create_offline_stats_response())

    basic_stats = await kb.get_stats()
    try:
        all_facts_data = await asyncio.to_thread(kb.redis_client.hgetall, "knowledge_base:facts")
    except Exception:
        all_facts_data = {}

    cat_counts, src_counts, type_counts, sizes = _analyze_facts_for_stats(all_facts_data)
    return DetailedKnowledgeStats(
        status="online" if basic_stats.get("initialized") else "offline",
        basic_stats=basic_stats,
        category_breakdown=cat_counts,
        source_breakdown=src_counts,
        type_breakdown=type_counts,
        size_metrics=_compute_size_metrics(sizes),
        rag_available=RAG_AVAILABLE,
    )


@router.get("/machine_profile", response_model=MachineProfileResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_machine_profile",
    error_code_prefix="KNOWLEDGE",
)
async def get_machine_profile(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """Get machine profile with system information and capabilities

    Issue #744: Requires admin authentication.
    """
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


@router.get("/man_pages/summary", response_model=ManPagesSummaryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_man_pages_summary",
    error_code_prefix="KNOWLEDGE",
)
async def get_man_pages_summary(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """Get summary of man pages integration status

    Issue #744: Requires admin authentication.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        # Issue #5407: KB instance not initialized.
        logger.warning("get_man_pages_summary: KB uninitialized - returning error status")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="man_pages_summary", reason="kb_uninit").inc()
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
        all_facts_data = await asyncio.to_thread(kb_to_use.redis_client.hgetall, "knowledge_base:facts")

        man_page_count = 0
        system_command_count = 0
        last_indexed = None

        # Process facts using helper (Issue #315)
        for fact_json in all_facts_data.values():
            is_man_page, is_system_command, created_at = _parse_man_page_fact(fact_json)
            if is_man_page:
                man_page_count += 1
            elif is_system_command:
                system_command_count += 1
            if created_at and (last_indexed is None or created_at > last_indexed):
                last_indexed = created_at

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
        logger.error("Redis error getting man pages: %s", redis_err)
        return {
            "status": "error",
            "message": "Failed to query knowledge base",
            "man_pages_summary": {
                "total_man_pages": 0,
                "indexed_count": 0,
                "last_indexed": None,
            },
        }


@router.post("/machine_knowledge/initialize", response_model=MachineKnowledgeInitResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="initialize_machine_knowledge",
    error_code_prefix="KNOWLEDGE",
)
async def initialize_machine_knowledge(
    admin_check: bool = Depends(check_admin_permission),
    request: dict = None,
    req: Request = None,
):
    """Initialize machine-specific knowledge including man pages and system commands

    Issue #744: Requires admin authentication.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        # Issue #5407: KB instance not initialized.
        logger.warning("initialize_machine_knowledge: KB uninitialized - returning error status")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="machine_knowledge_initialize", reason="kb_uninit").inc()
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
        "message": (f"Machine knowledge initialized. Added {commands_added} system commands."),
        "items_added": commands_added,
        "components": {
            "system_commands": commands_added,
            "man_pages": "background_task",  # Man pages run in background
        },
    }


@router.post("/man_pages/integrate", response_model=ManPagesIntegrateResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="integrate_man_pages",
    error_code_prefix="KNOWLEDGE",
)
async def integrate_man_pages(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
    background_tasks: BackgroundTasks = None,
):
    """Integrate system man pages into knowledge base (background task)

    Issue #744: Requires admin authentication.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        # Issue #5407: KB instance not initialized.
        logger.warning("integrate_man_pages: KB uninitialized - returning error status")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="man_pages_integrate", reason="kb_uninit").inc()
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


@router.get("/man_pages/search", response_model=ManPageSearchResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_man_pages",
    error_code_prefix="KNOWLEDGE",
)
async def search_man_pages(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
    query: str = None,
    limit: int = 10,
):
    """Search specifically for man pages in knowledge base

    Issue #744: Requires admin authentication.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        # Issue #5407: KB instance not initialized.
        logger.warning("search_man_pages: KB uninitialized - returning empty results")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="man_pages_search", reason="kb_uninit").inc()
        return {"results": [], "total_results": 0, "query": query}

    logger.info("Searching man pages: '%s' (limit=%s)", query, limit)

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


async def _clear_kb_via_redis(kb) -> int:
    """Clear knowledge base via Redis fallback (Issue #398: extracted)."""
    if not (hasattr(kb, "redis") and kb.redis):
        logger.error("No clear method available for knowledge base implementation")
        raise HTTPException(status_code=500, detail="Knowledge base clearing not supported")

    keys = await kb.redis.keys("fact:*")
    if keys:
        await kb.redis.delete(*keys)
    index_keys = await kb.redis.keys("index:*")
    if index_keys:
        await kb.redis.delete(*index_keys)
    return len(keys) if keys else 0


@router.post("/clear_all", response_model=ClearAllResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_all_knowledge",
    error_code_prefix="KNOWLEDGE",
)
async def clear_all_knowledge(
    admin_check: bool = Depends(check_admin_permission),
    request: dict = None,
    req: Request = None,
):
    """Clear all entries from the knowledge base - DESTRUCTIVE OPERATION.

    Issue #744: Requires admin authentication.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        # Issue #5407: KB instance not initialized.
        logger.warning("clear_all_knowledge: KB uninitialized - returning error status")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="clear_all", reason="kb_uninit").inc()
        return {
            "status": "error",
            "items_removed": 0,
            "message": "Knowledge base not initialized - please check logs for errors",
        }

    logger.warning("Starting DESTRUCTIVE operation: clearing all knowledge base entries")
    try:
        stats_before = await kb.get_stats()
        items_before = stats_before.get("total_facts", 0)
    except Exception:
        items_before = 0

    if hasattr(kb, "clear_all"):
        result = await kb.clear_all()
        items_removed = result.get("items_removed", items_before)
    else:
        try:
            items_removed = await _clear_kb_via_redis(kb)
        except Exception as e:
            logger.error("Error during knowledge base clearing: %s", e)
            raise HTTPException(status_code=500, detail="Failed to clear")

    logger.warning("Knowledge base cleared. Removed %s entries.", items_removed)
    _user = get_auth_middleware().get_user_from_request(req)
    audit_record(
        user_id=str((_user or {}).get("user_id", "unknown")),
        action=AuditAction.KNOWLEDGE_REMOVE,
        resource_type="knowledge_doc",
        resource_id="all",
        ip_address=req.client.host if req and req.client else "unknown",
        session_id=None,
        outcome="success",
        metadata={"items_removed": items_removed},
    )
    return {
        "status": "success",
        "items_removed": items_removed,
        "items_before": items_before,
        "message": f"Successfully cleared knowledge base. Removed {items_removed} entries.",
    }


# Legacy endpoints for backward compatibility
@router.post("/add_document", response_model=AddTextResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_document_to_knowledge",
    error_code_prefix="KNOWLEDGE",
)
async def add_document_to_knowledge(
    admin_check: bool = Depends(check_admin_permission),
    request: dict = None,
    req: Request = None,
):
    """Legacy endpoint - redirects to add_text

    Issue #744: Requires admin authentication.
    """
    return await add_text_to_knowledge(request, req)


@router.post("/query", response_model=QueryKnowledgeResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="query_knowledge",
    error_code_prefix="KNOWLEDGE",
)
async def query_knowledge(
    admin_check: bool = Depends(check_admin_permission),
    request: dict = None,
    req: Request = None,
):
    """Legacy endpoint - redirects to search (now in knowledge_search.py)

    Issue #744: Requires admin authentication.
    """
    # Import search function from knowledge_search module
    from api.knowledge_search import search_knowledge

    return await search_knowledge(request, req)


# NOTE: _enhance_search_with_rag helper moved to knowledge_search.py (Issue #209)


# =============================================================================
# Helper Functions for get_facts_by_category (Issue #281)
# =============================================================================


async def _check_facts_cache(kb, category: str | None, limit: int) -> tuple:
    """Check cache for facts_by_category result (Issue #281: extracted)."""
    import json

    cache_key = f"kb:cache:facts_by_category:{category or 'all'}:{limit}"
    cached_result = await asyncio.to_thread(kb.redis_client.get, cache_key)

    if cached_result:
        logger.debug(f"Cache HIT for facts_by_category (category={category}, limit={limit})")
        return (
            json.loads(cached_result.decode("utf-8") if isinstance(cached_result, bytes) else cached_result),
            cache_key,
        )

    logger.info(
        f"Cache MISS for facts_by_category - using category index lookup " f"(category={category}, limit={limit})"
    )
    return None, cache_key


async def _fetch_category_fact_ids(kb, categories_to_fetch: list, limit: int) -> dict:
    """Fetch fact IDs from category indexes (Issue #281: extracted)."""
    category_fact_ids = {}
    for cat in categories_to_fetch:
        index_key = f"category:index:{cat}"
        fact_ids = await asyncio.to_thread(kb.redis_client.srandmember, index_key, limit)
        if fact_ids:
            decoded_ids = [fid.decode("utf-8") if isinstance(fid, bytes) else fid for fid in fact_ids]
            category_fact_ids[cat] = decoded_ids
            logger.debug(f"Category index {cat}: fetched {len(decoded_ids)} fact IDs")
    return category_fact_ids


async def _batch_fetch_facts(kb, category_fact_ids: dict) -> tuple:
    """Batch fetch fact data using pipeline (Issue #281: extracted)."""
    all_fact_keys = []
    for cat, fact_ids in category_fact_ids.items():
        for fid in fact_ids:
            all_fact_keys.append((cat, f"fact:{fid}"))

    if not all_fact_keys:
        return [], []

    pipeline = kb.redis_client.pipeline()
    for _, fact_key in all_fact_keys:
        pipeline.hgetall(fact_key)
    fact_results = await asyncio.to_thread(pipeline.execute)

    return all_fact_keys, fact_results


def _process_fact_data(fact_data: dict, cat: str, fact_key: str) -> dict | None:
    """Process a single fact from Redis data (Issue #281: extracted)."""
    import json

    if not fact_data:
        return None

    try:
        # Extract metadata
        metadata_raw = fact_data.get(b"metadata") or fact_data.get("metadata", b"{}")
        metadata_str = metadata_raw.decode("utf-8") if isinstance(metadata_raw, bytes) else str(metadata_raw)
        metadata = json.loads(metadata_str) if metadata_str else {}

        # Extract content
        content_raw = fact_data.get(b"content") or fact_data.get("content", b"")
        content = (
            content_raw.decode("utf-8") if isinstance(content_raw, bytes) else str(content_raw) if content_raw else ""
        )

        fact_title = metadata.get("title", metadata.get("command", "Untitled"))
        fact_type = metadata.get("type", "unknown")

        return {
            "key": fact_key,
            "title": fact_title,
            "content": content[:500] + "..." if len(content) > 500 else content,
            "full_content": content,
            "category": cat,
            "type": fact_type,
            "metadata": metadata,
        }
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.debug("Skipping invalid fact entry: %s", e)
        return None


async def _cache_facts_result(kb, cache_key: str, result: dict) -> None:
    """Cache the facts_by_category result (Issue #281: extracted)."""
    import json

    try:
        await asyncio.to_thread(kb.redis_client.setex, cache_key, 60, json.dumps(result))
        logger.debug("Cached facts_by_category result")
    except Exception as cache_error:
        logger.warning("Failed to cache facts_by_category: %s", cache_error)


def _raise_kb_unavailable() -> None:
    """Raise HTTP 503 for unavailable KB (Issue #398: extracted)."""
    logger.error("Knowledge base not available for get_facts_by_category")
    raise HTTPException(
        status_code=503,
        detail={
            "error": "Knowledge base unavailable",
            "message": "The knowledge base service failed to initialize. Check server logs.",
            "code": "KB_INIT_FAILED",
        },
    )


def _build_categories_dict(all_fact_keys: list, fact_results: list) -> dict:
    """Build categories dict from fetched facts (Issue #398: extracted)."""
    categories_dict: dict = {}
    for (cat, fact_key), fact_data in zip(all_fact_keys, fact_results):
        processed = _process_fact_data(fact_data, cat, fact_key)
        if processed:
            if cat not in categories_dict:
                categories_dict[cat] = []
            categories_dict[cat].append(processed)
    return categories_dict


@router.get("/facts/by_category", response_model=FactsByCategoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_facts_by_category",
    error_code_prefix="KNOWLEDGE",
)
async def get_facts_by_category(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
    category: str | None = None,
    limit: int = 100,
):
    """Get facts grouped by category for browsing with caching.

    Issue #744: Requires admin authentication.
    """
    kb = await get_or_create_knowledge_base(req.app)
    if kb is None:
        # Issue #5407: KB instance not initialized - emit counter before 503.
        logger.warning("get_facts_by_category: KB uninitialized - raising 503")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="facts_by_category", reason="kb_uninit").inc()
        _raise_kb_unavailable()

    cached_result, cache_key = await _check_facts_cache(kb, category, limit)
    if cached_result:
        return cached_result

    from knowledge_categories import KnowledgeCategory

    categories_to_fetch = [category] if category else [c.value for c in KnowledgeCategory]

    try:
        category_fact_ids = await _fetch_category_fact_ids(kb, categories_to_fetch, limit)
        if not category_fact_ids:
            logger.warning("No category indexes - falling back to SCAN method")
            return await _get_facts_by_category_legacy(kb, category, limit)

        all_fact_keys, fact_results = await _batch_fetch_facts(kb, category_fact_ids)
        if not all_fact_keys:
            return {"categories": {}, "total_facts": 0}

        categories_dict = _build_categories_dict(all_fact_keys, fact_results)
    except Exception as e:
        logger.error("Error in indexed fact retrieval: %s", e)
        return {"categories": {}, "total_facts": 0, "error": "Internal server error"}

    result = {
        "categories": categories_dict,
        "total_facts": sum(len(v) for v in categories_dict.values()),
        "category_filter": category,
    }
    await _cache_facts_result(kb, cache_key, result)
    return result


async def _scan_all_fact_keys(kb) -> list:
    """Collect all fact keys using SCAN (Issue #398: extracted)."""
    all_fact_keys = []
    cursor = 0
    while True:
        cursor, keys = await asyncio.to_thread(kb.redis_client.scan, cursor, match="fact:*", count=1000)
        all_fact_keys.extend(keys)
        if cursor == 0:
            break
    return all_fact_keys


async def _batch_fetch_facts_legacy(kb, fact_keys: list, chunk_size: int = 500) -> list:
    """Batch fetch fact data using pipeline for legacy method (Issue #398: extracted)."""
    all_facts_data = []
    for i in range(0, len(fact_keys), chunk_size):
        chunk_keys = fact_keys[i : i + chunk_size]
        pipeline = kb.redis_client.pipeline()
        for key in chunk_keys:
            pipeline.hgetall(key)
        chunk_results = await asyncio.to_thread(pipeline.execute)
        all_facts_data.extend(zip(chunk_keys, chunk_results))
    return all_facts_data


def _decode_bytes(raw, default: str = "") -> str:
    """Decode bytes to string (Issue #398: extracted)."""
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw) if raw else default


def _parse_fact_entry(fact_key_bytes, fact_data, get_category_for_source) -> tuple | None:
    """Parse a single fact entry (Issue #398: extracted).

    Returns:
        Tuple of (fact_key, category, title, content, type, metadata) or None
    """
    if not fact_data:
        return None
    try:
        fact_key = _decode_bytes(fact_key_bytes)
        metadata_raw = fact_data.get(b"metadata") or fact_data.get("metadata", b"{}")
        metadata = json.loads(_decode_bytes(metadata_raw, "{}"))
        content_raw = fact_data.get(b"content") or fact_data.get("content", b"")
        content = _decode_bytes(content_raw)
        source = metadata.get("source", "")
        category = get_category_for_source(source).value if source else "general"
        title = metadata.get("title", metadata.get("command", "Untitled"))
        fact_type = metadata.get("type", "unknown")
        return (fact_key, category, title, content, fact_type, metadata)
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


async def _get_facts_by_category_legacy(kb, category: str | None, limit: int):
    """Legacy fallback: Get facts by scanning all keys (Issue #398: refactored)."""
    from knowledge_categories import get_category_for_source

    all_fact_keys = await _scan_all_fact_keys(kb)
    if not all_fact_keys:
        return {"categories": {}, "total_facts": 0}

    all_facts_data = await _batch_fetch_facts_legacy(kb, all_fact_keys)
    categories_dict: dict = {}

    for fact_key_bytes, fact_data in all_facts_data:
        parsed = _parse_fact_entry(fact_key_bytes, fact_data, get_category_for_source)
        if not parsed:
            continue
        fact_key, fact_cat, title, content, fact_type, metadata = parsed
        if category and fact_cat != category:
            continue
        if fact_cat not in categories_dict:
            categories_dict[fact_cat] = []
        if len(categories_dict[fact_cat]) >= limit:
            continue
        categories_dict[fact_cat].append(
            {
                "key": fact_key,
                "title": title,
                "content": content[:500] + "..." if len(content) > 500 else content,
                "full_content": content,
                "category": fact_cat,
                "type": fact_type,
                "metadata": metadata,
            }
        )

    return {
        "categories": categories_dict,
        "total_facts": sum(len(v) for v in categories_dict.values()),
        "category_filter": category,
    }


def _extract_fact_metadata(fact_data: dict) -> dict:
    """
    Extract and parse metadata from Redis fact data.

    Handles both bytes and string keys from Redis responses.
    Issue #620.

    Args:
        fact_data: Raw fact data from Redis hgetall

    Returns:
        Parsed metadata dictionary
    """
    metadata_str = fact_data.get("metadata") or fact_data.get(b"metadata", b"{}")
    return json.loads(metadata_str.decode("utf-8") if isinstance(metadata_str, bytes) else metadata_str)


def _extract_fact_content(fact_data: dict) -> str:
    """
    Extract content string from Redis fact data.

    Handles both bytes and string keys from Redis responses.
    Issue #620.

    Args:
        fact_data: Raw fact data from Redis hgetall

    Returns:
        Content string
    """
    content_raw = fact_data.get("content") or fact_data.get(b"content", b"")
    return content_raw.decode("utf-8") if isinstance(content_raw, bytes) else str(content_raw) if content_raw else ""


def _extract_fact_created_at(fact_data: dict) -> str:
    """
    Extract created_at timestamp from Redis fact data.

    Handles both bytes and string keys from Redis responses.
    Issue #620.

    Args:
        fact_data: Raw fact data from Redis hgetall

    Returns:
        Created at timestamp string
    """
    created_at_raw = fact_data.get("created_at") or fact_data.get(b"created_at", b"")
    return (
        created_at_raw.decode("utf-8")
        if isinstance(created_at_raw, bytes)
        else str(created_at_raw) if created_at_raw else ""
    )


@router.get("/fact/{fact_key}", response_model=FactByKeyResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_fact_by_key",
    error_code_prefix="KNOWLEDGE",
)
async def get_fact_by_key(
    admin_check: bool = Depends(check_admin_permission),
    fact_key: str = Path(..., pattern=r"^[a-zA-Z0-9_:-]+$", max_length=255),
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

    Issue #744: Requires admin authentication.
    """
    if contains_path_traversal(fact_key):
        raise HTTPException(status_code=400, detail="Invalid fact_key: path traversal not allowed")

    kb = await get_or_create_knowledge_base(req.app)
    fact_data = await asyncio.to_thread(kb.redis_client.hgetall, fact_key)

    if not fact_data:
        raise HTTPException(status_code=404, detail=f"Fact not found: {fact_key}")

    return {
        "key": fact_key,
        "content": _extract_fact_content(fact_data),
        "metadata": _extract_fact_metadata(fact_data),
        "created_at": _extract_fact_created_at(fact_data),
    }


@router.get("/import/status", response_model=ImportStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_import_status",
    error_code_prefix="KNOWLEDGE",
)
async def get_import_status(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
    file_path: str | None = None,
    category: str | None = None,
):
    """Get import status for files

    Issue #744: Requires admin authentication.
    """
    from models.knowledge_import_tracking import ImportTracker

    tracker = ImportTracker()
    results = tracker.get_import_status(file_path=file_path, category=category)

    return {"status": "success", "imports": results, "total": len(results)}


@router.get("/import/statistics", response_model=ImportStatisticsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_import_statistics",
    error_code_prefix="KNOWLEDGE",
)
async def get_import_statistics(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """Get import statistics

    Issue #744: Requires admin authentication.
    """
    from models.knowledge_import_tracking import ImportTracker

    tracker = ImportTracker()
    stats = tracker.get_statistics()

    return {"status": "success", "statistics": stats}


# =============================================================================
# Issue #165: Documentation Browser API - Browse and filter indexed documentation
# =============================================================================


async def _get_indexed_docs_from_redis(kb) -> list:
    """
    Get all indexed documentation metadata from Redis doc_hash keys.

    Issue #165: Scans doc_hash:* keys to get document metadata for browsing.
    """
    docs = []
    cursor = 0
    while True:
        cursor, keys = await asyncio.to_thread(kb.redis_client.scan, cursor, match="doc_hash:*", count=500)
        if keys:
            # Batch fetch document data
            values = await asyncio.to_thread(kb.redis_client.mget, keys)
            for key, value in zip(keys, values):
                if value:
                    try:
                        doc_data = json.loads(value)
                        doc_data["content_hash"] = key.replace("doc_hash:", "")
                        docs.append(doc_data)
                    except (json.JSONDecodeError, TypeError):
                        continue
        if cursor == 0:
            break
    return docs


def _filter_docs(docs: list, request: DocsBrowseRequest) -> list:
    """
    Apply filters to document list.

    Issue #165: Filters by category, doc_type, and file_path_pattern.
    """
    filtered = docs

    # Filter by category (from file path detection)
    if request.category:
        category_lower = request.category.lower()
        filtered = [
            d
            for d in filtered
            if category_lower in d.get("file_path", "").lower() or d.get("category", "").lower() == category_lower
        ]

    # Filter by doc_type
    if request.doc_type:
        doc_type_lower = request.doc_type.lower()
        filtered = [
            d
            for d in filtered
            if d.get("doc_type", "").lower() == doc_type_lower
            or d.get("file_path", "").lower().endswith(f".{doc_type_lower}")
        ]

    # Filter by file path pattern
    if request.file_path_pattern:
        pattern = request.file_path_pattern.lower()
        filtered = [d for d in filtered if pattern in d.get("file_path", "").lower()]

    # Filter by search query (title match)
    if request.search_query:
        query_lower = request.search_query.lower()
        filtered = [
            d
            for d in filtered
            if query_lower in d.get("title", "").lower() or query_lower in d.get("file_path", "").lower()
        ]

    return filtered


def _sort_docs(docs: list, sort_by: str, sort_order: str) -> list:
    """Sort documents by specified field and order."""
    reverse = sort_order == "desc"
    return sorted(docs, key=lambda d: d.get(sort_by, ""), reverse=reverse)


def _paginate_docs(docs: list, page: int, page_size: int) -> tuple:
    """Paginate document list. Returns (paginated_docs, total_count, total_pages)."""
    total = len(docs)
    total_pages = (total + page_size - 1) // page_size if total > 0 else 1
    start = (page - 1) * page_size
    end = start + page_size
    return docs[start:end], total, total_pages


@router.post("/docs/browse", response_model=DocsBrowseResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="browse_documentation",
    error_code_prefix="KNOWLEDGE",
)
async def browse_documentation(
    admin_check: bool = Depends(check_admin_permission),
    request: DocsBrowseRequest = None,
    req: Request = None,
):
    """
    Browse indexed documentation with filtering and pagination.

    Issue #165: Provides frontend with filterable documentation browsing.
    Supports category, doc_type, file_path, and search filters.
    Issue #744: Requires admin authentication.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        # Issue #5407: KB instance not initialized - emit counter before 503.
        logger.warning("browse_documentation: KB uninitialized - raising 503")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="docs_browse", reason="kb_uninit").inc()
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")

    # Get all indexed documents
    all_docs = await _get_indexed_docs_from_redis(kb)

    # Apply filters
    filtered_docs = _filter_docs(all_docs, request)

    # Sort
    sorted_docs = _sort_docs(filtered_docs, request.sort_by, request.sort_order)

    # Paginate
    paginated, total, total_pages = _paginate_docs(sorted_docs, request.page, request.page_size)

    return {
        "success": True,
        "documents": paginated,
        "pagination": {
            "page": request.page,
            "page_size": request.page_size,
            "total_documents": total,
            "total_pages": total_pages,
        },
        "filters_applied": {
            "category": request.category,
            "doc_type": request.doc_type,
            "file_path_pattern": request.file_path_pattern,
            "search_query": request.search_query,
        },
    }


@router.get("/docs/categories", response_model=DocsCategoriesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_documentation_categories",
    error_code_prefix="KNOWLEDGE",
)
async def get_documentation_categories(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """
    Get list of documentation categories with counts.

    Issue #165: Provides category filter options for documentation browser.
    Categories are detected from file paths using CATEGORY_TAXONOMY.
    Issue #744: Requires admin authentication.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        # Issue #5407: KB instance not initialized - emit counter before 503.
        logger.warning("get_documentation_categories: KB uninitialized - raising 503")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="docs_categories", reason="kb_uninit").inc()
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")

    # Get all indexed documents
    all_docs = await _get_indexed_docs_from_redis(kb)

    # Count by category (detected from file path)
    from pathlib import Path

    from scripts.utilities.index_documentation import CATEGORY_TAXONOMY, detect_category

    category_counts: dict = {}
    for doc in all_docs:
        file_path = doc.get("file_path", "")
        if file_path:
            try:
                category = detect_category(Path(file_path))
            except Exception:
                category = "general"
        else:
            category = "general"

        category_counts[category] = category_counts.get(category, 0) + 1

    # Build category list with metadata
    categories = []
    for cat_id, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        cat_meta = CATEGORY_TAXONOMY.get(cat_id, {})
        categories.append(
            {
                "id": cat_id,
                "name": cat_meta.get("name", cat_id.title()),
                "description": cat_meta.get("description", ""),
                "count": count,
            }
        )

    return {
        "success": True,
        "categories": categories,
        "total_documents": len(all_docs),
    }


@router.get("/docs/stats", response_model=DocsStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_documentation_stats",
    error_code_prefix="KNOWLEDGE",
)
async def get_documentation_stats(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """
    Get documentation indexing statistics.

    Issue #165: Provides overview stats for documentation health dashboard.
    Issue #744: Requires admin authentication.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        # Issue #5407: KB instance not initialized - emit counter before 503.
        logger.warning("get_documentation_stats: KB uninitialized - raising 503")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="docs_stats", reason="kb_uninit").inc()
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")

    all_docs = await _get_indexed_docs_from_redis(kb)

    # Calculate stats
    total_chunks = sum(doc.get("chunks", 0) for doc in all_docs)

    # Get unique file paths for doc count
    unique_files = set(doc.get("file_path", "") for doc in all_docs)

    # Get latest indexed timestamp
    latest_indexed = None
    for doc in all_docs:
        indexed_at = doc.get("indexed_at")
        if indexed_at and (latest_indexed is None or indexed_at > latest_indexed):
            latest_indexed = indexed_at

    return {
        "success": True,
        "stats": {
            "total_documents": len(unique_files),
            "total_indexed_entries": len(all_docs),
            "total_chunks": total_chunks,
            "latest_indexed": latest_indexed,
            "categories_count": len(set(doc.get("category", "general") for doc in all_docs)),
        },
    }


@router.get("/docs/watcher/status", response_model=DocsWatcherStatusResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_documentation_watcher_status",
    error_code_prefix="KNOWLEDGE",
)
async def get_documentation_watcher_status(
    admin_check: bool = Depends(check_admin_permission),
    req: Request = None,
):
    """
    Get documentation watcher status.

    Issue #165: Returns status of the real-time documentation sync service.
    Issue #744: Requires admin authentication.
    """
    try:
        from services.documentation_watcher import get_documentation_watcher

        watcher = get_documentation_watcher()
        stats = watcher.get_stats()

        return {
            "success": True,
            "watcher": stats,
        }
    except ImportError:
        return {
            "success": True,
            "watcher": {
                "is_running": False,
                "message": "Documentation watcher not available",
            },
        }


@router.post("/docs/watcher/control", response_model=DocsWatcherControlResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="control_documentation_watcher",
    error_code_prefix="KNOWLEDGE",
)
async def control_documentation_watcher(
    admin_check: bool = Depends(check_admin_permission),
    request: dict = None,
    req: Request = None,
):
    """
    Control documentation watcher (start/stop).

    Issue #165: Allows manual control of the real-time sync service.
    Issue #744: Requires admin authentication.
    """
    action = request.get("action", "status")

    try:
        from services.documentation_watcher import (
            get_documentation_watcher,
            start_documentation_watcher,
            stop_documentation_watcher,
        )

        if action == "start":
            success = await start_documentation_watcher()
            return {
                "success": success,
                "message": "Watcher started" if success else "Failed to start watcher",
            }

        elif action == "stop":
            await stop_documentation_watcher()
            return {
                "success": True,
                "message": "Watcher stopped",
            }

        elif action == "status":
            watcher = get_documentation_watcher()
            return {
                "success": True,
                "watcher": watcher.get_stats(),
            }

        else:
            return {
                "success": False,
                "message": f"Unknown action: {action}",
            }

    except ImportError:
        return {
            "success": False,
            "message": "Documentation watcher not available",
        }


# ===== PER-ORG LLM + EMBEDDING MODEL CONFIG (Issue #4451) =====
# Admin-only endpoints for reading and writing an organization's persisted
# LLM provider, LLM model, and embedding model. Config is resolved via the
# fallback chain org config -> SSOT default (see OrgKnowledgeConfigService).


def _resolve_target_org_id(current_user: dict, override_org_id: str | None) -> str | None:
    """Pick the org_id a config request should target.

    Admins can target another org via ``?org_id=`` query param. Non-admins
    always read/write their own org. A missing ``org_id`` means single-org
    mode — the service uses the ``__default__`` sentinel.
    """
    if override_org_id:
        role = (current_user or {}).get("role", "")
        if role not in ("admin", "platform_admin", "superadmin"):
            raise HTTPException(status_code=403, detail="Only admins may target another org")
        return override_org_id
    return (current_user or {}).get("org_id")


@router.get("/org-config", response_model=OrgKnowledgeConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_org_model_config",
    error_code_prefix="KNOWLEDGE",
)
async def get_org_model_config(
    org_id: str | None = Query(default=None, max_length=128),
    current_user: dict = Depends(get_current_user),
):
    """Return the org's persisted model config with SSOT-resolved defaults.

    The response always contains a non-null ``effective`` payload (org
    config merged over SSOT defaults) and a ``stored`` payload showing what
    was actually persisted (may be ``null`` when the org has never set a
    preference).
    """
    from services.knowledge.org_knowledge_config import (
        get_org_knowledge_config_service,
    )

    target_org = _resolve_target_org_id(current_user, org_id)
    service = get_org_knowledge_config_service()
    stored = await service.get(target_org)
    effective = await service.get_effective(target_org)
    return {
        "org_id": target_org or "__default__",
        "stored": stored.model_dump() if stored else None,
        "effective": effective.model_dump(),
    }


@router.put("/org-config", response_model=OrgKnowledgeConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="set_org_model_config",
    error_code_prefix="KNOWLEDGE",
)
async def set_org_model_config(
    payload: OrgKnowledgeConfigPayload,
    org_id: str | None = Query(default=None, max_length=128),
    current_user: dict = Depends(get_current_user),
    admin_check: bool = Depends(check_admin_permission),
):
    """Persist the org's LLM + embedding model config (admin only)."""
    from services.knowledge.org_knowledge_config import (
        OrgKnowledgeConfig,
        get_org_knowledge_config_service,
    )

    target_org = _resolve_target_org_id(current_user, org_id)
    service = get_org_knowledge_config_service()
    stored = await service.set(target_org, OrgKnowledgeConfig(**payload.model_dump()))
    effective = await service.get_effective(target_org)
    return {
        "org_id": target_org or "__default__",
        "stored": stored.model_dump(),
        "effective": effective.model_dump(),
    }


# ===== MAINTENANCE ENDPOINTS =====
# NOTE: Maintenance and bulk operation endpoints moved to knowledge_maintenance.py (Issue #185)
# Includes: deduplication, bulk operations, orphaned facts, export/import, cleanup, host scanning

from api.knowledge_maintenance import router as maintenance_router

router.include_router(maintenance_router)

# ===== CONSOLIDATED KNOWLEDGE ROUTERS (Issue #708) =====
# These routers were previously registered separately in feature_routers.py
# Now consolidated under the main knowledge router for cleaner organization

# AI Stack RAG Integration - Enhanced search, knowledge extraction, document analysis
# Provides: /search/enhanced, /search/rag, /extract, /analyze/documents, /query/reformulate,
#           /system/insights, /stats/enhanced, /health/enhanced
try:
    from api.knowledge_ai_stack import router as ai_stack_router

    router.include_router(ai_stack_router, prefix="/ai-stack", tags=["knowledge-enhanced", "ai-stack"])
except ImportError as e:
    logging.warning("AI Stack knowledge router not available: %s", e)

# Debug/Testing Endpoints - Fresh stats, Redis debug, index rebuild
# Provides: /fresh_stats, /debug_redis, /rebuild_index
try:
    from api.knowledge_debug import router as debug_router

    router.include_router(debug_router, prefix="/debug", tags=["knowledge-debug"])
except ImportError as e:
    logging.warning("Knowledge debug router not available: %s", e)

# Unified Search - Combined search across all knowledge sources
# Provides: /unified/search, /unified/stats, /unified/context, /unified/documentation/*,
#           /unified/graph (for KnowledgeGraph.vue visualization)
try:
    from api.knowledge_search_aggregator import router as unified_router

    router.include_router(unified_router, tags=["knowledge-unified", "documentation"])
except ImportError as e:
    logging.warning("Unified knowledge search router not available: %s", e)


# ===== KB WATCH FOLDERS (Issue #9000) =====


@router.post("/watch-folders", response_model=WatchFolderResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="create_watch_folder",
    error_code_prefix="KNOWLEDGE",
)
async def create_watch_folder(
    request: WatchFolderCreateRequest,
    current_user: dict = Depends(get_current_user),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Create a new watch folder for auto-ingestion.

    Issue #9000: Register a filesystem path to automatically ingest new files
    into the knowledge base.
    """
    import uuid

    from services.kb_folder_watcher import WatchFolderConfig, get_kb_folder_watcher

    try:
        watcher = get_kb_folder_watcher()

        # Generate unique folder ID
        folder_id = str(uuid.uuid4())

        # Create config
        config = WatchFolderConfig(
            folder_id=folder_id,
            path=request.path,
            collection=request.collection,
            enabled=request.enabled,
            file_types=request.file_types,
            recursive=request.recursive,
            category=request.category,
            tags=request.tags,
        )

        # Add watch folder
        success = await watcher.add_watch_folder(config)

        if success:
            return {
                "success": True,
                "message": "Watch folder created successfully",
                "folder_id": folder_id,
                "folder": config.to_dict(),
            }
        else:
            return {
                "success": False,
                "message": "Failed to create watch folder",
            }

    except Exception as e:
        logger.error("Error creating watch folder: %s", e)
        return {
            "success": False,
            "message": f"Error: {str(e)}",
        }


@router.get("/watch-folders", response_model=WatchFolderListResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_watch_folders",
    error_code_prefix="KNOWLEDGE",
)
async def list_watch_folders(
    current_user: dict = Depends(get_current_user),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    List all configured watch folders.

    Issue #9000: Get all watch folders with their configurations and stats.
    """
    from services.kb_folder_watcher import get_kb_folder_watcher

    try:
        watcher = get_kb_folder_watcher()

        # Initialize if not already done
        if not watcher._is_running:
            await watcher.initialize()

        folders = watcher.get_watch_folders()

        return {
            "success": True,
            "folders": folders,
            "total": len(folders),
        }

    except Exception as e:
        logger.error("Error listing watch folders: %s", e)
        return {
            "success": False,
            "folders": [],
            "total": 0,
        }


@router.delete("/watch-folders/{folder_id}", response_model=WatchFolderResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="delete_watch_folder",
    error_code_prefix="KNOWLEDGE",
)
async def delete_watch_folder(
    folder_id: str,
    current_user: dict = Depends(get_current_user),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Delete a watch folder.

    Issue #9000: Remove a watch folder and stop monitoring it.
    """
    from services.kb_folder_watcher import get_kb_folder_watcher

    try:
        watcher = get_kb_folder_watcher()
        success = await watcher.remove_watch_folder(folder_id)

        return {
            "success": success,
            "message": "Watch folder deleted" if success else "Failed to delete watch folder",
        }

    except Exception as e:
        logger.error("Error deleting watch folder: %s", e)
        return {
            "success": False,
            "message": f"Error: {str(e)}",
        }


@router.patch("/watch-folders/{folder_id}/control", response_model=WatchFolderResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="control_watch_folder",
    error_code_prefix="KNOWLEDGE",
)
async def control_watch_folder(
    folder_id: str,
    request: WatchFolderControlRequest,
    current_user: dict = Depends(get_current_user),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Enable or disable a watch folder.

    Issue #9000: Control whether a watch folder is actively monitoring for changes.
    """
    from services.kb_folder_watcher import get_kb_folder_watcher

    try:
        watcher = get_kb_folder_watcher()

        enabled = request.action == "enable"
        success = await watcher.update_watch_folder(folder_id, enabled)

        return {
            "success": success,
            "message": (
                f"Watch folder {'enabled' if enabled else 'disabled'}" if success else "Failed to update watch folder"
            ),
        }

    except Exception as e:
        logger.error("Error controlling watch folder: %s", e)
        return {
            "success": False,
            "message": f"Error: {str(e)}",
        }


@router.get("/watch-folders/stats", response_model=WatchFolderStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_watch_folder_stats",
    error_code_prefix="KNOWLEDGE",
)
async def get_watch_folder_stats(
    current_user: dict = Depends(get_current_user),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get overall watch folder statistics.

    Issue #9000: Get aggregated stats across all watch folders.
    """
    from services.kb_folder_watcher import get_kb_folder_watcher

    try:
        watcher = get_kb_folder_watcher()

        # Initialize if not already done
        if not watcher._is_running:
            await watcher.initialize()

        stats = watcher.get_stats()

        return {
            "success": True,
            "stats": stats,
        }

    except Exception as e:
        logger.error("Error getting watch folder stats: %s", e)
        return {
            "success": False,
            "stats": {},
        }
