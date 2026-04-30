# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code review, git, skills, database, template, log, voice, access-control, MCP, and file-sandbox schemas.
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from autobot_shared.ssot_config import PROJECT_ROOT, config as _ssot_config
from constants.threshold_constants import QueryDefaults
from type_defs.common import JSONObject

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


class RegionRect(BaseModel):
    """Bounding-box coordinates for a detected page region."""

    x: float
    y: float
    w: float
    h: float


class PageRegion(BaseModel):
    """A single interactive region detected on a browser page."""

    selector: str
    xpath: str
    rect: RegionRect
    text_preview: str
    role: str


class SnapshotWithRegionsResponse(BaseModel):
    """Response for POST /playwright/snapshot-with-regions (#5136)."""

    screenshot: str  # base64 PNG
    regions: List[PageRegion]
    viewport: Dict[str, Any]  # width, height, devicePixelRatio


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


# ---------------------------------------------------------------------------
# integration_cicd.py schemas  (Issue #5987)
# ---------------------------------------------------------------------------


class CICDConnectionTestResponse(BaseModel):
    """Response for POST /test-connection (CI/CD)."""

    status: str
    message: str
    details: Optional[Dict[str, Any]] = None


class CICDProvidersListResponse(BaseModel):
    """Response for GET /providers (CI/CD) — list returned directly."""

    model_config = {"extra": "allow"}


class CICDPipelinesResponse(BaseModel):
    """Response for GET /{provider}/pipelines — opaque provider payload."""

    model_config = {"extra": "allow"}


class CICDPipelineStatusResponse(BaseModel):
    """Response for GET /{provider}/pipelines/{pipeline_id}/status — opaque."""

    model_config = {"extra": "allow"}


class CICDPipelineTriggerResponse(BaseModel):
    """Response for POST /{provider}/pipelines/{pipeline_id}/trigger — opaque."""

    model_config = {"extra": "allow"}


class CICDPipelineLogsResponse(BaseModel):
    """Response for GET /{provider}/pipelines/{pipeline_id}/logs — opaque."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# integration_database.py schemas  (Issue #5987)
# ---------------------------------------------------------------------------


class IntegrationDatabaseConnectionTestResponse(BaseModel):
    """Response for POST /test-connection (database integration).

    Returns health.dict() from integration.test_connection().
    Extra fields allowed for provider-specific fields.
    """

    model_config = {"extra": "allow"}


class IntegrationDatabaseProvidersResponse(BaseModel):
    """Response for GET /providers (database integration)."""

    providers: List[Any]
    count: int


class IntegrationDatabaseQueryResponse(BaseModel):
    """Response for POST /{provider}/query — opaque integration payload."""

    model_config = {"extra": "allow"}


class IntegrationMongoQueryResponse(BaseModel):
    """Response for POST /mongodb/query-collection — opaque payload."""

    model_config = {"extra": "allow"}


class IntegrationDatabaseListResponse(BaseModel):
    """Response for POST /{provider}/databases — opaque list payload."""

    model_config = {"extra": "allow"}


class IntegrationTablesListResponse(BaseModel):
    """Response for POST /{provider}/tables — opaque list payload."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# integration_monitoring.py schemas  (Issue #5987)
# ---------------------------------------------------------------------------


class MonitoringConnectionTestResponse(BaseModel):
    """Response for POST /test-connection (monitoring)."""

    provider: str
    status: str
    message: str
    details: Optional[Dict[str, Any]] = None


class MonitoringProviderItem(BaseModel):
    """Single provider entry in monitoring providers list."""

    name: str
    display_name: str
    required_credentials: List[str]


class MonitoringProvidersResponse(BaseModel):
    """Response for GET /providers (monitoring)."""

    providers: List[MonitoringProviderItem]


class MonitoringHostsResponse(BaseModel):
    """Response for GET /{provider}/hosts — opaque provider payload."""

    model_config = {"extra": "allow"}


class MonitoringMetricsResponse(BaseModel):
    """Response for POST /{provider}/metrics — opaque provider payload."""

    model_config = {"extra": "allow"}


class MonitoringAlertsResponse(BaseModel):
    """Response for GET /{provider}/alerts — opaque provider payload."""

    model_config = {"extra": "allow"}


class MonitoringEventsResponse(BaseModel):
    """Response for POST /{provider}/events — opaque provider payload."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# integration_project_management.py schemas  (Issue #5987)
# ---------------------------------------------------------------------------


class PMProjectsResponse(BaseModel):
    """Response for GET /{provider}/projects — opaque provider payload."""

    model_config = {"extra": "allow"}


class PMIssuesResponse(BaseModel):
    """Response for GET /{provider}/issues — opaque provider payload."""

    model_config = {"extra": "allow"}


class PMIssueCreateResponse(BaseModel):
    """Response for POST /{provider}/issues — opaque provider payload."""

    model_config = {"extra": "allow"}


class PMIssueUpdateResponse(BaseModel):
    """Response for PATCH /{provider}/issues/{issue_id} — opaque payload."""

    model_config = {"extra": "allow"}


class PMIssueSearchResponse(BaseModel):
    """Response for GET /{provider}/search — opaque provider payload."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# integration_cloud.py schemas  (Issue #5987)
# ---------------------------------------------------------------------------


class CloudConnectionTestResponse(BaseModel):
    """Response for POST /test-connection (cloud) — provider health dict."""

    provider: str
    status: str
    latency_ms: Optional[float] = None
    message: str
    details: Optional[Dict[str, Any]] = None
    last_checked: str


