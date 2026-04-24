# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared Pydantic response schemas for AutoBot API endpoints.

Provides typed response models for terminal.py and terminal_tools.py.
All models are used as response_model= on FastAPI router decorators so that
FastAPI generates accurate OpenAPI docs and validates outbound data.

Schema naming convention:
  <Domain><EntityOrAction>Response
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Generic / reusable
# ---------------------------------------------------------------------------


class SuccessResponse(BaseModel):
    """Minimal success/failure envelope used by several endpoints."""

    success: bool
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Terminal session schemas  (terminal.py — session lifecycle)
# ---------------------------------------------------------------------------


class TerminalSessionCreateResponse(BaseModel):
    """Response for POST /sessions."""

    session_id: str
    status: str
    security_level: str
    websocket_url: str
    created_at: str
    ssh_keys: Optional[Dict[str, Any]] = None


class TerminalSessionItem(BaseModel):
    """Single session entry within a list response."""

    session_id: str
    user_id: Optional[str] = None
    security_level: Optional[str] = None
    created_at: Optional[str] = None
    is_active: bool


class TerminalSessionListResponse(BaseModel):
    """Response for GET /sessions."""

    sessions: List[TerminalSessionItem]
    total: int
    active: int


class TerminalSessionDetailResponse(BaseModel):
    """Response for GET /sessions/{session_id}."""

    session_id: str
    config: Dict[str, Any]
    is_active: bool
    statistics: Dict[str, Any]


class TerminalSessionDeleteResponse(BaseModel):
    """Response for DELETE /sessions/{session_id}."""

    session_id: str
    status: str


# ---------------------------------------------------------------------------
# SSH key management schemas  (terminal.py — Issue #211)
# ---------------------------------------------------------------------------


class SSHKeyItem(BaseModel):
    """A single SSH key entry as returned by get_session_keys()."""

    name: str
    fingerprint: Optional[str] = None
    has_passphrase: Optional[bool] = None
    key_path: Optional[str] = None


class SSHKeyListResponse(BaseModel):
    """Response for GET /sessions/{session_id}/ssh-keys."""

    session_id: str
    keys: List[Any]  # key dicts are opaque — shape defined by terminal_secrets_service
    total: int


class SSHKeyAgentResponse(BaseModel):
    """Response for POST /sessions/{session_id}/ssh-keys/{key_name}/agent."""

    session_id: str
    key_name: str
    status: str
    message: str


class SSHKeyPathResponse(BaseModel):
    """Response for GET /sessions/{session_id}/ssh-keys/{key_name}/path."""

    session_id: str
    key_name: str
    key_path: str
    usage: str


# ---------------------------------------------------------------------------
# Command / input / signal schemas
# ---------------------------------------------------------------------------


class CommandAssessResponse(BaseModel):
    """Response for POST /command."""

    command: str
    risk_level: str
    status: str
    message: str
    requires_confirmation: bool


class TerminalInputResponse(BaseModel):
    """Response for POST /sessions/{session_id}/input."""

    session_id: str
    status: str
    input: str


class TerminalSignalResponse(BaseModel):
    """Response for POST /sessions/{session_id}/signal/{signal_name}."""

    session_id: str
    signal: str
    status: str


# ---------------------------------------------------------------------------
# History / audit schemas
# ---------------------------------------------------------------------------


class TerminalCommandHistoryResponse(BaseModel):
    """Response for GET /sessions/{session_id}/history."""

    session_id: str
    is_active: bool
    history: List[Any]
    total_commands: Optional[int] = None
    message: Optional[str] = None


class TerminalAuditLogResponse(BaseModel):
    """Response for GET /audit/{session_id}."""

    session_id: str
    audit_available: bool
    security_level: Optional[str] = None
    message: str


# ---------------------------------------------------------------------------
# Info / health / status schemas
# ---------------------------------------------------------------------------


class TerminalInfoResponse(BaseModel):
    """Response for GET /."""

    name: str
    version: str
    description: str
    features: List[str]
    endpoints: Dict[str, str]
    security_levels: List[str]
    notice: str


