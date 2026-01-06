# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base API Models - Pydantic models for request/response validation.

This module contains all Pydantic models used by the knowledge base API endpoints.
Extracted from knowledge.py for better maintainability (Issue #185).

Models:
- FactIdValidator: Validates fact ID format
- SearchRequest: Basic search parameters
- EnhancedSearchRequest: Advanced search with tags, modes
- PaginationRequest: Pagination parameters
- AddTextRequest: Add text to knowledge base
- ScanHostChangesRequest: Scan for host document changes
- AdvancedSearchRequest: RAG search with reranking
- RerankRequest: Rerank existing results
- TagValidator: Tag format validation
- AddTagsRequest: Add tags to fact
- RemoveTagsRequest: Remove tags from fact
- BulkTagRequest: Bulk tag operations
- SearchByTagsRequest: Search by tags
- ExportFormat: Export format enum
- ExportFilters: Export filtering options
- ExportRequest: Knowledge export
- ImportRequest: Knowledge import
- DeduplicationRequest: Deduplication parameters
- BulkDeleteRequest: Bulk delete facts
- BulkCategoryUpdateRequest: Bulk update categories
- CleanupRequest: Cleanup operations
- UpdateFactRequest: Update fact content

Related Issues: #77 (Tags), #78 (Enhanced Search), #79 (Bulk Operations), #185 (Split)
"""

import re
from datetime import datetime
from enum import Enum
from typing import List, Optional

from backend.type_defs.common import Metadata
from pydantic import BaseModel, Field, validator
from src.constants.threshold_constants import CategoryDefaults, QueryDefaults
from src.utils.path_validation import contains_path_traversal

# Issue #380: Module-level frozenset for tag operations
_VALID_TAG_OPERATIONS = frozenset({"add", "remove"})

# Issue #380: Pre-compiled regex patterns for validators
# These are called on every request validation, so pre-compilation is important
_ALNUM_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")  # Mixed case: IDs, categories, cursors
_LOWERCASE_TAG_RE = re.compile(r"^[a-z0-9_-]+$")  # Lowercase: tags

# Issue #380: Module-level tuples for search mode and sort validation
_VALID_SEARCH_MODES = ("semantic", "keyword", "hybrid", "auto")
_VALID_SORT_OPTIONS = ("newest", "oldest", "longest")


# ===== BASIC VALIDATION MODELS =====


class FactIdValidator(BaseModel):
    """Validator for fact ID format and security"""

    fact_id: str = Field(..., min_length=1, max_length=255)

    @validator("fact_id")
    def validate_fact_id(cls, v):
        """Validate fact_id format to prevent injection attacks"""
        # Allow UUID format or safe alphanumeric with underscores/hyphens
        if not _ALNUM_ID_RE.match(v):
            raise ValueError(
                "Invalid fact_id format: only alphanumeric, underscore, and hyphen allowed"
            )
        # Prevent path traversal attempts (Issue #328 - uses shared validation)
        if contains_path_traversal(v):
            raise ValueError("Path traversal not allowed in fact_id")
        return v


class SearchRequest(BaseModel):
    """Request model for search endpoints"""

    query: str = Field(..., min_length=1, max_length=1000)
    limit: int = Field(default=QueryDefaults.DEFAULT_SEARCH_LIMIT, ge=1, le=100)
    category: Optional[str] = Field(default=None, max_length=100)

    @validator("category")
    def validate_category(cls, v):
        """Validate category format"""
        if v and not _ALNUM_ID_RE.match(v):
            raise ValueError("Invalid category format")
        return v


class EnhancedSearchRequest(BaseModel):
    """Enhanced search request with tag filtering and hybrid mode (Issue #78)"""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    limit: int = Field(default=QueryDefaults.DEFAULT_SEARCH_LIMIT, ge=1, le=100, description="Max results to return")
    offset: int = Field(default=QueryDefaults.DEFAULT_OFFSET, ge=0, description="Pagination offset")
    category: Optional[str] = Field(default=None, max_length=100)
    tags: Optional[List[str]] = Field(
        default=None,
        max_items=10,
        description="Filter results by tags (facts must have ALL specified tags)",
    )
    tags_match_any: bool = Field(
        default=False,
        description="If True, match facts with ANY tag. If False (default), match ALL tags.",
    )
    mode: str = Field(
        default=CategoryDefaults.SEARCH_MODE_HYBRID,
        description="Search mode: 'semantic' (vector only), 'keyword' (text only), "
        "'hybrid' (both)",
    )
    enable_reranking: bool = Field(
        default=False,
        description="Enable cross-encoder reranking for better relevance",
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score threshold (0.0-1.0)",
    )

    @validator("category")
    def validate_category(cls, v):
        """Validate category format"""
        if v and not _ALNUM_ID_RE.match(v):
            raise ValueError("Invalid category format")
        return v

    @validator("tags", each_item=True)
    def validate_tag_item(cls, v):
        """Validate each tag"""
        if v:
            v = v.lower().strip()
            if not _LOWERCASE_TAG_RE.match(v):
                raise ValueError(f"Invalid tag format: {v}")
        return v

    @validator("mode")
    def validate_mode(cls, v):
        """Validate search mode"""
        if v not in _VALID_SEARCH_MODES:  # Issue #380: use module constant
            raise ValueError(f"Invalid mode: {v}. Must be one of {_VALID_SEARCH_MODES}")
        return v

    # === Issue #372: Feature Envy Reduction Methods ===

    def to_search_params(self) -> dict:
        """Convert to parameters dict for knowledge base search (Issue #372)."""
        return {
            "query": self.query,
            "limit": self.limit,
            "offset": self.offset,
            "category": self.category,
            "tags": self.tags,
            "tags_match_any": self.tags_match_any,
            "mode": self.mode,
            "enable_reranking": self.enable_reranking,
            "min_score": self.min_score,
        }

    def get_log_summary(self) -> str:
        """Get formatted log summary string (Issue #372 - reduces feature envy)."""
        return (
            f"'{self.query}' (limit={self.limit}, offset={self.offset}, "
            f"mode={self.mode}, tags={self.tags}, min_score={self.min_score})"
        )

    def get_fallback_response(self, results: list) -> dict:
        """Build fallback response when enhanced search is unavailable (Issue #372)."""
        return {
            "success": True,
            "results": results,
            "total_count": len(results),
            "query_processed": self.query,
            "mode": self.mode,
            "tags_applied": [],
            "min_score_applied": 0.0,
            "reranking_applied": False,
            "message": "Using fallback search - enhanced features not available",
        }

    def get_safe_mode(self, valid_modes: set) -> str:
        """Get mode with fallback if not in valid modes (Issue #372)."""
        return self.mode if self.mode in valid_modes else "auto"


class ConsolidatedSearchRequest(BaseModel):
    """
    Consolidated search request model combining all search features (Issue #555).

    This is the primary search endpoint that supports all search capabilities:
    - Basic search (query, limit)
    - Enhanced search (tags, hybrid mode, reranking)
    - RAG search (query reformulation, synthesis)
    - Advanced filtering (date filters, term filters)
    - Analytics tracking

    Deprecates: /enhanced_search, /rag_search, /similarity_search, /enhanced_search_v2
    """

    # Core search parameters
    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    top_k: int = Field(default=QueryDefaults.DEFAULT_TOP_K, ge=1, le=100, description="Maximum results to return")
    category: Optional[str] = Field(
        default=None, max_length=100, description="Filter by category"
    )

    # Search mode
    mode: str = Field(
        default=CategoryDefaults.SEARCH_MODE_HYBRID,
        description="Search mode: 'semantic' (vector only), 'keyword' (text only), "
        "'hybrid' (both, default), 'auto' (intelligent selection)",
    )

    # RAG enhancement options
    enable_rag: bool = Field(
        default=False,
        description="Enable RAG enhancement for synthesized responses",
    )
    enable_reranking: bool = Field(
        default=False,
        description="Enable cross-encoder reranking for improved relevance",
    )
    reformulate_query: bool = Field(
        default=False,
        description="Use RAG agent to expand/reformulate query for better coverage",
    )
    return_context: bool = Field(
        default=False,
        description="Return optimized context for RAG (useful for chat integration)",
    )

    # Filtering options
    tags: Optional[List[str]] = Field(
        default=None,
        max_items=10,
        description="Filter results by tags",
    )
    tags_match_any: bool = Field(
        default=False,
        description="If True, match facts with ANY tag. If False (default), match ALL tags.",
    )
    min_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Minimum similarity score threshold (0.0-1.0)",
    )

    # Pagination
    offset: int = Field(default=QueryDefaults.DEFAULT_OFFSET, ge=0, description="Pagination offset")

    # Advanced filtering (Issue #78 v2 features)
    created_after: Optional[str] = Field(
        default=None,
        description="Filter facts created after this date (ISO format: YYYY-MM-DD)",
    )
    created_before: Optional[str] = Field(
        default=None,
        description="Filter facts created before this date (ISO format: YYYY-MM-DD)",
    )
    exclude_terms: Optional[List[str]] = Field(
        default=None,
        max_items=20,
        description="Exclude results containing these terms",
    )
    require_terms: Optional[List[str]] = Field(
        default=None,
        max_items=20,
        description="Only include results containing ALL of these terms",
    )

    # Advanced features
    include_documentation: bool = Field(
        default=False,
        description="Also search project documentation",
    )
    include_relations: bool = Field(
        default=False,
        description="Include related facts in results",
    )

    # Analytics
    track_analytics: bool = Field(
        default=True,
        description="Track this search for analytics (default: true)",
    )
    session_id: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Session ID for analytics correlation",
    )

    @validator("category")
    def validate_category(cls, v):
        """Validate category format."""
        if v and not _ALNUM_ID_RE.match(v):
            raise ValueError("Invalid category format")
        return v

    @validator("tags", each_item=True)
    def validate_tag_item(cls, v):
        """Validate each tag."""
        if v:
            v = v.lower().strip()
            if not _LOWERCASE_TAG_RE.match(v):
                raise ValueError(f"Invalid tag format: {v}")
        return v

    @validator("mode")
    def validate_mode(cls, v):
        """Validate search mode."""
        if v not in _VALID_SEARCH_MODES:
            raise ValueError(f"Invalid mode: {v}. Must be one of {_VALID_SEARCH_MODES}")
        return v

    @validator("created_after", "created_before")
    def validate_date(cls, v):
        """Validate date format."""
        if v:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        return v

    def to_legacy_params(self) -> dict:
        """Convert to parameters compatible with existing KB search methods."""
        return {
            "query": self.query,
            "limit": self.top_k,
            "offset": self.offset,
            "category": self.category,
            "tags": self.tags,
            "tags_match_any": self.tags_match_any,
            "mode": self.mode,
            "enable_reranking": self.enable_reranking,
            "min_score": self.min_score,
        }

    def get_log_summary(self) -> str:
        """Get formatted log summary string."""
        features = []
        if self.enable_rag:
            features.append("RAG")
        if self.enable_reranking:
            features.append("rerank")
        if self.reformulate_query:
            features.append("reformulate")
        if self.tags:
            features.append(f"tags={len(self.tags)}")

        feature_str = f" [{', '.join(features)}]" if features else ""
        return (
            f"'{self.query}' (top_k={self.top_k}, mode={self.mode}"
            f"{feature_str})"
        )