class CloudResourcesResponse(BaseModel):
    """Response for GET /{provider}/resources — opaque compute resource list."""

    model_config = {"extra": "allow"}


class CloudStorageResponse(BaseModel):
    """Response for GET /{provider}/storage — opaque storage resource list."""

    model_config = {"extra": "allow"}


class CloudAccountInfoResponse(BaseModel):
    """Response for GET /{provider}/account — opaque account info payload."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# integration_version_control.py schemas  (Issue #5987)
# ---------------------------------------------------------------------------


class VCSRepositoriesResponse(BaseModel):
    """Response for GET /{provider}/repositories — opaque provider list."""

    model_config = {"extra": "allow"}


class VCSBranchesResponse(BaseModel):
    """Response for GET /{provider}/repositories/{repo_id}/branches — opaque."""

    model_config = {"extra": "allow"}


class VCSPullRequestsResponse(BaseModel):
    """Response for GET /{provider}/repositories/{repo_id}/pull-requests — opaque."""

    model_config = {"extra": "allow"}


class VCSCommitInfoResponse(BaseModel):
    """Response for GET /{provider}/repositories/{repo_id}/commits — opaque."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# sandbox.py schemas  (Issue #5987)
# ---------------------------------------------------------------------------


class SandboxExecutionResponse(BaseModel):
    """Response for POST /execute, /execute/script, /execute/batch.

    Returns success_response() or error_response() envelope — opaque.
    Extra fields allowed to handle both success and error paths.
    """

    model_config = {"extra": "allow"}


class SandboxStatsResponse(BaseModel):
    """Response for GET /stats — sandbox stats envelope."""

    model_config = {"extra": "allow"}


class SandboxSecurityLevelsResponse(BaseModel):
    """Response for GET /security-levels — security level descriptions."""

    model_config = {"extra": "allow"}


