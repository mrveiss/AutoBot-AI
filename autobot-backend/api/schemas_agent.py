# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent config, memory, and LLM schemas.
"""

import uuid
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from models.session_collaboration import PermissionLevel
from user_management.schemas import UserResponse as _UserResponse


# ---------------------------------------------------------------------------
# Agent schemas
# ---------------------------------------------------------------------------

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
# a2a.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class A2AAgentCardResponse(BaseModel):
    """Response for GET /a2a/agent-card — AgentCard.to_dict() shape."""

    model_config = {"extra": "allow"}


class A2ASignedAgentCardResponse(BaseModel):
    """Response for GET /a2a/agent-card/signed — {card, issued_at, signature}."""

    card: Dict[str, Any]
    issued_at: int
    signature: str


class A2ASubmitTaskResponse(BaseModel):
    """Response for POST /a2a/tasks — {id, state, traceId}."""

    id: str
    state: str
    traceId: str


class A2ATaskResponse(BaseModel):
    """Response for GET /a2a/tasks/{id} and GET /a2a/tasks list items.

    Shape comes from _task_response() which returns the full task dict.
    Extra fields allowed because the shape includes dynamic artifacts.
    """

    model_config = {"extra": "allow"}

    id: str
    state: str


class A2ATaskTraceResponse(BaseModel):
    """Response for GET /a2a/tasks/{id}/trace."""

    task_id: str
    trace: Optional[Dict[str, Any]] = None
    events: List[Any]


class A2ACancelTaskResponse(BaseModel):
    """Response for DELETE /a2a/tasks/{id}."""

    id: str
    state: str


class A2AStatsResponse(BaseModel):
    """Response for GET /a2a/stats."""

    counts: Dict[str, int]
    total: int


class A2ACapabilitiesResponse(BaseModel):
    """Response for GET /a2a/capabilities and POST /a2a/capabilities/verify.

    Shape from CapabilityVerificationReport.to_dict() — opaque; extra fields allowed.
    """

    model_config = {"extra": "allow"}


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



class LLMPatternsHealthResponse(BaseModel):
    """Response for GET /llm-patterns/health."""

    status: str
    service: str
    deprecated: bool
    use_instead: str
    features: List[str]
    supported_categories: List[str]
    optimization_types: List[str]



class LLMPatternsAnalyzeResponse(BaseModel):
    """Response for POST /llm-patterns/analyze."""

    prompt_hash: str
    category: str
    estimated_tokens: int
    estimated_cost: float
    issues: List[Any]
    recommendations: List[str]
    cache_potential: bool



class LLMPatternsRecordResponse(BaseModel):
    """Response for POST /llm-patterns/record."""

    recorded: bool
    prompt_hash: str
    category: str
    cost: float
    cache_count: int



class LLMPatternsStatsResponse(BaseModel):
    """Response for GET /llm-patterns/stats.

    Shape includes totals and by_date/by_model/by_category which are dynamic;
    extra fields allowed.
    """

    model_config = {"extra": "allow"}

    period_days: int
    total_requests: int
    total_cost: float
    successful_requests: int



class LLMPatternsCacheOpportunitiesResponse(BaseModel):
    """Response for GET /llm-patterns/cache-opportunities."""

    opportunities: List[Any]
    count: int
    min_occurrences: int



class LLMPatternsRecommendationsResponse(BaseModel):
    """Response for GET /llm-patterns/recommendations."""

    recommendations: List[Any]



class LLMPatternsModelComparisonResponse(BaseModel):
    """Response for GET /llm-patterns/model-comparison."""

    models: List[Any]
    period_days: int



class LLMPatternsCategoryDistributionResponse(BaseModel):
    """Response for GET /llm-patterns/category-distribution."""

    categories: List[Any]
    total_count: int
    total_cost: float



class LLMPatternsCostBreakdownResponse(BaseModel):
    """Response for GET /llm-patterns/cost-breakdown."""

    period_days: int
    total_cost: float
    total_requests: int
    avg_cost_per_request: float
    by_model: List[Any]
    by_category: List[Any]
    daily_trend: List[Any]


# ---------------------------------------------------------------------------
# intelligent_agent.py schemas  (Issue #5937)
# ---------------------------------------------------------------------------



class AgentSystemCapabilitiesResponse(BaseModel):
    """Response for GET /intelligent-agent/system-info — OS, user, and tool capabilities."""

    os_type: str
    distro: str = ""
    user: str
    capabilities: List[str]
    available_tools: List[str]


class GoalRequest(BaseModel):
    """Request body for POST /intelligent-agent/process."""

    goal: str
    context: Dict[str, Any] = {}


class GoalResponse(BaseModel):
    """Response for POST /intelligent-agent/process."""

    success: bool
    result: str
    execution_time: float
    metadata: Dict[str, Any] = {}


class HealthResponse(BaseModel):
    """Response for GET /intelligent-agent/health."""

    status: str
    components: Dict[str, str]
    uptime: float


# ---------------------------------------------------------------------------
# auth.py schemas  (Issue #5985)
# ---------------------------------------------------------------------------


class AuthUserInfoResponse(BaseModel):
    """Response for GET /auth/me."""

    username: str
    role: str
    email: str
    auth_method: str
    authenticated: bool
    deployment_mode: str


class AuthCheckResponse(BaseModel):
    """Response for GET /auth/check."""

    authenticated: bool
    role: Optional[str] = None
    auth_enabled: bool
    deployment_mode: Optional[str] = None
    error: Optional[str] = None


class AuthPermissionResponse(BaseModel):
    """Response for GET /auth/permissions/{operation}."""

    permitted: bool
    operation: str
    user_role: Optional[str] = None
    username: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# agent_terminal.py schemas  (Issue #5985)
# ---------------------------------------------------------------------------


class AgentTerminalExecuteResponse(BaseModel):
    """Response for POST /agent-terminal/execute — shape varies, extra fields allowed."""

    model_config = {"extra": "allow"}
    status: str


class AgentTerminalApproveResponse(BaseModel):
    """Response for POST /agent-terminal/sessions/{session_id}/approve."""

    model_config = {"extra": "allow"}
    status: str


class AgentTerminalInterruptResponse(BaseModel):
    """Response for POST /agent-terminal/sessions/{session_id}/interrupt."""

    status: str
    message: Optional[str] = None
    previous_state: Optional[str] = None
    current_state: Optional[str] = None
    pending_approval: Optional[Any] = None
    error: Optional[str] = None


class AgentTerminalResumeResponse(BaseModel):
    """Response for POST /agent-terminal/sessions/{session_id}/resume."""

    status: str
    message: Optional[str] = None
    current_state: Optional[str] = None
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# voice.py schemas  (Issue #5985)
# ---------------------------------------------------------------------------


class VoiceCreateResponse(BaseModel):
    """Response for POST /voice/voices/create — shape from tts.create_voice(), extra fields allowed."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# llm.py schemas  (Issue #5985)