class TerminalHealthComponents(BaseModel):
    terminal_manager: str
    websocket_manager: str
    pty_system: str
    session_manager: str


class TerminalHealthMetrics(BaseModel):
    active_sessions: int
    manager_initialized: bool


class TerminalHealthResponse(BaseModel):
    """Response for GET /health (healthy path)."""

    status: str
    service: str
    components: Optional[TerminalHealthComponents] = None
    metrics: Optional[TerminalHealthMetrics] = None
    error: Optional[str] = None


class TerminalStatusFeatures(BaseModel):
    pty_support: bool
    websocket_support: bool
    command_validation: bool
    security_policies: bool
    approval_workflow: bool
    agent_integration: bool


class TerminalStatusSessionInfo(BaseModel):
    active_sessions: int
    max_concurrent_sessions: Optional[int] = None


class TerminalSystemStatusResponse(BaseModel):
    """Response for GET /status."""

    status: str
    terminal_types: Optional[List[str]] = None
    features: Optional[TerminalStatusFeatures] = None
    session_info: Optional[TerminalStatusSessionInfo] = None
    error: Optional[str] = None


class TerminalCapabilitiesResponse(BaseModel):
    """Response for GET /capabilities."""

    pty_management: bool
    websocket_streaming: bool
    command_execution: bool
    security_validation: bool
    session_management: bool
    terminal_types: Dict[str, Any]
    pty_features: Dict[str, Any]
    websocket_features: Dict[str, Any]


class TerminalSecurityPoliciesResponse(BaseModel):
    """Response for GET /security."""

    command_validation: str
    risk_assessment: str
    risk_levels: Dict[str, str]
    security_executor: str
    approval_workflow: Dict[str, Any]
    audit_logging: Dict[str, Any]


class TerminalImplementationItem(BaseModel):
    name: str
    description: str
    frontend_component: str
    backend_api: str
    approval_workflow: bool
    service_layer: Optional[str] = None


class TerminalFeaturesResponse(BaseModel):
    """Response for GET /features."""

    manager_class: str
    websocket_class: str
    pty_implementation: str
    implementations: List[TerminalImplementationItem]
    features: Dict[str, str]
    shared_infrastructure: Dict[str, str]


# ---------------------------------------------------------------------------
# Stats schema
# ---------------------------------------------------------------------------


class TerminalStatsResponse(BaseModel):
    """Response for GET /stats.

    The session manager returns an opaque dict whose shape varies between
    the 'all sessions' and 'single session' cases.  A permissive model
    lets FastAPI pass the dict through while still documenting the endpoint.
    """

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# Admin execute schema  (SLM admin terminal — Issue #983)
# ---------------------------------------------------------------------------


class AdminExecuteResponse(BaseModel):
    """Response for POST /execute."""

    stdout: str
    stderr: str
    exit_code: int


# ---------------------------------------------------------------------------
# terminal_tools.py schemas
# ---------------------------------------------------------------------------


class PackageManagersResponse(BaseModel):
    """Response for GET /terminal/package-managers."""

    detected: Optional[str] = None
    available: List[str]
    package_managers: Dict[str, Any]


# ---------------------------------------------------------------------------
# Generic data envelope  (ai_stack_integration, agent, etc.)
# ---------------------------------------------------------------------------


class DataResponse(BaseModel):
    """Generic envelope returned by create_success_response() helpers.

    Covers all endpoints that delegate to utils.response_helpers.create_success_response,
    which always produces {"success": True, "data": ..., "message": ..., "timestamp": ...}.
    """

    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None
    timestamp: Optional[str] = None


# ---------------------------------------------------------------------------
# agent.py — simple message / approval responses
# ---------------------------------------------------------------------------


class AgentMessageResponse(BaseModel):
    """Response for /goal, /pause, /resume — plain {"message": str}."""

    message: str


class AgentCommandApprovalResponse(BaseModel):
    """Response for POST /command_approval."""

    message: str
    task_id: str
    approved: bool


class AgentCommandExecuteResponse(BaseModel):
    """Response for POST /execute_command — success path returns {"message", "output", "status"}."""

    message: str
    output: Optional[str] = None
    status: Optional[str] = None


