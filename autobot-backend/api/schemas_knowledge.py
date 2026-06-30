# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge base collection, category, fact, grounding, and audit schemas.
"""

import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List

from pydantic import AliasChoices, BaseModel, Field, field_validator

from constants.threshold_constants import CategoryDefaults, QueryDefaults
from knowledge.ownership import AccessLevel, VisibilityLevel
from type_defs.common import Metadata
from utils.path_validation import contains_dotdot_traversal, contains_path_traversal

# ---------------------------------------------------------------------------
# Knowledge schemas
# ---------------------------------------------------------------------------


class KnowledgeMetadataTemplateResponse(BaseModel):
    """Response for POST /metadata/templates and PUT /metadata/templates/{id}."""

    status: str
    message: str | None = None
    template: Dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class KnowledgeMetadataTemplateListResponse(BaseModel):
    """Response for GET /metadata/templates."""

    status: str
    count: int | None = None
    templates: List[Any] | None = None

    model_config = {"extra": "allow"}


class KnowledgeMetadataTemplateDetailResponse(BaseModel):
    """Response for GET /metadata/templates/{template_id}."""

    status: str
    template: Dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class KnowledgeMetadataTemplateDeleteResponse(BaseModel):
    """Response for DELETE /metadata/templates/{template_id}."""

    status: str
    message: str | None = None

    model_config = {"extra": "allow"}


class KnowledgeMetadataValidateResponse(BaseModel):
    """Response for POST /metadata/validate."""

    valid: bool | None = None
    errors: List[Any] | None = None
    warnings: List[Any] | None = None

    model_config = {"extra": "allow"}


class KnowledgeMetadataSearchResponse(BaseModel):
    """Response for POST /metadata/search."""

    status: str
    count: int | None = None
    facts: List[Any] | None = None

    model_config = {"extra": "allow"}


class KnowledgeFactVersionListResponse(BaseModel):
    """Response for GET /facts/{fact_id}/versions."""

    status: str
    fact_id: str | None = None
    versions: List[Any] | None = None
    count: int | None = None

    model_config = {"extra": "allow"}


class KnowledgeFactVersionDetailResponse(BaseModel):
    """Response for GET /facts/{fact_id}/versions/{version}."""

    status: str
    fact_id: str | None = None
    version: int | None = None
    content: Any | None = None

    model_config = {"extra": "allow"}


class KnowledgeFactRevertResponse(BaseModel):
    """Response for POST /facts/{fact_id}/revert."""

    status: str
    message: str | None = None
    new_version: int | None = None

    model_config = {"extra": "allow"}


class KnowledgeFactVersionCompareResponse(BaseModel):
    """Response for POST /facts/{fact_id}/versions/compare."""

    status: str
    fact_id: str | None = None
    version_a: int | None = None
    version_b: int | None = None
    diff: Any | None = None

    model_config = {"extra": "allow"}


class KnowledgeFactVersionHistoryDeleteResponse(BaseModel):
    """Response for DELETE /facts/{fact_id}/versions."""

    status: str
    message: str | None = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# knowledge_collections.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeCollectionCreateResponse(BaseModel):
    """Response for POST /collections."""

    status: str
    collection: Dict[str, Any] | None = None
    message: str | None = None


class KnowledgeCollectionListResponse(BaseModel):
    """Response for GET /collections."""

    status: str
    collections: List[Any]
    total_count: int
    returned_count: int
    limit: int
    offset: int
    has_more: bool


class KnowledgeCollectionDetailResponse(BaseModel):
    """Response for GET /collections/{collection_id}."""

    status: str
    collection: Dict[str, Any] | None = None


class KnowledgeCollectionUpdateResponse(BaseModel):
    """Response for PUT /collections/{collection_id}."""

    status: str
    collection: Dict[str, Any] | None = None
    message: str | None = None


class KnowledgeCollectionDeleteResponse(BaseModel):
    """Response for DELETE /collections/{collection_id}."""

    status: str
    collection_id: str | None = None
    facts_in_collection: int
    facts_deleted: int
    message: str | None = None


class KnowledgeCollectionAddFactsResponse(BaseModel):
    """Response for POST /collections/{collection_id}/facts."""

    status: str
    collection_id: str | None = None
    added_count: int
    already_in_collection: int
    not_found: List[Any]
    total_facts: int
    message: str | None = None


class KnowledgeCollectionRemoveFactsResponse(BaseModel):
    """Response for DELETE /collections/{collection_id}/facts."""

    status: str
    collection_id: str | None = None
    removed_count: int
    not_in_collection: int
    total_facts: int
    message: str | None = None


class KnowledgeCollectionFactsListResponse(BaseModel):
    """Response for GET /collections/{collection_id}/facts."""

    status: str
    collection_id: str | None = None
    collection_name: str | None = None
    facts: List[Any]
    total_count: int
    returned_count: int
    limit: int
    offset: int
    has_more: bool


class KnowledgeFactCollectionsResponse(BaseModel):
    """Response for GET /facts/{fact_id}/collections."""

    status: str
    fact_id: str | None = None
    collections: List[Any]
    count: int


class KnowledgeCollectionExportResponse(BaseModel):
    """Response for POST /collections/{collection_id}/export."""

    status: str
    collection: Dict[str, Any] | None = None
    facts: List[Any]
    total_count: int
    exported_at: str | None = None


class KnowledgeCollectionBulkDeleteResponse(BaseModel):
    """Response for POST /collections/{collection_id}/bulk-delete."""

    status: str
    collection_id: str | None = None
    facts_to_delete: int | None = None
    deleted_count: int
    confirm_required: bool
    message: str | None = None


# ---------------------------------------------------------------------------
# knowledge_categories.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeCategoryCreateResponse(BaseModel):
    """Response for POST /categories."""

    status: str
    category: Dict[str, Any] | None = None
    message: str | None = None


class KnowledgeCategoryTreeResponse(BaseModel):
    """Response for GET /categories/tree."""

    status: str
    tree: List[Any]
    total_categories: int


class KnowledgeCategoryDetailResponse(BaseModel):
    """Response for GET /categories/{category_id} and GET /categories/path/{path}."""

    status: str
    category: Dict[str, Any] | None = None


class KnowledgeCategoryUpdateResponse(BaseModel):
    """Response for PUT /categories/{category_id}."""

    status: str
    category: Dict[str, Any] | None = None
    message: str | None = None


class KnowledgeCategoryDeleteResponse(BaseModel):
    """Response for DELETE /categories/{category_id}."""

    status: str
    deleted_count: int
    facts_reassigned: int
    message: str | None = None


class KnowledgeCategoryChildrenResponse(BaseModel):
    """Response for GET /categories/{category_id}/children."""

    status: str
    parent_id: str | None = None
    children: List[Any]
    count: int


class KnowledgeCategoryAncestorsResponse(BaseModel):
    """Response for GET /categories/{category_id}/ancestors."""

    status: str
    category_id: str | None = None
    ancestors: List[Any]
    depth: int


class KnowledgeCategoryFactsResponse(BaseModel):
    """Response for GET /categories/{category_id}/facts."""

    status: str
    category_id: str | None = None
    category_path: str | None = None
    facts: List[Any]
    total_count: int
    returned_count: int
    limit: int
    offset: int
    has_more: bool
    include_descendants: bool


class KnowledgeFactAssignCategoryResponse(BaseModel):
    """Response for POST /facts/{fact_id}/category."""

    status: str
    fact_id: str | None = None
    category_id: str | None = None
    category_path: str | None = None
    message: str | None = None


class KnowledgeCategorySearchResponse(BaseModel):
    """Response for POST /categories/search."""

    status: str
    pattern: str | None = None
    categories: List[Any]
    count: int


# ---------------------------------------------------------------------------
# validation_dashboard.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeAggregatedSearchResponse(BaseModel):
    """Response for POST /aggregated/search."""

    success: bool
    query: str
    facts: List[Any]
    related_facts: List[Any]
    documentation: List[Any]
    sources_searched: List[str]
    total_results: int


class KnowledgeAggregatedStatsResponse(BaseModel):
    """Response for GET /aggregated/stats.

    Sections are populated dynamically — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    success: bool
    knowledge_base: Dict[str, Any]
    relations: Dict[str, Any]
    documentation: Dict[str, Any]


class KnowledgeAggregatedContextResponse(BaseModel):
    """Response for POST /aggregated/context."""

    success: bool
    context: str
    context_length: int
    citations: List[Any]
    sources_used: List[Any]


class KnowledgeDocumentationSearchResponse(BaseModel):
    """Response for GET /aggregated/documentation/search."""

    success: bool
    query: str | None = None
    results: List[Any]
    total_results: int | None = None
    message: str | None = None


class KnowledgeDocumentationStatsResponse(BaseModel):
    """Response for GET /aggregated/documentation/stats."""

    success: bool
    indexed: bool | None = None
    message: str | None = None
    how_to_index: str | None = None
    collection_name: str | None = None
    document_count: int | None = None


class KnowledgeAggregatedGraphResponse(BaseModel):
    """Response for POST /aggregated/graph and GET /aggregated/graph."""

    success: bool
    data: Dict[str, Any]
    stats: Dict[str, Any]


# ---------------------------------------------------------------------------
# knowledge_relations.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeRelationResultResponse(BaseModel):
    """Generic response for relation create/delete/traverse/hybrid-search/stats endpoints.

    KB methods return opaque success dicts — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    success: bool


class KnowledgeRelationTypesResponse(BaseModel):
    """Response for GET /types."""

    success: bool
    relation_types: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# knowledge_collaboration.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeScopedFactsResponse(BaseModel):
    """Response for GET /knowledge/collaboration/facts and /facts/organization/{id} and /facts/group/{id}."""

    facts: List[Any]
    count: int
    total: int | None = None


class KnowledgeShareResponse(BaseModel):
    """Response for POST /knowledge/collaboration/facts/{id}/share."""

    success: bool
    fact_id: str
    visibility: str | None = None
    shared_with: List[Any]
    group_ids: List[Any]


class KnowledgeUnshareResponse(BaseModel):
    """Response for DELETE /knowledge/collaboration/facts/{id}/share/{entity_id}."""

    success: bool
    fact_id: str
    visibility: str | None = None
    shared_with: List[Any]
    group_ids: List[Any]


class KnowledgePermissionsUpdateResponse(BaseModel):
    """Response for PUT /knowledge/collaboration/facts/{id}/permissions."""

    success: bool
    fact_id: str
    visibility: str | None = None
    organization_id: str | None = None
    group_ids: List[Any]


class KnowledgeAccessInfoResponse(BaseModel):
    """Response for GET /knowledge/collaboration/facts/{id}/access."""

    fact_id: str
    owner_id: str | None = None
    visibility: str | None = None
    organization_id: str | None = None
    group_ids: List[Any]
    shared_with: List[Any]
    can_edit: bool
    can_share: bool
    can_delete: bool
    has_access: bool


# ---------------------------------------------------------------------------
# knowledge_audit.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeAuditEventsResponse(BaseModel):
    """Response for GET /knowledge/audit/user-activity, /fact/{id}/access-log, /organization/audit-log."""

    events: List[Any]
    count: int
    user_id: str | None = None
    fact_id: str | None = None
    organization_id: str | None = None


class KnowledgePermissionChangesResponse(BaseModel):
    """Response for GET /knowledge/audit/permission-changes."""

    events: List[Any]
    count: int


class KnowledgeComplianceReportResponse(BaseModel):
    """Response for POST /knowledge/audit/compliance-report and GET /compliance-summary.

    Shape is defined by AuditLog.generate_compliance_report() — allow extra fields.
    """

    model_config = {"extra": "allow"}

    total_events: int


# ---------------------------------------------------------------------------
# knowledge_verification.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeVerificationPendingResponse(BaseModel):
    """Response for GET /verification/pending."""

    status: str
    pending: List[Any]
    total: int
    limit: int
    offset: int
    has_more: bool


class KnowledgeVerificationApproveResponse(BaseModel):
    """Response for POST /verification/{fact_id}/approve."""

    status: str
    fact_id: str
    verified_by: str | None = None
    verified_at: str | None = None
    message: str | None = None


class KnowledgeVerificationRejectResponse(BaseModel):
    """Response for POST /verification/{fact_id}/reject."""

    status: str
    fact_id: str
    deleted: bool
    message: str | None = None


class KnowledgeVerificationConfigResponse(BaseModel):
    """Response for GET/PUT /verification/config."""

    status: str
    config: Dict[str, Any]
    message: str | None = None


# ---------------------------------------------------------------------------
# knowledge_suggestions.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeSuggestionsTagsResponse(BaseModel):
    """Response for POST /suggestions/tags.

    KB method returns opaque success dict — allow extra fields.
    """

    model_config = {"extra": "allow"}

    success: bool
    suggestions: List[Any] | None = None
    similar_docs_analyzed: int | None = None


class KnowledgeSuggestionsCategoriesResponse(BaseModel):
    """Response for POST /suggestions/categories."""

    model_config = {"extra": "allow"}

    success: bool
    suggestions: List[Any] | None = None
    similar_docs_analyzed: int | None = None


class KnowledgeSuggestionsAllResponse(BaseModel):
    """Response for POST /suggestions/all."""

    model_config = {"extra": "allow"}

    success: bool


class KnowledgeSuggestionsContextResponse(BaseModel):
    """Response for POST /suggestions/context."""

    model_config = {"extra": "allow"}

    success: bool
    suggestions: List[Any] | None = None
    total_candidates: int | None = None


class KnowledgeAutoApplySuggestionsResponse(BaseModel):
    """Response for POST /facts/{fact_id}/auto-apply."""

    model_config = {"extra": "allow"}

    success: bool


# ---------------------------------------------------------------------------
# knowledge_ownership.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeShareFactResponse(BaseModel):
    """Response for POST /api/knowledge/facts/{fact_id}/share."""

    success: bool
    fact_id: str
    shared_with: List[Any]
    visibility: str | None = None


class KnowledgeUnshareFactResponse(BaseModel):
    """Response for DELETE /api/knowledge/facts/{fact_id}/share/{user_id_to_remove}."""

    success: bool
    fact_id: str
    shared_with: List[Any]
    visibility: str | None = None


class KnowledgeUpdateVisibilityResponse(BaseModel):
    """Response for PUT /api/knowledge/facts/{fact_id}/visibility."""

    success: bool
    fact_id: str
    visibility: str | None = None


class KnowledgeMyFactsResponse(BaseModel):
    """Response for GET /api/knowledge/facts/mine."""

    success: bool
    user_id: str
    owned_count: int
    shared_count: int
    facts: List[Any]
    total_returned: int


class KnowledgeSharedWithMeResponse(BaseModel):
    """Response for GET /api/knowledge/facts/shared-with-me."""

    success: bool
    user_id: str
    facts: List[Any]
    total_returned: int


# ---------------------------------------------------------------------------
# knowledge_grounding.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeGroundResponseResponse(BaseModel):
    """Response for POST /api/ground-response."""

    status: str
    data: Dict[str, Any]


class KnowledgeVerifyClaimResponse(BaseModel):
    """Response for POST /api/verify-claim."""

    status: str
    claim_text: str
    kb_status: str
    confidence: float
    evidence: List[Any] | None = None
    verification_method: str | None = None
    kb_source: str | None = None


class KnowledgeConflictsListResponse(BaseModel):
    """Response for GET /api/kb-conflicts."""

    status: str
    conflicts: List[Any]
    total: int
    limit: int
    offset: int
    has_more: bool


class KnowledgeResolveConflictResponse(BaseModel):
    """Response for POST /api/kb-conflicts/{conflict_id}/resolve."""

    status: str
    data: Dict[str, Any]


class KnowledgeGroundingStatsResponse(BaseModel):
    """Response for GET /api/kb-stats.

    Stats shape is dynamic — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    status: str
    period: str