class PaginationRequest(BaseModel):
    """Request model for pagination"""

    limit: int = Field(default=QueryDefaults.KNOWLEDGE_DEFAULT_LIMIT, ge=1, le=1000)
    offset: int = Field(default=QueryDefaults.DEFAULT_OFFSET, ge=0)
    cursor: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = Field(default=None, max_length=100)

    @validator("cursor")
    def validate_cursor(cls, v):
        """Validate cursor format"""
        if v and not _ALNUM_ID_RE.match(v):
            raise ValueError("Invalid cursor format")
        return v

    @validator("category")
    def validate_category(cls, v):
        """Validate category format"""
        if v and not _ALNUM_ID_RE.match(v):
            raise ValueError("Invalid category format")
        return v


class AddTextRequest(BaseModel):
    """Request model for adding text to knowledge base"""

    text: str = Field(..., min_length=1, max_length=1000000)
    metadata: Optional[Metadata] = Field(default=None)
    category: Optional[str] = Field(default=CategoryDefaults.GENERAL, max_length=100)

    @validator("metadata")
    def validate_metadata(cls, v):
        """Validate metadata structure"""
        if v is not None and not isinstance(v, dict):
            raise ValueError("Metadata must be a dictionary")
        return v


class ScanHostChangesRequest(BaseModel):
    """Request model for scanning host document changes"""

    machine_id: str = Field(..., min_length=1, max_length=100)
    force: bool = Field(default=False)
    scan_type: str = Field(default="manpages", max_length=50)
    auto_vectorize: bool = Field(
        default=False, description="Automatically vectorize detected changes"
    )


