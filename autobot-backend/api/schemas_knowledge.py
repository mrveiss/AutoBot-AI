# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge base collection, category, fact, grounding, and audit schemas.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Knowledge schemas
# ---------------------------------------------------------------------------

class KnowledgeMetadataTemplateResponse(BaseModel):
    """Response for POST /metadata/templates and PUT /metadata/templates/{id}."""

    status: str
    message: Optional[str] = None
    template: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}



class KnowledgeMetadataTemplateListResponse(BaseModel):
    """Response for GET /metadata/templates."""

    status: str
    count: Optional[int] = None
    templates: Optional[List[Any]] = None

    model_config = {"extra": "allow"}



class KnowledgeMetadataTemplateDetailResponse(BaseModel):
    """Response for GET /metadata/templates/{template_id}."""

    status: str
    template: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}



class KnowledgeMetadataTemplateDeleteResponse(BaseModel):
    """Response for DELETE /metadata/templates/{template_id}."""

    status: str
    message: Optional[str] = None

    model_config = {"extra": "allow"}



class KnowledgeMetadataValidateResponse(BaseModel):
    """Response for POST /metadata/validate."""

    valid: Optional[bool] = None
    errors: Optional[List[Any]] = None
    warnings: Optional[List[Any]] = None

    model_config = {"extra": "allow"}



class KnowledgeMetadataSearchResponse(BaseModel):
    """Response for POST /metadata/search."""

    status: str
    count: Optional[int] = None
    facts: Optional[List[Any]] = None

    model_config = {"extra": "allow"}



class KnowledgeFactVersionListResponse(BaseModel):
    """Response for GET /facts/{fact_id}/versions."""

    status: str
    fact_id: Optional[str] = None
    versions: Optional[List[Any]] = None
    count: Optional[int] = None

    model_config = {"extra": "allow"}



class KnowledgeFactVersionDetailResponse(BaseModel):
    """Response for GET /facts/{fact_id}/versions/{version}."""

    status: str
    fact_id: Optional[str] = None
    version: Optional[int] = None
    content: Optional[Any] = None

    model_config = {"extra": "allow"}



class KnowledgeFactRevertResponse(BaseModel):
    """Response for POST /facts/{fact_id}/revert."""

    status: str
    message: Optional[str] = None
    new_version: Optional[int] = None

    model_config = {"extra": "allow"}



class KnowledgeFactVersionCompareResponse(BaseModel):
    """Response for POST /facts/{fact_id}/versions/compare."""

    status: str
    fact_id: Optional[str] = None
    version_a: Optional[int] = None
    version_b: Optional[int] = None
    diff: Optional[Any] = None

    model_config = {"extra": "allow"}



class KnowledgeFactVersionHistoryDeleteResponse(BaseModel):
    """Response for DELETE /facts/{fact_id}/versions."""

    status: str
    message: Optional[str] = None

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# knowledge_collections.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class KnowledgeCollectionCreateResponse(BaseModel):
    """Response for POST /collections."""

    status: str
    collection: Optional[Dict[str, Any]] = None
    message: Optional[str] = None



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
    collection: Optional[Dict[str, Any]] = None



class KnowledgeCollectionUpdateResponse(BaseModel):
    """Response for PUT /collections/{collection_id}."""

    status: str
    collection: Optional[Dict[str, Any]] = None
    message: Optional[str] = None



class KnowledgeCollectionDeleteResponse(BaseModel):
    """Response for DELETE /collections/{collection_id}."""

    status: str
    collection_id: Optional[str] = None
    facts_in_collection: int
    facts_deleted: int
    message: Optional[str] = None



class KnowledgeCollectionAddFactsResponse(BaseModel):
    """Response for POST /collections/{collection_id}/facts."""

    status: str
    collection_id: Optional[str] = None
    added_count: int
    already_in_collection: int
    not_found: List[Any]
    total_facts: int
    message: Optional[str] = None



class KnowledgeCollectionRemoveFactsResponse(BaseModel):
    """Response for DELETE /collections/{collection_id}/facts."""

    status: str
    collection_id: Optional[str] = None
    removed_count: int
    not_in_collection: int
    total_facts: int
    message: Optional[str] = None



