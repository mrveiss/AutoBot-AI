# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code review, git, skills, database, template, log, voice, access-control, MCP, and file-sandbox schemas.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from api.schemas_common import SuccessMessageResponse


# ---------------------------------------------------------------------------
# Code schemas
# ---------------------------------------------------------------------------

class TemplatesRootResponse(BaseModel):
    """Response for GET / (templates root)."""

    message: str
    endpoints: Dict[str, str]



class TemplateListResponse(BaseModel):
    """Response for GET /templates."""

    success: bool
    templates: List[Any]
    total: int



class TemplateSecretsUsageResponse(BaseModel):
    """Response for GET /templates/secrets-usage."""

    success: bool
    secrets_usage: Dict[str, Any]



class TemplateSearchResponse(BaseModel):
    """Response for GET /templates/search."""

    success: bool
    query: str
    results: List[Any]
    total: int



class TemplateCategoriesResponse(BaseModel):
    """Response for GET /templates/categories."""

    success: bool
    categories: List[Any]



class TemplateStatsResponse(BaseModel):
    """Response for GET /templates/stats."""

    success: bool
    statistics: Dict[str, Any]



class TemplateDetailResponse(BaseModel):
    """Response for GET /templates/{template_id}."""

    success: bool
    template: Dict[str, Any]



class TemplatePreviewResponse(BaseModel):
    """Response for GET /templates/{template_id}/preview."""

    success: bool
    template_id: str
    template_name: str
    description: str
    estimated_duration_minutes: Optional[int] = None
    agents_involved: List[str]
    workflow_preview: List[str]
    variables_used: Dict[str, Any]
    total_steps: int
    approval_required_steps: int



class TemplateValidationResponse(BaseModel):
    """Response for POST /templates/{template_id}/validate."""

    success: bool
    template_id: str
    validation: Dict[str, Any]



class TemplateCreateWorkflowResponse(BaseModel):
    """Response for POST /templates/{template_id}/create-workflow.

    success=False path includes validation dict; success=True includes workflow.
    Extra fields allowed to handle both paths.
    """

    model_config = {"extra": "allow"}

    success: bool



class TemplateExecuteResponse(SuccessMessageResponse):
    """Response for POST /templates/{template_id}/execute."""

    workflow_id: str
    template_info: Dict[str, Any]


# ---------------------------------------------------------------------------
# state_tracking.py schemas
# ---------------------------------------------------------------------------



class CodeReviewAnalyzeResponse(BaseModel):
    """Response for GET /analyze (code review diff analysis).

    Returns either the no-data envelope or the full analysis payload.
    Extra fields allowed to cover both shapes.
    """

    model_config = {"extra": "allow"}

    status: str



class CodeReviewReviewByIdResponse(BaseModel):
    """Response for GET /review/{review_id}.

    Shape is the opaque result_payload dict stored in Redis — allow extra fields.
    """

    model_config = {"extra": "allow"}



class CodeReviewFileResponse(BaseModel):
    """Response for POST /review-file."""

    status: str
    file_path: Optional[str] = None
    timestamp: str
    total_comments: int
    score: float
    comments: List[Any]
    summary: Dict[str, Any]



class CodeReviewHistoryResponse(BaseModel):
    """Response for GET /history.

    Returns either no-data envelope or success+reviews shape.
    Extra fields allowed.
    """

    model_config = {"extra": "allow"}

    status: str



class CodeReviewMetricsResponse(BaseModel):
    """Response for GET /metrics — no-data envelope."""

    model_config = {"extra": "allow"}

    status: str



class CodeReviewFeedbackResponse(BaseModel):
    """Response for POST /feedback."""

    status: str
    feedback: Dict[str, Any]



class CodeReviewSummaryResponse(BaseModel):
    """Response for GET /summary — no-data envelope."""

    model_config = {"extra": "allow"}

    status: str



class CodeReviewPatternToggleResponse(BaseModel):
    """Response for POST /patterns/toggle."""

    status: str
    pattern_id: str
    enabled: bool