class AdvancedSearchRequest(BaseModel):
    """Request model for advanced RAG search with reranking"""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    max_results: int = Field(
        default=5, ge=1, le=50, description="Maximum results to return"
    )
    enable_reranking: bool = Field(
        default=True, description="Enable cross-encoder reranking"
    )
    return_context: bool = Field(
        default=False, description="Return optimized context for RAG"
    )
    timeout: Optional[float] = Field(
        default=None, description="Optional timeout in seconds"
    )


class RerankRequest(BaseModel):
    """Request model for reranking existing search results"""

    query: str = Field(
        ..., min_length=1, max_length=1000, description="Original search query"
    )
    results: List[Metadata] = Field(..., description="Search results to rerank")


# ===== TAG MANAGEMENT MODELS (Issue #77) =====


class TagValidator(BaseModel):
    """Validator for tag format and security"""

    tag: str = Field(..., min_length=1, max_length=50)

    @validator("tag")
    def validate_tag(cls, v):
        """Validate tag format - lowercase alphanumeric with hyphens/underscores"""
        # Normalize to lowercase
        v = v.lower().strip()
        # Allow alphanumeric, hyphens, underscores
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError(
                "Invalid tag format: only lowercase alphanumeric, underscore, "
                "and hyphen allowed"
            )
        # Prevent injection attempts (Issue #328 - uses shared validation)
        if contains_path_traversal(v):
            raise ValueError("Invalid characters in tag")
        return v


class AddTagsRequest(BaseModel):
    """Request model for adding tags to a fact"""

    tags: List[str] = Field(
        ...,
        min_items=1,
        max_items=20,
        description="List of tags to add (max 20 per request)",
    )

    @validator("tags", each_item=True)
    def validate_tag_item(cls, v):
        """Validate each tag in the list"""
        v = v.lower().strip()
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError(f"Invalid tag format: {v}")
        if len(v) > 50:
            raise ValueError(f"Tag too long: {v}")
        return v


class RemoveTagsRequest(BaseModel):
    """Request model for removing tags from a fact"""

    tags: List[str] = Field(
        ...,
        min_items=1,
        max_items=20,
        description="List of tags to remove",
    )

    @validator("tags", each_item=True)
    def validate_tag_item(cls, v):
        """Validate each tag in the list"""
        v = v.lower().strip()
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError(f"Invalid tag format: {v}")
        return v


class BulkTagRequest(BaseModel):
    """Request model for bulk tagging operations"""

    fact_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=100,
        description="List of fact IDs to tag",
    )
    tags: List[str] = Field(
        ...,
        min_items=1,
        max_items=20,
        description="List of tags to apply",
    )
    operation: str = Field(
        default="add",
        description="Operation: 'add' or 'remove'",
    )

    @validator("fact_ids", each_item=True)
    def validate_fact_id_item(cls, v):
        """Validate each fact ID format (Critical fix #5)"""
        # Reuse existing FactIdValidator logic
        if not _ALNUM_ID_RE.match(v):
            raise ValueError(
                f"Invalid fact_id format: {v} - only alphanumeric, "
                "underscore, and hyphen allowed"
            )
        # Prevent path traversal attempts (Issue #328 - uses shared validation)
        if contains_path_traversal(v):
            raise ValueError(f"Path traversal not allowed in fact_id: {v}")
        return v

    @validator("operation")
    def validate_operation(cls, v):
        """Validate operation type"""
        if v not in _VALID_TAG_OPERATIONS:
            raise ValueError("Operation must be 'add' or 'remove'")
        return v

    @validator("tags", each_item=True)
    def validate_tag_item(cls, v):
        """Validate each tag"""
        v = v.lower().strip()
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError(f"Invalid tag format: {v}")
        return v