class KnowledgeCollectionFactsListResponse(BaseModel):
    """Response for GET /collections/{collection_id}/facts."""

    status: str
    collection_id: Optional[str] = None
    collection_name: Optional[str] = None
    facts: List[Any]
    total_count: int
    returned_count: int
    limit: int
    offset: int
    has_more: bool



class KnowledgeFactCollectionsResponse(BaseModel):
    """Response for GET /facts/{fact_id}/collections."""

    status: str
    fact_id: Optional[str] = None
    collections: List[Any]
    count: int



class KnowledgeCollectionExportResponse(BaseModel):
    """Response for POST /collections/{collection_id}/export."""

    status: str
    collection: Optional[Dict[str, Any]] = None
    facts: List[Any]
    total_count: int
    exported_at: Optional[str] = None



class KnowledgeCollectionBulkDeleteResponse(BaseModel):
    """Response for POST /collections/{collection_id}/bulk-delete."""

    status: str
    collection_id: Optional[str] = None
    facts_to_delete: Optional[int] = None
    deleted_count: int
    confirm_required: bool
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# knowledge_categories.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class KnowledgeCategoryCreateResponse(BaseModel):
    """Response for POST /categories."""

    status: str
    category: Optional[Dict[str, Any]] = None
    message: Optional[str] = None



class KnowledgeCategoryTreeResponse(BaseModel):
    """Response for GET /categories/tree."""

    status: str
    tree: List[Any]
    total_categories: int



class KnowledgeCategoryDetailResponse(BaseModel):
    """Response for GET /categories/{category_id} and GET /categories/path/{path}."""

    status: str
    category: Optional[Dict[str, Any]] = None



class KnowledgeCategoryUpdateResponse(BaseModel):
    """Response for PUT /categories/{category_id}."""

    status: str
    category: Optional[Dict[str, Any]] = None
    message: Optional[str] = None



class KnowledgeCategoryDeleteResponse(BaseModel):
    """Response for DELETE /categories/{category_id}."""

    status: str
    deleted_count: int
    facts_reassigned: int
    message: Optional[str] = None



class KnowledgeCategoryChildrenResponse(BaseModel):
    """Response for GET /categories/{category_id}/children."""

    status: str
    parent_id: Optional[str] = None
    children: List[Any]
    count: int



class KnowledgeCategoryAncestorsResponse(BaseModel):
    """Response for GET /categories/{category_id}/ancestors."""

    status: str
    category_id: Optional[str] = None
    ancestors: List[Any]
    depth: int



class KnowledgeCategoryFactsResponse(BaseModel):
    """Response for GET /categories/{category_id}/facts."""

    status: str
    category_id: Optional[str] = None
    category_path: Optional[str] = None
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
    fact_id: Optional[str] = None
    category_id: Optional[str] = None
    category_path: Optional[str] = None
    message: Optional[str] = None



class KnowledgeCategorySearchResponse(BaseModel):
    """Response for POST /categories/search."""

    status: str
    pattern: Optional[str] = None
    categories: List[Any]
    count: int


# ---------------------------------------------------------------------------
# validation_dashboard.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class KnowledgeUnifiedSearchResponse(BaseModel):
    """Response for POST /unified/search."""

    success: bool
    query: str
    facts: List[Any]
    related_facts: List[Any]
    documentation: List[Any]
    sources_searched: List[str]
    total_results: int