class SandboxExamplesResponse(BaseModel):
    """Response for GET /examples — sandbox usage examples."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# code_intelligence.py schemas  (Issue #5987)
# ---------------------------------------------------------------------------


class CodeReportResponse(BaseModel):
    """Response for GET /security/report and GET /performance/report.

    Delegates to _generate_report_response() which returns a JSONResponse
    with status, timestamp, path, format, and report fields.
    Extra fields allowed for both json and markdown formats.
    """

    model_config = {"extra": "allow"}

    status: str
    path: str
    format: str


# ---------------------------------------------------------------------------
# code_search.py schemas  (Issue #5987)
# ---------------------------------------------------------------------------


class CodeSearchGetResponse(BaseModel):
    """Response for GET /search — delegates to search_code() POST handler.

    Shape mirrors SearchResponse: results, stats, query, search_type.
    Extra fields allowed for language_filter and dynamic stats.
    """

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# prometheus_mcp.py schemas  (Issue #5991)
# ---------------------------------------------------------------------------


class PrometheusMCPToolItem(BaseModel):
    """Single MCP tool descriptor returned by GET /prometheus/mcp/tools."""

    model_config = {"extra": "allow"}

    name: str
    description: str
    input_schema: Any



class PrometheusMCPExecuteResponse(BaseModel):
    """Response for POST /prometheus/mcp/{tool_name}.

    Shape varies by tool and includes dynamic metrics data; extra fields allowed.    """

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# skills.py schemas  (Issue #5987)
# ---------------------------------------------------------------------------


class SkillToggleResponse(BaseModel):
    """Response for POST /skills/{name}/enable and /skills/{name}/disable."""

    model_config = {"extra": "allow"}

    success: bool


# ---------------------------------------------------------------------------
# manual_mcp.py schemas  (Issue #5991)
# ---------------------------------------------------------------------------


class ManualMCPToolItem(BaseModel):
    """Single MCP tool descriptor returned by GET /manual/mcp/tools."""

    model_config = {"extra": "allow"}


class SkillConfigUpdateResponse(BaseModel):
    """Response for PUT /skills/{name}/config."""

    model_config = {"extra": "allow"}

    success: bool


class SkillExecuteResponse(BaseModel):
    """Response for POST /skills/{name}/execute."""

    model_config = {"extra": "allow"}

    success: bool


# ---------------------------------------------------------------------------
# skills_repos.py schemas  (Issue #5987)
# ---------------------------------------------------------------------------


class SkillRepoAddResponse(BaseModel):
    """Response for POST /skill-repos/ — register a repository."""

    id: str
    name: str
    status: str


class SkillRepoItem(BaseModel):
    """Single skill repository entry in the list response."""

    id: str
    name: str
    url: str
    repo_type: Any
    auto_sync: bool
    sync_interval: int
    last_synced: Optional[Any] = None
    skill_count: Optional[int] = None
    status: Optional[str] = None


class SkillRepoSyncResponse(BaseModel):
    """Response for POST /skill-repos/{repo_id}/sync."""

    synced: int
    repo: str


class SkillRepoBrowseResponse(BaseModel):
    """Response for GET /skill-repos/{repo_id}/browse."""

    packages: List[str]
    count: int


# ---------------------------------------------------------------------------
# skills/external catalog schemas  (Issue #5063)
# ---------------------------------------------------------------------------


class SkillCatalogEntry(BaseModel):
    """Single skill entry returned by GET /skills/catalog."""

    name: str
    version: Optional[str] = None
    description: Optional[str] = None
    install_action: Optional[str] = None


class SkillCatalogResponse(BaseModel):
    """Response for GET /skills/catalog."""

    catalog_url: str
    page: int
    page_size: int
    skills: List[SkillCatalogEntry]
    total: int


class SkillInstallResponse(BaseModel):
    """Response for POST /skills/catalog/{name}/install."""

    success: bool
    id: str
    name: str
    version: str
    trust_level: str


class SkillExternalSyncResponse(BaseModel):
    """Response for POST /skills/repos/{id}/sync via SkillManager.sync_external_repo."""

    imported: int
    packages: List[Any]


# permissions.py schemas are defined in schemas_system.py (PermissionRuleMutateResponse,
# PermissionClearApprovalsResponse, PermissionStoreApprovalResponse,
# PermissionMemoryStatsResponse) — already wired in permissions.py.


# ---------------------------------------------------------------------------
# filesystem_mcp schemas (#6042)
# ---------------------------------------------------------------------------


class FilesystemReadTextResponse(BaseModel):
    """Response for POST /mcp/read_text_file."""

    success: bool
    path: str
    content: str
    lines: int
    size_bytes: int


class FilesystemReadMediaResponse(BaseModel):
    """Response for POST /mcp/read_media_file."""

    success: bool
    path: str
    mime_type: str
    base64_data: str
    size_bytes: int


class FilesystemReadMultipleResponse(BaseModel):
    """Response for POST /mcp/read_multiple_files."""

    success: bool
    files_read: int
    files_failed: int
    results: List[Dict]
    errors: Optional[List[Dict]] = None


class FilesystemWriteFileResponse(BaseModel):
    """Response for POST /mcp/write_file."""

    success: bool
    path: str
    size_bytes: int
    message: str


class FilesystemEditFileResponse(BaseModel):
    """Response for POST /mcp/edit_file."""

    success: bool
    path: str
    edits_applied: int
    dry_run: bool
    changes: List[Dict]
    size_before: int
    size_after: int


class FilesystemCreateDirectoryResponse(BaseModel):
    """Response for POST /mcp/create_directory."""

    success: bool
    path: str
    message: str


class FilesystemListDirectoryResponse(BaseModel):
    """Response for POST /mcp/list_directory."""

    success: bool
    path: str
    entry_count: int
    entries: List[str]


class FilesystemListDirectoryWithSizesResponse(BaseModel):
    """Response for POST /mcp/list_directory_with_sizes."""

    success: bool
    path: str
    entry_count: int
    sorted_by: Optional[str] = None
    entries: List[Dict]


class FilesystemMoveFileResponse(BaseModel):
    """Response for POST /mcp/move_file."""

    success: bool
    source: str
    destination: str
    message: str


class FilesystemSearchFilesResponse(BaseModel):
    """Response for POST /mcp/search_files."""

    success: bool
    search_path: str
    pattern: str
    matches_found: int
    matches: List[str]


class FilesystemDirectoryTreeResponse(BaseModel):
    """Response for POST /mcp/directory_tree."""

    success: bool
    root_path: str
    tree: Dict


class FilesystemFileInfoResponse(BaseModel):
    """Response for POST /mcp/get_file_info."""

    success: bool
    path: str
    name: str
    type: str
    size_bytes: int
    created: str
    modified: str
    accessed: str
    permissions: str
    mime_type: Optional[str] = None


class FilesystemSecurityInfo(BaseModel):
    path_traversal_blocked: bool
    symlink_validation: bool
    max_file_size_bytes: int


class FilesystemListAllowedResponse(BaseModel):
    """Response for GET /mcp/list_allowed_directories."""

    success: bool
    allowed_directories: List[str]
    directory_count: int
    security_info: FilesystemSecurityInfo


class MCPTool(BaseModel):
    """Standard MCP tool definition (shared across all MCP endpoint files)."""

    name: str
    description: str
    input_schema: JSONObject


class ReadTextFileRequest(BaseModel):
    """Request model for reading text files."""

    path: str = Field(..., description="Absolute path to file")
    head: Optional[int] = Field(None, description="Read only first N lines")
    tail: Optional[int] = Field(None, description="Read only last N lines")


class ReadMediaFileRequest(BaseModel):
    """Request model for reading media files (images, audio)."""

    path: str = Field(..., description="Absolute path to media file")


class ReadMultipleFilesRequest(BaseModel):
    """Request model for reading multiple files."""

    paths: List[str] = Field(..., description="List of absolute file paths")


class WriteFileRequest(BaseModel):
    """Request model for writing files."""

    path: str = Field(..., description="Absolute path to file")
    content: str = Field(..., description="File content to write")


class EditFileRequest(BaseModel):
    """Request model for editing files."""

    path: str = Field(..., description="Absolute path to file")
    edits: List[Dict[str, str]] = Field(
        ..., description="List of {old_text, new_text} edits"
    )
    dry_run: Optional[bool] = Field(False, description="Preview changes without applying")


class CreateDirectoryRequest(BaseModel):
    """Request model for creating directories."""

    path: str = Field(..., description="Absolute path to directory")


class ListDirectoryRequest(BaseModel):
    """Request model for listing directory contents."""

    path: str = Field(..., description="Absolute path to directory")


class ListDirectoryWithSizesRequest(BaseModel):
    """Request model for listing directory with sizes."""

    path: str = Field(..., description="Absolute path to directory")
    sort_by: Optional[str] = Field("name", description="Sort by 'name' or 'size'")


class MoveFileRequest(BaseModel):
    """Request model for moving/renaming files."""

    source: str = Field(..., description="Source path")
    destination: str = Field(..., description="Destination path")


class SearchFilesRequest(BaseModel):
    """Request model for searching files."""

    path: str = Field(..., description="Directory to search")
    pattern: str = Field(..., description="Search pattern (e.g., '*.py')")
    exclude_patterns: Optional[List[str]] = Field(None, description="Patterns to exclude")


class DirectoryTreeRequest(BaseModel):
    """Request model for directory tree."""

    path: str = Field(..., description="Root directory path")


class GetFileInfoRequest(BaseModel):
    """Request model for file metadata."""

    path: str = Field(..., description="File or directory path")


# ---------------------------------------------------------------------------
# code_intelligence response schemas (#6042)
# ---------------------------------------------------------------------------


class SuggestionItem(BaseModel):
    id: str
    type: str
    priority: str
    title: str
    description: str
    impact: str


class SuggestionsResponse(BaseModel):
    suggestions: List[SuggestionItem]


class FindingsPlaceholderResponse(BaseModel):
    findings: List[Any]
    score: Optional[float]
    message: str


class CodeIntelligenceTaskStatusResponse(BaseModel):
    """Generic task status returned by BackgroundTaskManager (code_intelligence)."""

    status: str
    task_id: Optional[str] = None
    progress: Optional[float] = None
    message: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class StartTaskResponse(BaseModel):
    task_id: str
    status: str


class ClearStuckResponse(BaseModel):
    cleared_count: int
    message: str


class CachedSecurityScoreResponse(BaseModel):
    status: str
    from_cache: Optional[bool] = None
    completed_at: Optional[str] = None
    security_score: Optional[float] = None
    grade: Optional[str] = None
    risk_level: Optional[str] = None
    status_message: Optional[str] = None
    total_findings: Optional[int] = None
    critical_issues: Optional[int] = None
    high_issues: Optional[int] = None
    files_analyzed: Optional[int] = None
    severity_breakdown: Optional[Dict[str, Any]] = None
    owasp_breakdown: Optional[Dict[str, Any]] = None
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# playwright request schemas (#6042)
# ---------------------------------------------------------------------------


class PlaywrightSearchRequest(BaseModel):
    query: str
    search_engine: str = "duckduckgo"
    max_results: int = 5


class PlaywrightScreenshotRequest(BaseModel):
    url: str
    full_page: bool = True
    wait_timeout: int = 5000


class PlaywrightNavigateRequest(BaseModel):
    url: str
    wait_until: str = "networkidle"
    timeout: int = 30000


class PlaywrightReloadRequest(BaseModel):
    wait_until: str = "networkidle"


class PlaywrightInteractRequest(BaseModel):
    action: str
    x: Optional[float] = None
    y: Optional[float] = None
    deltaX: float = 0
    deltaY: float = 0
    text: Optional[str] = None


# ---------------------------------------------------------------------------
# ide_integration response schemas (#6042) — clean IDE-prefixed classes only
# (Generic LSP types Position/Range/Diagnostic etc. deferred to follow-up PR)
# ---------------------------------------------------------------------------


class IDERulesResponse(BaseModel):
    """Response for GET /rules."""

    rules: List[Dict[str, Any]]
    total: int
    enabled: int


class IDEConfigUpdateResponse(BaseModel):
    """Response for PUT /config."""

    updated: bool


class IDECategoryItem(BaseModel):
    """A single category entry."""

    id: str
    name: str


class IDECategoriesResponse(BaseModel):
    """Response for GET /categories."""

    categories: List[IDECategoryItem]


class IDESeverityItem(BaseModel):
    """A single severity entry."""

    id: str
    name: str
    lsp_code: int


class IDESeveritiesResponse(BaseModel):
    """Response for GET /severities."""

    severities: List[IDESeverityItem]


class IDEBatchAnalyzeResponse(BaseModel):
    """Response for POST /batch-analyze."""

    results: List[Any]
    files_analyzed: int
    total_issues: int
    errors: int


class IDEHealthResponse(BaseModel):
    """Response for GET /health."""

    status: str
    rules_loaded: int
    disabled_rules: int
    cache_size: int



# ---------------------------------------------------------------------------
# openai_compat.py schemas (#6042)
# ---------------------------------------------------------------------------


class OAIMessage(BaseModel):
    role: str
    content: str
    name: Optional[str] = None


class OAIStreamOptions(BaseModel):
    include_usage: bool = False


class ChatCompletionRequest(BaseModel):
    model: str = "autobot-default"
    messages: List[OAIMessage]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stop: Optional[List[str]] = None
    stream: bool = False
    stream_options: Optional[OAIStreamOptions] = None
    n: int = Field(default=1, ge=1)
    user: Optional[str] = None


class OAIChoiceMessage(BaseModel):
    role: str
    content: str


class OAIChoice(BaseModel):
    index: int
    message: OAIChoiceMessage
    finish_reason: str = "stop"


class OAIUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[OAIChoice]
    usage: OAIUsage


class OAIDeltaMessage(BaseModel):
    role: Optional[str] = None
    content: Optional[str] = None


class OAIStreamChoice(BaseModel):
    index: int
    delta: OAIDeltaMessage
    finish_reason: Optional[str] = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[OAIStreamChoice]
    usage: Optional[OAIUsage] = None


class OAIModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = 0
    owned_by: str = "autobot"


class OAIModelListResponse(BaseModel):
    object: str = "list"
    data: List[OAIModelCard]


# ---------------------------------------------------------------------------
# git_mcp.py request schemas (#6042)
# ---------------------------------------------------------------------------

_GIT_DEFAULT_REPO_PATH = str(PROJECT_ROOT)
_GIT_MAX_LOG_ENTRIES = 100
_GIT_SAFE_PATH_RE = re.compile(r"^[a-zA-Z0-9_\-./]+$")
_GIT_SHELL_METACHAR_RE = re.compile(r"[;&|`$]")
_GIT_COMMIT_REF_RE = re.compile(r"^[a-zA-Z0-9_\-./^~]+$")
_GIT_FULL_REF_RE = re.compile(r"^[a-zA-Z0-9_\-./^~:]+$")


class GitStatusRequest(BaseModel):
    """Git status request model"""

    repo_path: str = Field(default=_GIT_DEFAULT_REPO_PATH, description="Repository path (must be whitelisted)")
    short: Optional[bool] = Field(default=False, description="Use short format output")


class GitLogRequest(BaseModel):
    """Git log request model"""

    repo_path: str = Field(default=_GIT_DEFAULT_REPO_PATH, description="Repository path")
    max_count: Optional[int] = Field(
        default=QueryDefaults.DEFAULT_SEARCH_LIMIT,
        ge=1,
        le=_GIT_MAX_LOG_ENTRIES,
        description=f"Maximum number of commits (1-{_GIT_MAX_LOG_ENTRIES})",
    )
    oneline: Optional[bool] = Field(default=False, description="Use one-line format")
    file_path: Optional[str] = Field(default=None, description="Filter log to specific file")

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v):
        if v:
            if not _GIT_SAFE_PATH_RE.match(v):
                raise ValueError("Invalid file path format")
            if ".." in v:
                raise ValueError("Path traversal not allowed")
            if v.startswith("/"):
                raise ValueError("Absolute paths not allowed")
        return v

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, v):
        if not v or not v.strip():
            raise ValueError("Repository path cannot be empty")
        if _GIT_SHELL_METACHAR_RE.search(v):
            raise ValueError("Invalid characters in repository path")
        return v.strip()


class GitDiffRequest(BaseModel):
    """Git diff request model"""

    repo_path: str = Field(default=_GIT_DEFAULT_REPO_PATH, description="Repository path")
    staged: Optional[bool] = Field(default=False, description="Show staged changes only")
    file_path: Optional[str] = Field(default=None, description="Diff specific file")
    commit: Optional[str] = Field(default=None, description="Compare with specific commit")

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v):
        if v:
            if not _GIT_SAFE_PATH_RE.match(v):
                raise ValueError("Invalid file path format")
            if ".." in v:
                raise ValueError("Path traversal not allowed")
            if v.startswith("/"):
                raise ValueError("Absolute paths not allowed")
        return v

    @field_validator("commit")
    @classmethod
    def validate_commit_ref(cls, v):
        if v and not _GIT_COMMIT_REF_RE.match(v):
            raise ValueError("Invalid commit reference format")
        return v

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, v):
        if not v or not v.strip():
            raise ValueError("Repository path cannot be empty")
        if _GIT_SHELL_METACHAR_RE.search(v):
            raise ValueError("Invalid characters in repository path")
        return v.strip()


class GitBranchRequest(BaseModel):
    """Git branch request model"""

    repo_path: str = Field(default=_GIT_DEFAULT_REPO_PATH, description="Repository path")
    all_branches: Optional[bool] = Field(default=False, description="Show remote branches too")


class GitBlameRequest(BaseModel):
    """Git blame request model"""

    repo_path: str = Field(default=_GIT_DEFAULT_REPO_PATH, description="Repository path")
    file_path: str = Field(..., description="File to blame")
    line_start: Optional[int] = Field(default=None, ge=1, description="Starting line number")
    line_end: Optional[int] = Field(default=None, ge=1, description="Ending line number")

    @field_validator("file_path")
    @classmethod
    def validate_file_path(cls, v):
        if not _GIT_SAFE_PATH_RE.match(v):
            raise ValueError("Invalid file path format")
        if ".." in v:
            raise ValueError("Path traversal not allowed")
        if v.startswith("/"):
            raise ValueError("Absolute paths not allowed")
        return v

    @field_validator("repo_path")
    @classmethod
    def validate_repo_path(cls, v):
        if not v or not v.strip():
            raise ValueError("Repository path cannot be empty")
        if _GIT_SHELL_METACHAR_RE.search(v):
            raise ValueError("Invalid characters in repository path")
        return v.strip()


class GitShowRequest(BaseModel):
    """Git show request model"""

    repo_path: str = Field(default=_GIT_DEFAULT_REPO_PATH, description="Repository path")
    ref: str = Field(default="HEAD", description="Commit or ref to show (default: HEAD)")

    @field_validator("ref")
    @classmethod
    def validate_ref(cls, v):
        if not _GIT_FULL_REF_RE.match(v):
            raise ValueError("Invalid ref format")
        return v


# ---------------------------------------------------------------------------
# code_search.py schemas (#6042)
# ---------------------------------------------------------------------------


class CodeSearchIndexRequest(BaseModel):
    root_path: str
    force_reindex: bool = False


class CodeSearchRequest(BaseModel):
    query: str
    search_type: str = "semantic"
    language: Optional[str] = None
    max_results: int = 20


class CodeSearchResponse(BaseModel):
    results: List[dict]
    stats: dict
    query: str
    search_type: str


class CodeAnalyticsRequest(BaseModel):
    root_path: str
    include_patterns: Optional[List[str]] = None
    exclude_patterns: Optional[List[str]] = ["*.pyc", "*.git*", "*__pycache__*"]
    languages: Optional[List[str]] = None


class CodeDeclaration(BaseModel):
    name: str
    type: str
    file_path: str
    line_number: int
    usage_count: int
    definition: str
    context: str
    complexity_score: Optional[float] = None


class ReusabilityReport(BaseModel):
    declaration: CodeDeclaration
    reusability_score: float
    usage_patterns: List[str]
    refactor_suggestions: List[str]
    similar_declarations: List[str]


class CodeIntelAnalysisRequest(BaseModel):
    """Request model for code analysis (directory or inline code)."""

    path: Optional[str] = Field(default=None, description="Directory path to analyze")
    code: Optional[str] = Field(default=None, description="Inline code to analyze")
    language: Optional[str] = Field(default=None, description="Language of the inline code")
    filename: Optional[str] = Field(default=None, description="Virtual filename for inline code")
    include_suggestions: Optional[bool] = Field(default=None, description="Whether to include improvement suggestions")
    exclude_dirs: Optional[list] = Field(default=None, description="Directories to exclude from analysis")
    min_severity: Optional[str] = Field(default=None, description="Minimum severity level to include")


class CodeIntelQuickScanRequest(BaseModel):
    """Request for quick single-file scan."""

    file_path: str = Field(..., description="Path to Python file to analyze")


class CodeIntelSuggestionsRequest(BaseModel):
    """Request model for code suggestions."""

    code: str = Field(..., description="Code to get suggestions for")
    language: Optional[str] = Field(default="python", description="Programming language")


class RedisAnalysisRequest(BaseModel):
    """Request model for Redis optimization analysis."""

    path: str = Field(..., description="Directory or file path to analyze for Redis optimizations")
    exclude_patterns: Optional[list] = Field(default=None, description="Glob patterns to exclude from analysis")
    min_severity: Optional[str] = Field(default=None, description="Minimum severity level to include (info, low, medium, high, critical)")


class RedisFileScanRequest(BaseModel):
    """Request for scanning a single file for Redis optimizations."""

    file_path: str = Field(..., description="Path to Python file to analyze")


class SecurityAnalysisRequest(BaseModel):
    """Request model for security analysis."""

    path: str = Field(..., description="Directory path to analyze for security vulnerabilities")
    exclude_patterns: Optional[list] = Field(default=None, description="Patterns to exclude from analysis (e.g., ['test_*', 'venv'])")
    min_severity: Optional[str] = Field(default=None, description="Minimum severity level to include (info, low, medium, high, critical)")


class SecurityFileScanRequest(BaseModel):
    """Request for single file security scan."""

    file_path: str = Field(..., description="Path to Python file to analyze")


class PerformanceAnalysisRequest(BaseModel):
    """Request model for performance analysis."""

    path: str = Field(..., description="Directory path to analyze for performance issues")
    exclude_patterns: Optional[list] = Field(default=None, description="Patterns to exclude from analysis")
    min_severity: Optional[str] = Field(default=None, description="Minimum severity level to include")


class PerformanceFileScanRequest(BaseModel):
    """Request for single file performance scan."""

    file_path: str = Field(..., description="Path to Python file to analyze")


# ---------------------------------------------------------------------------
# database_mcp.py schemas
# ---------------------------------------------------------------------------

_DB_MCP_MAX_RESULT_ROWS = 1000
_DB_MCP_ALLOWED_DML_OPERATIONS = ("INSERT", "UPDATE", "DELETE")


class DatabaseMCPTool(BaseModel):
    """Standard MCP tool definition (database)"""

    name: str
    description: str
    input_schema: JSONObject


class SQLQueryRequest(BaseModel):
    """SQL query request model."""

    database: str = Field(..., description="Database name from whitelist")
    query: str = Field(..., description="SQL SELECT query (parameterized)")
    params: Optional[List[Any]] = Field(default=None, description="Query parameters for ? placeholders")
    limit: Optional[int] = Field(
        default=100,
        ge=1,
        le=_DB_MCP_MAX_RESULT_ROWS,
        description=f"Max rows to return (1-{_DB_MCP_MAX_RESULT_ROWS})",
    )

    @field_validator("query")
    @classmethod
    def validate_query_is_select(cls, v):
        normalized = v.strip().upper()
        if not normalized.startswith("SELECT"):
            raise ValueError(
                "Only SELECT queries allowed. Use execute_sql for modifications."
            )
        return v


class SQLExecuteRequest(BaseModel):
    """SQL execute request model (for INSERT/UPDATE/DELETE)."""

    database: str = Field(..., description="Database name from whitelist")
    statement: str = Field(..., description="SQL statement (INSERT/UPDATE/DELETE)")
    params: Optional[List[Any]] = Field(default=None, description="Statement parameters for ? placeholders")

    @field_validator("statement")
    @classmethod
    def validate_statement_type(cls, v):
        normalized = v.strip().upper()
        if not any(normalized.startswith(op) for op in _DB_MCP_ALLOWED_DML_OPERATIONS):
            raise ValueError(
                f"Only {', '.join(_DB_MCP_ALLOWED_DML_OPERATIONS)} statements allowed"
            )
        return v


class SchemaRequest(BaseModel):
    """Database schema request model."""

    database: str = Field(..., description="Database name from whitelist")
    table: Optional[str] = Field(default=None, description="Specific table to describe (optional)")


class TableListRequest(BaseModel):
    """List tables request model."""

    database: str = Field(..., description="Database name from whitelist")


# ---------------------------------------------------------------------------
# merge_conflict_resolution.py schemas
# ---------------------------------------------------------------------------


class ConflictAnalysisRequest(BaseModel):
    """Request model for conflict analysis."""

    file_path: str = Field(..., description="Path to file with merge conflicts")


class ConflictResolutionRequest(BaseModel):
    """Request model for conflict resolution."""

    file_path: str = Field(..., description="Path to file with merge conflicts")
    strategy: Optional[str] = Field(
        default=None,
        description=(
            "Resolution strategy: semantic_merge, accept_both, pattern_based, "
            "accept_ours, accept_theirs, manual_review"
        ),
    )
    safe_mode: bool = Field(default=True, description="Enable safe mode (require review for complex conflicts)")
    validate: bool = Field(default=True, description="Validate resolved code for syntax errors")


class RepositoryAnalysisRequest(BaseModel):
    """Request model for repository-wide conflict analysis."""

    repo_path: str = Field(..., description="Path to git repository")


class ApplyResolutionRequest(BaseModel):
    """Request model for applying a resolution to file."""

    file_path: str = Field(..., description="Path to file")
    resolved_content: str = Field(..., description="Resolved file content")
    create_backup: bool = Field(default=True, description="Create backup before applying")


# ---------------------------------------------------------------------------
# anti_pattern.py schemas
# ---------------------------------------------------------------------------


class AntiPatternAnalysisRequest(BaseModel):
    """Request model for anti-pattern analysis."""

    root_path: str = Field(default=".", description="Root path to analyze")
    patterns: List[str] = Field(default=["**/*.py"], description="Glob patterns for files to include")
    exclude_patterns: List[str] = Field(
        default=[
            "__pycache__",
            ".git",
            "node_modules",
            ".venv",
            "venv",
            "test_",
            "_test.py",
        ],
        description="Patterns to exclude from analysis",
    )


class SeveritySummary(BaseModel):
    """Summary of issues by severity."""

    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0


class AntiPatternSummary(BaseModel):
    """Summary information about detected anti-patterns."""

    total_issues: int
    severity_counts: SeveritySummary
    health_score: float
    summary_by_type: dict
    analysis_time_seconds: float


class AnalysisResponse(BaseModel):
    """Response model for anti-pattern analysis."""

    success: bool
    summary: AntiPatternSummary
    anti_patterns: List[dict]
    recommendations: List[str]


# ---------------------------------------------------------------------------
# playwright.py schemas
# ---------------------------------------------------------------------------


class TestMessageRequest(BaseModel):
    message: str = "what network scanning tools do we have available?"
    frontend_url: str = Field(default_factory=lambda: _ssot_config.frontend_url)


class FrontendTestRequest(BaseModel):
    frontend_url: str = Field(default_factory=lambda: _ssot_config.frontend_url)


class SnapshotWithRegionsRequest(BaseModel):
    session_id: str
    goal: str = ""


# ---------------------------------------------------------------------------
# mcp_registry.py schemas
# ---------------------------------------------------------------------------


class MCPToolInfo(BaseModel):
    """Information about an MCP tool."""

    name: str
    description: str
    input_schema: JSONObject
    bridge: str
    endpoint: str


class MCPBridgeInfo(BaseModel):
    """Information about an MCP bridge."""

    name: str
    description: str
    status: str
    tool_count: int
    endpoint: str
    features: List[str]


class MCPRegistryStats(BaseModel):
    """Overall MCP registry statistics."""

    total_bridges: int
    total_tools: int
    healthy_bridges: int
    last_updated: str


# ---------------------------------------------------------------------------
# manual_mcp.py schemas
# ---------------------------------------------------------------------------


class ManPageRequest(BaseModel):
    """Request model for man page lookup."""

    command: str = Field(..., description="Command name to look up (e.g. 'ls')")
    section: Optional[str] = Field(None, description="Manual section (1-8). Defaults to section 1.")


class ManPageSearchRequest(BaseModel):
    """Request model for documentation index query."""

    query: str = Field(..., description="Search query against the doc index")
    max_results: int = Field(10, ge=1, le=50, description="Maximum results to return")


class ManPageResult(BaseModel):
    """Structured man page result."""

    command: str
    section: str
    title: str
    synopsis: str
    description: str
    options: str
    examples: str
    see_also: str
    cached: bool


# ---------------------------------------------------------------------------
# ide_integration.py enums + schemas
# ---------------------------------------------------------------------------


class DiagnosticSeverity(str, Enum):
    """LSP-compatible diagnostic severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"
    HINT = "hint"