# ---------------------------------------------------------------------------


class LLMConfigResponse(BaseModel):
    """Response for GET /llm/config — provider-specific shape, extra fields allowed."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# logs.py schemas  (Issue #5985)
# ---------------------------------------------------------------------------


class LogFileMetadata(BaseModel):
    """Single log file entry for GET /logs/list — shape from log sources, extra fields allowed."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# intelligent_agent.py reload schema  (Issue #5985)
# ---------------------------------------------------------------------------



class AgentReloadResponse(BaseModel):
    """Response for POST /intelligent-agent/reload."""

    status: str
    message: str


# ---------------------------------------------------------------------------
# voice.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# bi_export_endpoints.py schemas  (Issue #5991)
# ---------------------------------------------------------------------------



class SavedReportResponse(BaseModel):
    """Response for POST /bi/reports/save — shape from SavedReportsService.create_report()."""

    id: str
    name: str
    report_type: str
    sections: List[str]
    created_at: Any
    updated_at: Any



class SavedReportsListResponse(BaseModel):
    """Response for GET /bi/reports/saved."""

    reports: List[Any]


# ---------------------------------------------------------------------------
# conversation_export.py schemas  (Issue #5991)
# ---------------------------------------------------------------------------



class ConversationImportResponse(BaseModel):
    """Response for POST /conversations/import.

    Shape from import_conversation() — includes success, session_id, and
    optional conflict/rename_suffix fields; extra fields allowed.
    """

    model_config = {"extra": "allow"}

    success: bool
    session_id: str