class AgentHealthResponse(BaseModel):
    """Response for GET /health/enhanced."""

    status: str
    ai_stack_available: bool
    multi_agent_coordination: bool
    enhanced_capabilities: bool
    timestamp: str
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# enhanced_memory.py schemas
# ---------------------------------------------------------------------------


class MemoryStatisticsResponse(BaseModel):
    """Response for GET /statistics."""

    period_days: int
    timestamp: str
    task_execution: Optional[Any] = None
    markdown_system: Optional[Any] = None
    active_tasks: Optional[Any] = None
    performance_insights: Optional[Any] = None


class MemoryTaskHistoryResponse(BaseModel):
    """Response for GET /tasks/history."""

    total_records: int
    filter_criteria: Dict[str, Any]
    tasks: List[Any]


class MemoryTaskCreateResponse(BaseModel):
    """Response for POST /tasks."""

    task_id: str
    status: str
    timestamp: str


class MemoryTaskUpdateResponse(BaseModel):
    """Response for PUT /tasks/{task_id}."""

    task_id: str
    status: str
    timestamp: str


class MemoryMarkdownReferenceResponse(BaseModel):
    """Response for POST /tasks/{task_id}/markdown-reference."""

    task_id: str
    markdown_file: str
    reference_type: str
    status: str
    timestamp: str


class MemoryMarkdownScanResponse(BaseModel):
    """Response for GET /markdown/scan."""

    status: str
    scan_results: Optional[Any] = None
    timestamp: str


class MemoryMarkdownSearchResponse(BaseModel):
    """Response for GET /markdown/search."""

    query: str
    filters: Dict[str, Any]
    total_results: int
    results: List[Any]


class MemoryDocumentReferencesResponse(BaseModel):
    """Response for GET /markdown/{file_path}/references."""

    file_path: str
    timestamp: str
    references: Optional[Any] = None


class MemoryEmbeddingCacheStatsResponse(BaseModel):
    """Response for GET /embeddings/cache-stats."""

    cache_size: Optional[Any] = None
    timestamp: str
    status: str


class MemoryCleanupResponse(BaseModel):
    """Response for DELETE /cleanup."""

    status: str
    cleanup_results: Dict[str, Any]
    days_kept: int
    timestamp: str


class MemoryActiveTasksResponse(BaseModel):
    """Response for GET /active-tasks."""

    count: int
    active_tasks: List[Any]
    timestamp: str


# ---------------------------------------------------------------------------
# agent_config.py schemas
# ---------------------------------------------------------------------------


class AgentConfigEnableDisableResponse(BaseModel):
    """Response for POST /agents/{agent_id}/enable and /disable."""

    status: str
    message: str
    agent_name: str


class AgentConfigUpdateModelResponse(BaseModel):
    """Response for POST /agents/{agent_id}/model."""

    status: str
    message: str
    updated_config: Dict[str, Any]


class AgentConfigHealthResponse(BaseModel):
    """Response for GET /agents/{agent_id}/health."""

    agent_id: str
    agent_name: str
    status: str
    enabled: bool
    model: Optional[str] = None
    checks: Dict[str, Any]
    timestamp: str
    response_time: float


class AgentConfigOverviewResponse(BaseModel):
    """Response for GET /status/overview."""

    total_agents: int
    enabled_agents: int
    healthy_agents: int
    unhealthy_agents: int
    disabled_agents: int
    overall_health: str
    agents: List[Any]
    timestamp: str

# ---------------------------------------------------------------------------
# LLM schemas  (llm.py)
# ---------------------------------------------------------------------------


class LLMConnectionTestResponse(BaseModel):
    """Response for POST /llm/test_connection."""

    status: str
    message: Optional[str] = None

    model_config = {"extra": "allow"}


class LLMModelsResponse(BaseModel):
    """Response for GET /llm/models."""

    models: List[Any]
    total_count: int


class LLMCurrentResponse(BaseModel):
    """Response for GET /llm/current."""

    model: str
    provider: str
    config: Dict[str, Any]


class LLMEmbeddingModelsResponse(BaseModel):
    """Response for GET /llm/embedding/models."""

    models: List[Any]
    total_count: int