# ---------------------------------------------------------------------------
# knowledge_organization.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeOrganizationPolicyResponse(BaseModel):
    """Response for GET/PUT /knowledge/organization/policy.

    Returns OrganizationKnowledgePolicy fields — allow extra fields.
    """

    model_config = {"extra": "allow"}

    default_visibility: Any
    allow_user_private: bool
    allow_user_shared: bool
    allow_user_organization: bool
    require_approval_for_system: bool
    retention_days: int | None = None


class KnowledgeOrganizationStatsResponse(BaseModel):
    """Response for GET /knowledge/organization/stats."""

    organization_id: str
    total_facts: int
    by_visibility: Dict[str, Any]
    by_source: Dict[str, Any]
    total_size_bytes: int
    user_count: int
    team_count: int
    top_contributors: List[Any]


class KnowledgeOrganizationCleanupResponse(BaseModel):
    """Response for DELETE /knowledge/organization/cleanup."""

    success: bool
    organization_id: str
    retention_days: int
    deleted_count: int
    cutoff_date: str


# ---------------------------------------------------------------------------
# knowledge_search_scoped.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeScopedSearchResponse(BaseModel):
    """Response for POST /knowledge/search/scoped and POST /knowledge/search/rag/scoped."""

    model_config = {"extra": "allow"}

    results: List[Any] | None = None
    total_results: int | None = None
    query: str | None = None
    mode: str | None = None
    user_id: str | None = None
    filtered_by_permissions: bool | None = None


class KnowledgeAccessibleScopesResponse(BaseModel):
    """Response for GET /knowledge/search/accessible-scopes."""

    user_id: str | None = None
    organization_id: str | None = None
    group_count: int
    accessible_scopes: List[Any]


# ---------------------------------------------------------------------------
# knowledge_debug.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeFreshStatsResponse(BaseModel):
    """Response for GET /fresh_stats.

    Shape varies between success and error paths — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    source: str
    total_facts: int
    status: str


class KnowledgeDebugRedisResponse(BaseModel):
    """Response for GET /debug_redis.

    Shape varies between success and failure — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    redis_connection: str


class KnowledgeRebuildIndexResponse(BaseModel):
    """Response for POST /rebuild_index.

    Shape varies depending on result.get('status') — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    operation: str
    success: bool


# ---------------------------------------------------------------------------
# knowledge_boards.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeBoardsListResponse(BaseModel):
    """Response for GET /boards."""

    boards: List[Any]
    total: int


class KnowledgeBoardCreateResponse(BaseModel):
    """Response for POST /boards."""

    board_id: str
    name: str
    created: bool


class KnowledgeBoardDeleteResponse(BaseModel):
    """Response for DELETE /boards/{board_id}."""

    board_id: str
    deleted: bool


# ---------------------------------------------------------------------------
# knowledge_cognition.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeCognitionStatusResponse(BaseModel):
    """Response for GET /cognition-store/status."""

    collections: List[Any]
    total_seeded_collections: int


class KnowledgeCognitionSeedResponse(BaseModel):
    """Response for POST /cognition-store/seed."""

    status: str
    manifest: str


# ---------------------------------------------------------------------------
# knowledge_sync_queue.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


class KnowledgeSyncQueueResponse(BaseModel):
    """Response for GET /knowledge/sync-queue."""

    pending: List[Any]
    failed: List[Any]
    counts: Dict[str, Any]
    limit: int
    offset: int


class KnowledgeSyncQueuePruneResponse(BaseModel):
    """Response for POST /knowledge/sync-queue/prune."""

    pruned: int


# ---------------------------------------------------------------------------
# memory.py schemas  (Issue #5960)
# ---------------------------------------------------------------------------


class MemoryEntityListResponse(BaseModel):
    """Response for GET /memory/entities/all — JSONResponse shape from helper."""

    model_config = {"extra": "allow"}


class MemoryOrphanScanResponse(BaseModel):
    """Response for GET /memory/entities/orphans — JSONResponse shape from helper."""

    model_config = {"extra": "allow"}


class MemoryOrphanCleanupResponse(BaseModel):
    """Response for DELETE /memory/entities/orphans — JSONResponse shape from helper."""

    model_config = {"extra": "allow"}


class MemoryDeleteEntityResponse(BaseModel):
    """Response for DELETE /memory/entities/{entity_id} — JSONResponse shape from helper."""

    model_config = {"extra": "allow"}


class MemoryRelatedEntitiesResponse(BaseModel):
    """Response for GET /memory/entities/{entity_id}/relations — JSONResponse shape."""

    model_config = {"extra": "allow"}


class MemoryDeleteRelationResponse(BaseModel):
    """Response for DELETE /memory/relations — JSONResponse shape from helper."""

    model_config = {"extra": "allow"}


class MemoryEntityInvalidateResponse(BaseModel):
    """Response for PATCH /memory/entities/{entity_id}/invalidate — JSONResponse shape."""

    model_config = {"extra": "allow"}


class MemoryRelationInvalidateResponse(BaseModel):
    """Response for PATCH /memory/relations/invalidate — JSONResponse shape."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# workflow_export.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# knowledge_models.py classes (merged from knowledge_models.py — Issue #5996)
# ---------------------------------------------------------------------------

# Issue #380: Module-level frozenset for tag operations
_VALID_TAG_OPERATIONS = frozenset({"add", "remove"})

# Issue #380: Pre-compiled regex patterns for validators
# These are called on every request validation, so pre-compilation is important
_ALNUM_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")  # Mixed case: IDs, categories, cursors
_LOWERCASE_TAG_RE = re.compile(r"^[a-z0-9_-]+$")  # Lowercase: tags

# Issue #380: Module-level tuples for search mode and sort validation
_VALID_SEARCH_MODES = ("semantic", "keyword", "hybrid", "auto")
_VALID_SORT_OPTIONS = ("newest", "oldest", "longest")


# Issue #685: Access level filtering
# Create AccessLevelFilter from AccessLevel to prevent value drift
_filter_values = {member.name: member.value for member in AccessLevel}
_filter_values["ALL"] = "all"  # Add the special filter-only value
AccessLevelFilter = Enum("AccessLevelFilter", _filter_values, type=str)
AccessLevelFilter.__doc__ = """Filter enum for access levels in knowledge search.

Dynamically created from AccessLevel to ensure synchronized values.
Includes an additional ALL value for no-filter searches.
This approach prevents accidental drift between AccessLevel and AccessLevelFilter.
"""


# ===== BASIC VALIDATION MODELS =====


class FactIdValidator(BaseModel):
    """Validator for fact ID format and security"""

    fact_id: str = Field(..., min_length=1, max_length=255)

    @field_validator("fact_id")
    @classmethod
    def validate_fact_id(cls, v):
        """Validate fact_id format to prevent injection attacks"""
        # Allow UUID format or safe alphanumeric with underscores/hyphens
        if not _ALNUM_ID_RE.match(v):
            raise ValueError("Invalid fact_id format: only alphanumeric, underscore, and hyphen allowed")
        # Prevent path traversal attempts (Issue #328 - uses shared validation)
        if contains_path_traversal(v):
            raise ValueError("Path traversal not allowed in fact_id")
        return v


class SearchRequest(BaseModel):
    """Canonical request model for knowledge-base vector/document search (#78, #685, #555, #10654, #10666).

    Consolidates the former SearchRequest, SearchRequest, SearchRequest,
    and SearchRequest into one model.  All added fields carry defaults so existing
    callers that only set query/limit/category remain fully backward-compatible.

    ``limit`` accepts the legacy ``top_k`` wire name via ``validation_alias`` so JSON
    payloads that send ``{"top_k": 10}`` continue to parse without change.
    """

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    limit: int = Field(
        default=QueryDefaults.DEFAULT_SEARCH_LIMIT,
        ge=1,
        le=100,
        validation_alias=AliasChoices("limit", "top_k"),
        description="Max results to return (also accepts legacy 'top_k' wire name)",
    )
    offset: int = Field(default=QueryDefaults.DEFAULT_OFFSET, ge=0, description="Pagination offset")
    category: str | None = Field(default=None, max_length=100)
    tags: List[str] | None = Field(
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
        description=(
            "Search mode: 'semantic' (vector only), 'keyword' (text only), "
            "'hybrid' (both, default), 'auto' (intelligent selection)"
        ),
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
    # Issue #685: Access level filtering
    access_level: str = Field(
        default=AccessLevelFilter.ALL.value,
        description="Filter by access level: all, autobot, general, system, user",
    )
    # Board scoping (Issue #3242)
    board_id: str | None = Field(
        default=None,
        max_length=100,
        description="Project-scoped board ID for namespaced search. None / '__global__' searches all boards.",
    )
    # RAG enhancement options (from former SearchRequest)
    enable_rag: bool = Field(
        default=False,
        description="Enable RAG enhancement for synthesized responses",
    )
    reformulate_query: bool = Field(
        default=False,
        description="Use RAG agent to expand/reformulate query for better coverage",
    )
    return_context: bool = Field(
        default=False,
        description="Return optimized context for RAG (useful for chat integration)",
    )
    # Advanced date/term filters (from former SearchRequest)
    created_after: str | None = Field(
        default=None,
        description="Filter facts created after this date (ISO format: YYYY-MM-DD)",
    )
    created_before: str | None = Field(
        default=None,
        description="Filter facts created before this date (ISO format: YYYY-MM-DD)",
    )
    exclude_terms: List[str] | None = Field(
        default=None,
        max_items=20,
        description="Exclude results containing these terms",
    )
    require_terms: List[str] | None = Field(
        default=None,
        max_items=20,
        description="Only include results containing ALL of these terms",
    )
    # Documentation / relation expansion (from former SearchRequest / SearchRequest)
    include_documentation: bool = Field(
        default=False,
        description="Also search project documentation",
    )
    include_relations: bool = Field(
        default=False,
        description="Include related facts in results",
    )
    # Multi-source search (from former SearchRequest)
    doc_results: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Max documentation results (aggregated multi-source search)",
    )
    expand_relations: bool = Field(
        default=True,
        description="Include related facts via graph (aggregated multi-source search)",
    )
    include_sources: List[str] = Field(
        default=["facts", "relations", "documentation"],
        description="Which sources to search: facts, relations, documentation",
    )
    # Analytics (from former SearchRequest)
    track_analytics: bool = Field(
        default=True,
        description="Track this search for analytics (default: true)",
    )
    session_id: str | None = Field(
        default=None,
        max_length=100,
        description="Session ID for analytics correlation",
    )
    # Advanced search options (folded from former advanced endpoint — #10666)
    enable_query_expansion: bool = Field(
        default=False,
        description="Expand query with synonyms/related terms before searching",
    )
    enable_relevance_scoring: bool = Field(
        default=False,
        description="Apply additional relevance scoring on top of vector similarity",
    )
    enable_clustering: bool = Field(
        default=False,
        description="Cluster results by topic before returning",
    )
    exclude_sources: List[str] | None = Field(
        default=None,
        max_items=20,
        description="Exclude results from these source identifiers",
    )
    verified_only: bool = Field(
        default=False,
        description="Return only facts that have been verified/approved",
    )

    model_config = {"populate_by_name": True}

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        """Validate category format."""
        if v and not _ALNUM_ID_RE.match(v):
            raise ValueError("Invalid category format")
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tag_item(cls, v):
        """Validate each tag."""
        if v is None:
            return v
        result = []
        for item in v:
            if item:
                item = item.lower().strip()
                if not _LOWERCASE_TAG_RE.match(item):
                    raise ValueError(f"Invalid tag format: {item}")
            result.append(item)
        return result

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v):
        """Validate search mode."""
        if v not in _VALID_SEARCH_MODES:  # Issue #380: use module constant
            raise ValueError(f"Invalid mode: {v}. Must be one of {_VALID_SEARCH_MODES}")
        return v

    @field_validator("created_after", "created_before")
    @classmethod
    def validate_date(cls, v):
        """Validate date format."""
        if v:
            try:
                datetime.strptime(v, "%Y-%m-%d")
            except ValueError:
                raise ValueError(f"Invalid date format: {v}. Use YYYY-MM-DD")
        return v

    # === Issue #372: Feature Envy Reduction Methods ===

    def to_search_params(self) -> dict:
        """Convert to parameters dict for knowledge base enhanced_search (Issue #372)."""
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
            "board_id": self.board_id,
        }

    def to_legacy_params(self) -> dict:
        """Convert to parameters compatible with existing KB search methods."""
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
            "board_id": self.board_id,
        }

    def to_advanced_params(self) -> dict:
        """Convert to parameters dict for knowledge base advanced search (#10666)."""
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
            "enable_query_expansion": self.enable_query_expansion,
            "enable_relevance_scoring": self.enable_relevance_scoring,
            "enable_clustering": self.enable_clustering,
            "track_analytics": self.track_analytics,
            "created_after": self.created_after,
            "created_before": self.created_before,
            "exclude_terms": self.exclude_terms,
            "require_terms": self.require_terms,
            "exclude_sources": self.exclude_sources,
            "verified_only": self.verified_only,
            "session_id": self.session_id,
        }

    def uses_advanced_features(self) -> bool:
        """Return True when any advanced-only field is set (#10666)."""
        return bool(
            self.enable_query_expansion
            or self.enable_relevance_scoring
            or self.enable_clustering
            or self.exclude_sources
            or self.verified_only
            or self.created_after
            or self.created_before
            or self.exclude_terms
            or self.require_terms
            or self.session_id
        )

    def get_log_summary(self) -> str:
        """Get formatted log summary string (Issue #372 - reduces feature envy)."""
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
            f"'{self.query}' (limit={self.limit}, offset={self.offset}, "
            f"mode={self.mode}, tags={self.tags}, min_score={self.min_score}{feature_str})"
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