# ---------------------------------------------------------------------------
# nl_database.py schemas  (Issue #5991)
# ---------------------------------------------------------------------------



class NLDatabaseSchemaResponse(BaseModel):
    """Response for GET /nl-database/schema.

    Contains vanna_available flag, trained database summaries, and local db path.
    trained_databases keys are db_id strings — opaque; extra fields allowed.
    """

    model_config = {"extra": "allow"}

    vanna_available: bool
    local_db_path: str


# ---------------------------------------------------------------------------
# triggers.py schemas  (Issue #5991)
# ---------------------------------------------------------------------------



class WebhookAcceptedResponse(BaseModel):
    """Response for POST /triggers/webhook/{trigger_id}."""

    status: str


# ---------------------------------------------------------------------------
# self_capabilities.py schemas  (Issue #5991)
# ---------------------------------------------------------------------------



class SelfCapabilitiesResponse(BaseModel):
    """Response for GET /api/self/capabilities.

    Live endpoint discovery result with endpoint list, tag/operation-type
    groupings — opaque; extra fields allowed.
    """

    model_config = {"extra": "allow"}

    total_endpoints: int
    unique_paths: int


# ---------------------------------------------------------------------------
# agent.py / ai_stack_integration.py — DataResponse[T] payload models (#5772)
# ---------------------------------------------------------------------------


class AgentCapabilityInfo(BaseModel):
    """Single agent entry in the /agents/available response."""

    name: str
    description: str
    capabilities: List[str]
    status: str


class AgentAvailableData(BaseModel):
    """data payload for GET /agent/agents/available."""

    total_agents: int
    agents: List[AgentCapabilityInfo]
    coordination_modes: List[str]
    multi_agent_support: bool


class AgentStatusData(BaseModel):
    """data payload for GET /agent/agents/status."""

    ai_stack_status: str
    total_agents: int
    available_agents: List[str]
    multi_agent_coordination: bool
    npu_acceleration: bool
    research_capabilities: bool
    development_tools: bool


class AgentTaskData(BaseModel):
    """Base for agent execution payload models that invoke AI Stack multi-agent queries."""

    agents_used: List[str]
    execution_time: float
    result: Optional[Dict[str, Any]] = None


class EnhancedGoalData(AgentTaskData):
    """data payload for POST /agent/goal/enhanced."""

    goal: str
    coordination_mode: str
    priority: Optional[str] = None
    enhanced_context_used: bool
    knowledge_base_integrated: bool
    timestamp: str


class MultiAgentCoordinationData(AgentTaskData):
    """data payload for POST /agent/multi-agent/coordinate."""

    task: str
    coordination_strategy: str
    subtasks_count: int
    dependencies_count: int
    timestamp: str


class AgentResearchData(AgentTaskData):
    """data payload for POST /agent/research/comprehensive."""

    research_query: str
    research_depth: Optional[str] = None
    include_web: bool
    include_code_search: bool
    sources: Optional[List[str]] = None


class DevelopmentAnalysisData(AgentTaskData):
    """data payload for POST /agent/development/analyze."""

    analysis_type: str
    target_path: str
    include_performance: bool
    include_optimization: bool


class MultiAgentQueryData(BaseModel):
    """data payload for POST /ai-stack/orchestrate/multi-agent-query."""

    query: str
    coordination_mode: str
    agents_used: List[str]
    results: Dict[str, Any]


class EnhancedKnowledgeSearchData(BaseModel):
    """data payload for POST /ai-stack/knowledge/enhanced-search."""

    local_kb: List[Dict[str, Any]]
    enhanced: Dict[str, Any]


