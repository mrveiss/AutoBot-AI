# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Knowledge Base API endpoints for content management and search with RAG integration."""

import asyncio
import json
import logging
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field, field_validator

# NOTE: Pydantic models moved to knowledge_maintenance.py (Issue #185 - split oversized files)
# NOTE: Tag-related models moved to knowledge_tags.py
# NOTE: Search models (EnhancedSearchRequest) moved to knowledge_search.py
from backend.knowledge_factory import get_or_create_knowledge_base
from src.exceptions import InternalError
from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.constants.threshold_constants import CategoryDefaults, QueryDefaults
from src.utils.path_validation import contains_path_traversal


# =============================================================================
# Issue #549: Pydantic Models for Knowledge Ingestion Endpoints
# =============================================================================


class AddFactsRequest(BaseModel):
    """Request model for adding text content to knowledge base."""

    content: str = Field(..., min_length=1, max_length=100000, description="Text content")
    title: str = Field(default="", max_length=500, description="Document title")
    source: str = Field(default="Manual Entry", max_length=500, description="Content source")
    category: str = Field(default=CategoryDefaults.GENERAL, max_length=100, description="Category")
    tags: List[str] = Field(default_factory=list, description="Tags for the content")

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        if len(v) > 20:
            raise ValueError("Maximum 20 tags allowed")
        return [tag[:50] for tag in v]  # Limit tag length


class AddUrlRequest(BaseModel):
    """Request model for adding URL content to knowledge base."""

    url: str = Field(..., min_length=1, max_length=2000, description="URL to fetch")
    title: str = Field(default="", max_length=500, description="Document title")
    method: str = Field(default="fetch", pattern="^(fetch|raw)$", description="Fetch method")
    category: str = Field(default="web", max_length=100, description="Category")
    tags: List[str] = Field(default_factory=list, description="Tags")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


# File upload constants (Issue #549 Code Review)
MAX_FILE_SIZE_MB = 10
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".json", ".csv", ".html"}

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


async def _compute_category_counts(
    all_facts: list, get_category_for_source, category_counts: dict
) -> None:
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


def _get_category_cache_keys(KnowledgeCategory) -> dict:
    """Get cache keys for category counts (Issue #398: extracted)."""
    return {
        KnowledgeCategory.AUTOBOT_DOCUMENTATION: "kb:stats:category:autobot-documentation",
        KnowledgeCategory.SYSTEM_KNOWLEDGE: "kb:stats:category:system-knowledge",
        KnowledgeCategory.USER_KNOWLEDGE: "kb:stats:category:user-knowledge",
    }


async def _get_or_compute_category_counts(
    kb, cache_keys: dict, get_category_for_source, category_counts: dict
) -> None:
    """Get cached counts or compute from facts (Issue #398: extracted)."""
    cached_values = await kb.aioredis_client.mget(list(cache_keys.values()))
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
            await kb.aioredis_client.set(
                cache_key, category_counts[cat_id], ex=CATEGORY_CACHE_TTL
            )


def _build_main_categories(CATEGORY_METADATA, category_counts: dict) -> list:
    """Build main categories list with counts (Issue #398: extracted)."""
    return [
        {
            "id": cat_id, "name": meta["name"], "description": meta["description"],
            "icon": meta["icon"], "color": meta["color"],
            "examples": meta["examples"], "count": category_counts.get(cat_id, 0),
        }
        for cat_id, meta in CATEGORY_METADATA.items()
    ]


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_main_categories",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/categories/main")
async def get_main_categories(req: Request):
    """Get the 3 main knowledge base categories with their metadata and stats."""
    from backend.knowledge_categories import (
        CATEGORY_METADATA, KnowledgeCategory, get_category_for_source,
    )

    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    has_redis = kb.aioredis_client is not None if kb else False
    logger.info("get_main_categories - kb: %s, has_redis: %s", kb is not None, has_redis)

    category_counts = {
        KnowledgeCategory.AUTOBOT_DOCUMENTATION: 0,
        KnowledgeCategory.SYSTEM_KNOWLEDGE: 0,
        KnowledgeCategory.USER_KNOWLEDGE: 0,
    }

    if kb and kb.aioredis_client:
        logger.info("Attempting to get cached category counts...")
        try:
            cache_keys = _get_category_cache_keys(KnowledgeCategory)
            await _get_or_compute_category_counts(
                kb, cache_keys, get_category_for_source, category_counts
            )
        except Exception as e:
            logger.error("Error categorizing facts: %s", e)

    main_categories = _build_main_categories(CATEGORY_METADATA, category_counts)
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