class PaginationRequest(BaseModel):
    """Request model for pagination"""

    limit: int = Field(default=QueryDefaults.KNOWLEDGE_DEFAULT_LIMIT, ge=1, le=1000)
    offset: int = Field(default=QueryDefaults.DEFAULT_OFFSET, ge=0)
    cursor: str | None = Field(default=None, max_length=255)
    category: str | None = Field(default=None, max_length=100)

    @field_validator("cursor")
    @classmethod
    def validate_cursor(cls, v):
        """Validate cursor format"""
        if v and not _ALNUM_ID_RE.match(v):
            raise ValueError("Invalid cursor format")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        """Validate category format"""
        if v and not _ALNUM_ID_RE.match(v):
            raise ValueError("Invalid category format")
        return v


class AddTextRequest(BaseModel):
    """Request model for adding text to knowledge base (Issue #688: enhanced, #685: access levels)."""

    text: str = Field(..., min_length=1, max_length=1000000)
    metadata: Metadata | None = Field(default=None)
    category: str | None = Field(default=CategoryDefaults.GENERAL, max_length=100)
    # Issue #688: Ownership fields
    owner_id: str | None = Field(default=None, max_length=100)
    visibility: str = Field(
        default="private",
        description="Visibility level: private, shared, group, organization, system, public",
    )
    source_type: str = Field(
        default="manual",
        description="Source type: chat, manual, import, system",
    )
    shared_with: List[str] | None = Field(
        default=None,
        max_items=50,
        description="List of user IDs to share with",
    )
    # Issue #685: Hierarchical access fields
    access_level: str = Field(
        default="user",
        description="Access level: autobot, general, system, user",
    )
    organization_id: str | None = Field(
        default=None,
        max_length=100,
        description="Organization ID for org-level knowledge",
    )
    group_ids: List[str] | None = Field(
        default=None,
        max_items=20,
        description="List of group/team IDs for group-level knowledge",
    )

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v):
        """Validate metadata structure"""
        if v is not None and not isinstance(v, dict):
            raise ValueError("Metadata must be a dictionary")
        return v

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v):
        """Validate visibility level (Issue #685: expanded)."""
        valid_levels = {
            "private",
            "shared",
            "group",
            "organization",
            "system",
            "public",
        }
        if v not in valid_levels:
            raise ValueError(f"Invalid visibility: {v}. Must be one of: {valid_levels}")
        return v

    @field_validator("access_level")
    @classmethod
    def validate_access_level(cls, v):
        """Validate access level (Issue #685)."""
        valid_levels = {"autobot", "general", "system", "user"}
        if v not in valid_levels:
            raise ValueError(f"Invalid access_level: {v}. Must be one of: {valid_levels}")
        return v

    @field_validator("source_type")
    @classmethod
    def validate_source_type(cls, v):
        """Validate source type."""
        valid_types = {"chat", "manual", "import", "system"}
        if v not in valid_types:
            raise ValueError(f"Invalid source_type: {v}. Must be one of: {valid_types}")
        return v


class ScanHostChangesRequest(BaseModel):
    """Request model for scanning host document changes"""

    machine_id: str = Field(..., min_length=1, max_length=100)
    force: bool = Field(default=False)
    scan_type: str = Field(default="manpages", max_length=50)
    auto_vectorize: bool = Field(default=False, description="Automatically vectorize detected changes")


class AdvancedSearchRequest(BaseModel):
    """Request model for advanced RAG search with reranking"""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    max_results: int = Field(
        default=QueryDefaults.RAG_DEFAULT_RESULTS,
        ge=1,
        le=50,
        description="Maximum results to return",
    )
    enable_reranking: bool = Field(default=True, description="Enable cross-encoder reranking")
    return_context: bool = Field(default=False, description="Return optimized context for RAG")
    timeout: float | None = Field(default=None, description="Optional timeout in seconds")


class RerankRequest(BaseModel):
    """Request model for reranking existing search results"""

    query: str = Field(..., min_length=1, max_length=1000, description="Original search query")
    results: List[Metadata] = Field(..., description="Search results to rerank")


# ===== TAG MANAGEMENT MODELS (Issue #77) =====


class TagValidator(BaseModel):
    """Validator for tag format and security"""

    tag: str = Field(..., min_length=1, max_length=50)

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, v):
        """Validate tag format - lowercase alphanumeric with hyphens/underscores"""
        # Normalize to lowercase
        v = v.lower().strip()
        # Allow alphanumeric, hyphens, underscores
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError("Invalid tag format: only lowercase alphanumeric, underscore, " "and hyphen allowed")
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

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tag_item(cls, v):
        """Validate each tag in the list"""
        result = []
        for item in v:
            item = item.lower().strip()
            if not _LOWERCASE_TAG_RE.match(item):
                raise ValueError(f"Invalid tag format: {item}")
            if len(item) > 50:
                raise ValueError(f"Tag too long: {item}")
            result.append(item)
        return result


class RemoveTagsRequest(BaseModel):
    """Request model for removing tags from a fact"""

    tags: List[str] = Field(
        ...,
        min_items=1,
        max_items=20,
        description="List of tags to remove",
    )

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tag_item(cls, v):
        """Validate each tag in the list"""
        result = []
        for item in v:
            item = item.lower().strip()
            if not _LOWERCASE_TAG_RE.match(item):
                raise ValueError(f"Invalid tag format: {item}")
            result.append(item)
        return result


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

    @field_validator("fact_ids", mode="before")
    @classmethod
    def validate_fact_id_item(cls, v):
        """Validate each fact ID format (Critical fix #5)"""
        result = []
        for item in v:
            if not _ALNUM_ID_RE.match(item):
                raise ValueError(
                    f"Invalid fact_id format: {item} - only alphanumeric, " "underscore, and hyphen allowed"
                )
            # Prevent path traversal attempts (Issue #328 - uses shared validation)
            if contains_path_traversal(item):
                raise ValueError(f"Path traversal not allowed in fact_id: {item}")
            result.append(item)
        return result

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, v):
        """Validate operation type"""
        if v not in _VALID_TAG_OPERATIONS:
            raise ValueError("Operation must be 'add' or 'remove'")
        return v

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tag_item(cls, v):
        """Validate each tag"""
        result = []
        for item in v:
            item = item.lower().strip()
            if not _LOWERCASE_TAG_RE.match(item):
                raise ValueError(f"Invalid tag format: {item}")
            result.append(item)
        return result


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
    category: str | None = Field(default=None, max_length=100)

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tag_item(cls, v):
        """Validate each tag"""
        result = []
        for item in v:
            item = item.lower().strip()
            if not _LOWERCASE_TAG_RE.match(item):
                raise ValueError(f"Invalid tag format: {item}")
            result.append(item)
        return result


# ===== TAG MANAGEMENT CRUD MODELS (Issue #409) =====


class RenameTagRequest(BaseModel):
    """Request model for renaming a tag globally."""

    new_tag: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="New name for the tag",
    )

    @field_validator("new_tag")
    @classmethod
    def validate_new_tag(cls, v):
        """Validate new tag format."""
        v = v.lower().strip()
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError("Invalid tag format: only lowercase alphanumeric, underscore, " "and hyphen allowed")
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

    @field_validator("source_tags", mode="before")
    @classmethod
    def validate_source_tag_item(cls, v):
        """Validate each source tag."""
        result = []
        for item in v:
            item = item.lower().strip()
            if not _LOWERCASE_TAG_RE.match(item):
                raise ValueError(f"Invalid tag format: {item}")
            result.append(item)
        return result

    @field_validator("target_tag")
    @classmethod
    def validate_target_tag(cls, v):
        """Validate target tag format."""
        v = v.lower().strip()
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError("Invalid tag format: only lowercase alphanumeric, underscore, " "and hyphen allowed")
        if contains_path_traversal(v):
            raise ValueError("Invalid characters in tag")
        return v


class GetFactsByTagRequest(BaseModel):
    """Request model for getting facts by tag with pagination."""

    limit: int = Field(
        default=QueryDefaults.DEFAULT_PAGE_SIZE,
        ge=1,
        le=500,
        description="Max facts to return",
    )
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

    color: str | None = Field(
        default=None,
        min_length=7,
        max_length=7,
        description="Hex color code (e.g., '#3B82F6')",
    )
    icon: str | None = Field(
        default=None,
        max_length=50,
        description="Optional icon class (e.g., 'fas fa-code')",
    )
    description: str | None = Field(
        default=None,
        max_length=200,
        description="Optional tag description",
    )

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        """Validate hex color format."""
        if v is not None:
            if not _HEX_COLOR_RE.match(v):
                raise ValueError(f"Invalid color format: {v}. Use hex format like '#3B82F6'")
        return v

    @field_validator("icon")
    @classmethod
    def validate_icon(cls, v):
        """Validate icon class format (basic sanitization)."""
        if v is not None:
            # Only allow alphanumeric, hyphens, and spaces (for icon classes)
            if not re.match(r"^[a-zA-Z0-9\s\-]+$", v):
                raise ValueError("Invalid icon format: only alphanumeric, spaces, hyphens")
        return v


# ===== CATEGORY MANAGEMENT MODELS (Issue #411) =====