class ComprehensiveResearchData(BaseModel):
    """data payload for POST /ai-stack/research/comprehensive."""

    research: Dict[str, Any]
    web_research: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# agent_org.py schemas (#6042)
# ---------------------------------------------------------------------------


class OrgNodeResponse(BaseModel):
    """Single node in the org tree response (#1405)."""

    agent_id: str
    name: str
    org_role: str
    title: Optional[str] = None
    capabilities: Optional[str] = None
    direct_reports_count: int = 0
    children: List["OrgNodeResponse"] = Field(default_factory=list)


OrgNodeResponse.model_rebuild()


class AgentSummary(BaseModel):
    """Compact agent summary used in chain of command (#1405)."""

    agent_id: str
    name: str
    org_role: str
    title: Optional[str] = None


class ChainOfCommandResponse(BaseModel):
    """Ordered list from agent to org root (#1405)."""

    chain: List[AgentSummary]


class UpdateOrgRequest(BaseModel):
    """Request body for PATCH /agents/{agent_id}/org (#1405)."""

    reports_to: Optional[str] = Field(
        default=None,
        description="agent_id of the new manager, or null to clear",
    )
    org_role: Optional[str] = Field(
        default=None,
        description="One of: manager, coordinator, specialist, worker",
    )
    title: Optional[str] = Field(default=None, description="Human-readable job title")
    capabilities: Optional[str] = Field(
        default=None, description="Free-text capability description"
    )


class UpsertOrgRequest(BaseModel):
    """Request body for PUT /agents/{agent_id}/org (#1405)."""

    name: str
    org_role: str = "worker"
    reports_to: Optional[str] = None
    title: Optional[str] = None
    capabilities: Optional[str] = None


class AgentDelegateRequest(BaseModel):
    """Request body for POST /{manager_id}/delegate (#1753)."""

    assignee_id: str = Field(..., description="Direct report to assign to")
    task_description: str = Field(..., description="What the assignee should do")
    context: Optional[Dict[str, Any]] = Field(
        default=None, description="Extra context for the task"
    )


class DelegationResponse(BaseModel):
    """Response for a task delegation (#1753)."""

    id: str
    delegator_id: str
    assignee_id: str
    task_description: str
    status: str
    escalated_to: Optional[str] = None
    created_at: Optional[str] = None


class DelegationStatusUpdate(BaseModel):
    """Request body for PATCH /delegations/{id}/status (#1753)."""

    status: str = Field(..., description="New status value")
    result: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# collaboration.py schemas (#6042)
# ---------------------------------------------------------------------------


class CollabInviteRequest(BaseModel):
    """Request to invite user to session."""

    user_id: str = Field(..., description="User ID to invite")
    permission: PermissionLevel = Field(
        ..., description="Permission level (owner/editor/viewer)"
    )


class CollabRemoveRequest(BaseModel):
    """Request to remove collaborator."""

    user_id: str = Field(..., description="User ID to remove")


class CollabShareSecretRequest(BaseModel):
    """Request to share secret with session participants."""

    secret_id: str = Field(..., description="Secret ID to share")
    participant_ids: Optional[List[str]] = Field(
        None,
        description="Specific participants (None = all with editor+)",
    )


class CollabParticipantResponse(BaseModel):
    """Participant information."""

    user_id: str
    permission: str
    is_owner: bool
    online: bool = False


class SessionParticipantsResponse(BaseModel):
    """Session participants list."""

    session_id: str
    owner_id: str
    participants: List[CollabParticipantResponse]
    total_count: int


class CollabInviteResponse(BaseModel):
    """Invitation response."""

    success: bool
    session_id: str
    invited_user_id: str
    permission: str


class CollabRemoveResponse(BaseModel):
    """Remove collaborator response."""

    success: bool
    session_id: str
    removed_user_id: str


# user_management/teams.py schemas (#6042)


class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    settings: Optional[dict] = Field(default_factory=dict)
    is_default: bool = Field(False)


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    settings: Optional[dict] = Field(None)