class KnowledgeUnifiedStatsResponse(BaseModel):
    """Response for GET /unified/stats.

    Sections are populated dynamically — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    success: bool
    knowledge_base: Dict[str, Any]
    relations: Dict[str, Any]
    documentation: Dict[str, Any]



class KnowledgeUnifiedContextResponse(BaseModel):
    """Response for POST /unified/context."""

    success: bool
    context: str
    context_length: int
    citations: List[Any]
    sources_used: List[Any]



class KnowledgeDocumentationSearchResponse(BaseModel):
    """Response for GET /unified/documentation/search."""

    success: bool
    query: Optional[str] = None
    results: List[Any]
    total_results: Optional[int] = None
    message: Optional[str] = None



class KnowledgeDocumentationStatsResponse(BaseModel):
    """Response for GET /unified/documentation/stats."""

    success: bool
    indexed: Optional[bool] = None
    message: Optional[str] = None
    how_to_index: Optional[str] = None
    collection_name: Optional[str] = None
    document_count: Optional[int] = None



class KnowledgeUnifiedGraphResponse(BaseModel):
    """Response for POST /unified/graph and GET /unified/graph."""

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
    total: Optional[int] = None



class KnowledgeShareResponse(BaseModel):
    """Response for POST /knowledge/collaboration/facts/{id}/share."""

    success: bool
    fact_id: str
    visibility: Optional[str] = None
    shared_with: List[Any]
    group_ids: List[Any]



class KnowledgeUnshareResponse(BaseModel):
    """Response for DELETE /knowledge/collaboration/facts/{id}/share/{entity_id}."""

    success: bool
    fact_id: str
    visibility: Optional[str] = None
    shared_with: List[Any]
    group_ids: List[Any]



class KnowledgePermissionsUpdateResponse(BaseModel):
    """Response for PUT /knowledge/collaboration/facts/{id}/permissions."""

    success: bool
    fact_id: str
    visibility: Optional[str] = None
    organization_id: Optional[str] = None
    group_ids: List[Any]



class KnowledgeAccessInfoResponse(BaseModel):
    """Response for GET /knowledge/collaboration/facts/{id}/access."""

    fact_id: str
    owner_id: Optional[str] = None
    visibility: Optional[str] = None
    organization_id: Optional[str] = None
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
    user_id: Optional[str] = None
    fact_id: Optional[str] = None
    organization_id: Optional[str] = None



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
    verified_by: Optional[str] = None
    verified_at: Optional[str] = None
    message: Optional[str] = None



class KnowledgeVerificationRejectResponse(BaseModel):
    """Response for POST /verification/{fact_id}/reject."""

    status: str
    fact_id: str
    deleted: bool
    message: Optional[str] = None



class KnowledgeVerificationConfigResponse(BaseModel):
    """Response for GET/PUT /verification/config."""

    status: str
    config: Dict[str, Any]
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# knowledge_suggestions.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class KnowledgeSuggestionsTagsResponse(BaseModel):
    """Response for POST /suggestions/tags.

    KB method returns opaque success dict — allow extra fields.
    """

    model_config = {"extra": "allow"}

    success: bool
    suggestions: Optional[List[Any]] = None
    similar_docs_analyzed: Optional[int] = None



class KnowledgeSuggestionsCategoriesResponse(BaseModel):
    """Response for POST /suggestions/categories."""

    model_config = {"extra": "allow"}

    success: bool
    suggestions: Optional[List[Any]] = None
    similar_docs_analyzed: Optional[int] = None



class KnowledgeSuggestionsAllResponse(BaseModel):
    """Response for POST /suggestions/all."""

    model_config = {"extra": "allow"}

    success: bool



class KnowledgeSuggestionsContextResponse(BaseModel):
    """Response for POST /suggestions/context."""

    model_config = {"extra": "allow"}

    success: bool
    suggestions: Optional[List[Any]] = None
    total_candidates: Optional[int] = None



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
    visibility: Optional[str] = None



class KnowledgeUnshareFactResponse(BaseModel):
    """Response for DELETE /api/knowledge/facts/{fact_id}/share/{user_id_to_remove}."""

    success: bool
    fact_id: str
    shared_with: List[Any]
    visibility: Optional[str] = None



class KnowledgeUpdateVisibilityResponse(BaseModel):
    """Response for PUT /api/knowledge/facts/{fact_id}/visibility."""

    success: bool
    fact_id: str
    visibility: Optional[str] = None



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
    evidence: Optional[List[Any]] = None
    verification_method: Optional[str] = None
    kb_source: Optional[str] = None



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
    retention_days: Optional[int] = None



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

    results: Optional[List[Any]] = None
    total_results: Optional[int] = None
    query: Optional[str] = None
    mode: Optional[str] = None
    user_id: Optional[str] = None
    filtered_by_permissions: Optional[bool] = None



class KnowledgeAccessibleScopesResponse(BaseModel):
    """Response for GET /knowledge/search/accessible-scopes."""

    user_id: Optional[str] = None
    organization_id: Optional[str] = None
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
# workflow_export.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------