# Issue #411: Pre-compiled regex for category name validation
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
    parent_id: str | None = Field(
        default=None,
        description="Parent category ID (None = root category)",
    )
    description: str | None = Field(
        default=None,
        max_length=200,
        description="Category description",
    )
    icon: str | None = Field(
        default=None,
        max_length=50,
        description="Icon identifier (e.g., 'fas fa-code')",
    )
    color: str | None = Field(
        default=None,
        min_length=7,
        max_length=7,
        description="Hex color code (e.g., '#3B82F6')",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Validate category name format."""
        v = v.lower().strip().replace(" ", "-")
        if not _LOWERCASE_TAG_RE.match(v):
            raise ValueError("Invalid category name: only lowercase alphanumeric, " "hyphens, underscores allowed")
        if contains_path_traversal(v):
            raise ValueError("Invalid characters in category name")
        return v

    @field_validator("parent_id")
    @classmethod
    def validate_parent_id(cls, v):
        """Validate parent_id format."""
        if v is not None:
            if not _ALNUM_ID_RE.match(v):
                raise ValueError("Invalid parent_id format")
            if contains_path_traversal(v):
                raise ValueError("Invalid characters in parent_id")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        """Validate hex color format."""
        if v is not None:
            if not _HEX_COLOR_RE.match(v):
                raise ValueError(f"Invalid color format: {v}. Use hex format like '#3B82F6'")
        return v


class UpdateCategoryRequest(BaseModel):
    """
    Request model for updating a category (Issue #411).

    All fields are optional; only provided fields are updated.
    Note: Renaming a category updates its path and all descendant paths.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=50,
        description="New category name (triggers path update)",
    )
    description: str | None = Field(
        default=None,
        max_length=200,
        description="New description",
    )
    icon: str | None = Field(
        default=None,
        max_length=50,
        description="New icon identifier",
    )
    color: str | None = Field(
        default=None,
        min_length=7,
        max_length=7,
        description="New hex color code",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Validate category name format if provided."""
        if v is not None:
            v = v.lower().strip().replace(" ", "-")
            if not _LOWERCASE_TAG_RE.match(v):
                raise ValueError("Invalid category name: only lowercase alphanumeric, " "hyphens, underscores allowed")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        """Validate hex color format if provided."""
        if v is not None:
            if not _HEX_COLOR_RE.match(v):
                raise ValueError(f"Invalid color format: {v}. Use hex format like '#3B82F6'")
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
    reassign_to: str | None = Field(
        default=None,
        description="Category ID to reassign facts to. If None, facts become uncategorized.",
    )

    @field_validator("reassign_to")
    @classmethod
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

    @field_validator("category_id")
    @classmethod
    def validate_category_id(cls, v):
        """Validate category_id format."""
        if not _ALNUM_ID_RE.match(v):
            raise ValueError("Invalid category_id format")
        if contains_path_traversal(v):
            raise ValueError("Invalid characters in category_id")
        return v


# ---------------------------------------------------------------------------
# chat_knowledge.py response schemas (#6509c)
# ---------------------------------------------------------------------------


class ChatKnowledgeContextData(BaseModel):
    """data payload for create_chat_context / get_chat_context."""

    model_config = {"extra": "allow"}

    success: bool


class ChatKnowledgeFileAssocData(BaseModel):
    """data payload for associate_file_with_chat."""

    model_config = {"extra": "allow"}

    success: bool


class ChatKnowledgeUploadData(BaseModel):
    """data payload for upload_file_to_chat."""

    model_config = {"extra": "allow"}

    success: bool


class ChatKnowledgeTempData(BaseModel):
    """data payload for add_temporary_knowledge."""

    model_config = {"extra": "allow"}

    success: bool


class ChatKnowledgePendingData(BaseModel):
    """data payload for get_pending_knowledge_decisions."""

    model_config = {"extra": "allow"}

    success: bool


class ChatKnowledgeDecisionData(BaseModel):
    """data payload for apply_knowledge_decision."""

    model_config = {"extra": "allow"}

    success: bool


class ChatKnowledgeCompileData(BaseModel):
    """data payload for compile_chat_to_knowledge."""

    model_config = {"extra": "allow"}

    success: bool


class ChatKnowledgeSearchResultData(BaseModel):
    """data payload for search_chat_knowledge."""

    model_config = {"extra": "allow"}

    success: bool


# ---------------------------------------------------------------------------
# knowledge_ai_stack.py response schemas (#6509c)
# ---------------------------------------------------------------------------


class AIStackSearchData(BaseModel):
    """data payload for POST /search/advanced."""

    model_config = {"extra": "allow"}


class AIStackRagSearchData(BaseModel):
    """data payload for POST /search/rag."""

    model_config = {"extra": "allow"}


class AIStackKnowledgeExtractData(BaseModel):
    """data payload for POST /knowledge/extract."""

    model_config = {"extra": "allow"}


class AIStackDocumentAnalysisData(BaseModel):
    """data payload for POST /documents/analyze."""

    model_config = {"extra": "allow"}


class AIStackQueryReformulateData(BaseModel):
    """data payload for POST /search/reformulate."""

    model_config = {"extra": "allow"}


class AIStackSystemInsightsData(BaseModel):
    """data payload for GET /knowledge/system-insights."""

    model_config = {"extra": "allow"}


class AIStackStatsData(BaseModel):
    """data payload for GET /stats/advanced."""

    model_config = {"extra": "allow"}


class AIStackHealthStatusData(BaseModel):
    """data payload for GET /health/status."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# memory.py bare DataResponse response schemas (#6509c)
# ---------------------------------------------------------------------------


class MemoryEntityData(BaseModel):
    """data payload for create_entity / get_entity_by_name / add_observations."""

    model_config = {"extra": "allow"}


class MemoryRelationData(BaseModel):
    """data payload for create_relation."""

    model_config = {"extra": "allow"}


class MemoryEntityGraphData(BaseModel):
    """data payload for get_entity_graph."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# embeddings.py response schemas (#6509c)
# ---------------------------------------------------------------------------


class EmbeddingSettingsData(BaseModel):
    """data payload for GET /settings."""

    model_config = {"extra": "allow"}


class EmbeddingUpdateData(BaseModel):
    """data payload for PUT /settings."""

    model_config = {"extra": "allow"}


class EmbeddingModelsData(BaseModel):
    """data payload for GET /models."""

    model_config = {"extra": "allow"}


class EmbeddingRefreshData(BaseModel):
    """data payload for POST /providers/{provider_name}/refresh-models."""

    model_config = {"extra": "allow"}


class EmbeddingStatusData(BaseModel):
    """data payload for GET /status."""

    model_config = {"extra": "allow"}


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

    @field_validator("path_pattern")
    @classmethod
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
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Collection description",
    )
    icon: str | None = Field(
        default=None,
        max_length=50,
        description="Icon identifier (e.g., 'fas fa-folder')",
    )
    color: str | None = Field(
        default=None,
        min_length=7,
        max_length=7,
        description="Hex color code (e.g., '#3B82F6')",
    )
    metadata: dict | None = Field(
        default=None,
        description="Custom metadata for the collection",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Validate collection name."""
        v = v.strip()
        if not v:
            raise ValueError("Collection name cannot be empty")
        if contains_path_traversal(v):
            raise ValueError("Invalid characters in collection name")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        """Validate hex color format."""
        if v is not None:
            if not _HEX_COLOR_RE.match(v):
                raise ValueError(f"Invalid color format: {v}. Use hex format like '#3B82F6'")
        return v


class UpdateCollectionRequest(BaseModel):
    """
    Request model for updating a collection (Issue #412).

    All fields are optional; only provided fields are updated.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="New collection name",
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="New description",
    )
    icon: str | None = Field(
        default=None,
        max_length=50,
        description="New icon identifier",
    )
    color: str | None = Field(
        default=None,
        min_length=7,
        max_length=7,
        description="New hex color code",
    )
    metadata: dict | None = Field(
        default=None,
        description="New custom metadata (replaces existing)",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Validate collection name if provided."""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Collection name cannot be empty")
        return v

    @field_validator("color")
    @classmethod
    def validate_color(cls, v):
        """Validate hex color format if provided."""
        if v is not None:
            if not _HEX_COLOR_RE.match(v):
                raise ValueError(f"Invalid color format: {v}. Use hex format like '#3B82F6'")
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

    @field_validator("fact_ids", mode="before")
    @classmethod
    def validate_fact_id(cls, v):
        """Validate fact ID format."""
        result = []
        for item in v:
            if not _ALNUM_ID_RE.match(item):
                raise ValueError(f"Invalid fact_id format: {item}")
            if contains_path_traversal(item):
                raise ValueError(f"Invalid characters in fact_id: {item}")
            result.append(item)
        return result


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


# ===== CONTEXT SUGGESTION MODELS (Issue #3284) =====


class ContextSuggestionsRequest(BaseModel):
    """
    Request model for context-based KB document suggestions (Issue #3284).

    Returns ranked KB documents relevant to the current conversation context,
    scored by semantic similarity to the context and boosted by recency.
    Each suggestion includes a short preview snippet.
    """

    context: str = Field(
        ...,
        min_length=10,
        max_length=10000,
        description="Current conversation context or query to find relevant KB documents for",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of document suggestions to return",
    )
    recency_weight: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description=("Weight of recency boost relative to relevance score (0=purely semantic, " "1=purely recency)"),
    )
    min_score: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="Minimum combined score threshold for a suggestion to be included",
    )
    snippet_length: int = Field(
        default=200,
        ge=50,
        le=500,
        description="Maximum character length of the preview snippet",
    )