class SearchByTagsRequest(BaseModel):
    """Request model for searching by tags"""

    tags: List[str] = Field(
        ...,
        min_items=1,
        max_items=10,
        description="Tags to search for",
    )
    match_all: bool = Field(
        default=False,
        description="If True, facts must have ALL tags. If False, facts with ANY tag.",
    )
    limit: int = Field(default=QueryDefaults.DEFAULT_PAGE_SIZE, ge=1, le=500)
    offset: int = Field(default=QueryDefaults.DEFAULT_OFFSET, ge=0)
    category: Optional[str] = Field(default=None, max_length=100)

    @validator("tags", each_item=True)
    def validate_tag_item(cls, v):
        """Validate each tag"""
        v = v.lower().strip()
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError(f"Invalid tag format: {v}")
        return v


# ===== TAG MANAGEMENT CRUD MODELS (Issue #409) =====


class RenameTagRequest(BaseModel):
    """Request model for renaming a tag globally."""

    new_tag: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="New name for the tag",
    )

    @validator("new_tag")
    def validate_new_tag(cls, v):
        """Validate new tag format."""
        v = v.lower().strip()
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError(
                "Invalid tag format: only lowercase alphanumeric, underscore, "
                "and hyphen allowed"
            )
        if contains_path_traversal(v):
            raise ValueError("Invalid characters in tag")
        return v


class MergeTagsRequest(BaseModel):
    """Request model for merging multiple tags into one."""

    source_tags: List[str] = Field(
        ...,
        min_items=1,
        max_items=20,
        description="Tags to merge (these will be removed)",
    )
    target_tag: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Target tag to merge into",
    )

    @validator("source_tags", each_item=True)
    def validate_source_tag_item(cls, v):
        """Validate each source tag."""
        v = v.lower().strip()
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError(f"Invalid tag format: {v}")
        return v

    @validator("target_tag")
    def validate_target_tag(cls, v):
        """Validate target tag format."""
        v = v.lower().strip()
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError(
                "Invalid tag format: only lowercase alphanumeric, underscore, "
                "and hyphen allowed"
            )
        if contains_path_traversal(v):
            raise ValueError("Invalid characters in tag")
        return v


class GetFactsByTagRequest(BaseModel):
    """Request model for getting facts by tag with pagination."""

    limit: int = Field(default=QueryDefaults.DEFAULT_PAGE_SIZE, ge=1, le=500, description="Max facts to return")
    offset: int = Field(default=QueryDefaults.DEFAULT_OFFSET, ge=0, description="Pagination offset")
    include_content: bool = Field(
        default=False,
        description="Include fact content in response",
    )


# Issue #410: Pre-compiled regex for hex color validation
_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# Issue #410: Default tag colors for auto-assignment
DEFAULT_TAG_COLORS = [
    "#3B82F6",  # Blue
    "#10B981",  # Green
    "#F59E0B",  # Amber
    "#EF4444",  # Red
    "#8B5CF6",  # Purple
    "#EC4899",  # Pink
    "#06B6D4",  # Cyan
    "#F97316",  # Orange
]


class UpdateTagStyleRequest(BaseModel):
    """
    Request model for updating tag styling (Issue #410).

    Allows setting color and optional icon for visual tag customization.
    """

    color: Optional[str] = Field(
        default=None,
        min_length=7,
        max_length=7,
        description="Hex color code (e.g., '#3B82F6')",
    )
    icon: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Optional icon class (e.g., 'fas fa-code')",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Optional tag description",
    )

    @validator("color")
    def validate_color(cls, v):
        """Validate hex color format."""
        if v is not None:
            if not _HEX_COLOR_RE.match(v):
                raise ValueError(
                    f"Invalid color format: {v}. Use hex format like '#3B82F6'"
                )
        return v

    @validator("icon")
    def validate_icon(cls, v):
        """Validate icon class format (basic sanitization)."""
        if v is not None:
            # Only allow alphanumeric, hyphens, and spaces (for icon classes)
            if not re.match(r"^[a-zA-Z0-9\s\-]+$", v):
                raise ValueError("Invalid icon format: only alphanumeric, spaces, hyphens")
        return v


# ===== CATEGORY MANAGEMENT MODELS (Issue #411) =====

# Issue #411: Pre-compiled regex for category name validation
_CATEGORY_NAME_RE = re.compile(r"^[a-z0-9_-]+$")
_CATEGORY_PATH_RE = re.compile(r"^[a-z0-9_/-]+$")