class CodeActionKind(str, Enum):
    """LSP-compatible code action kinds."""

    QUICKFIX = "quickfix"
    REFACTOR = "refactor"
    REFACTOR_EXTRACT = "refactor.extract"
    REFACTOR_INLINE = "refactor.inline"
    REFACTOR_REWRITE = "refactor.rewrite"
    SOURCE = "source"
    SOURCE_ORGANIZE_IMPORTS = "source.organizeImports"
    SOURCE_FIX_ALL = "source.fixAll"


class IDEPatternCategory(str, Enum):
    """Categories of detected patterns (IDE)."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    CODE_QUALITY = "code_quality"
    BEST_PRACTICE = "best_practice"
    ERROR_PRONE = "error_prone"
    STYLE = "style"
    DEPRECATED = "deprecated"


class CompletionItemKind(str, Enum):
    """LSP-compatible completion item kinds."""

    TEXT = "Text"
    METHOD = "Method"
    FUNCTION = "Function"
    CONSTRUCTOR = "Constructor"
    FIELD = "Field"
    VARIABLE = "Variable"
    CLASS = "Class"
    INTERFACE = "Interface"
    MODULE = "Module"
    PROPERTY = "Property"
    UNIT = "Unit"
    VALUE = "Value"
    ENUM = "Enum"
    CONSTANT = "Constant"
    KEYWORD = "Keyword"
    SNIPPET = "Snippet"


class LSPPosition(BaseModel):
    """LSP-compatible position (0-indexed)."""

    line: int = Field(..., ge=0)
    character: int = Field(..., ge=0)


class LSPRange(BaseModel):
    """LSP-compatible range."""

    start: LSPPosition
    end: LSPPosition


class Diagnostic(BaseModel):
    """LSP-compatible diagnostic."""

    range: LSPRange
    severity: DiagnosticSeverity
    code: str
    source: str = "autobot"
    message: str
    category: IDEPatternCategory
    data: Optional[Dict[str, Any]] = None


class TextEdit(BaseModel):
    """LSP-compatible text edit."""

    range: LSPRange
    new_text: str


class CodeAction(BaseModel):
    """LSP-compatible code action."""

    title: str
    kind: CodeActionKind
    diagnostics: List[Diagnostic] = []
    is_preferred: bool = False
    edit: Optional[Dict[str, Any]] = None


class IDEAnalysisRequest(BaseModel):
    """Request for code analysis."""

    file_path: str = Field(..., description="Path to the file being analyzed")
    content: str = Field(..., description="File content to analyze")
    language: str = Field(default="python", description="Programming language")
    include_hints: bool = Field(default=True, description="Include hint-level diagnostics")
    categories: Optional[List[IDEPatternCategory]] = Field(None, description="Filter by categories")


class IDEAnalysisResponse(BaseModel):
    """Response from code analysis."""

    file_path: str
    diagnostics: List[Diagnostic]
    analysis_time_ms: float
    patterns_checked: int
    issues_found: int


class QuickFixRequest(BaseModel):
    """Request for quick fix suggestions."""

    file_path: str
    content: str
    diagnostic_code: str
    range: LSPRange


class QuickFixResponse(BaseModel):
    """Response with quick fix suggestions."""

    actions: List[CodeAction]
    diagnostic_code: str


class HoverRequest(BaseModel):
    """Request for hover information."""

    file_path: str
    content: str
    position: LSPPosition


class HoverResponse(BaseModel):
    """Response with hover information."""

    contents: str
    range: Optional[LSPRange] = None


class IDEConfigurationUpdate(BaseModel):
    """Configuration update for IDE plugin."""

    enabled_rules: Optional[List[str]] = None
    disabled_rules: Optional[List[str]] = None
    severity_overrides: Optional[Dict[str, DiagnosticSeverity]] = None
    categories: Optional[List[IDEPatternCategory]] = None


class CompletionItem(BaseModel):
    """LSP-compatible completion item."""

    label: str = Field(..., description="Display text")
    kind: CompletionItemKind = Field(default=CompletionItemKind.TEXT, description="Item kind")
    detail: Optional[str] = Field(None, description="Additional details")
    documentation: Optional[str] = Field(None, description="Documentation")
    insert_text: Optional[str] = Field(None, description="Text to insert")
    sort_text: Optional[str] = Field(None, description="Sort order")
    filter_text: Optional[str] = Field(None, description="Filter text")
    score: float = Field(default=0.0, description="Relevance score")


class CompletionRequest(BaseModel):
    """Request for code completion."""

    file_path: str = Field(..., description="Path to the file")
    content: str = Field(..., description="File content")
    cursor_line: int = Field(..., ge=0, description="Cursor line (0-indexed)")
    cursor_position: int = Field(..., ge=0, description="Cursor column position")
    language: str = Field(default="python", description="Programming language")
    max_completions: int = Field(default=20, ge=1, le=100, description="Max results")


class CompletionResponse(BaseModel):
    """Response with code completions."""

    completions: List[CompletionItem]
    completion_time_ms: float
    source: str
    cached: bool = False


# ---------------------------------------------------------------------------
# development_speedup.py schemas
# ---------------------------------------------------------------------------


class DevelopmentSpeedupAnalysisRequest(BaseModel):
    """Request model for development_speedup code analysis."""

    root_path: str
    analysis_type: str = "comprehensive"


# ---------------------------------------------------------------------------
# skills_repos.py schemas
# ---------------------------------------------------------------------------

from skills.models import RepoType as _SkillsRepoType


class AddRepoRequest(BaseModel):
    """Request body for registering a new skill repository."""

    name: str = Field(..., description="Human-readable repo name")
    url: str = Field(..., description="git URL, local path, HTTP URL, or MCP URL")
    repo_type: _SkillsRepoType = Field(...)
    auto_sync: bool = Field(False)
    sync_interval: int = Field(60, description="Sync interval in minutes")