# ---------------------------------------------------------------------------
# LLM Optimization schemas  (llm_optimization.py)
# ---------------------------------------------------------------------------


class LLMOptimizationHealthResponse(BaseModel):
    """Response for GET /llm-optimization/health."""

    status: str
    available_models: int
    cache_size: int
    ollama_connection: bool
    redis_connected: bool


class LLMAvailableModelsResponse(BaseModel):
    """Response for GET /llm-optimization/models/available."""

    models_count: int
    models: List[Any]
    timestamp: float


class LLMSelectModelResponse(BaseModel):
    """Response for POST /llm-optimization/models/select."""

    selected_model: Optional[str] = None
    model_details: Optional[Dict[str, Any]] = None
    task_complexity: str
    selection_reasoning: Dict[str, Any]
    timestamp: float


class LLMTrackPerformanceResponse(BaseModel):
    """Response for POST /llm-optimization/models/performance/track."""

    status: str
    message: str
    recorded_data: Dict[str, Any]


class LLMOptimizationSuggestionsResponse(BaseModel):
    """Response for GET /llm-optimization/optimization/suggestions."""

    suggestions_count: int
    suggestions: List[Any]
    timestamp: float


class LLMModelsComparisonResponse(BaseModel):
    """Response for GET /llm-optimization/models/comparison."""

    comparison: Dict[str, Any]
    best_models: Dict[str, Any]
    total_models: int
    timestamp: float

    model_config = {"extra": "allow"}


class LLMBenchmarkResponse(BaseModel):
    """Response for POST /llm-optimization/models/benchmark/{model_name}."""

    model_name: str
    test_queries: List[str]
    iterations_per_query: int
    status: str
    message: str
    expected_metrics: List[str]
    timestamp: float


class LLMSystemResourcesResponse(BaseModel):
    """Response for GET /llm-optimization/system/resources."""

    resources: Dict[str, Any]
    recommendations: List[Any]
    optimal_model_size_gb: float
    timestamp: float


class LLMOptimizationConfigResponse(BaseModel):
    """Response for GET /llm-optimization/config."""

    performance_threshold: float
    cache_ttl: int
    min_samples: int
    model_classification: Dict[str, Any]
    task_complexity_levels: List[str]
    optimization_factors: List[str]


class LLMInferenceSettingsResponse(BaseModel):
    """Response for GET/POST /llm-optimization/inference/settings."""

    settings: Dict[str, Any]
    timestamp: float


class LLMInferenceMetricsResponse(BaseModel):
    """Response for GET /llm-optimization/inference/metrics."""

    optimization: Dict[str, Any]
    cache: Dict[str, Any]
    provider_usage: Dict[str, Any]
    total_requests: int
    avg_response_time: float
    fallback_count: int
    timestamp: float


class LLMProviderOptimizationSummaryResponse(BaseModel):
    """Response for GET /llm-optimization/inference/provider/{provider_type}/optimizations."""

    provider: str
    is_local: bool
    is_cloud: bool
    optimizations: Dict[str, Any]
    timestamp: float


class LLMModelPerformanceHistoryResponse(BaseModel):
    """Response for GET /llm-optimization/models/performance/history/{model_name}.

    Shape is opaque — defined by model.to_performance_history_dict().
    """

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# LLM Awareness schemas  (llm_awareness.py)
# ---------------------------------------------------------------------------


class LLMAwarenessStatusResponse(BaseModel):
    """Response for GET /llm-awareness/status."""

    status: str
    service: str
    timestamp: str
    system_identity: Dict[str, Any]
    capabilities_count: int
    system_maturity: str


class LLMSystemContextResponse(BaseModel):
    """Response for GET /llm-awareness/context."""

    status: str
    format: str
    context: Dict[str, Any]
    timestamp: str


class LLMCapabilitiesSummaryResponse(BaseModel):
    """Response for GET /llm-awareness/capabilities."""

    status: str
    capabilities: Dict[str, Any]
    timestamp: str


class LLMInjectContextResponse(BaseModel):
    """Response for POST /llm-awareness/inject-context."""

    status: str
    original_prompt: str
    enhanced_prompt: str
    context_level: str
    timestamp: str