class CreateCategoryRequest(BaseModel):
    """
    Request model for creating a new category (Issue #411).

    Categories support hierarchical organization with parent-child relationships.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Category name (lowercase, alphanumeric, hyphens, underscores)",
    )
    parent_id: Optional[str] = Field(
        default=None,
        description="Parent category ID (None = root category)",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Category description",
    )
    icon: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Icon identifier (e.g., 'fas fa-code')",
    )
    color: Optional[str] = Field(
        default=None,
        min_length=7,
        max_length=7,
        description="Hex color code (e.g., '#3B82F6')",
    )

    @validator("name")
    def validate_name(cls, v):
        """Validate category name format."""
        v = v.lower().strip().replace(" ", "-")
        if not _CATEGORY_NAME_RE.match(v):
            raise ValueError(
                "Invalid category name: only lowercase alphanumeric, "
                "hyphens, underscores allowed"
            )
        if contains_path_traversal(v):
            raise ValueError("Invalid characters in category name")
        return v

    @validator("parent_id")
    def validate_parent_id(cls, v):
        """Validate parent_id format."""
        if v is not None:
            if not _ALNUM_ID_RE.match(v):
                raise ValueError("Invalid parent_id format")
            if contains_path_traversal(v):
                raise ValueError("Invalid characters in parent_id")
        return v

    @validator("color")
    def validate_color(cls, v):
        """Validate hex color format."""
        if v is not None:
            if not _HEX_COLOR_RE.match(v):
                raise ValueError(
                    f"Invalid color format: {v}. Use hex format like '#3B82F6'"
                )
        return v


class UpdateCategoryRequest(BaseModel):
    """
    Request model for updating a category (Issue #411).

    All fields are optional; only provided fields are updated.
    Note: Renaming a category updates its path and all descendant paths.
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="New category name (triggers path update)",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=200,
        description="New description",
    )
    icon: Optional[str] = Field(
        default=None,
        max_length=50,
        description="New icon identifier",
    )
    color: Optional[str] = Field(
        default=None,
        min_length=7,
        max_length=7,
        description="New hex color code",
    )

    @validator("name")
    def validate_name(cls, v):
        """Validate category name format if provided."""
        if v is not None:
            v = v.lower().strip().replace(" ", "-")
            if not _CATEGORY_NAME_RE.match(v):
                raise ValueError(
                    "Invalid category name: only lowercase alphanumeric, "
                    "hyphens, underscores allowed"
                )
        return v

    @validator("color")
    def validate_color(cls, v):
        """Validate hex color format if provided."""
        if v is not None:
            if not _HEX_COLOR_RE.match(v):
                raise ValueError(
                    f"Invalid color format: {v}. Use hex format like '#3B82F6'"
                )
        return v


class DeleteCategoryRequest(BaseModel):
    """
    Request model for deleting a category (Issue #411).

    Provides options for handling child categories and assigned facts.
    """

    recursive: bool = Field(
        default=False,
        description="Delete all descendant categories. If False, fails if has children.",
    )
    reassign_to: Optional[str] = Field(
        default=None,
        description="Category ID to reassign facts to. If None, facts become uncategorized.",
    )

    @validator("reassign_to")
    def validate_reassign_to(cls, v):
        """Validate reassign_to format if provided."""
        if v is not None:
            if not _ALNUM_ID_RE.match(v):
                raise ValueError("Invalid reassign_to category ID format")
        return v


class AssignFactToCategoryRequest(BaseModel):
    """
    Request model for assigning a fact to a category (Issue #411).
    """

    category_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Category ID to assign fact to",
    )

    @validator("category_id")
    def validate_category_id(cls, v):
        """Validate category_id format."""
        if not _ALNUM_ID_RE.match(v):
            raise ValueError("Invalid category_id format")
        if contains_path_traversal(v):
            raise ValueError("Invalid characters in category_id")
        return v


class SearchCategoriesByPathRequest(BaseModel):
    """
    Request model for searching categories by path pattern (Issue #411).

    Supports wildcard patterns like 'tech/python/*'.
    """

    path_pattern: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Path pattern with optional wildcard (e.g., 'tech/python/*')",
    )
    limit: int = Field(
        default=QueryDefaults.DEFAULT_PAGE_SIZE,
        ge=1,
        le=200,
        description="Maximum number of categories to return",
    )

    @validator("path_pattern")
    def validate_path_pattern(cls, v):
        """Validate path pattern format."""
        v = v.lower().strip()
        # Remove trailing asterisk for validation
        check_pattern = v.rstrip("*")
        if check_pattern and not _CATEGORY_PATH_RE.match(check_pattern):
            raise ValueError(
                "Invalid path pattern: only lowercase alphanumeric, "
                "hyphens, underscores, and forward slashes allowed"
            )
        return v


# ===== COLLECTION MANAGEMENT MODELS (Issue #412) =====


class CreateCollectionRequest(BaseModel):
    """
    Request model for creating a new collection (Issue #412).

    Collections enable project-based grouping of facts with many-to-many relationships.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Collection name",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Collection description",
    )
    icon: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Icon identifier (e.g., 'fas fa-folder')",
    )
    color: Optional[str] = Field(
        default=None,
        min_length=7,
        max_length=7,
        description="Hex color code (e.g., '#3B82F6')",
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Custom metadata for the collection",
    )

    @validator("name")
    def validate_name(cls, v):
        """Validate collection name."""
        v = v.strip()
        if not v:
            raise ValueError("Collection name cannot be empty")
        if contains_path_traversal(v):
            raise ValueError("Invalid characters in collection name")
        return v

    @validator("color")
    def validate_color(cls, v):
        """Validate hex color format."""
        if v is not None:
            if not _HEX_COLOR_RE.match(v):
                raise ValueError(
                    f"Invalid color format: {v}. Use hex format like '#3B82F6'"
                )
        return v


class UpdateCollectionRequest(BaseModel):
    """
    Request model for updating a collection (Issue #412).

    All fields are optional; only provided fields are updated.
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="New collection name",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="New description",
    )
    icon: Optional[str] = Field(
        default=None,
        max_length=50,
        description="New icon identifier",
    )
    color: Optional[str] = Field(
        default=None,
        min_length=7,
        max_length=7,
        description="New hex color code",
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="New custom metadata (replaces existing)",
    )

    @validator("name")
    def validate_name(cls, v):
        """Validate collection name if provided."""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Collection name cannot be empty")
        return v

    @validator("color")
    def validate_color(cls, v):
        """Validate hex color format if provided."""
        if v is not None:
            if not _HEX_COLOR_RE.match(v):
                raise ValueError(
                    f"Invalid color format: {v}. Use hex format like '#3B82F6'"
                )
        return v