class ContextSuggestionItem(BaseModel):
    """
    A single context-based KB document suggestion (Issue #3284).

    Returned as part of the ContextSuggestionsResponse.
    """

    fact_id: str = Field(description="Unique identifier of the KB fact")
    title: str = Field(description="Title or first-line of the document")
    snippet: str = Field(description="Short preview snippet of the document content")
    relevance_score: float = Field(description="Semantic similarity score (0.0-1.0)")
    recency_score: float = Field(description="Recency score derived from timestamp (0.0-1.0)")
    combined_score: float = Field(description="Weighted combination of relevance and recency")
    tags: list[str] = Field(default_factory=list, description="Tags associated with the document")
    category: str = Field(default="", description="Category path of the document")
    created_at: str = Field(default="", description="ISO-8601 timestamp when the fact was created")


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
    default: str | None = Field(
        default=None,
        description="Default value if not provided",
    )
    validation: str | None = Field(
        default=None,
        max_length=200,
        description="Optional regex validation pattern",
    )
    description: str | None = Field(
        default=None,
        max_length=200,
        description="Field description for UI",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        """Validate field name format."""
        v = v.strip()
        if not re.match(r"^[a-zA-Z][a-zA-Z0-9_]*$", v):
            raise ValueError("Field name must start with letter, contain only alphanumeric/underscore")
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        """Validate field type."""
        if v not in VALID_FIELD_TYPES:
            raise ValueError(f"Invalid type: {v}. Must be one of: {VALID_FIELD_TYPES}")
        return v

    @field_validator("validation")
    @classmethod
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
    description: str | None = Field(
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
    applicable_categories: List[str] | None = Field(
        default=None,
        max_items=20,
        description="Categories this template applies to",
    )

    @field_validator("name")
    @classmethod
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

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="New template name",
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="New description",
    )
    fields: List[MetadataFieldDefinition] | None = Field(
        default=None,
        max_items=20,
        description="New field definitions (replaces all existing)",
    )
    applicable_categories: List[str] | None = Field(
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
    category: str | None = Field(
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

    @field_validator("operator")
    @classmethod
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
    created_by: str | None = Field(
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

    categories: List[str] | None = Field(default=None, max_items=20)
    tags: List[str] | None = Field(default=None, max_items=20)
    date_from: str | None = Field(
        default=None,
        description="ISO date string (YYYY-MM-DD)",
    )
    date_to: str | None = Field(
        default=None,
        description="ISO date string (YYYY-MM-DD)",
    )
    fact_ids: List[str] | None = Field(default=None, max_items=1000)

    @field_validator("date_from", "date_to")
    @classmethod
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
    filters: ExportFilters | None = Field(default=None)
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
    category: str | None = Field(
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

    @field_validator("keep_strategy")
    @classmethod
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

    @field_validator("fact_ids", mode="before")
    @classmethod
    def validate_fact_id(cls, v):
        """Validate fact ID format"""
        result = []
        for item in v:
            if not _ALNUM_ID_RE.match(item):
                raise ValueError(f"Invalid fact_id format: {item}")
            # Prevent path traversal (Issue #328 - uses shared validation)
            if contains_path_traversal(item):
                raise ValueError(f"Path traversal not allowed in fact_id: {item}")
            result.append(item)
        return result


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

    @field_validator("fact_ids", mode="before")
    @classmethod
    def validate_fact_id(cls, v):
        """Validate fact ID format"""
        result = []
        for item in v:
            if not _ALNUM_ID_RE.match(item):
                raise ValueError(f"Invalid fact_id format: {item}")
            result.append(item)
        return result

    @field_validator("new_category")
    @classmethod
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

    @field_validator("backup_file")
    @classmethod
    def validate_backup_file(cls, v):
        """Validate backup file path (Issue #419).

        Uses contains_dotdot_traversal (not contains_path_traversal) because
        backup_file is a full filesystem path — absolute paths legitimately
        contain forward-slashes.  Only dotdot sequences and null bytes are
        genuine traversal attacks here.  (#9670)
        """
        if contains_dotdot_traversal(v):
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

    @field_validator("backup_file")
    @classmethod
    def validate_backup_file(cls, v):
        """Validate backup file path (Issue #419).

        Uses contains_dotdot_traversal (not contains_path_traversal) because
        backup_file is a full filesystem path — absolute paths legitimately
        contain forward-slashes.  Only dotdot sequences and null bytes are
        genuine traversal attacks here.  (#9670)
        """
        if contains_dotdot_traversal(v):
            raise ValueError("Path traversal not allowed in backup_file")
        return v


class UpdateFactRequest(BaseModel):
    """Request model for updating a fact"""

    content: str | None = Field(
        default=None,
        min_length=1,
        max_length=1000000,
        description="New content for the fact",
    )
    category: str | None = Field(default=None, max_length=100, description="New category")
    metadata: Metadata | None = Field(default=None, description="New or updated metadata")

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        """Validate category format"""
        if v and not _ALNUM_ID_RE.match(v):
            raise ValueError(f"Invalid category format: {v}")
        return v


# ===== OWNERSHIP AND SHARING MODELS (Issue #688) =====


class ShareFactRequest(BaseModel):
    """Request model for sharing a fact with users (Issue #688)."""

    user_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=50,
        description="List of user IDs to share with",
    )

    @field_validator("user_ids", mode="before")
    @classmethod
    def validate_user_id(cls, v):
        """Validate user ID format."""
        result = []
        for item in v:
            if not item or len(item) > 100:
                raise ValueError("Invalid user_id: must be 1-100 characters")
            result.append(item)
        return result


class UnshareFactRequest(BaseModel):
    """Request model for removing users from fact sharing (Issue #688)."""

    user_ids: List[str] = Field(
        ...,
        min_items=1,
        max_items=50,
        description="List of user IDs to remove from sharing",
    )

    @field_validator("user_ids", mode="before")
    @classmethod
    def validate_user_id(cls, v):
        """Validate user ID format."""
        result = []
        for item in v:
            if not item or len(item) > 100:
                raise ValueError("Invalid user_id: must be 1-100 characters")
            result.append(item)
        return result


class UpdateVisibilityRequest(BaseModel):
    """Request model for changing fact visibility (Issue #688)."""

    visibility: str = Field(
        ...,
        description="Visibility level: private, shared, public",
    )

    @field_validator("visibility")
    @classmethod
    def validate_visibility(cls, v):
        """Validate visibility level."""
        valid_levels = {"private", "shared", "public"}
        if v not in valid_levels:
            raise ValueError(f"Invalid visibility: {v}. Must be one of: {valid_levels}")
        return v


class GetUserFactsRequest(BaseModel):
    """Request model for getting user's facts with pagination (Issue #688)."""

    limit: int = Field(
        default=QueryDefaults.DEFAULT_PAGE_SIZE,
        ge=1,
        le=500,
        description="Maximum number of facts to return",
    )
    offset: int = Field(
        default=QueryDefaults.DEFAULT_OFFSET,
        ge=0,
        description="Pagination offset",
    )
    include_shared: bool = Field(
        default=False,
        description="Include facts shared with user in addition to owned facts",
    )


# ===== SOURCE PROVENANCE MODELS (Issue #1252) =====


class ProvenanceMetadata(BaseModel):
    """Provenance metadata for knowledge facts and documents (Issue #1252).

    Tracks origin and verification status for every piece of knowledge stored.
    """

    source_type: str = Field(
        default="manual_upload",
        description="Origin type: manual_upload|url_fetch|web_research|connector",
    )
    source_connector_id: str | None = Field(
        default=None,
        description="Connector ID when source_type='connector'",
    )
    verification_status: str = Field(
        default="unverified",
        description="Verification state: unverified|pending_review|verified|rejected",
    )
    verification_method: str | None = Field(
        default=None,
        description="How it was verified: auto_quality|user_approved|connector_trusted",
    )
    verified_by: str | None = Field(
        default=None,
        description="User or system that performed verification",
    )
    verified_at: str | None = Field(
        default=None,
        description="ISO-8601 timestamp of verification",
    )
    quality_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Automated quality score (0.0 - 1.0)",
    )
    provenance_chain: List[str] = Field(
        default_factory=list,
        description="Ordered list of source IDs/URLs representing derivation chain",
    )


class VerificationConfig(BaseModel):
    """Configuration for the librarian verification mode (Issue #1252)."""

    mode: str = Field(
        default="autonomous",
        description="Verification mode: autonomous|collaborative",
    )
    quality_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Minimum quality score for autonomous storage",
    )


class VerificationRequest(BaseModel):
    """Request body for approving or rejecting a fact (Issue #1252)."""

    user: str = Field(
        default="system",
        min_length=1,
        max_length=255,
        description="Username performing the verification action",
    )
    delete_on_reject: bool = Field(
        default=False,
        description="When rejecting: also delete the fact from the knowledge base",
    )


class PendingSourceResponse(BaseModel):
    """Single pending-review fact in the verification queue (Issue #1252)."""

    fact_id: str
    content: str
    source_type: str
    quality_score: float
    timestamp: str
    domain: str | None = None
    title: str | None = None
    url: str | None = None


# ---------------------------------------------------------------------------
# chat_knowledge.py schemas (#5984)
# ---------------------------------------------------------------------------


class ChatKnowledgeHealthResponse(BaseModel):
    """Health check response for the chat knowledge service."""

    status: str
    service: str
    manager_initialized: bool
    timestamp: str


class SessionFactItem(BaseModel):
    """Single fact returned in a session-facts listing."""

    id: str | None = None
    content: str
    full_content: str
    category: str
    tags: List[str]
    important: bool
    preserve: bool
    created_at: str | None = None


class SessionFactsResponse(BaseModel):
    """Response for GET /chat/sessions/{session_id}/facts."""

    status: str
    session_id: str
    fact_count: int
    facts: List[SessionFactItem]


class PreserveSessionFactsResponse(BaseModel):
    """Response for POST /chat/sessions/{session_id}/facts/preserve."""

    status: str
    session_id: str
    updated_count: int
    failed_count: int
    errors: List[str] | None = None

    # ---------------------------------------------------------------------------
    # code_search.py schemas (#5984)
    # ---------------------------------------------------------------------------

    # #6799: removed duplicate CodeSearchGetResponse (was here AND in
    # schemas_code.py with identical shape). The canonical definition lives in
    # schemas_code.py:1179. Only api/code_search.py imported this name and it
    # already pulls from schemas_code.

    success: bool = True


# ---------------------------------------------------------------------------
# documents.py schemas (#5984)
# ---------------------------------------------------------------------------


class AIDocumentResponse(BaseModel):
    """Single AI document (mirrors AIDocument.model_dump() fields)."""

    id: str
    title: str
    content: str
    source_facts: List[str]
    source_session_id: str | None = None
    source_message_id: str | None = None
    user_id: str
    tags: List[str]
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str


class AIDocumentListResponse(BaseModel):
    """Response for GET /documents."""

    documents: List[AIDocumentResponse]
    total: int


# ---------------------------------------------------------------------------
# enhanced_search.py schemas (#5984)
# ---------------------------------------------------------------------------


class SearchHardwareStatusResponse(BaseModel):
    """Response for GET /hardware/status.

    hardware_status, cache_stats, and configuration are service-delegated dicts.
    """

    model_config = {"extra": "allow"}

    hardware_status: Dict[str, Any]
    knowledge_base_ready: bool
    cache_stats: Dict[str, Any]
    configuration: Dict[str, Any]
    timestamp: float


class SearchBenchmarkResponse(BaseModel):
    """Response for POST /benchmark.

    benchmark_results shape is service-delegated.
    """

    model_config = {"extra": "allow"}

    benchmark_results: Dict[str, Any]
    timestamp: float
    recommendations: List[str]


class SearchOptimizeResponse(BaseModel):
    """Response for POST /optimize."""

    model_config = {"extra": "allow"}

    optimization_applied: str
    configuration: Dict[str, Any]
    timestamp: float


class SearchPerformanceAnalyticsResponse(BaseModel):
    """Response for GET /performance/analytics.

    search_statistics, hardware_status, and performance_analysis are
    service-delegated dicts.
    """

    model_config = {"extra": "allow"}

    search_statistics: Dict[str, Any]
    hardware_status: Dict[str, Any]
    performance_analysis: Dict[str, Any]
    recommendations: List[str]
    timestamp: float


class SearchConnectivityResponse(BaseModel):
    """Response for GET /test/connectivity."""

    connectivity: str
    timestamp: float
    npu_worker_url: str | None = None
    test_search_results: int | None = None
    test_device_used: str | None = None
    test_time_ms: float | None = None
    error: str | None = None
    fallback_available: bool | None = None


class SearchHealthResponse(BaseModel):
    """Response for GET /health (enhanced search service)."""

    status: str
    service: str
    timestamp: float
    npu_search_engine_ready: bool | None = None
    knowledge_base_ready: bool | None = None
    cache_size: int | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# kb_librarian.py schemas (#5984)
# ---------------------------------------------------------------------------


class KbLibrarianStatusResponse(BaseModel):
    """Response for GET /status."""

    enabled: bool
    similarity_threshold: float
    max_results: int
    auto_summarize: bool
    knowledge_base_active: bool


class KbLibrarianConfigureResponse(BaseModel):
    """Response for PUT /configure."""

    message: str
    enabled: bool
    similarity_threshold: float
    max_results: int
    auto_summarize: bool


# ---------------------------------------------------------------------------
# knowledge_graph_routes.py schemas (#5984)
# ---------------------------------------------------------------------------


class KnowledgeGraphEntitiesResponse(BaseModel):
    """Response for GET /entities."""

    entities: List[Dict[str, Any]]
    total: int


class KnowledgeGraphEntityRelationshipsResponse(BaseModel):
    """Response for GET /entities/{entity_id}/relationships."""

    entity_id: str
    relationships: List[Dict[str, Any]]
    total: int


class KnowledgeGraphEventsResponse(BaseModel):
    """Response for GET /events."""

    events: List[Dict[str, Any]]
    total: int


class KnowledgeGraphEventTimelineResponse(BaseModel):
    """Response for GET /events/{entity_name}/timeline."""

    entity_name: str
    events: List[Dict[str, Any]]
    total: int


class KnowledgeGraphSummariesResponse(BaseModel):
    """Response for GET /summaries/search."""

    summaries: List[Dict[str, Any]]
    total: int


class KnowledgeGraphDocumentOverviewResponse(BaseModel):
    """Response for GET /documents/{document_id}/overview.

    Shape is service-delegated (SummarySearchService.get_document_overview).
    """

    model_config = {"extra": "allow"}


class KnowledgeGraphDrillDownResponse(BaseModel):
    """Response for GET /summaries/{summary_id}/drill-down.

    Shape is service-delegated (SummarySearchService.drill_down).
    """

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# natural_language_search.py schemas (#5984)
# ---------------------------------------------------------------------------


class NLSuggestionItem(BaseModel):
    """Single query suggestion."""

    suggestion: str
    reason: str
    intent: str
    relevance_score: float


class NLQuerySuggestionsResponse(BaseModel):
    """Response for GET /suggestions."""

    original_query: str
    parsed_intent: str
    suggestions: List[NLSuggestionItem]


class NLCodeExplanationResponse(BaseModel):
    """Response for POST /explain."""

    code_snippet: str
    file_path: str
    line_number: int
    summary: str
    detailed_explanation: str
    purpose: str
    key_concepts: List[str]
    related_code: List[str]


class NLIntentItem(BaseModel):
    """Single supported query intent entry."""

    intent: str
    description: str
    example_queries: List[str]


class NLIntentsResponse(BaseModel):
    """Response for GET /intents."""

    intents: List[NLIntentItem]


class NLDomainItem(BaseModel):
    """Single supported query domain entry."""

    domain: str
    keywords: List[str]


class NLDomainsResponse(BaseModel):
    """Response for GET /domains."""

    domains: List[NLDomainItem]


class NLSearchHealthResponse(BaseModel):
    """Response for GET /health (natural language search service)."""

    status: str
    service: str
    deprecated: bool
    use_instead: str
    features: List[str]
    llm_available: bool


# ---------------------------------------------------------------------------
# knowledge_tags schemas (#6042)
# ---------------------------------------------------------------------------


class KnowledgeTagFactTagsResponse(BaseModel):
    """Response for POST/DELETE/GET /fact/{fact_id}/tags."""

    status: str
    fact_id: str
    tags: List[Any]
    message: str | None = None
    added_count: int | None = None
    removed_count: int | None = None


class KnowledgeTagGetFactTagsResponse(BaseModel):
    """Response for GET /fact/{fact_id}/tags."""

    status: str
    fact_id: str
    tags: List[Any]


class KnowledgeTagSearchResponse(BaseModel):
    """Response for POST /tags/search."""

    status: str
    facts: List[Any]
    total_count: int
    tags_searched: List[str]
    match_all: bool
    limit: int
    offset: int


class KnowledgeTagListResponse(BaseModel):
    """Response for GET /tags."""

    status: str
    tags: List[Any]
    total_count: int


class KnowledgeTagBulkResponse(BaseModel):
    """Response for POST /tags/bulk."""

    status: str
    operation: str
    processed_count: int
    failed_count: int
    results: List[Any]


class KnowledgeTagRenameResponse(BaseModel):
    """Response for PUT /tags/{tag_name}."""

    status: str
    old_tag: str
    new_tag: str
    affected_count: int
    message: str


class KnowledgeTagDeleteResponse(BaseModel):
    """Response for DELETE /tags/{tag_name}."""

    status: str
    tag: str
    affected_count: int
    message: str


class KnowledgeTagMergeResponse(BaseModel):
    """Response for POST /tags/merge."""

    status: str
    source_tags: List[str]
    target_tag: str
    affected_count: int
    message: str


class KnowledgeTagFactsByTagResponse(BaseModel):
    """Response for GET /tags/{tag_name}/facts."""

    status: str
    tag: str
    facts: List[Any]
    total_count: int
    returned_count: int
    limit: int
    offset: int
    has_more: bool


class KnowledgeTagInfoResponse(BaseModel):
    """Response for GET /tags/{tag_name}/info."""

    status: str
    tag: str
    fact_count: int


class KnowledgeTagStyleInfo(BaseModel):
    color: str | None = None
    icon: str | None = None
    description: str | None = None
    is_default: bool


class KnowledgeTagStyleResponse(BaseModel):
    """Response for PATCH/GET /tags/{tag_name}/style."""

    status: str
    tag: str
    style: Dict[str, Any]
    message: str | None = None


class KnowledgeTagDeleteStyleResponse(BaseModel):
    """Response for DELETE /tags/{tag_name}/style."""

    status: str
    tag: str
    message: str


# ---------------------------------------------------------------------------
# conversation_files.py schemas (#6042)
# ---------------------------------------------------------------------------


class FileDestination(str, Enum):
    """File transfer destination options."""

    KNOWLEDGE_BASE = "kb"
    SHARED = "shared"


class ConversationFileInfo(BaseModel):
    """Conversation file information model."""

    file_id: str
    filename: str
    original_filename: str
    size: int
    mime_type: str | None = None
    session_id: str
    uploaded_at: datetime
    uploaded_by: str
    file_path: str
    extension: str | None = None


class ConversationFileListResponse(BaseModel):
    """Response model for listing conversation files."""

    session_id: str
    files: List[ConversationFileInfo]
    total_files: int
    total_size: int
    page: int = 1
    page_size: int = 50


class FileUploadResponse(BaseModel):
    """Response model for file upload."""

    success: bool
    message: str
    file_info: ConversationFileInfo | None = None
    upload_id: str


class FileTransferRequest(BaseModel):
    """Request model for file transfer operation."""

    file_ids: List[str] = Field(..., min_length=1, description="List of file IDs to transfer")
    destination: FileDestination = Field(..., description="Transfer destination (kb or shared)")
    target_path: str | None = Field(None, description="Target path in destination")
    copy_files: bool = Field(False, alias="copy", description="Copy instead of move")
    tags: List[str] | None = Field(None, description="Tags for KB indexing")

    @field_validator("file_ids")
    @classmethod
    def validate_file_ids(cls, v):
        """Validate that at least one file ID is provided."""
        if not v:
            raise ValueError("At least one file ID must be provided")
        return v


class FileTransferResponse(BaseModel):
    """Response model for file transfer operation."""

    success: bool
    message: str
    transferred_files: List[Dict[str, str]]
    failed_files: List[Dict[str, str]]
    total_transferred: int
    total_failed: int


class ConversationFilePreviewResponse(BaseModel):
    """Response model for conversation-attached file preview (#6799 — renamed
    from ``FilePreviewResponse`` to disambiguate from the system-level
    ``FilePreviewResponse`` in schemas_system.py which has a different shape
    (``type/url/content`` for filesystem preview vs the conversation-attached
    ``file_info/preview_available/preview_content`` here).
    """

    file_info: ConversationFileInfo
    preview_available: bool
    preview_content: str | None = None
    preview_type: str | None = None


class ConvFileCreateRequest(BaseModel):
    """Request model for creating a new file."""

    filename: str = Field(..., min_length=1, max_length=255)
    content: str = Field(default="")
    mime_type: str = Field(default="text/plain")


class ConvFileRenameRequest(BaseModel):
    """Request model for renaming a file."""

    new_filename: str = Field(..., min_length=1, max_length=255)


class ConvFileUpdateContentRequest(BaseModel):
    """Request model for updating file content."""

    content: str


class ConvFileCopyRequest(BaseModel):
    """Request model for copying a file."""

    new_filename: str | None = Field(None, max_length=255, description="Optional new name for the copy")


class AgentGenerateFileRequest(BaseModel):
    """Request model for agent file generation."""

    filename: str = Field(..., min_length=1, max_length=255)
    content: str
    file_type: str = Field(default="generated", description="File type tag")
    mime_type: str = Field(default="text/plain")
    agent_name: str | None = Field(None, description="Name of generating agent")
    metadata: Dict[str, str] | None = Field(None, description="Extra metadata")


class MCPToolCallRequest(BaseModel):
    """Request model for MCP tool call dispatch."""

    tool_name: str = Field(..., description="Name of the MCP tool to call")
    arguments: Dict = Field(default_factory=dict, description="Tool arguments")


# memory.py schemas (#6042)

_VALID_ENTITY_TYPES = frozenset(
    {
        "conversation",
        "bug_fix",
        "feature",
        "decision",
        "task",
        "user_preference",
        "context",
        "learning",
        "research",
        "implementation",
    }
)
_VALID_RELATION_TYPES = frozenset(
    {
        "relates_to",
        "depends_on",
        "implements",
        "fixes",
        "informs",
        "guides",
        "follows",
        "contains",
        "blocks",
    }
)


class EntityCreateRequest(BaseModel):
    entity_type: str = Field(..., description="Type of entity")
    name: str = Field(..., min_length=1, max_length=200)
    observations: List[str] = Field(..., min_length=1)
    metadata: Metadata | None = Field(default_factory=dict)
    tags: List[str] | None = Field(default_factory=list)

    @field_validator("entity_type")
    @classmethod
    def validate_entity_type(cls, v):
        if v not in _VALID_ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of: {_VALID_ENTITY_TYPES}")
        return v


class ObservationAddRequest(BaseModel):
    observations: List[str] = Field(..., min_length=1)


class RelationCreateRequest(BaseModel):
    from_entity: str = Field(..., description="Source entity name")
    to_entity: str = Field(..., description="Target entity name")
    relation_type: str = Field(..., description="Type of relationship")
    bidirectional: bool = Field(default=False)
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: Metadata | None = Field(default_factory=dict)

    @field_validator("relation_type")
    @classmethod
    def validate_relation_type(cls, v):
        if v not in _VALID_RELATION_TYPES:
            raise ValueError(f"relation_type must be one of: {_VALID_RELATION_TYPES}")
        return v


class InvalidateEntityRequest(BaseModel):
    ended_at: str | None = Field(default=None, description="ISO-8601 timestamp for valid_to")


class InvalidateRelationRequest(BaseModel):
    from_id: str = Field(..., description="Source entity UUID")
    relation_type: str = Field(..., description="Type of the relation")
    to_id: str = Field(..., description="Target entity UUID")
    ended_at: str | None = Field(default=None)


class EntityResponse(BaseModel):
    id: str
    type: str
    name: str
    created_at: int
    updated_at: int
    observations: List[str]
    metadata: Metadata


class RelationResponse(BaseModel):
    to: str
    type: str
    created_at: int
    metadata: Metadata


class GraphNodeResponse(BaseModel):
    entity: EntityResponse
    relations: Dict[str, List[RelationResponse]]


class SearchResponse(BaseModel):
    entities: List[EntityResponse]
    total_count: int
    query: str
    filters: Metadata


class MemorySearchResponse(BaseModel):
    """Envelope for GET /api/memory/search — wraps SearchResponse in the
    standard {success, data, request_id} envelope used across memory.py."""

    success: bool
    data: SearchResponse
    request_id: str


class MemoryEntityDetailResponse(BaseModel):
    """Envelope for GET /api/memory/entities/{entity_id} — wraps EntityResponse."""

    success: bool
    data: EntityResponse
    request_id: str


# ai_stack_integration.py schemas (#6042)


class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=10000)
    documents: List[Metadata] | None = None
    context: str | None = None
    max_results: int = Field(10, ge=1, le=50)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=50000)
    context: str | None = None
    chat_history: List[Metadata] | None = None
    use_knowledge_base: bool = Field(True)
    response_style: str = Field("conversational")