class CodeReviewPatternPreferencesResponse(BaseModel):
    """Response for GET /patterns/preferences."""

    patterns: Dict[str, Any]


# ---------------------------------------------------------------------------
# metrics.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class LogSourcesResponse(BaseModel):
    """Response for GET /logs/sources."""

    file_logs: List[Any]
    container_logs: List[Any]
    total_sources: int



class LogRecentResponse(BaseModel):
    """Response for GET /logs/recent."""

    entries: List[Any]
    count: int
    limit: int
    source: str
    error: Optional[str] = None



class LogReadResponse(BaseModel):
    """Response for GET /logs/read/{filename}."""

    filename: str
    lines: List[str]
    total_lines: int
    offset: int
    count: int



class LogContainerResponse(BaseModel):
    """Response for GET /logs/container/{service}."""

    service: str
    container: str
    lines: List[Any]
    count: int
    source_type: str



class LogUnifiedResponse(BaseModel):
    """Response for GET /logs/unified."""

    logs: List[Any]
    total_count: int
    sources_included: List[str]



class LogSearchResponse(BaseModel):
    """Response for GET /logs/search."""

    query: str
    results: List[Any]
    count: int
    truncated: bool


# ---------------------------------------------------------------------------
# git_mcp.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class GitMCPOperationResponse(BaseModel):
    """Shared response for all POST /git/mcp/* operation endpoints.

    All git MCP operation endpoints return the same stable shape.
    Extra fields (repository-specific) are allowed through.
    """

    model_config = {"extra": "allow"}

    success: bool
    repository: str
    output: str
    timestamp: str
    errors: Optional[str] = None



class GitMCPInfoResponse(BaseModel):
    """Response for GET /git/mcp/info."""

    success: bool
    repositories: List[Any]
    repository_count: int
    timestamp: str



class GitMCPServiceStatusResponse(BaseModel):
    """Response for GET /git/mcp/service_status."""

    status: str
    service: str
    rate_limit: Dict[str, Any]
    configuration: Dict[str, Any]
    timestamp: str


# ---------------------------------------------------------------------------
# analytics_llm_patterns.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class VoiceListenResponse(BaseModel):
    """Response for POST /voice/listen (success path)."""

    message: str
    text: str



class VoiceSpeakResponse(BaseModel):
    """Response for POST /voice/speak (success path)."""

    message: str



class VoiceDeleteResponse(BaseModel):
    """Response for DELETE /voice/voices/{voice_id} (success path)."""

    deleted: str



class VoiceTranscribeResponse(BaseModel):
    """Response for POST /voice/transcribe."""

    text: str
    language: str
    confidence: float


# ---------------------------------------------------------------------------
# skills_governance.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class SkillsGapResponse(BaseModel):
    """Response for POST /skills-governance/gaps.

    Both success and failure paths share this shape.
    """

    success: bool
    errors: Optional[List[str]] = None
    draft: Optional[Any] = None
    draft_id: Optional[str] = None
    name: Optional[str] = None
    tools_found: Optional[List[str]] = None



class SkillsDraftListItem(BaseModel):
    """Single draft entry in the list response."""

    id: str
    name: str
    version: Optional[Any] = None
    gap_reason: Optional[str] = None
    created_at: Optional[Any] = None
    trust_level: Optional[Any] = None



class SkillsDraftTestResponse(BaseModel):
    """Response for POST /skills-governance/drafts/{skill_id}/test."""

    valid: bool
    errors: List[Any]
    tools_found: List[str]



class SkillsDraftPromoteResponse(BaseModel):
    """Response for POST /skills-governance/drafts/{skill_id}/promote."""

    promoted: bool
    path: str
    name: str



class SkillsApprovalItem(BaseModel):
    """Single approval entry in the list response."""

    id: str
    skill_id: str
    requested_by: Optional[str] = None
    requested_at: Optional[Any] = None
    reason: Optional[str] = None
    status: str