class CollectionFactsRequest(BaseModel):
    """
    Request model for adding/removing facts from a collection (Issue #412).
    """

    fact_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=500,
        description="List of fact IDs to add/remove",
    )

    @validator("fact_ids", each_item=True)
    def validate_fact_id(cls, v):
        """Validate fact ID format."""
        if not _ALNUM_ID_RE.match(v):
            raise ValueError(f"Invalid fact_id format: {v}")
        if contains_path_traversal(v):
            raise ValueError(f"Invalid characters in fact_id: {v}")
        return v


# ===== ML-BASED SUGGESTION MODELS (Issue #413) =====


class SuggestTagsRequest(BaseModel):
    """
    Request model for tag suggestions based on content (Issue #413).

    Uses embedding-based similarity to find related documents and
    suggest tags with confidence scores.
    """

    content: str = Field(
        ...,
        min_length=10,
        max_length=100000,
        description="Document content to analyze for tag suggestions",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of tag suggestions to return",
    )
    min_confidence: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold for suggestions (0.0-1.0)",
    )
    similarity_limit: int = Field(
        default=20,
        ge=5,
        le=50,
        description="Number of similar documents to analyze",
    )


class SuggestCategoriesRequest(BaseModel):
    """
    Request model for category suggestions based on content (Issue #413).

    Uses embedding-based similarity to find related documents and
    suggest categories with confidence scores.
    """

    content: str = Field(
        ...,
        min_length=10,
        max_length=100000,
        description="Document content to analyze for category suggestions",
    )
    limit: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of category suggestions to return",
    )
    min_confidence: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold for suggestions (0.0-1.0)",
    )
    similarity_limit: int = Field(
        default=20,
        ge=5,
        le=50,
        description="Number of similar documents to analyze",
    )


class SuggestAllRequest(BaseModel):
    """
    Request model for combined tag and category suggestions (Issue #413).

    More efficient than separate calls as it only performs one similarity search.
    """

    content: str = Field(
        ...,
        min_length=10,
        max_length=100000,
        description="Document content to analyze",
    )
    tag_limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of tag suggestions",
    )
    category_limit: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of category suggestions",
    )
    min_confidence: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum confidence threshold",
    )
    similarity_limit: int = Field(
        default=20,
        ge=5,
        le=50,
        description="Number of similar documents to analyze",
    )


class AutoApplySuggestionsRequest(BaseModel):
    """
    Request model for auto-applying suggestions to a fact (Issue #413).

    Automatically applies high-confidence tags and categories to an existing fact.
    """

    content: str = Field(
        ...,
        min_length=10,
        max_length=100000,
        description="Content to analyze for suggestions",
    )
    apply_tags: bool = Field(
        default=True,
        description="Whether to apply tag suggestions",
    )
    apply_category: bool = Field(
        default=True,
        description="Whether to apply category suggestion",
    )
    min_confidence: float = Field(
        default=0.85,
        ge=0.5,
        le=1.0,
        description="Minimum confidence to auto-apply (0.5-1.0, higher = stricter)",
    )


# ===== METADATA TEMPLATE MODELS (Issue #414) =====

# Valid field types for metadata templates
VALID_FIELD_TYPES = ("string", "number", "date", "boolean", "list", "url", "email")