class KnowledgeExtractionRequest(BaseModel):
    content: str = Field(..., min_length=1)
    content_type: str = Field("text")
    extraction_mode: str = Field("comprehensive")


class ResearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000)
    research_depth: str = Field("comprehensive")
    sources: List[str] | None = None
    include_web: bool = Field(True)


class KbCodeSearchRequest(BaseModel):
    """KB-side code search request (#6799 — renamed from ``CodeSearchRequest``
    to disambiguate from the search-engine ``CodeSearchRequest`` in
    schemas_code.py with a different shape (``query/search_type/language/
    max_results`` vs the KB ``query/search_scope/include_npu`` here).
    """

    query: str = Field(..., min_length=1)
    search_scope: str = Field("codebase")
    include_npu: bool = Field(True)


class DevelopmentAnalysisRequest(BaseModel):
    code_path: str | None = None
    analysis_type: str = Field("comprehensive")


class ContentClassificationRequest(BaseModel):
    content: str = Field(..., min_length=1)
    classification_types: List[str] | None = None


# chat_knowledge.py schemas (#6042)


class KnowledgeDecision(str, Enum):
    ADD_TO_KB = "add_to_kb"
    KEEP_TEMPORARY = "keep_temporary"
    DELETE = "delete"


class FileAssociationType(str, Enum):
    REFERENCE = "reference"
    UPLOAD = "upload"
    GENERATED = "generated"
    MODIFIED = "modified"


class CreateContextRequest(BaseModel):
    chat_id: str
    topic: str | None = None
    keywords: List[str] | None = None
    user_id: str | None = None


class AssociateFileRequest(BaseModel):
    chat_id: str
    file_path: str
    association_type: FileAssociationType
    metadata: Metadata | None = None


class AddKnowledgeRequest(BaseModel):
    chat_id: str
    content: str
    metadata: Metadata | None = None


class KnowledgeDecisionRequest(BaseModel):
    chat_id: str
    knowledge_id: str
    decision: KnowledgeDecision


class CompileChatRequest(BaseModel):
    chat_id: str
    title: str | None = None
    include_system_messages: bool = False


class ChatKnowledgeSearchRequest(BaseModel):
    query: str
    chat_id: str | None = None
    include_temporary: bool = True


class MarkFactsPreservedRequest(BaseModel):
    fact_ids: List[str]
    preserve: bool = True


# ---------------------------------------------------------------------------
# entity_extraction.py schemas (#6042)
# ---------------------------------------------------------------------------

_EXTRACTION_VALID_ROLES = frozenset({"user", "assistant", "system"})


class ExtractionMessage(BaseModel):
    """Message in conversation."""

    role: str = Field(..., description="Message role (user/assistant/system)")
    content: str = Field(..., min_length=1, description="Message content")

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        if v not in _EXTRACTION_VALID_ROLES:
            raise ValueError(f"Role must be one of {_EXTRACTION_VALID_ROLES}")
        return v


class EntityExtractionRequest(BaseModel):
    """Request model for entity extraction."""

    conversation_id: str = Field(..., min_length=1, max_length=200, description="Conversation identifier")
    messages: List[ExtractionMessage] = Field(..., min_length=1, description="Conversation messages")
    session_metadata: Metadata | None = Field(None, description="Optional session metadata")

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, v):
        if not v.strip():
            raise ValueError("Conversation ID cannot be empty or whitespace")
        return v.strip()


class BatchExtractionRequest(BaseModel):
    """Request model for batch entity extraction."""

    conversations: List[EntityExtractionRequest] = Field(
        ..., min_length=1, max_length=50, description="Conversations to process (max 50)"
    )


class EntityExtractionResponse(BaseModel):
    """Response model for entity extraction."""

    success: bool = Field(..., description="Whether extraction succeeded")
    conversation_id: str = Field(..., description="Conversation identifier")
    facts_analyzed: int = Field(..., description="Number of facts analyzed")
    entities_created: int = Field(..., description="Number of entities created")
    relations_created: int = Field(..., description="Number of relations created")
    processing_time: float = Field(..., description="Processing time in seconds")
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
    request_id: str = Field(..., description="Unique request identifier")


class BatchExtractionResponse(BaseModel):
    """Response model for batch extraction."""

    success: bool = Field(..., description="Whether batch succeeded")
    total_conversations: int = Field(..., description="Total conversations processed")
    successful_extractions: int = Field(..., description="Number of successful extractions")
    failed_extractions: int = Field(..., description="Number of failed extractions")
    results: List[EntityExtractionResponse] = Field(..., description="Individual extraction results")
    total_processing_time: float = Field(..., description="Total processing time in seconds")
    request_id: str = Field(..., description="Unique request identifier")


class EntityExtractionHealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(..., description="Service status (healthy, degraded, unhealthy)")
    components: Dict[str, str] = Field(..., description="Component health status")
    timestamp: str = Field(..., description="Timestamp of health check")


# ---------------------------------------------------------------------------
# multimodal.py schemas
# ---------------------------------------------------------------------------


class CrossModalSearchRequest(BaseModel):
    query: str | bytes
    query_modality: str = Field(..., description="Type of query: text, image, audio")
    target_modalities: List[str] | None = Field(default=None, description="Target modalities to search")
    limit: int = Field(
        default=QueryDefaults.DEFAULT_SEARCH_LIMIT, ge=1, le=100, description="Maximum results per modality"
    )
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class TextProcessingRequest(BaseModel):
    text: str = Field(..., description="Text content to process")
    intent: str = Field(default="analysis", description="Processing intent")
    metadata: Metadata | None = Field(default=None)


class EmbeddingRequest(BaseModel):
    content: str | bytes
    modality: str = Field(..., description="Content modality: text, image, audio")
    preferred_device: str | None = Field(default=None, description="Preferred processing device")


class MultiModalResponse(BaseModel):
    success: bool
    result_id: str
    modality: str
    processing_time: float
    confidence: float
    result_data: Metadata
    device_used: str | None = None
    error_message: str | None = None


class CrossModalSearchResponse(BaseModel):
    query: str
    query_modality: str
    results: Dict[str, List[Metadata]]
    total_found: int
    processing_time: float