class SkillsApprovalDecisionResponse(BaseModel):
    """Response for POST /skills-governance/approvals/{approval_id}."""

    approval_id: str
    status: str



class SkillsGovernanceConfigResponse(BaseModel):
    """Response for GET /skills-governance/ (may return default dict or full config).

    Extra fields allowed to cover the default-dict path.
    """

    model_config = {"extra": "allow"}

    mode: Any



class SkillsGovernanceUpdateResponse(BaseModel):
    """Response for PUT /skills-governance/."""

    mode: Any



# ---------------------------------------------------------------------------
# mcp_registry.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class MCPRegistryToolsResponse(BaseModel):
    """Response for GET /tools — aggregated tool list from all bridges."""

    status: str
    total_tools: int
    total_bridges: int
    healthy_bridges: int
    tools: List[Any]
    last_updated: str
    cached: bool



class MCPRegistryBridgesResponse(BaseModel):
    """Response for GET /bridges — bridge health and metadata."""

    status: str
    total_bridges: int
    healthy_bridges: int
    bridges: List[Any]
    last_checked: str
    cached: bool



class MCPRegistryCacheInvalidateResponse(BaseModel):
    """Response for POST /cache/invalidate."""

    status: str
    message: str
    timestamp: str
    cache_stats: Dict[str, Any]



class MCPRegistryCacheStatsResponse(BaseModel):
    """Response for GET /cache/stats."""

    status: str
    cache: Dict[str, Any]
    timestamp: str



class MCPRegistryToolDetailResponse(BaseModel):
    """Response for GET /tools/{bridge_name}/{tool_name}."""

    status: str
    tool: Dict[str, Any]



class MCPRegistryHealthResponse(BaseModel):
    """Response for GET /health."""

    status: str
    total_bridges: int
    healthy_bridges: int
    checks: List[Any]
    cache_stats: Dict[str, Any]
    timestamp: str



class MCPRegistryStatsResponse(BaseModel):
    """Response for GET /stats."""

    status: str
    overview: Dict[str, Any]
    tools_by_bridge: Dict[str, Any]
    bridge_health: Dict[str, Any]
    available_features: List[str]
    cache: Dict[str, Any]
    timestamp: str



class MCPRegistryInfoResponse(BaseModel):
    """Response for GET / — registry info and architecture overview."""

    name: str
    version: str
    description: str
    architecture: Dict[str, Any]
    endpoints: Dict[str, str]
    performance: Dict[str, Any]
    note: str


# ---------------------------------------------------------------------------
# feature_flags.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class AccessControlMetricsResponse(BaseModel):
    """Response for GET /access-control/metrics."""

    success: bool
    data: Optional[Dict[str, Any]] = None



class AccessControlEndpointMetricsResponse(BaseModel):
    """Response for GET /access-control/endpoint/{endpoint:path}."""

    success: bool
    data: Optional[Any] = None



class AccessControlUserMetricsResponse(BaseModel):
    """Response for GET /access-control/user/{username}."""

    success: bool
    data: Optional[Any] = None



class AccessControlCleanupResponse(SuccessMessageResponse):
    """Response for POST /access-control/cleanup."""


# ---------------------------------------------------------------------------
# http_client_mcp.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class HTTPClientMCPStatusResponse(BaseModel):
    """Response for GET /mcp/status — HTTP client service status."""

    status: str
    service: str
    rate_limit: Dict[str, Any]
    configuration: Dict[str, Any]
    timestamp: str



class HTTPRequestResultResponse(BaseModel):
    """Response for POST /mcp/get|post|put|patch|delete|head.

    Shape is the standardised HTTP response dict from _build_http_response().
    Extra fields allowed to handle dynamic headers dict.
    """

    model_config = {"extra": "allow"}

    success: bool
    status_code: int
    url: str
    method: str
    is_json: bool
    timestamp: str


# ---------------------------------------------------------------------------
# database_mcp.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class DatabaseQueryResponse(BaseModel):
    """Response for POST /mcp/query."""

    success: bool
    database: str
    query: str
    row_count: int
    columns: List[str]
    results: List[Any]
    timestamp: str