class MetadataFieldDefinition(BaseModel):
    """
    Definition of a single metadata field (Issue #414).

    Used within metadata templates to define custom fields.
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Field name (alphanumeric, underscores)",
    )
    type: str = Field(
        default="string",
        description="Field type: string, number, date, boolean, list, url, email",
    )
    required: bool = Field(
        default=False,
        description="Whether this field is required",
    )
    default: Optional[str] = Field(
        default=None,
        description="Default value if not provided",
    )
    validation: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Optional regex validation pattern",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Field description for UI",
    )

    @validator("name")
    def validate_name(cls, v):
        """Validate field name format."""
        v = v.strip()
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", v):
            raise ValueError(
                "Field name must start with letter, contain only alphanumeric/underscore"
            )
        return v

    @validator("type")
    def validate_type(cls, v):
        """Validate field type."""
        if v not in VALID_FIELD_TYPES:
            raise ValueError(f"Invalid type: {v}. Must be one of: {VALID_FIELD_TYPES}")
        return v

    @validator("validation")
    def validate_regex(cls, v):
        """Validate regex pattern if provided."""
        if v:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")
        return v


class CreateMetadataTemplateRequest(BaseModel):
    """
    Request model for creating a metadata template (Issue #414).
    """

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Template name (e.g., 'API Documentation')",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Template description",
    )
    fields: List[MetadataFieldDefinition] = Field(
        ...,
        min_items=1,
        max_items=20,
        description="List of field definitions",
    )
    applicable_categories: Optional[List[str]] = Field(
        default=None,
        max_items=20,
        description="Categories this template applies to",
    )

    @validator("name")
    def validate_name(cls, v):
        """Validate template name."""
        v = v.strip()
        if not v:
            raise ValueError("Template name cannot be empty")
        return v


class UpdateMetadataTemplateRequest(BaseModel):
    """
    Request model for updating a metadata template (Issue #414).
    """

    name: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="New template name",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="New description",
    )
    fields: Optional[List[MetadataFieldDefinition]] = Field(
        default=None,
        max_items=20,
        description="New field definitions (replaces all existing)",
    )
    applicable_categories: Optional[List[str]] = Field(
        default=None,
        max_items=20,
        description="New applicable categories",
    )


class ValidateMetadataRequest(BaseModel):
    """
    Request model for validating metadata against templates (Issue #414).
    """

    metadata: dict = Field(
        ...,
        description="Metadata dict to validate",
    )
    category: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Category to determine applicable templates",
    )


class SearchByMetadataRequest(BaseModel):
    """
    Request model for searching facts by metadata field (Issue #414).
    """

    field_name: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Metadata field name to search",
    )
    value: str = Field(
        ...,
        max_length=500,
        description="Value to match",
    )
    operator: str = Field(
        default="eq",
        description="Comparison operator: eq, contains, gt, lt",
    )
    limit: int = Field(
        default=QueryDefaults.DEFAULT_PAGE_SIZE,
        ge=1,
        le=200,
        description="Maximum results to return",
    )

    @validator("operator")
    def validate_operator(cls, v):
        """Validate comparison operator."""
        valid_ops = ("eq", "contains", "gt", "lt")
        if v not in valid_ops:
            raise ValueError(f"Invalid operator: {v}. Must be one of: {valid_ops}")
        return v


# ===== VERSION HISTORY MODELS (Issue #414) =====


class RevertToVersionRequest(BaseModel):
    """
    Request model for reverting a fact to a previous version (Issue #414).
    """

    version: int = Field(
        ...,
        ge=1,
        description="Version number to revert to",
    )
    created_by: Optional[str] = Field(
        default=None,
        max_length=100,
        description="User/agent performing the revert",
    )


class CompareVersionsRequest(BaseModel):
    """
    Request model for comparing two versions of a fact (Issue #414).
    """

    version_a: int = Field(
        ...,
        ge=1,
        description="First version number",
    )
    version_b: int = Field(
        ...,
        ge=1,
        description="Second version number",
    )


# ===== BULK OPERATION MODELS (Issue #79) =====


class ExportFormat(str, Enum):
    """Supported export formats"""

    JSON = "json"
    CSV = "csv"
    MARKDOWN = "markdown"


class ExportFilters(BaseModel):
    """Filters for export operations"""

    categories: Optional[List[str]] = Field(default=None, max_items=20)
    tags: Optional[List[str]] = Field(default=None, max_items=20)
    date_from: Optional[str] = Field(
        default=None,
        description="ISO date string (YYYY-MM-DD)",
    )
    date_to: Optional[str] = Field(
        default=None,
        description="ISO date string (YYYY-MM-DD)",
    )
    fact_ids: Optional[List[str]] = Field(default=None, max_items=1000)

    @validator("date_from", "date_to")
    def validate_date(cls, v):
        """Validate date format"""
        if v:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        return v


class ExportRequest(BaseModel):
    """Request model for knowledge base export"""

    format: ExportFormat = Field(default=ExportFormat.JSON)
    filters: Optional[ExportFilters] = Field(default=None)
    include_metadata: bool = Field(default=True)
    include_tags: bool = Field(default=True)
    include_embeddings: bool = Field(
        default=False,
        description="Include vector embeddings (large file size)",
    )


class ImportRequest(BaseModel):
    """Request model for knowledge base import"""

    format: ExportFormat = Field(default=ExportFormat.JSON)
    validate_only: bool = Field(
        default=False,
        description="Only validate, don't import",
    )
    skip_duplicates: bool = Field(
        default=True,
        description="Skip facts that already exist",
    )
    overwrite_existing: bool = Field(
        default=False,
        description="Overwrite existing facts with same ID",
    )
    default_category: str = Field(default="imported", max_length=100)


class DeduplicationRequest(BaseModel):
    """Request model for deduplication operations"""

    similarity_threshold: float = Field(
        default=0.95,
        ge=0.5,
        le=1.0,
        description="Similarity threshold for detecting duplicates (0.5-1.0)",
    )
    use_embeddings: bool = Field(
        default=False,
        description="Use vector embeddings for semantic similarity (Issue #417)",
    )
    dry_run: bool = Field(
        default=True,
        description="If True, only report duplicates without merging",
    )
    keep_strategy: str = Field(
        default="newest",
        description="Strategy for keeping facts: 'newest', 'oldest', 'longest'",
    )
    category: Optional[str] = Field(
        default=None,
        description="Limit deduplication to specific category",
    )
    max_results: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of duplicate groups to return",
    )
    max_comparisons: int = Field(
        default=10000,
        ge=100,
        le=100000,
        description="Maximum number of comparisons to avoid timeout (hash mode only)",
    )

    @validator("keep_strategy")
    def validate_strategy(cls, v):
        """Validate keep strategy"""
        if v not in _VALID_SORT_OPTIONS:  # Issue #380: use module constant
            raise ValueError(f"Invalid strategy: {v}. Must be one of {_VALID_SORT_OPTIONS}")
        return v


class BulkDeleteRequest(BaseModel):
    """Request model for bulk delete operations"""

    fact_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=500,
        description="List of fact IDs to delete",
    )
    confirm: bool = Field(
        default=False,
        description="Must be True to actually delete",
    )

    @validator("fact_ids", each_item=True)
    def validate_fact_id(cls, v):
        """Validate fact ID format"""
        if not _ALNUM_ID_RE.match(v):
            raise ValueError(f"Invalid fact_id format: {v}")
        # Prevent path traversal (Issue #328 - uses shared validation)
        if contains_path_traversal(v):
            raise ValueError(f"Path traversal not allowed in fact_id: {v}")
        return v


class BulkCategoryUpdateRequest(BaseModel):
    """Request model for bulk category updates"""

    fact_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=500,
    )
    new_category: str = Field(
        ...,
        min_length=1,
        max_length=100,
    )

    @validator("fact_ids", each_item=True)
    def validate_fact_id(cls, v):
        """Validate fact ID format"""
        if not _ALNUM_ID_RE.match(v):
            raise ValueError(f"Invalid fact_id format: {v}")
        return v

    @validator("new_category")
    def validate_category(cls, v):
        """Validate category format"""
        if not _ALNUM_ID_RE.match(v):
            raise ValueError(f"Invalid category format: {v}")
        return v


class CleanupRequest(BaseModel):
    """Request model for cleanup operations"""

    remove_empty: bool = Field(
        default=True,
        description="Remove facts with empty content",
    )
    remove_orphaned_tags: bool = Field(
        default=True,
        description="Remove tags with no associated facts",
    )
    fix_metadata: bool = Field(
        default=True,
        description="Fix malformed metadata JSON",
    )
    dry_run: bool = Field(
        default=True,
        description="Only report issues without fixing",
    )


# ===== BACKUP AND RESTORE MODELS (Issue #419) =====


class BackupRequest(BaseModel):
    """Request model for creating knowledge base backups (Issue #419)"""

    include_embeddings: bool = Field(
        default=True,
        description="Include vector embeddings in backup (larger file size)",
    )
    include_metadata: bool = Field(
        default=True,
        description="Include backup metadata (stats, categories)",
    )
    compression: bool = Field(
        default=True,
        description="Use gzip compression for backup file",
    )
    description: str = Field(
        default="",
        max_length=500,
        description="Optional description for the backup",
    )


class RestoreRequest(BaseModel):
    """Request model for restoring knowledge base from backup (Issue #419)"""

    backup_file: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Path to backup file to restore",
    )
    overwrite_existing: bool = Field(
        default=False,
        description="Overwrite existing facts with backup data",
    )
    skip_duplicates: bool = Field(
        default=True,
        description="Skip facts that already exist",
    )
    restore_embeddings: bool = Field(
        default=True,
        description="Restore vector embeddings if available",
    )
    dry_run: bool = Field(
        default=True,
        description="Only validate backup, don't actually restore",
    )

    @validator("backup_file")
    def validate_backup_file(cls, v):
        """Validate backup file path (Issue #419)."""
        # Prevent path traversal attempts
        if contains_path_traversal(v):
            raise ValueError("Path traversal not allowed in backup_file")
        # Validate it looks like a backup file
        if not v.endswith((".json", ".jsongz", ".json.gz")):
            raise ValueError("Backup file must be .json or .json.gz format")
        return v


class DeleteBackupRequest(BaseModel):
    """Request model for deleting a backup file (Issue #419)"""

    backup_file: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Path to backup file to delete",
    )

    @validator("backup_file")
    def validate_backup_file(cls, v):
        """Validate backup file path (Issue #419)."""
        if contains_path_traversal(v):
            raise ValueError("Path traversal not allowed in backup_file")
        return v


class UpdateFactRequest(BaseModel):
    """Request model for updating a fact"""

    content: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=1000000,
        description="New content for the fact",
    )
    category: Optional[str] = Field(
        default=None, max_length=100, description="New category"
    )
    metadata: Optional[Metadata] = Field(
        default=None, description="New or updated metadata"
    )

    @validator("category")
    def validate_category(cls, v):
        """Validate category format"""
        if v and not _ALNUM_ID_RE.match(v):
            raise ValueError(f"Invalid category format: {v}")
        return v


# ===== MODULE EXPORTS =====

__all__ = [
    # Basic validators
    "FactIdValidator",
    "SearchRequest",
    "EnhancedSearchRequest",
    "ConsolidatedSearchRequest",  # Issue #555: Consolidated search endpoint
    "PaginationRequest",
    "AddTextRequest",
    "ScanHostChangesRequest",
    "AdvancedSearchRequest",
    "RerankRequest",
    # Tag management
    "TagValidator",
    "AddTagsRequest",
    "RemoveTagsRequest",
    "BulkTagRequest",
    "SearchByTagsRequest",
    # Tag management CRUD (Issue #409)
    "RenameTagRequest",
    "MergeTagsRequest",
    "GetFactsByTagRequest",
    # Tag styling (Issue #410)
    "UpdateTagStyleRequest",
    "DEFAULT_TAG_COLORS",
    # Category management (Issue #411)
    "CreateCategoryRequest",
    "UpdateCategoryRequest",
    "DeleteCategoryRequest",
    "AssignFactToCategoryRequest",
    "SearchCategoriesByPathRequest",
    # Collection management (Issue #412)
    "CreateCollectionRequest",
    "UpdateCollectionRequest",
    "CollectionFactsRequest",
    # ML-based suggestions (Issue #413)
    "SuggestTagsRequest",
    "SuggestCategoriesRequest",
    "SuggestAllRequest",
    "AutoApplySuggestionsRequest",
    # Metadata templates (Issue #414)
    "VALID_FIELD_TYPES",
    "MetadataFieldDefinition",
    "CreateMetadataTemplateRequest",
    "UpdateMetadataTemplateRequest",
    "ValidateMetadataRequest",
    "SearchByMetadataRequest",
    # Version history (Issue #414)
    "RevertToVersionRequest",
    "CompareVersionsRequest",
    # Bulk operations
    "ExportFormat",
    "ExportFilters",
    "ExportRequest",
    "ImportRequest",
    "DeduplicationRequest",
    "BulkDeleteRequest",
    "BulkCategoryUpdateRequest",
    "CleanupRequest",
    "UpdateFactRequest",
    # Backup and restore (Issue #419)
    "BackupRequest",
    "RestoreRequest",
    "DeleteBackupRequest",
]