class LLMAnalyzeQueryResponse(BaseModel):
    """Response for POST /llm-awareness/analyze-query."""

    status: str
    analysis: Dict[str, Any]
    timestamp: str


class LLMCapabilitySummaryTextResponse(BaseModel):
    """Response for GET /llm-awareness/summary/text."""

    status: str
    summary: str
    format: str
    timestamp: str


class LLMPhaseInfoResponse(BaseModel):
    """Response for GET /llm-awareness/phase-info."""

    status: str
    phase_info: Dict[str, Any]
    timestamp: str


class LLMAwarenessMetricsResponse(BaseModel):
    """Response for GET /llm-awareness/metrics."""

    status: str
    metrics: Dict[str, Any]
    timestamp: str


class LLMExportAwarenessResponse(BaseModel):
    """Response for POST /llm-awareness/export."""

    status: str
    message: str
    output_path: str
    format: str
    timestamp: str


class LLMAwarenessHealthResponse(BaseModel):
    """Response for GET /llm-awareness/health."""

    status: str
    service: str
    components: Dict[str, Any]
    system_maturity: str
    capabilities_count: int
    timestamp: str


# ---------------------------------------------------------------------------
# system.py schemas
# ---------------------------------------------------------------------------


class SystemFrontendConfigResponse(BaseModel):
    """Response for GET /frontend-config."""

    status: str
    config: Dict[str, Any]
    timestamp: str


class SystemHealthResponse(BaseModel):
    """Response for GET /health and GET /system/health.

    Shape varies between healthy/degraded/unhealthy paths — extra fields
    (cpu_percent, memory_percent, services, etc.) are allowed through.
    """

    model_config = {"extra": "allow"}

    status: str
    timestamp: str


class SystemInfoResponse(BaseModel):
    """Response for GET /info."""

    name: str
    version: str
    python_version: str
    timestamp: str
    features: Dict[str, Any]


class SystemReloadConfigResponse(BaseModel):
    """Response for POST /reload_config."""

    status: str
    message: str
    timestamp: str


class SystemPromptReloadResponse(BaseModel):
    """Response for GET /prompt_reload."""

    status: str
    message: str
    timestamp: str


class SystemAdminCheckResponse(BaseModel):
    """Response for GET /admin_check."""

    user: str
    admin: bool
    timestamp: str


class SystemDynamicImportResponse(BaseModel):
    """Response for POST /dynamic_import."""

    status: str
    message: str
    module_info: Dict[str, Any]
    timestamp: str


class SystemCacheStatsResponse(BaseModel):
    """Response for GET /cache/stats.

    Redis info and performance sections are dynamic — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    timestamp: str
    cache: Dict[str, Any]


class SystemCacheActivityResponse(BaseModel):
    """Response for GET /cache/activity."""

    model_config = {"extra": "allow"}

    timestamp: str
    activity: Dict[str, Any]


class SystemMetricsResponse(BaseModel):
    """Response for GET /metrics.

    psutil-derived payload is dynamic; extra fields allowed through.
    """

    model_config = {"extra": "allow"}

    timestamp: str


class SystemCacheCoordinatorStatsResponse(BaseModel):
    """Response for GET /api/cache/stats.

    Shape is defined by CacheCoordinator.get_unified_stats() — opaque.
    """

    model_config = {"extra": "allow"}


class SystemCacheEvictResponse(BaseModel):
    """Response for POST /api/cache/evict."""

    status: str
    evicted: int
    timestamp: str


class SystemCacheClearResponse(BaseModel):
    """Response for POST /api/cache/clear/{cache_name}."""

    status: str
    cache: str
    timestamp: str


class SystemBackupStatusResponse(BaseModel):
    """Response for GET /system/backup/status.

    BackupScheduler.get_status() returns an opaque dict with a timestamp added.
    """

    model_config = {"extra": "allow"}

    timestamp: str


# ---------------------------------------------------------------------------
# agent_terminal.py schemas
# ---------------------------------------------------------------------------


class AgentTerminalSessionCreateResponse(BaseModel):
    """Response for POST /agent-terminal/sessions."""

    status: str
    session_id: str
    agent_id: str
    agent_role: str
    conversation_id: Optional[str] = None
    host: str
    state: str
    created_at: float
    pty_session_id: Optional[str] = None


class AgentTerminalSessionItem(BaseModel):
    """Single session entry within list response."""

    session_id: str
    agent_id: str
    agent_role: str
    conversation_id: Optional[str] = None
    host: str
    state: str
    created_at: float
    last_activity: Optional[float] = None
    command_count: int
    pty_session_id: Optional[str] = None


class AgentTerminalSessionListResponse(BaseModel):
    """Response for GET /agent-terminal/sessions."""

    status: str
    total: int
    sessions: List[AgentTerminalSessionItem]


class AgentTerminalSessionDetailResponse(BaseModel):
    """Response for GET /agent-terminal/sessions/{session_id}.

    session_info dict shape is opaque — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    status: str