class DatabaseExecuteResponse(BaseModel):
    """Response for POST /mcp/execute."""

    success: bool
    database: str
    statement: str
    rows_affected: int
    timestamp: str



class DatabaseListTablesResponse(BaseModel):
    """Response for POST /mcp/list_tables."""

    success: bool
    database: str
    table_count: int
    tables: List[Any]
    timestamp: str



class DatabaseDescribeSchemaResponse(BaseModel):
    """Response for POST /mcp/describe_schema."""

    success: bool
    database: str
    table_count: int
    schemas: Dict[str, Any]
    timestamp: str



class DatabaseListDatabasesResponse(BaseModel):
    """Response for GET /mcp/list_databases."""

    success: bool
    database_count: int
    databases: List[Any]
    timestamp: str



class DatabaseStatisticsResponse(BaseModel):
    """Response for POST /mcp/statistics."""

    success: bool
    database: str
    statistics: Dict[str, Any]
    timestamp: str



class DatabaseMCPStatusResponse(BaseModel):
    """Response for GET /mcp/status — database service status."""

    status: str
    service: str
    rate_limit: Dict[str, Any]
    configuration: Dict[str, Any]
    database_availability: Dict[str, Any]
    timestamp: str


# ---------------------------------------------------------------------------
# knowledge_search_aggregator.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class FileSandboxViewResponse(BaseModel):
    """Response for GET /files/view/{path}."""

    file_info: Any
    content: Optional[str] = None
    is_text: bool



class FileSandboxRenameResponse(BaseModel):
    """Response for POST /files/rename."""

    message: str
    item_info: Any



class FileSandboxPreviewResponse(BaseModel):
    """Response for GET /files/preview."""

    type: str
    url: str
    content: Optional[str] = None
    mime_type: Optional[str] = None
    size: int
    name: str



class FileSandboxDeleteResponse(BaseModel):
    """Response for DELETE /files/delete."""

    message: str



class FileSandboxCreateDirResponse(BaseModel):
    """Response for POST /files/create_directory."""

    message: str
    directory_info: Any



class FileSandboxTreeResponse(BaseModel):
    """Response for GET /files/tree."""

    path: str
    tree: List[Any]



class FileSandboxStatsResponse(BaseModel):
    """Response for GET /files/stats."""

    sandbox_root: str
    total_files: int
    total_directories: int
    total_size: int
    total_size_mb: float
    max_file_size_mb: int
    allowed_extensions: List[str]


# ---------------------------------------------------------------------------
# playwright.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class PlaywrightStatusResponse(BaseModel):
    """Response for GET /playwright/status.

    Shape from service.get_service_status() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}

    service: str
    status: str


class PlaywrightHealthResponse(BaseModel):
    """Response for GET /playwright/health."""

    status: str
    ready: bool
    service: str
    message: str


class PlaywrightQuickTestResponse(BaseModel):
    """Response for POST /playwright/automation/quick-test."""

    status: str
    message: str
    check_logs: str
    tests: List[str]


class PlaywrightBrowserActionResponse(BaseModel):
    """Response for POST /playwright/navigate, /reload, /back, /forward, /interact,
    and /worker-screenshot.

    Shape comes from the Browser VM and is opaque; extra fields allowed.
    """

    model_config = {"extra": "allow"}


class PlaywrightWorkerStatusResponse(BaseModel):
    """Response for GET /playwright/worker-status."""

    status: str
    browser_connected: bool
    page_open: Optional[bool] = None


class PlaywrightCapabilitiesResponse(BaseModel):
    """Response for GET /playwright/capabilities."""

    service: str
    integration: str
    capabilities: Dict[str, Any]
    endpoints: List[str]


# ---------------------------------------------------------------------------
# research_browser.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class ResearchBrowserHealthResponse(BaseModel):
    """Response for GET /research-browser/health."""

    status: str
    service: str
    browser_service_url: Optional[str] = None
    detail: Optional[str] = None
    timestamp: str