class MembershipUpdate(BaseModel):
    role: str = Field(..., description="New role (owner, admin, member)")


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    email: str
    display_name: Optional[str]
    role: str
    joined_at: str

    model_config = {"from_attributes": True}


class TeamResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: Optional[str]
    settings: dict
    is_default: bool
    member_count: int = 0
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class TeamListResponse(BaseModel):
    teams: List[TeamResponse]
    total: int
    limit: int
    offset: int


class TeamCreatedResponse(BaseModel):
    success: bool = True
    message: str
    team: TeamResponse


class TeamDeletedResponse(BaseModel):
    success: bool = True
    message: str


class MemberAddedResponse(BaseModel):
    success: bool = True
    message: str
    member: MemberResponse


class MemberRemovedResponse(BaseModel):
    success: bool = True
    message: str


# user_management/users.py schemas (#6042)


class UserCreatedResponse(BaseModel):
    success: bool = True
    message: str
    user: _UserResponse


class UserDeletedResponse(BaseModel):
    success: bool = True
    message: str


class PasswordChangedResponse(BaseModel):
    success: bool = True
    message: str


class RoleAssignmentResponse(BaseModel):
    success: bool = True
    message: str
    role_id: uuid.UUID


class RoleUpdateRequest(BaseModel):
    role: str = Field(..., description="Role name: admin, user, or readonly",
                     pattern="^(admin|user|readonly)$")


class RoleUpdateResponse(BaseModel):
    success: bool = True
    message: str
    username: str
    role: str


class UserSearchResult(BaseModel):
    id: str
    name: str
    type: str = "user"


class UserSearchResponse(BaseModel):
    users: List[UserSearchResult]
    available: bool


# auth.py schemas (#6042)


class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("Username cannot be empty")
        if len(v) > 50:
            raise ValueError("Username too long")
        v = v.strip().lower()
        if not v.replace("_", "").replace("-", "").replace(".", "").isalnum():
            raise ValueError("Username contains invalid characters")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if not v or len(v) < 1:
            raise ValueError("Password cannot be empty")
        if len(v) > 128:
            raise ValueError("Password too long")
        return v


class LoginResponse(BaseModel):
    success: bool
    message: str
    user: Optional[dict] = None
    token: Optional[str] = None
    session_id: Optional[str] = None


class LogoutRequest(BaseModel):
    session_id: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(v) > 128:
            raise ValueError("Password too long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class ChangePasswordResponse(BaseModel):
    success: bool
    message: str


class SignupRequest(BaseModel):
    username: str
    email: str
    password: str
    display_name: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        v = v.strip().lower()
        if not v or len(v) < 3:
            raise ValueError("Username must be at least 3 characters")
        if len(v) > 50:
            raise ValueError("Username too long")
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username contains invalid characters")
        return v

    @field_validator("email")
    @classmethod
    def validate_email(cls, v):
        if "@" not in v or len(v) > 255:
            raise ValueError("Invalid email address")
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password too long")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class SignupResponse(BaseModel):
    success: bool
    message: str
    username: str | None = None


# user_management/organizations.py schemas (#6042)


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    slug: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    settings: Optional[dict] = Field(default_factory=dict)
    subscription_tier: str = Field("free")
    max_users: int = Field(-1)


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=500)
    settings: Optional[dict] = None
    subscription_tier: Optional[str] = None
    max_users: Optional[int] = None


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: Optional[str]
    settings: dict
    subscription_tier: str
    max_users: int
    is_active: bool
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class OrganizationListResponse(BaseModel):
    organizations: List[OrganizationResponse]
    total: int
    limit: int
    offset: int


class OrganizationCreatedResponse(BaseModel):
    success: bool = True
    message: str
    organization: OrganizationResponse


class OrganizationDeletedResponse(BaseModel):
    success: bool = True
    message: str


class OrganizationStatsResponse(BaseModel):
    organization_id: str
    name: str
    slug: str
    subscription_tier: str
    users: dict
    teams: dict
    is_active: bool
    created_at: Optional[str]