# ---------------------------------------------------------------------------
# natural_language_search.py schemas
# ---------------------------------------------------------------------------


class NLSearchRequest(BaseModel):
    """Request model for natural language search."""

    query: str = Field(..., description="Natural language query")
    max_results: int = Field(default=QueryDefaults.DEFAULT_SEARCH_LIMIT, description="Maximum results to return")
    include_explanations: bool = Field(default=True, description="Include LLM-generated explanations")
    language_filter: str | None = Field(default=None, description="Filter by programming language")


class ParsedQueryResponse(BaseModel):
    """Response model for parsed query."""

    original_query: str
    normalized_query: str
    intent: str
    domain: str
    entities: List[str]
    keywords: List[str]
    search_terms: List[str]
    confidence: float
    question_type: str


class SearchResultWithExplanation(BaseModel):
    """Search result with optional explanation."""

    file_path: str
    line_number: int
    content: str
    confidence: float
    summary: str | None = None
    explanation: str | None = None
    key_concepts: List[str] | None = None


class NLSearchResponse(BaseModel):
    """Response model for natural language search."""

    query: ParsedQueryResponse
    results: List[SearchResultWithExplanation]
    suggestions: List[Dict[str, Any]]
    total_results: int
    search_time_ms: float


class QuerySuggestionResponse(BaseModel):
    """Response model for query suggestions."""

    suggestions: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# knowledge.py schemas
# ---------------------------------------------------------------------------


class AddFactsRequest(BaseModel):
    """Request model for adding text content to knowledge base."""

    content: str = Field(..., min_length=1, max_length=100000, description="Text content")
    title: str = Field(default="", max_length=500, description="Document title")
    source: str = Field(default="Manual Entry", max_length=500, description="Content source")
    category: str = Field(default=CategoryDefaults.GENERAL, max_length=100, description="Category")
    tags: List[str] = Field(default_factory=list, description="Tags for the content")
    board_id: str | None = Field(
        default=None, max_length=100, description="Board ID to scope this fact. None means global board."
    )

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        if len(v) > 20:
            raise ValueError("Maximum 20 tags allowed")
        return [tag[:50] for tag in v]


class AddUrlRequest(BaseModel):
    """Request model for adding URL content to knowledge base."""

    url: str = Field(..., min_length=1, max_length=2000, description="URL to fetch")
    title: str = Field(default="", max_length=500, description="Document title")
    method: str = Field(default="fetch", pattern="^(fetch|raw)$", description="Fetch method")
    category: str = Field(default="web", max_length=100, description="Category")
    tags: List[str] = Field(default_factory=list, description="Tags")
    board_id: str | None = Field(
        default=None, max_length=100, description="Board ID to scope this URL content. None means global board."
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v):
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v


class AudioIngestRequest(BaseModel):
    """Request body for POST /api/knowledge_base/audio (URL-based ingestion)."""

    url: str = Field(..., min_length=1, max_length=2000, description="YouTube URL or direct audio/video URL")
    title: str = Field(default="", max_length=500)
    category: str = Field(default="audio", max_length=100)
    tags: List[str] = Field(default_factory=list)
    whisper_model: str = Field(
        default="base", pattern="^(tiny|base|small|medium|large|large-v2|large-v3)$", description="Whisper model size"
    )
    language: str | None = Field(default=None, max_length=10, description="ISO-639-1 language hint")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("URL must start with http:// or https://")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list) -> list:
        if len(v) > 20:
            raise ValueError("Maximum 20 tags allowed")
        return [str(t)[:50] for t in v]


class DocsBrowseRequest(BaseModel):
    """Request model for browsing indexed documentation."""

    category: str | None = Field(
        default=None, max_length=100, description="Filter by category (e.g., 'developer', 'api', 'troubleshooting')"
    )
    doc_type: str | None = Field(
        default=None, max_length=50, description="Filter by document type (e.g., 'markdown', 'code')"
    )
    file_path_pattern: str | None = Field(
        default=None, max_length=500, description="Filter by file path pattern (e.g., 'docs/api/')"
    )
    search_query: str | None = Field(default=None, max_length=500, description="Optional text search within documents")
    page: int = Field(default=1, ge=1, le=1000, description="Page number")
    page_size: int = Field(default=20, ge=1, le=100, description="Results per page")
    sort_by: str = Field(
        default="indexed_at", pattern="^(indexed_at|title|category|file_path)$", description="Sort field"
    )
    sort_order: str = Field(default="desc", pattern="^(asc|desc)$", description="Sort order")


class OrgKnowledgeConfigPayload(BaseModel):
    """Per-org LLM + embedding model config payload."""

    llm_provider: str | None = Field(default=None, max_length=64)
    llm_model: str | None = Field(default=None, max_length=256)
    embedding_model: str | None = Field(default=None, max_length=256)
    embedding_dimension: int | None = Field(default=None, ge=1, le=65536)


# ---------------------------------------------------------------------------
# knowledge_grounding.py schemas
# ---------------------------------------------------------------------------


class GroundResponseRequest(BaseModel):
    """Request to ground an agent response."""

    query: str = Field(..., min_length=1, max_length=2000, description="User query")
    agent_response: str = Field(..., min_length=1, max_length=5000, description="Agent response to ground")
    context: Dict[str, Any] | None = Field(None, description="Optional context metadata")


class VerifyClaimRequest(BaseModel):
    """Request to verify a single claim."""

    claim_text: str = Field(..., min_length=1, max_length=500)
    subject: str | None = Field(None, max_length=200)
    predicate: str | None = Field(None, max_length=200)
    object: str | None = Field(None, max_length=200)


class ResolveConflictRequest(BaseModel):
    """Request to resolve a conflict."""

    chosen_fact: str = Field(..., min_length=1, description="Chosen fact ID")
    reasoning: str = Field(..., min_length=10, max_length=1000)


class GroundedResponseSchema(BaseModel):
    """Schema for grounded response API response."""

    response_id: str
    original_query: str
    response_text: str
    verified_claims: List[Dict[str, Any]]
    unverified_claims: List[Dict[str, Any]]
    conflicts: List[Dict[str, Any]]
    confidence_overall: float
    requires_human_review: bool
    timestamp: float


class ConflictSchema(BaseModel):
    """Schema for a conflict."""

    conflict_id: str
    claim_1_id: str
    claim_2_id: str | None = None
    description: str
    severity: str
    resolution: str
    chosen_fact: str | None = None
    timestamp: float


# ---------------------------------------------------------------------------
# knowledge_relations.py schemas
# ---------------------------------------------------------------------------


class CreateRelationRequest(BaseModel):
    """Request model for creating a fact relation."""

    source_fact_id: str = Field(..., description="ID of the source fact")
    target_fact_id: str = Field(..., description="ID of the target fact")
    relation_type: str = Field(..., description="Type of relation (e.g., relates_to, depends_on, implements)")
    metadata: dict | None = Field(None, description="Optional metadata for the relation")


class DeleteRelationRequest(BaseModel):
    """Request model for deleting a fact relation."""

    source_fact_id: str = Field(..., description="ID of the source fact")
    target_fact_id: str = Field(..., description="ID of the target fact")
    relation_type: str | None = Field(None, description="Specific relation type to delete (None = all relations)")


class TraverseRequest(BaseModel):
    """Request model for graph traversal."""

    start_fact_id: str = Field(..., description="Starting fact ID for traversal")
    max_depth: int = Field(2, ge=1, le=5, description="Maximum traversal depth")
    relation_types: List[str] | None = Field(None, description="Optional list of relation types to follow")
    include_fact_details: bool = Field(False, description="Include full fact content in results")


class HybridSearchRequest(BaseModel):
    """Request model for hybrid (vector + graph) search."""

    query: str = Field(..., description="Search query text")
    top_k: int = Field(10, ge=1, le=100, description="Number of vector matches")
    expand_relations: bool = Field(True, description="Expand results with graph relations")
    relation_depth: int = Field(1, ge=1, le=3, description="Relation traversal depth")
    relation_types: List[str] | None = Field(None, description="Filter by relation types")


# ---------------------------------------------------------------------------
# nl_database.py schemas
# ---------------------------------------------------------------------------


class NLQueryRequest(BaseModel):
    """Request body for a natural language database query."""

    question: str = Field(
        ..., min_length=1, max_length=2048, description="Natural language question to translate into SQL"
    )
    db_id: str = Field(
        default="local", max_length=128, description="Database identifier. Use 'local' for autobot_data.db"
    )
    db_secret_id: str | None = Field(
        default=None, max_length=128, description="Secret ID (from secrets manager) containing the database_url"
    )


class TrainRequest(BaseModel):
    """Request body for training the NL service on an external database."""

    db_id: str = Field(..., min_length=1, max_length=128, description="Unique identifier for this database connection")
    db_secret_id: str = Field(
        ..., max_length=128, description="Secret ID containing the database_url in the secrets manager"
    )
    db_type: str = Field(default="postgresql", description="Database type: postgresql, mysql, or sqlite")


class NLQueryResponse(BaseModel):
    """Response for a natural language query execution."""

    question: str
    sql: str | None
    results: List[Dict[str, Any]]
    columns: List[str]
    row_count: int
    db_id: str
    elapsed_ms: int
    error: str | None = None


class TrainResponse(BaseModel):
    """Response for a database schema training operation."""

    success: bool
    db_id: str
    schema_length: int | None = None
    table_count: int | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# knowledge_collaboration.py schemas
# ---------------------------------------------------------------------------


class KnowledgeScopeFilter(BaseModel):
    """Filter for knowledge by scope."""

    scope: VisibilityLevel | None = Field(default=None, description="Visibility level to filter by")
    organization_id: str | None = Field(default=None, description="Organization ID filter")
    group_ids: List[str] | None = Field(default=None, description="Group IDs to filter by")


class ShareKnowledgeRequest(BaseModel):
    """Request to share knowledge with users or groups."""

    user_ids: List[str] | None = Field(default=None, description="User IDs to share with")
    group_ids: List[str] | None = Field(default=None, description="Group IDs to share with")


class UpdatePermissionsRequest(BaseModel):
    """Request to update knowledge permissions."""

    visibility: VisibilityLevel = Field(description="New visibility level")
    organization_id: str | None = Field(default=None, description="Organization ID for org-level knowledge")
    group_ids: List[str] | None = Field(default=None, description="Group IDs for group-level knowledge")


class KnowledgeAccessResponse(BaseModel):
    """Response with knowledge access details."""

    fact_id: str
    owner_id: str
    visibility: VisibilityLevel
    organization_id: str | None = None
    group_ids: List[str] = []
    shared_with: List[str] = []
    can_edit: bool
    can_share: bool
    can_delete: bool


# ---------------------------------------------------------------------------
# knowledge_graph_routes.py schemas
# ---------------------------------------------------------------------------


class PipelineRunRequest(BaseModel):
    """Request to run the ECL pipeline on a document."""

    document_id: str = Field(..., description="Document ID to process")
    config: dict | None = Field(None, description="Pipeline configuration overrides")


class PipelineRunResponse(BaseModel):
    """Pipeline execution result."""

    document_id: str
    entities_count: int = 0
    relationships_count: int = 0
    events_count: int = 0
    summaries_count: int = 0
    chunks_count: int = 0
    stages_completed: List[str] = []
    errors: List[str] = []


class EventSearchRequest(BaseModel):
    """Temporal event search parameters."""

    start_date: str | None = None
    end_date: str | None = None
    event_types: List[str] | None = None
    entity_name: str | None = None
    limit: int = Field(100, ge=1, le=500)


# ---------------------------------------------------------------------------
# knowledge_search_aggregator.py schemas
# ---------------------------------------------------------------------------


class ContextRequest(BaseModel):
    """Request model for getting LLM context."""

    query: str = Field(..., description="User query for context retrieval")
    max_context_length: int = Field(4000, ge=500, le=16000, description="Maximum context length in characters")
    include_documentation: bool = Field(True, description="Include documentation in context")
    include_relations: bool = Field(True, description="Include related facts in context")


class GraphRequest(BaseModel):
    """Request model for aggregated knowledge graph."""

    max_facts: int = Field(50, ge=1, le=200, description="Maximum facts to include")
    max_depth: int = Field(2, ge=1, le=3, description="Maximum relation depth")
    include_categories: bool = Field(True, description="Include category nodes")
    include_relations: bool = Field(True, description="Include fact relations")
    category_filter: str | None = Field(None, description="Filter by category path")


# ---------------------------------------------------------------------------
# knowledge_organization.py schemas
# ---------------------------------------------------------------------------


class OrganizationKnowledgePolicy(BaseModel):
    """Organization-wide knowledge policies."""

    default_visibility: VisibilityLevel = Field(
        default=VisibilityLevel.PRIVATE, description="Default visibility for new knowledge"
    )
    allow_user_private: bool = Field(default=True, description="Allow users to create private knowledge")
    allow_user_shared: bool = Field(default=True, description="Allow users to share knowledge")
    allow_user_organization: bool = Field(default=False, description="Allow non-admins to create org-wide knowledge")
    require_approval_for_system: bool = Field(
        default=True, description="Require admin approval for system-wide knowledge"
    )
    retention_days: int | None = Field(default=None, description="Knowledge retention period (None = indefinite)")