def _sanitize_html_content(html_content: str) -> tuple:
    """
    Safely extract text and title from HTML content (Issue #549 Code Review: Security fix).

    Uses html.parser for safe HTML processing instead of regex.

    Args:
        html_content: Raw HTML content

    Returns:
        Tuple of (plain_text, extracted_title)
    """
    from html.parser import HTMLParser
    from html import unescape

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.text_parts = []
            self.title = ""
            self._in_script = False
            self._in_style = False
            self._in_title = False

        def handle_starttag(self, tag, attrs):
            tag_lower = tag.lower()
            if tag_lower == "script":
                self._in_script = True
            elif tag_lower == "style":
                self._in_style = True
            elif tag_lower == "title":
                self._in_title = True

        def handle_endtag(self, tag):
            tag_lower = tag.lower()
            if tag_lower == "script":
                self._in_script = False
            elif tag_lower == "style":
                self._in_style = False
            elif tag_lower == "title":
                self._in_title = False

        def handle_data(self, data):
            if self._in_title:
                self.title = data.strip()
            elif not self._in_script and not self._in_style:
                text = data.strip()
                if text:
                    self.text_parts.append(text)

    parser = TextExtractor()
    try:
        parser.feed(html_content)
    except Exception:
        # Fallback: just unescape and strip tags with regex
        import re
        text = re.sub(r"<[^>]+>", " ", html_content)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip(), ""

    plain_text = " ".join(parser.text_parts)
    return plain_text, parser.title


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
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE_MB}MB"
        )

    # Check extension
    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Check for path traversal
    if contains_path_traversal(filename):
        raise HTTPException(status_code=400, detail="Invalid filename")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_facts_to_knowledge",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/facts")