class AgentTerminalSessionDeleteResponse(BaseModel):
    """Response for DELETE /agent-terminal/sessions/{session_id}."""

    status: str
    session_id: str


class AgentTerminalCommandStateResponse(BaseModel):
    """Response for GET /agent-terminal/commands/{command_id}."""

    command_id: str
    terminal_session_id: Optional[str] = None
    chat_id: Optional[str] = None
    command: str
    purpose: Optional[str] = None
    state: str
    output: Optional[str] = None
    stderr: Optional[str] = None
    return_code: Optional[int] = None
    risk_level: str
    risk_reasons: Optional[List[str]] = None
    requested_at: Optional[float] = None
    approved_at: Optional[float] = None
    execution_started_at: Optional[float] = None
    execution_completed_at: Optional[float] = None
    approved_by_user_id: Optional[str] = None
    approval_comment: Optional[str] = None


class AgentTerminalInfoResponse(BaseModel):
    """Response for GET /agent-terminal/."""

    name: str
    version: str
    description: str
    features: List[str]
    agent_roles: List[str]
    session_states: List[str]
    endpoints: Dict[str, str]
    security_features: Dict[str, str]


class AgentTerminalToolApprovalResponse(BaseModel):
    """Response for POST /agent-terminal/tools/approve/{approval_id}."""

    status: str
    approval_id: str
    approved: bool


class AgentTerminalHostSelectionRequestResponse(BaseModel):
    """Response for POST /agent-terminal/host-selection/request."""

    request_id: str
    status: str
    message: str


class AgentTerminalHostSelectionGetResponse(BaseModel):
    """Response for GET /agent-terminal/host-selection/{request_id}."""

    request_id: str
    status: str
    selected_host_id: Optional[str] = None
    selected_host_name: Optional[str] = None
    connection_info: Optional[Dict[str, Any]] = None
    created_at: str
    updated_at: Optional[str] = None


class AgentTerminalHostSelectionSubmitResponse(BaseModel):
    """Response for POST /agent-terminal/host-selection/{request_id}/select."""

    status: str
    request_id: str
    selected_host_id: Optional[str] = None
    selected_host_name: Optional[str] = None
    connection_info: Optional[Dict[str, Any]] = None


class AgentTerminalHostSelectionCancelResponse(BaseModel):
    """Response for POST /agent-terminal/host-selection/{request_id}/cancel."""

    status: str
    request_id: str


class AgentTerminalPendingSelectionsResponse(BaseModel):
    """Response for GET /agent-terminal/host-selection."""

    status: str
    pending_count: int
    pending_selections: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# knowledge_metadata.py schemas  (Issue #5317)
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


class ValidationDashboardStatusResponse(BaseModel):
    """Response for GET /status (healthy path; unavailable path uses JSONResponse)."""

    status: str
    service: str
    output_directory: Optional[str] = None
    refresh_interval: Optional[int] = None
    data_retention_days: Optional[int] = None
    timestamp: str


class ValidationDashboardReportResponse(BaseModel):
    """Response for GET /report."""

    status: str
    report: Optional[Any] = None
    timestamp: str


class ValidationDashboardGenerateResponse(BaseModel):
    """Response for POST /generate."""

    status: str
    message: str
    settings: Dict[str, Any]
    timestamp: str