class OrganizationKnowledgeStats(BaseModel):
    """Organization knowledge statistics."""

    organization_id: str
    total_facts: int
    by_visibility: Dict[str, int]
    by_source: Dict[str, int]
    total_size_bytes: int
    user_count: int
    team_count: int
    top_contributors: List[Dict[str, str]]


class UpdateOrganizationPolicyRequest(BaseModel):
    """Request to update organization knowledge policy."""

    policy: OrganizationKnowledgePolicy


# ---------------------------------------------------------------------------
# graph_rag.py schemas
# ---------------------------------------------------------------------------


class GraphRAGSearchRequest(BaseModel):
    """Request model for graph-aware RAG search."""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query string")
    start_entity: str | None = Field(
        None, max_length=200, description="Optional starting entity name for graph traversal"
    )
    max_depth: int = Field(2, ge=1, le=3, description="Maximum graph traversal depth (1-3 hops)")
    max_results: int = Field(5, ge=1, le=20, description="Maximum number of results to return")
    enable_reranking: bool = Field(True, description="Whether to apply cross-encoder reranking")
    timeout: float | None = Field(None, ge=1.0, le=30.0, description="Optional timeout in seconds (1-30s)")

    @field_validator("query")
    @classmethod
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace")
        return v.strip()


class GraphRAGSearchResponse(BaseModel):
    """Response model for graph-aware RAG search."""

    success: bool = Field(..., description="Whether the search succeeded")
    results: List[Metadata] = Field(..., description="Search results")
    metrics: Metadata = Field(..., description="Performance metrics")
    request_id: str = Field(..., description="Unique request identifier")


class GraphRAGHealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(..., description="Service status (healthy, degraded, unhealthy)")
    components: Dict[str, str] = Field(..., description="Component health status")
    timestamp: str = Field(..., description="Timestamp of health check")


# ---------------------------------------------------------------------------
# documents.py schemas
# ---------------------------------------------------------------------------


class CreateDocumentRequest(BaseModel):
    """Payload for creating a new AI document."""

    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(default="")
    source_facts: List[str] = Field(default_factory=list)
    source_session_id: str | None = None
    source_message_id: str | None = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdateDocumentRequest(BaseModel):
    """Partial-update payload — only supplied fields are applied."""

    title: str | None = Field(default=None, min_length=1, max_length=500)
    content: str | None = None
    tags: List[str] | None = None
    metadata: Dict[str, Any] | None = None


class RefineDocumentRequest(BaseModel):
    """Ask the AI to refine a specific section of the document."""

    instruction: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Refinement instruction, e.g. 'make the introduction shorter'",
    )
    section: str | None = Field(default=None, description="Optional section heading to scope the refinement")


# ---------------------------------------------------------------------------
# embeddings.py schemas
# ---------------------------------------------------------------------------


class EmbeddingProviderConfig(BaseModel):
    """Embedding provider configuration model."""

    provider: str
    endpoint: str
    selected_model: str
    models: List[str] = []


class EmbeddingConfig(BaseModel):
    """Embedding configuration model."""

    provider: str
    providers: Dict[str, EmbeddingProviderConfig]


class EmbeddingUpdate(BaseModel):
    """Embedding configuration update request."""

    provider: str
    selected_model: str
    endpoint: str | None = None


# ---------------------------------------------------------------------------
# task_memory.py schemas
# ---------------------------------------------------------------------------


class TaskCreateRequest(BaseModel):
    task_name: str
    description: str
    priority: str = "medium"
    agent_type: str | None = None
    inputs: Metadata | None = None
    parent_task_id: str | None = None
    metadata: Metadata | None = None


class TaskUpdateRequest(BaseModel):
    status: str | None = None
    outputs: Metadata | None = None
    error_message: str | None = None


class MarkdownReferenceRequest(BaseModel):
    task_id: str
    markdown_file_path: str
    reference_type: str = "documentation"


# ---------------------------------------------------------------------------
# enhanced_search.py schemas
# ---------------------------------------------------------------------------


class NPUSearchRequest(BaseModel):
    """Enhanced search request model."""

    query: str = Field(..., description="Search query")
    similarity_top_k: int = Field(10, description="Number of results to return", ge=1, le=100)
    filters: Metadata | None = Field(None, description="Optional metadata filters")
    enable_npu_acceleration: bool = Field(True, description="Enable NPU acceleration")
    force_device: str | None = Field(None, description="Force specific device (npu/gpu/cpu)")


class NPUSearchResponse(BaseModel):
    """Enhanced search response model."""

    query: str
    results: List[Metadata]
    metrics: Metadata
    total_results: int
    search_time_ms: float
    device_used: str
    cache_hit: bool = False


class BenchmarkRequest(BaseModel):
    """Benchmark request model."""

    test_queries: List[str] = Field(..., description="List of test queries")
    iterations: int = Field(3, description="Number of iterations per query", ge=1, le=10)


class NPUOptimizationRequest(BaseModel):
    """Optimization request model."""

    workload_type: str = Field(
        "balanced",
        description=("Workload type: latency_optimized, throughput_optimized, quality_optimized," "balanced"),
    )


# ---------------------------------------------------------------------------
# knowledge_ai_stack.py schemas (separate from existing knowledge schemas)
# ---------------------------------------------------------------------------


class AIStackSearchRequest(BaseModel):
    """Enhanced search request with AI Stack integration."""

    query: str = Field(..., min_length=1, max_length=5000, description="Search query")
    search_type: str = Field("comprehensive", description="Search type (precise, comprehensive, broad)")
    max_results: int = Field(10, ge=1, le=50, description="Maximum results to return")
    include_rag: bool = Field(True, description="Include RAG-enhanced results")
    include_local: bool = Field(True, description="Include local knowledge base results")
    confidence_threshold: float = Field(0.3, ge=0.0, le=1.0, description="Minimum confidence score")


class AIStackKnowledgeExtractionRequest(BaseModel):
    """Request model for knowledge extraction (AI Stack version)."""

    content: str = Field(..., min_length=1, description="Content to extract knowledge from")
    title: str | None = Field(None, description="Content title")
    source: str | None = Field("api", description="Content source")
    category: str | None = Field("general", description="Content category")
    content_type: str = Field("text", description="Content type (text, document, url)")
    extraction_mode: str = Field("comprehensive", description="Extraction mode")
    auto_store: bool = Field(True, description="Automatically store extracted knowledge")


class DocumentAnalysisRequest(BaseModel):
    """Request model for document analysis."""

    documents: List[Metadata] = Field(..., description="Documents to analyze")
    analysis_type: str = Field("comprehensive", description="Analysis type")
    extract_entities: bool = Field(True, description="Extract entities")
    generate_summary: bool = Field(True, description="Generate summary")


class AIStackRAGQueryRequest(BaseModel):
    """Request model for RAG queries (AI Stack version)."""

    query: str = Field(..., min_length=1, max_length=5000, description="RAG query")
    documents: List[Metadata] | None = Field(None, description="Specific documents to query")
    context: str | None = Field(None, description="Additional context")
    max_results: int = Field(10, ge=1, le=30, description="Maximum results")
    include_reasoning: bool = Field(False, description="Include reasoning steps")


# ---------------------------------------------------------------------------
# knowledge_boards.py schemas
# ---------------------------------------------------------------------------

# The implicit global board — never stored, always valid
KNOWLEDGE_BOARD_GLOBAL_ID = "__global__"

# Allowed characters for board IDs: lowercase letters, digits, hyphen, underscore
_BOARD_ID_RE = re.compile(r"^[a-z0-9_-]{1,100}$")


class CreateBoardRequest(BaseModel):
    """Request model for creating a new knowledge board."""

    board_id: str | None = Field(
        default=None,
        max_length=100,
        description=(
            "Stable identifier for the board (lowercase letters, digits, "
            "hyphen, underscore). Auto-generated when omitted."
        ),
    )
    name: str = Field(..., min_length=1, max_length=200, description="Human-readable board name")
    description: str = Field(default="", max_length=500, description="Optional description")

    @field_validator("board_id", mode="before")
    @classmethod
    def validate_board_id(cls, v):
        if v is None:
            return v
        if v == KNOWLEDGE_BOARD_GLOBAL_ID:
            raise ValueError("'__global__' is reserved and cannot be created")
        if not _BOARD_ID_RE.match(v):
            raise ValueError("board_id must only contain lowercase letters, digits, hyphen, or underscore")
        return v


# ---------------------------------------------------------------------------
# knowledge_cognition.py schemas
# ---------------------------------------------------------------------------


class SeedRequest(BaseModel):
    """Optional body for the cognition store seed endpoint."""

    manifest_path: str = "cognition_seed.yaml"


# ---------------------------------------------------------------------------
# knowledge_rag_feedback.py schemas
# ---------------------------------------------------------------------------

from typing import Literal as _Literal


class RagFeedbackRequest(BaseModel):
    """Annotation feedback submitted from the source card accept/reject UI."""

    source_url: str
    title: str = ""
    query: str
    decision: _Literal["accepted", "rejected"]  # noqa: F821  # Literal alias false-positive
    user_id: str | None = None


# ---------------------------------------------------------------------------
# knowledge_search_scoped.py schemas
# ---------------------------------------------------------------------------


class ScopedSearchRequest(BaseModel):
    """Scoped search request with automatic permission filtering."""

    query: str = Field(..., min_length=1, description="Search query")
    top_k: int = Field(default=10, ge=1, le=100, description="Maximum results")
    mode: str = Field(
        default="hybrid",
        pattern="^(semantic|keyword|hybrid|auto)$",
        description="Search mode",
    )
    category: str | None = Field(default=None, description="Filter by category")
    tags: List[str] | None = Field(default=None, description="Filter by tags")
    min_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum score threshold")
    enable_rag: bool = Field(default=False, description="Enable RAG enhancement")
    enable_reranking: bool = Field(default=False, description="Enable reranking")


# ---------------------------------------------------------------------------
# kb_librarian.py schemas
# ---------------------------------------------------------------------------


class KBQuery(BaseModel):
    """Knowledge base query request model."""

    query: str
    max_results: int | None = None
    similarity_threshold: float | None = None
    auto_summarize: bool | None = None


class KBQueryResponse(BaseModel):
    """Knowledge base query response model."""

    enabled: bool
    is_question: bool
    query: str
    documents_found: int
    documents: List[Metadata]
    summary: str | None = None


# ---------------------------------------------------------------------------
# knowledge_audit.py schemas
# ---------------------------------------------------------------------------

from datetime import datetime as _datetime

from services.audit.audit import AuditEventType as _AuditEventType  # GH#8290 Phase 2


class AuditEvent(BaseModel):
    """Audit event model."""

    id: str
    type: _AuditEventType
    user_id: str
    fact_id: str | None = None
    organization_id: str | None = None
    details: dict = Field(default_factory=dict)
    ip_address: str | None = None
    timestamp: str


class ComplianceReportRequest(BaseModel):
    """Request for compliance report."""

    start_date: _datetime = Field(description="Report start date")
    end_date: _datetime = Field(description="Report end date")
    organization_id: str | None = Field(default=None, description="Organization ID (defaults to user's org)")


# ---------------------------------------------------------------------------
# knowledge_test.py / graph_rag.py schemas (GH #6509 Batch E)
# ---------------------------------------------------------------------------


class KnowledgeFreshStatsData(BaseModel):
    """Response data for GET /knowledge/test/fresh_stats."""

    source: str = ""
    stats: Dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: str | None = None


class KnowledgeRebuildIndexData(BaseModel):
    """Response data for POST /knowledge/test/rebuild_index."""

    operation: str = ""
    result: Dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    error: str | None = None


class GraphRagMetricsData(BaseModel):
    """Response data for GET /graphrag/metrics."""

    service: str = ""
    graph_weight: float = 0.0
    entity_extraction_enabled: bool = False
    rag_service: Dict[str, Any] = Field(default_factory=dict)
    graph_initialized: bool = False


# ---------------------------------------------------------------------------
# KB Watch Folders (GH #9000)
# ---------------------------------------------------------------------------


class WatchFolderCreateRequest(BaseModel):
    """Request to create a new watch folder."""

    path: str = Field(description="Filesystem path to watch")
    collection: str = Field(description="Target KB collection", default="default")
    enabled: bool = Field(description="Whether to start watching immediately", default=True)
    file_types: List[str] = Field(
        description="File types to watch (pdf, docx, txt, md, csv, html)",
        default=["pdf", "docx", "txt", "md", "csv", "html"],
    )
    recursive: bool = Field(description="Watch subdirectories recursively", default=True)
    category: str = Field(description="KB category for ingested files", default="uploads")
    tags: List[str] = Field(description="Tags to apply to ingested files", default_factory=list)


class WatchFolderResponse(BaseModel):
    """Response for watch folder operations."""

    success: bool = True
    message: str | None = None
    folder_id: str | None = None
    folder: Dict[str, Any] | None = None


class WatchFolderListResponse(BaseModel):
    """Response for listing watch folders."""

    success: bool = True
    folders: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0


class WatchFolderStatsResponse(BaseModel):
    """Response for watch folder statistics."""

    success: bool = True
    stats: Dict[str, Any] = Field(default_factory=dict)


class WatchFolderControlRequest(BaseModel):
    """Request to control a watch folder (enable/disable)."""

    action: str = Field(description="Action to perform: 'enable' or 'disable'")