async def add_facts_to_knowledge(request: AddFactsRequest, req: Request):
    """
    Add text content to knowledge base (frontend-compatible endpoint).

    Issue #549: Created to match KnowledgeRepository.ts POST /api/knowledge_base/facts
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        raise InternalError("Knowledge base not initialized - please check logs for errors")

    logger.info(f"Adding fact: title='{request.title}', source='{request.source}', len={len(request.content)}")

    fact_id = await _store_fact_in_kb(
        kb_to_use,
        request.content,
        {
            "title": request.title,
            "source": request.source,
            "category": request.category,
            "tags": request.tags,
        },
    )

    return {
        "success": True,
        "document_id": fact_id,
        "title": request.title,
        "content": request.content[:100] + "..." if len(request.content) > 100 else request.content,
        "message": "Document added successfully",
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_url_to_knowledge",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/url")
async def add_url_to_knowledge(request: AddUrlRequest, req: Request):
    """
    Add content from URL to knowledge base.

    Issue #549: Created to match KnowledgeRepository.ts POST /api/knowledge_base/url
    """
    import aiohttp

    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        raise InternalError("Knowledge base not initialized")

    logger.info(f"Fetching content from URL: {request.url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(request.url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status != 200:
                    raise HTTPException(status_code=400, detail=f"HTTP {response.status}")
                html_content = await response.text()

                # Use safe HTML parser instead of regex (Issue #549 Code Review)
                content, extracted_title = _sanitize_html_content(html_content)
                title = request.title or extracted_title or request.url

    except aiohttp.ClientError as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {str(e)}")

    fact_id = await _store_fact_in_kb(
        kb_to_use,
        content,
        {
            "title": title,
            "source": request.url,
            "category": request.category,
            "tags": request.tags,
            "type": "url",
        },
    )

    return {
        "success": True,
        "document_id": fact_id,
        "title": title,
        "content": content[:100] + "..." if len(content) > 100 else content,
        "message": f"URL content added ({len(content)} chars)",
    }


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
    import io
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
        try:
            import pypdf
            pdf_reader = pypdf.PdfReader(io.BytesIO(file_content))
            return "\n".join(page.extract_text() or "" for page in pdf_reader.pages)
        except ImportError:
            raise HTTPException(status_code=400, detail="PDF support requires pypdf library")
        except Exception as e:
            logger.error("PDF parse error for %s: %s", filename, e)
            raise HTTPException(status_code=400, detail="Failed to parse PDF file")

    if ext == ".docx":
        try:
            import docx
            doc = docx.Document(io.BytesIO(file_content))
            return "\n".join(para.text for para in doc.paragraphs)
        except ImportError:
            raise HTTPException(status_code=400, detail="DOCX support requires python-docx library")
        except Exception as e:
            logger.error("DOCX parse error for %s: %s", filename, e)
            raise HTTPException(status_code=400, detail="Failed to parse DOCX file")

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="upload_file_to_knowledge",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/upload")
async def upload_file_to_knowledge(req: Request):
    """
    Upload file to knowledge base.

    Issue #549: Created to match KnowledgeRepository.ts POST /api/knowledge_base/upload
    Supports: .txt, .md, .pdf, .docx, .json, .csv, .html files
    """
    import os

    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb_to_use is None:
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

    word_count = len(content.split())
    return {
        "success": True,
        "document_id": fact_id,
        "title": title,
        "content": content[:100] + "..." if len(content) > 100 else content,
        "word_count": word_count,
        "message": f"File uploaded ({word_count} words)",
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


def _empty_entries_response(message: str = "", error: str = "") -> dict:
    """Create empty entries response (Issue #398: extracted)."""
    resp = {"entries": [], "next_cursor": "0", "count": 0, "has_more": False}
    if message:
        resp["message"] = message
    if error:
        resp["error"] = error
    return resp


def _parse_and_filter_facts(
    items: dict, category: Optional[str], limit: int
) -> list:
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


@router.get("/entries")
async def get_knowledge_entries(
    req: Request,
    limit: int = Query(default=QueryDefaults.KNOWLEDGE_DEFAULT_LIMIT, ge=1, le=1000),
    cursor: Optional[str] = Query(default="0", regex=r"^[0-9]+$"),
    category: Optional[str] = Query(default=None, regex=r"^[a-zA-Z0-9_-]*$"),
):
    """Get knowledge base entries with cursor-based pagination."""
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        return _empty_entries_response(message="Knowledge base not initialized")

    logger.info("Getting knowledge entries: limit=%s, cursor=%s", limit, cursor)
    current_cursor = int(cursor) if cursor else 0

    try:
        def _hscan():
            return kb.redis_client.hscan(
                "knowledge_base:facts", cursor=current_cursor, count=limit * 2
            )
        next_cursor, items = await asyncio.to_thread(_hscan)
        entries = _parse_and_filter_facts(items, category, limit)
        entries.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {
            "entries": entries[:limit], "next_cursor": str(next_cursor),
            "count": len(entries[:limit]), "has_more": next_cursor != 0,
        }
    except Exception as e:
        logger.error("Redis error getting facts: %s", e)
        return _empty_entries_response(error="Redis connection error")


def _create_offline_stats_response() -> dict:
    """Create offline stats response (Issue #398: extracted)."""
    return {
        "status": "offline", "message": "Knowledge base not initialized",
        "basic_stats": {}, "category_breakdown": {}, "source_breakdown": {},
        "type_breakdown": {}, "size_metrics": {},
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
            "total_content_size": 0, "average_fact_size": 0, "median_fact_size": 0,
            "largest_fact_size": 0, "smallest_fact_size": 0,
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_detailed_stats",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/detailed_stats")
async def get_detailed_stats(req: Request):
    """Get detailed knowledge base statistics with additional metrics."""
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        return _create_offline_stats_response()

    basic_stats = await kb.get_stats()
    try:
        all_facts_data = await asyncio.to_thread(
            kb.redis_client.hgetall, "knowledge_base:facts"
        )
    except Exception:
        all_facts_data = {}

    cat_counts, src_counts, type_counts, sizes = _analyze_facts_for_stats(all_facts_data)
    return {
        "status": "online" if basic_stats.get("initialized") else "offline",
        "basic_stats": basic_stats,
        "category_breakdown": cat_counts,
        "source_breakdown": src_counts,
        "type_breakdown": type_counts,
        "size_metrics": _compute_size_metrics(sizes),
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="clear_all_knowledge",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/clear_all")
async def clear_all_knowledge(request: dict, req: Request):
    """Clear all entries from the knowledge base - DESTRUCTIVE OPERATION."""
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        return {
            "status": "error", "items_removed": 0,
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
            raise HTTPException(status_code=500, detail=f"Failed to clear: {str(e)}")

    logger.warning("Knowledge base cleared. Removed %s entries.", items_removed)
    return {
        "status": "success", "items_removed": items_removed, "items_before": items_before,
        "message": f"Successfully cleared knowledge base. Removed {items_removed} entries.",
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


# =============================================================================
# Helper Functions for get_facts_by_category (Issue #281)
# =============================================================================


async def _check_facts_cache(kb, category: Optional[str], limit: int) -> tuple:
    """Check cache for facts_by_category result (Issue #281: extracted)."""
    import json
    cache_key = f"kb:cache:facts_by_category:{category or 'all'}:{limit}"
    cached_result = await asyncio.to_thread(kb.redis_client.get, cache_key)

    if cached_result:
        logger.debug(
            f"Cache HIT for facts_by_category (category={category}, limit={limit})"
        )
        return (
            json.loads(
                cached_result.decode("utf-8")
                if isinstance(cached_result, bytes)
                else cached_result
            ),
            cache_key,
        )

    logger.info(
        f"Cache MISS for facts_by_category - using category index lookup "
        f"(category={category}, limit={limit})"
    )
    return None, cache_key


async def _fetch_category_fact_ids(kb, categories_to_fetch: list, limit: int) -> dict:
    """Fetch fact IDs from category indexes (Issue #281: extracted)."""
    category_fact_ids = {}
    for cat in categories_to_fetch:
        index_key = f"category:index:{cat}"
        fact_ids = await asyncio.to_thread(
            kb.redis_client.srandmember, index_key, limit
        )
        if fact_ids:
            decoded_ids = [
                fid.decode("utf-8") if isinstance(fid, bytes) else fid
                for fid in fact_ids
            ]
            category_fact_ids[cat] = decoded_ids
            logger.debug(
                f"Category index {cat}: fetched {len(decoded_ids)} fact IDs"
            )
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


def _process_fact_data(fact_data: dict, cat: str, fact_key: str) -> Optional[dict]:
    """Process a single fact from Redis data (Issue #281: extracted)."""
    import json

    if not fact_data:
        return None

    try:
        # Extract metadata
        metadata_raw = fact_data.get(b"metadata") or fact_data.get("metadata", b"{}")
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
        await asyncio.to_thread(
            kb.redis_client.setex, cache_key, 60, json.dumps(result)
        )
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_facts_by_category",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/facts/by_category")
async def get_facts_by_category(
    req: Request, category: Optional[str] = None, limit: int = 100
):
    """Get facts grouped by category for browsing with caching."""
    kb = await get_or_create_knowledge_base(req.app)
    if kb is None:
        _raise_kb_unavailable()

    cached_result, cache_key = await _check_facts_cache(kb, category, limit)
    if cached_result:
        return cached_result

    from backend.knowledge_categories import KnowledgeCategory
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
        return {"categories": {}, "total_facts": 0, "error": str(e)}

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
        cursor, keys = await asyncio.to_thread(
            kb.redis_client.scan, cursor, match="fact:*", count=1000
        )
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


def _parse_fact_entry(
    fact_key_bytes, fact_data, get_category_for_source
) -> Optional[tuple]:
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


async def _get_facts_by_category_legacy(kb, category: Optional[str], limit: int):
    """Legacy fallback: Get facts by scanning all keys (Issue #398: refactored)."""
    from backend.knowledge_categories import get_category_for_source

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
        categories_dict[fact_cat].append({
            "key": fact_key, "title": title,
            "content": content[:500] + "..." if len(content) > 500 else content,
            "full_content": content, "category": fact_cat,
            "type": fact_type, "metadata": metadata,
        })

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


# =============================================================================
# Issue #165: Documentation Browser API - Browse and filter indexed documentation
# =============================================================================


class DocsBrowseRequest(BaseModel):
    """Request model for browsing indexed documentation."""

    category: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Filter by category (e.g., 'developer', 'api', 'troubleshooting')"
    )
    doc_type: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Filter by document type (e.g., 'markdown', 'code')"
    )
    file_path_pattern: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Filter by file path pattern (e.g., 'docs/api/')"
    )
    search_query: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional text search within documents"
    )
    page: int = Field(default=1, ge=1, le=1000, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Results per page")
    sort_by: str = Field(
        default="indexed_at",
        pattern="^(indexed_at|title|category|file_path)$",
        description="Sort field"
    )
    sort_order: str = Field(
        default="desc",
        pattern="^(asc|desc)$",
        description="Sort order"
    )


async def _get_indexed_docs_from_redis(kb) -> list:
    """
    Get all indexed documentation metadata from Redis doc_hash keys.

    Issue #165: Scans doc_hash:* keys to get document metadata for browsing.
    """
    docs = []
    cursor = 0
    while True:
        cursor, keys = await asyncio.to_thread(
            kb.redis_client.scan, cursor, match="doc_hash:*", count=500
        )
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
            d for d in filtered
            if category_lower in d.get("file_path", "").lower()
            or d.get("category", "").lower() == category_lower
        ]

    # Filter by doc_type
    if request.doc_type:
        doc_type_lower = request.doc_type.lower()
        filtered = [
            d for d in filtered
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
            d for d in filtered
            if query_lower in d.get("title", "").lower()
            or query_lower in d.get("file_path", "").lower()
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="browse_documentation",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/docs/browse")
async def browse_documentation(request: DocsBrowseRequest, req: Request):
    """
    Browse indexed documentation with filtering and pagination.

    Issue #165: Provides frontend with filterable documentation browsing.
    Supports category, doc_type, file_path, and search filters.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")

    # Get all indexed documents
    all_docs = await _get_indexed_docs_from_redis(kb)

    # Apply filters
    filtered_docs = _filter_docs(all_docs, request)

    # Sort
    sorted_docs = _sort_docs(filtered_docs, request.sort_by, request.sort_order)

    # Paginate
    paginated, total, total_pages = _paginate_docs(
        sorted_docs, request.page, request.page_size
    )

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_doc_categories",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/docs/categories")
async def get_documentation_categories(req: Request):
    """
    Get list of documentation categories with counts.

    Issue #165: Provides category filter options for documentation browser.
    Categories are detected from file paths using CATEGORY_TAXONOMY.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base unavailable")

    # Get all indexed documents
    all_docs = await _get_indexed_docs_from_redis(kb)

    # Count by category (detected from file path)
    from scripts.utilities.index_documentation import CATEGORY_TAXONOMY, detect_category
    from pathlib import Path

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
        categories.append({
            "id": cat_id,
            "name": cat_meta.get("name", cat_id.title()),
            "description": cat_meta.get("description", ""),
            "count": count,
        })

    return {
        "success": True,
        "categories": categories,
        "total_documents": len(all_docs),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_doc_stats",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/docs/stats")
async def get_documentation_stats(req: Request):
    """
    Get documentation indexing statistics.

    Issue #165: Provides overview stats for documentation health dashboard.
    """
    kb = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb is None:
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
            "categories_count": len(set(
                doc.get("category", "general") for doc in all_docs
            )),
        },
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_doc_watcher_status",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/docs/watcher/status")
async def get_documentation_watcher_status(req: Request):
    """
    Get documentation watcher status.

    Issue #165: Returns status of the real-time documentation sync service.
    """
    try:
        from backend.services.documentation_watcher import get_documentation_watcher

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="control_doc_watcher",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/docs/watcher/control")
async def control_documentation_watcher(request: dict, req: Request):
    """
    Control documentation watcher (start/stop).

    Issue #165: Allows manual control of the real-time sync service.
    """
    action = request.get("action", "status")

    try:
        from backend.services.documentation_watcher import (
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


# ===== MAINTENANCE ENDPOINTS =====
# NOTE: Maintenance and bulk operation endpoints moved to knowledge_maintenance.py (Issue #185)
# Includes: deduplication, bulk operations, orphaned facts, export/import, cleanup, host scanning

from backend.api.knowledge_maintenance import router as maintenance_router
router.include_router(maintenance_router)

# ===== CONSOLIDATED KNOWLEDGE ROUTERS (Issue #708) =====
# These routers were previously registered separately in feature_routers.py
# Now consolidated under the main knowledge router for cleaner organization

# AI Stack RAG Integration - Enhanced search, knowledge extraction, document analysis
# Provides: /search/enhanced, /search/rag, /extract, /analyze/documents, /query/reformulate,
#           /system/insights, /stats/enhanced, /health/enhanced
try:
    from backend.api.knowledge_ai_stack import router as ai_stack_router
    router.include_router(ai_stack_router, prefix="/ai-stack", tags=["knowledge-enhanced", "ai-stack"])
except ImportError as e:
    logging.warning("AI Stack knowledge router not available: %s", e)

# Debug/Testing Endpoints - Fresh stats, Redis debug, index rebuild
# Provides: /fresh_stats, /debug_redis, /rebuild_index
try:
    from backend.api.knowledge_debug import router as debug_router
    router.include_router(debug_router, prefix="/debug", tags=["knowledge-debug"])
except ImportError as e:
    logging.warning("Knowledge debug router not available: %s", e)

# Unified Search - Combined search across all knowledge sources
# Provides: /unified/search, /unified/stats, /unified/context, /unified/documentation/*,
#           /unified/graph (for KnowledgeGraph.vue visualization)
try:
    from backend.api.knowledge_search_combined import router as unified_router
    router.include_router(unified_router, tags=["knowledge-unified", "documentation"])
except ImportError as e:
    logging.warning("Unified knowledge search router not available: %s", e)