class ValidationDashboardMetricsResponse(BaseModel):
    """Response for GET /metrics."""

    status: str
    metrics: Dict[str, Any]
    timestamp: str


class ValidationDashboardTrendsResponse(BaseModel):
    """Response for GET /trends."""

    status: str
    trends: Optional[Any] = None
    timestamp: str


class ValidationDashboardAlertsResponse(BaseModel):
    """Response for GET /alerts."""

    status: str
    alerts: List[Any]
    alert_counts: Dict[str, int]
    timestamp: str


class ValidationDashboardRecommendationsResponse(BaseModel):
    """Response for GET /recommendations."""

    status: str
    recommendations: List[Any]
    recommendation_counts: Dict[str, int]
    timestamp: str


class ValidationJudgmentResponse(BaseModel):
    """Response for POST /judge_workflow_step and POST /judge_agent_response."""

    status: str
    judgment: Dict[str, Any]
    timestamp: str


class ValidationJudgeStatusResponse(BaseModel):
    """Response for GET /judge_status (healthy path; unavailable path uses JSONResponse)."""

    status: str
    service: str
    available_judges: List[str]
    judge_metrics: Dict[str, Any]
    timestamp: str



# ---------------------------------------------------------------------------
# templates.py schemas
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


class TemplateExecuteResponse(BaseModel):
    """Response for POST /templates/{template_id}/execute."""

    success: bool
    workflow_id: str
    template_info: Dict[str, Any]
    message: str


# ---------------------------------------------------------------------------
# state_tracking.py schemas
# ---------------------------------------------------------------------------


class StateTrackingStatusResponse(BaseModel):
    """Response for GET /status."""

    status: str
    service: str
    timestamp: str
    tracking_active: bool
    snapshot_count: Optional[Any] = None
    change_count: Optional[Any] = None
    latest_snapshot: Optional[Any] = None


class StateTrackingSummaryResponse(BaseModel):
    """Response for GET /summary."""

    status: str
    summary: Dict[str, Any]
    timestamp: str


class StateTrackingSnapshotResponse(BaseModel):
    """Response for POST /snapshot."""

    status: str
    message: str
    timestamp: str


class StateTrackingChangeResponse(BaseModel):
    """Response for POST /change (success path only).

    JSONResponse(400) for invalid change_type bypasses response_model.
    """

    status: str
    message: str
    change_type: str
    timestamp: str


class StateTrackingMilestonesResponse(BaseModel):
    """Response for GET /milestones."""

    status: str
    milestones: Dict[str, Any]
    achieved_count: int
    total_count: int
    timestamp: str


class StateTrackingTrendsResponse(BaseModel):
    """Response for GET /trends/{metric} (success path only).

    JSONResponse(400) for invalid metrics bypasses response_model.
    """

    status: str
    metric: str
    days: int
    data_points: int
    trend_data: List[Any]
    timestamp: str


class StateTrackingChangesResponse(BaseModel):
    """Response for GET /changes."""

    status: str
    changes: List[Any]
    total_changes: int
    showing: int
    timestamp: str


class StateTrackingReportResponse(BaseModel):
    """Response for GET /report."""

    status: str
    report: str
    format: str
    timestamp: str


class StateTrackingExportResponse(BaseModel):
    """Response for POST /export."""

    status: str
    message: str
    filename: str
    path: str
    format: str
    timestamp: str


class StateTrackingMetricsAllResponse(BaseModel):
    """Response for GET /metrics/all."""

    status: str
    metrics: Dict[str, Any]
    available_metrics: List[str]
    timestamp: str


class StateTrackingPhaseHistoryResponse(BaseModel):
    """Response for GET /phase-history/{phase_name}."""

    status: str
    phase_name: str
    days: int
    data_points: int
    history: List[Any]
    timestamp: str


# ---------------------------------------------------------------------------
# secrets.py schemas  (all endpoints use JSONResponse → response_model=None)
# development_speedup.py schemas  (all endpoints use JSONResponse → response_model=None)
# No new Pydantic models needed for those two files.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# analytics_code_review.py schemas
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


