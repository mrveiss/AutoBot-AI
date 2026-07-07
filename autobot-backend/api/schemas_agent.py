# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent config, memory, and LLM schemas.
"""

import uuid
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator

from models.session_collaboration import PermissionLevel
from services.personality_service import SUPPORTED_LANGUAGES
from skills.models import GovernanceMode, SkillActivationLevel
from type_defs.common import Metadata
from user_management.schemas import UserResponse as _UserResponse

_PERSONALITY_VALID_TONES = {"direct", "professional", "casual", "technical"}


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
    output: str | None = None
    status: str | None = None


class AgentHealthResponse(BaseModel):
    """Response for GET /health/detailed."""

    status: str
    ai_stack_available: bool
    multi_agent_coordination: bool
    advanced_capabilities: bool
    timestamp: str
    error: str | None = None


# ---------------------------------------------------------------------------
# task_memory.py schemas
# ---------------------------------------------------------------------------


class MemoryStatisticsResponse(BaseModel):
    """Response for GET /statistics."""

    period_days: int
    timestamp: str
    task_execution: Any | None = None
    markdown_system: Any | None = None
    active_tasks: Any | None = None
    performance_insights: Any | None = None


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
    scan_results: Any | None = None
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
    references: Any | None = None


class MemoryEmbeddingCacheStatsResponse(BaseModel):
    """Response for GET /embeddings/cache-stats."""

    cache_size: Any | None = None
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
    model: str | None = None
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
    trace: Dict[str, Any] | None = None
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
    message: str | None = None

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

    selected_model: str | None = None
    model_details: Dict[str, Any] | None = None
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
    augmented_prompt: str
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
    role: str | None = None
    auth_enabled: bool
    deployment_mode: str | None = None
    error: str | None = None


class AuthPermissionResponse(BaseModel):
    """Response for GET /auth/permissions/{operation}."""

    permitted: bool
    operation: str
    user_role: str | None = None
    username: str | None = None
    error: str | None = None


class AuthValidateRequest(BaseModel):
    """Optional body for POST /auth/validate — token may also come from Bearer header."""

    token: str | None = None


class AuthValidateClaims(BaseModel):
    """Claims block nested inside AuthValidateResponse."""

    username: str | None = None
    role: str | None = None
    user_id: str | None = None
    org_id: str | None = None
    email: str | None = None
    exp: int | None = None


class AuthValidateResponse(BaseModel):
    """Response for POST /auth/validate (#10195)."""

    valid: bool
    claims: AuthValidateClaims | None = None
    expired: bool = False
    revoked: bool = False


class AuthRoleEntry(BaseModel):
    """Single role entry for GET /auth/roles (#10195)."""

    name: str
    permissions: List[str]


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
    message: str | None = None
    previous_state: str | None = None
    current_state: str | None = None
    pending_approval: Any | None = None
    error: str | None = None


class AgentTerminalResumeResponse(BaseModel):
    """Response for POST /agent-terminal/sessions/{session_id}/resume."""

    status: str
    message: str | None = None
    current_state: str | None = None
    error: str | None = None


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


# ---------------------------------------------------------------------------
# Typed inner result models for AgentTaskData subclasses (Issue #6407)
# extra='allow' keeps the schema backward-compatible while the external
# AI Stack service response is fully documented.
# ---------------------------------------------------------------------------


class GoalExecutionResult(BaseModel):
    """Result payload for advanced goal execution via multi-agent coordination."""

    model_config = {"extra": "allow"}

    final_answer: str | None = None
    steps_taken: int | None = None
    reasoning: str | None = None
    agents_output: Dict[str, Any] | None = None


class MultiAgentCoordinationResult(BaseModel):
    """Result payload for multi-agent task coordination."""

    model_config = {"extra": "allow"}

    outcome: str | None = None
    subtask_results: List[Any] | None = None
    coordinated_response: str | None = None
    agents_output: Dict[str, Any] | None = None


class ResearchResult(BaseModel):
    """Result payload for comprehensive research tasks."""

    model_config = {"extra": "allow"}

    summary: str | None = None
    findings: List[Any] | None = None
    sources_consulted: List[str] | None = None
    confidence: float | None = None


class DevelopmentAnalysisResult(BaseModel):
    """Result payload for development codebase analysis."""

    model_config = {"extra": "allow"}

    recommendations: List[Any] | None = None
    issues_found: int | None = None
    speedup_opportunities: List[Any] | None = None
    analysis_summary: str | None = None


class AgentTaskData(BaseModel):
    """Base for agent execution payload models that invoke AI Stack multi-agent queries."""

    agents_used: List[str]
    execution_time: float
    result: Dict[str, Any] | None = None


class GoalData(AgentTaskData):
    """data payload for POST /agent/goal/orchestrated."""

    goal: str
    coordination_mode: str
    priority: str | None = None
    context_used: bool
    knowledge_base_integrated: bool
    timestamp: str
    result: GoalExecutionResult | None = None


class MultiAgentCoordinationData(AgentTaskData):
    """data payload for POST /agent/multi-agent/coordinate."""

    task: str
    coordination_strategy: str
    subtasks_count: int
    dependencies_count: int
    timestamp: str
    result: MultiAgentCoordinationResult | None = None


class AgentResearchData(AgentTaskData):
    """data payload for POST /agent/research/comprehensive."""

    research_query: str
    research_depth: str | None = None
    include_web: bool
    include_code_search: bool
    sources: List[str] | None = None
    result: ResearchResult | None = None


class DevelopmentAnalysisData(AgentTaskData):
    """data payload for POST /agent/development/analyze."""

    analysis_type: str
    target_path: str
    include_performance: bool
    include_optimization: bool
    result: DevelopmentAnalysisResult | None = None


class MultiAgentQueryData(BaseModel):
    """data payload for POST /ai-stack/orchestrate/multi-agent-query."""

    query: str
    coordination_mode: str
    agents_used: List[str]
    results: Dict[str, Any]


class KnowledgeSearchData(BaseModel):
    """data payload for POST /ai-stack/knowledge/search."""

    local_kb: List[Dict[str, Any]]
    rag_augmented: Dict[str, Any]


class ComprehensiveResearchData(BaseModel):
    """data payload for POST /ai-stack/research/comprehensive."""

    research: Dict[str, Any]
    web_research: Dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# agent_org.py schemas (#6042)
# ---------------------------------------------------------------------------


class OrgNodeResponse(BaseModel):
    """Single node in the org tree response (#1405)."""

    agent_id: str
    name: str
    org_role: str
    title: str | None = None
    capabilities: str | None = None
    direct_reports_count: int = 0
    children: List["OrgNodeResponse"] = Field(default_factory=list)


OrgNodeResponse.model_rebuild()


class AgentSummary(BaseModel):
    """Compact agent summary used in chain of command (#1405)."""

    agent_id: str
    name: str
    org_role: str
    title: str | None = None


class ChainOfCommandResponse(BaseModel):
    """Ordered list from agent to org root (#1405)."""

    chain: List[AgentSummary]


class AgentStatusItem(BaseModel):
    """Runtime status for one registered agent (#10502).

    Shape consumed by the Home dashboard "Agent Activity Monitor"
    (frontend ``useAgentActivityData`` ``Agent`` interface).
    """

    id: str
    name: str
    type: str = "worker"
    status: str = "idle"
    currentTask: str | None = None
    tasksCompleted: int = 0
    uptime: int = 0
    successRate: int = 0
    recentTasks: List[Dict[str, Any]] = Field(default_factory=list)
    activityTimeline: List[Dict[str, Any]] = Field(default_factory=list)


class AgentStatusListResponse(BaseModel):
    """All registered agents with runtime status (#10502)."""

    agents: List[AgentStatusItem] = Field(default_factory=list)
    total: int = 0


class UpdateOrgRequest(BaseModel):
    """Request body for PATCH /agents/{agent_id}/org (#1405)."""

    reports_to: str | None = Field(
        default=None,
        description="agent_id of the new manager, or null to clear",
    )
    org_role: str | None = Field(
        default=None,
        description="One of: manager, coordinator, specialist, worker",
    )
    title: str | None = Field(default=None, description="Human-readable job title")
    capabilities: str | None = Field(default=None, description="Free-text capability description")


class UpsertOrgRequest(BaseModel):
    """Request body for PUT /agents/{agent_id}/org (#1405)."""

    name: str
    org_role: str = "worker"
    reports_to: str | None = None
    title: str | None = None
    capabilities: str | None = None


class AgentDelegateRequest(BaseModel):
    """Request body for POST /{manager_id}/delegate (#1753)."""

    assignee_id: str = Field(..., description="Direct report to assign to")
    task_description: str = Field(..., description="What the assignee should do")
    context: Dict[str, Any] | None = Field(default=None, description="Extra context for the task")


class DelegationResponse(BaseModel):
    """Response for a task delegation (#1753)."""

    id: str
    delegator_id: str
    assignee_id: str
    task_description: str
    status: str
    escalated_to: str | None = None
    created_at: str | None = None


class DelegationStatusUpdate(BaseModel):
    """Request body for PATCH /delegations/{id}/status (#1753)."""

    status: str = Field(..., description="New status value")
    result: Dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# collaboration.py schemas (#6042)
# ---------------------------------------------------------------------------


class CollabInviteRequest(BaseModel):
    """Request to invite user to session."""

    user_id: str = Field(..., description="User ID to invite")
    permission: PermissionLevel = Field(..., description="Permission level (owner/editor/viewer)")


class CollabRemoveRequest(BaseModel):
    """Request to remove collaborator."""

    user_id: str = Field(..., description="User ID to remove")


class CollabShareSecretRequest(BaseModel):
    """Request to share secret with session participants."""

    secret_id: str = Field(..., description="Secret ID to share")
    participant_ids: List[str] | None = Field(
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
    description: str | None = Field(None, max_length=500)
    settings: dict | None = Field(default_factory=dict)
    is_default: bool = Field(False)


class TeamUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=500)
    settings: dict | None = Field(None)


class MembershipUpdate(BaseModel):
    role: str = Field(..., description="New role (owner, admin, member)")


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    username: str
    email: str
    display_name: str | None
    role: str
    joined_at: str

    model_config = {"from_attributes": True}


class TeamResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    description: str | None
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
    role: str = Field(..., description="Role name: admin, user, or readonly", pattern="^(admin|user|readonly)$")


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


class PasswordWarning(BaseModel):
    """Non-blocking soft warning attached to a successful login response (#10199).

    Presence of this field does NOT indicate an auth failure — the token is
    still valid.  Clients should surface the ``reason`` as a nudge to the user
    to update their password.
    """

    weak: bool = True
    reason: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    user: dict | None = None
    token: str | None = None
    session_id: str | None = None
    password_warning: PasswordWarning | None = None
    """Soft warning when the submitted password is weak (non-blocking, #10199)."""


class LogoutRequest(BaseModel):
    session_id: str | None = None


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
    slug: str | None = Field(None, max_length=100)
    description: str | None = Field(None, max_length=500)
    settings: dict | None = Field(default_factory=dict)
    subscription_tier: str = Field("free")
    max_users: int = Field(-1)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=500)
    settings: dict | None = None
    subscription_tier: str | None = None
    max_users: int | None = None


class OrganizationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None
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
    created_at: str | None


# ---------------------------------------------------------------------------
# agent.py request schemas (#6042)
# ---------------------------------------------------------------------------


class GoalPayload(BaseModel):
    """Goal payload — unified from bare and advanced variants (#10666 B1).

    The simple /goal endpoint reads only ``goal``/``use_phi2``/``user_role``.
    The /goal/orchestrated endpoint also reads the remaining optional fields.
    All added fields carry defaults, so existing callers that only send
    ``goal`` remain fully backward-compatible.
    """

    goal: str = Field(..., min_length=1, max_length=10000, description="Goal description")
    use_phi2: bool = False
    user_role: str = "user"
    # Fields from the former GoalPayload — all optional so /goal callers unaffected
    agents: List[str] | None = Field(None, description="Specific agents to use")
    coordination_mode: str = Field("intelligent", description="Coordination mode (parallel, sequential, intelligent)")
    priority: str = Field("normal", description="Task priority (low, normal, high, urgent)")
    context: str | None = Field(None, description="Additional context")
    use_knowledge_base: bool = Field(True, description="Use knowledge base for context")
    include_reasoning: bool = Field(False, description="Include reasoning steps")
    max_execution_time: int = Field(300, ge=30, le=1800, description="Max execution time in seconds")


class CommandApprovalPayload(BaseModel):
    task_id: str
    approved: bool
    user_role: str = "user"


class MultiAgentTaskPayload(BaseModel):
    """Multi-agent task coordination payload."""

    task: str = Field(..., min_length=1, description="Task description")
    agents: List[str] = Field(..., min_length=1, description="Agents to coordinate")
    coordination_strategy: str = Field("adaptive", description="Coordination strategy")
    subtasks: List[Metadata] | None = Field(None, description="Predefined subtasks")
    dependencies: List[Dict[str, str]] | None = Field(None, description="Task dependencies")


class AgentAnalysisRequest(BaseModel):
    """Agent analysis request for development and optimization."""

    analysis_type: str = Field("comprehensive", description="Analysis type")
    target_path: str | None = Field(None, description="Specific path to analyze")
    include_performance: bool = Field(True, description="Include performance analysis")
    include_optimization: bool = Field(True, description="Include optimization suggestions")


class ResearchTaskRequest(BaseModel):
    """Research task request using multiple research agents."""

    research_query: str = Field(..., min_length=1, description="Research query")
    research_depth: str = Field("comprehensive", description="Research depth")
    include_web: bool = Field(True, description="Include web research")
    include_code_search: bool = Field(False, description="Include code search")
    sources: List[str] | None = Field(None, description="Specific sources")


class PersonalityProfileSummary(BaseModel):
    id: str
    name: str
    is_system: bool
    active: bool


class PersonalityProfileDetail(BaseModel):
    id: str
    name: str
    tagline: str
    tone: str
    character_traits: List[str]
    operating_style: List[str]
    off_limits: List[str]
    custom_notes: str
    is_system: bool
    created_by: str
    created_at: str
    updated_at: str
    voice_id: str = ""
    voice_ids: Dict[str, str] = {}
    language_code: str = "en"


class PersonalityProfileCreate(BaseModel):
    name: str
    tagline: str = ""
    tone: str = "direct"
    character_traits: List[str] = []
    operating_style: List[str] = []
    off_limits: List[str] = []
    custom_notes: str = ""
    voice_id: str = ""
    voice_ids: Dict[str, str] = {}
    language_code: str = "en"

    @field_validator("tone")
    @classmethod
    def tone_must_be_valid(cls, v: str) -> str:
        if v not in _PERSONALITY_VALID_TONES:
            raise ValueError(f"tone must be one of {sorted(_PERSONALITY_VALID_TONES)}")
        return v

    @field_validator("language_code")
    @classmethod
    def language_code_must_be_valid(cls, v: str) -> str:
        if v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language_code must be one of {sorted(SUPPORTED_LANGUAGES)}")
        return v


class PersonalityProfileUpdate(BaseModel):
    name: str | None = None
    tagline: str | None = None
    tone: str | None = None
    character_traits: List[str] | None = None
    operating_style: List[str] | None = None
    off_limits: List[str] | None = None
    custom_notes: str | None = None
    voice_id: str | None = None
    voice_ids: Dict[str, str] | None = None
    language_code: str | None = None

    @field_validator("tone")
    @classmethod
    def tone_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in _PERSONALITY_VALID_TONES:
            raise ValueError(f"tone must be one of {sorted(_PERSONALITY_VALID_TONES)}")
        return v

    @field_validator("language_code")
    @classmethod
    def language_code_must_be_valid(cls, v: str | None) -> str | None:
        if v is not None and v not in SUPPORTED_LANGUAGES:
            raise ValueError(f"language_code must be one of {sorted(SUPPORTED_LANGUAGES)}")
        return v


class PersonalityToggleRequest(BaseModel):
    enabled: bool


class PersonalityStatusResponse(BaseModel):
    enabled: bool
    active_id: str | None


class SkillConfigUpdate(BaseModel):
    """Request body for updating a skill's configuration."""

    config: Dict[str, Any] = Field(..., description="Configuration values")


class SkillActionRequest(BaseModel):
    """Request body for executing a skill action."""

    action: str = Field(..., description="Tool/action name to execute")
    params: Dict[str, Any] = Field(default_factory=dict, description="Action parameters")


class UserSkillPreferences(BaseModel):
    """Request body for updating user skill preferences."""

    preferences: Dict[str, bool] = Field(..., description="Mapping of skill_name -> enabled")


class SkillFeedbackRequest(BaseModel):
    """Request body for submitting skill feedback."""

    rating: int = Field(..., description="User rating (1-5)", ge=1, le=5)
    feedback: str | None = Field(None, description="Feedback text")


class SkillInstallRequest(BaseModel):
    """Request body for installing a skill from the catalog."""

    catalog_url: str = Field(..., description="HTTP URL of the catalog endpoint")
    repo_id: str | None = Field(None, description="SkillRepo.id to link the package to")


# ---------------------------------------------------------------------------
# skills_governance.py schemas
# ---------------------------------------------------------------------------


class GapRequest(BaseModel):
    """Request body for generating a skill to fill a capability gap."""

    task: str = Field(...)
    agent_output: str = Field("")


class ApprovalDecision(BaseModel):
    """Request body for approving or rejecting a skill approval record."""

    approved: bool
    trust_level: SkillActivationLevel = SkillActivationLevel.MONITORED
    notes: str = ""


class GovernanceModeUpdate(BaseModel):
    """Request body for updating the active governance mode."""

    mode: GovernanceMode


# ---------------------------------------------------------------------------
# llm_awareness.py schemas
# ---------------------------------------------------------------------------


class LLMContextRequest(BaseModel):
    level: str = "basic"
    include_history: bool = False
    include_progression_rules: bool = False


class PromptInjectionRequest(BaseModel):
    prompt: str
    context_level: str = "basic"
    preserve_format: bool = True


class QueryAnalysisRequest(BaseModel):
    query: str
    analyze_capabilities: bool = True
    provide_recommendations: bool = True


# ---------------------------------------------------------------------------
# llm_optimization.py schemas
# ---------------------------------------------------------------------------


class LLMOptimizationRequest(BaseModel):
    """Model for optimization requests."""

    query: str
    task_type: str = "chat"
    max_response_time: float | None = None
    min_quality: float | None = None
    context_length: int = 0
    user_preference: str | None = None


class ModelPerformanceData(BaseModel):
    """Model for tracking performance data."""

    model_name: str
    response_time: float
    response_tokens: int
    success: bool
    user_rating: float | None = None


class InferenceOptimizationSettings(BaseModel):
    """Settings for inference optimization."""

    prompt_compression_enabled: bool = True
    prompt_compression_ratio: float = 0.7
    prompt_compression_min_length: int = 100
    prompt_compression_preserve_code: bool = True
    prompt_compression_aggressive: bool = False

    cache_enabled: bool = True
    cache_l1_size: int = 100
    cache_l2_ttl: int = 300

    cloud_connection_pool_size: int = 100
    cloud_batch_window_ms: int = 50
    cloud_max_batch_size: int = 10
    cloud_retry_max_attempts: int = 3
    cloud_retry_base_delay: float = 1.0
    cloud_retry_max_delay: float = 60.0

    local_speculation_enabled: bool = False
    local_speculation_draft_model: str = ""
    local_speculation_num_tokens: int = 5
    local_speculation_use_ngram: bool = False
    local_quantization_type: str = "none"
    local_vllm_multi_step: int = 8
    local_vllm_prefix_caching: bool = True
    local_vllm_async_output: bool = True


# ---------------------------------------------------------------------------
# a2a.py schemas
# ---------------------------------------------------------------------------


class TaskSendRequest(BaseModel):
    """Body for POST /tasks — submit a new A2A task."""

    message: str = Field(..., description="The natural-language task to execute")
    context: Dict[str, Any] | None = Field(None, description="Optional key-value context passed to the orchestrator")


class TaskSendResponse(BaseModel):
    """Immediate response when a task is accepted."""

    id: str
    state: str
    trace_id: str


class RemoteVerifyRequest(BaseModel):
    """Body for POST /capabilities/verify."""

    url: str = Field(..., description="Base URL of the remote agent to verify")


# ---------------------------------------------------------------------------
# agents_self_improvement.py schemas
# ---------------------------------------------------------------------------


class TaskOutcomeResponse(BaseModel):
    """Serialized task outcome record."""

    task_type: str
    goal: str
    output_summary: str
    strategy_used: str
    score: float
    rationale: str
    timestamp: str


class LearnedStrategyResponse(BaseModel):
    """Serialized learned strategy record."""

    task_type: str
    best_approach: str
    best_prompt_template: str
    avg_score: float
    sample_size: int
    confidence: float
    failure_patterns: List[str]
    timestamp: str


class ResetLearningResponse(BaseModel):
    """Response for reset-learning operation."""

    success: bool
    message: str


class FailurePatternRecord(BaseModel):
    """Serialized failure pattern for the knowledge-export document (GH#11151)."""

    pattern_id: str
    causal_chain: str
    occurrence_count: int
    successful_resolutions: List[str]
    resolution_success_rate: float
    confidence: float


class LearnedKnowledgeExport(BaseModel):
    """Human-reviewable export of an agent's learned knowledge (GH#11151)."""

    task_type: str
    learned_strategy: LearnedStrategyResponse | None
    high_confidence_threshold: float
    high_confidence_failure_patterns: List[FailurePatternRecord]


class LearnedKnowledgeImport(BaseModel):
    """Operator-curated learned strategy to import (GH#11151).

    ``best_prompt_template`` and ``best_approach`` are treated as untrusted and
    sanitized before persistence (reuses the #11060 data-only framing).
    """

    task_type: str
    best_approach: str
    best_prompt_template: str
    avg_score: float = 0.0
    sample_size: int = 0
    confidence: float = 0.0
    failure_patterns: List[str] = Field(default_factory=list)


class KnowledgeImportResponse(BaseModel):
    """Response for a knowledge-import operation (GH#11151)."""

    success: bool
    message: str
    task_type: str


# ---------------------------------------------------------------------------
# agent_config.py schemas
# ---------------------------------------------------------------------------


class AgentConfig(BaseModel):
    """Agent configuration summary model — minimal shape for list views."""

    agent_id: str
    name: str
    model: str
    provider: str
    enabled: bool
    priority: int | None = 1


class AgentConfigDetailHealthCheck(BaseModel):
    """Inline health-check block returned by GET /agents/{agent_id}."""

    last_check: str = Field(..., description="ISO timestamp of last health check")
    response_time: float = Field(default=0.0)
    status: str = Field(..., description="healthy | disabled")


class AgentConfigDetailOptions(BaseModel):
    """Inline configuration_options block returned by GET /agents/{agent_id}."""

    available_models: List[str] = Field(default_factory=list)
    available_providers: List[str] = Field(default_factory=list)
    configurable_settings: List[str] = Field(default_factory=list)


class AgentConfigDetailResponse(BaseModel):
    """Detailed response for GET /api/agents/{agent_id} — matches the actual
    dict shape produced by api/agent_config.py:946."""

    id: str
    name: str
    description: str
    current_model: str
    provider: str
    enabled: bool
    priority: int
    tasks: List[str] = Field(default_factory=list)
    mcp_tools: List[str] = Field(default_factory=list)
    default_model: str
    status: str = Field(..., description="connected | disconnected")
    config_source: str = Field(..., description="slm | local")
    configuration_options: AgentConfigDetailOptions
    health_check: AgentConfigDetailHealthCheck


class AgentModelUpdate(BaseModel):
    """Agent model update request."""

    agent_id: str
    model: str
    provider: str | None = "ollama"


# ---------------------------------------------------------------------------
# bi_export_endpoints.py schemas
# ---------------------------------------------------------------------------


class SavedReportRequest(BaseModel):
    """Request to save a BI report configuration."""

    name: str
    report_type: str = "executive"
    sections: List[str] = ["cost", "agents"]


# ---------------------------------------------------------------------------
# conversation_export.py schemas
# ---------------------------------------------------------------------------


class ConversationImportRequest(BaseModel):
    """Request body for importing a conversation."""

    document: dict = Field(
        ...,
        description=(
            "AutoBot conversation export document produced by the export endpoint " "(format: autobot-conversation-v1)."
        ),
    )
    on_conflict: str = Field(
        default="skip",
        description=("Conflict resolution strategy when session_id already exists. " "One of: skip, replace, rename."),
    )


# ---------------------------------------------------------------------------
# enterprise_features.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class EnterpriseStatusResponse(BaseModel):
    """Response for GET /status."""

    status: str
    enterprise_status: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class EnterpriseFeatureEnableResponse(BaseModel):
    """Response for POST /features/enable."""

    status: str
    feature: str = ""
    result: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class EnterpriseFeatureEnableAllResponse(BaseModel):
    """Response for POST /features/enable-all."""

    status: str
    phase: str = ""
    result: Dict[str, Any] = Field(default_factory=dict)
    success_rate: str = ""
    enterprise_capabilities: Dict[str, bool] = Field(default_factory=dict)
    message: str = ""
    warnings: List[str] = Field(default_factory=list)


class EnterpriseFeatureListResponse(BaseModel):
    """Response for GET /features."""

    status: str
    features: List[Dict[str, Any]] = Field(default_factory=list)
    total_features: int = 0
    categories: List[str] = Field(default_factory=list)
    statuses: List[str] = Field(default_factory=list)


class EnterpriseBulkEnableResponse(BaseModel):
    """Response for POST /features/bulk-enable."""

    status: str
    results: Dict[str, Any] = Field(default_factory=dict)
    summary: str = ""


class EnterprisePerformanceOptimizeResponse(BaseModel):
    """Response for POST /performance/optimize."""

    status: str
    optimization: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class EnterpriseInfrastructureResponse(BaseModel):
    """Response for GET /infrastructure."""

    status: str
    infrastructure: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class EnterpriseDeploymentResponse(BaseModel):
    """Response for POST /deployment/zero-downtime."""

    status: str
    deployment: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class EnterprisePhase4ValidationResponse(BaseModel):
    """Response for GET /phase4/validation."""

    status: str
    validation: Dict[str, Any] = Field(default_factory=dict)
    message: str = ""


# ---------------------------------------------------------------------------
# agent_config.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class AgentConfigListAgentsResponse(BaseModel):
    """Response for GET /agents."""

    agents: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    global_provider_type: str = ""
    timestamp: str = ""


class AgentConfigAllAgentsResponse(BaseModel):
    """Response for GET /agents/all."""

    agents: List[Dict[str, Any]] = Field(default_factory=list)
    specialized_agents: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""


class AgentConfigSpecializedListResponse(BaseModel):
    """Response for GET /agents/specialized."""

    agents: List[Dict[str, Any]] = Field(default_factory=list)
    total_count: int = 0
    categories: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = ""


class AgentConfigSpecializedDetailResponse(BaseModel):
    """Response for GET /agents/specialized/{agent_id}."""

    id: str = ""
    name: str = ""
    description: str = ""
    tools: List[str] = Field(default_factory=list)
    model: str | None = None
    category: str | None = None


class AgentConfigUsageResponse(BaseModel):
    """Response for GET /agents/usage."""

    agents: List[Dict[str, Any]] = Field(default_factory=list)
    daily_trend: List[Dict[str, Any]] = Field(default_factory=list)
    total_tasks: int = 0
    timestamp: str = ""


# ---------------------------------------------------------------------------
# adapters.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class AdapterListResponse(BaseModel):
    """Response for GET /."""

    adapters: List[Any] = Field(default_factory=list)
    total: int = 0


class AdapterTestResponse(BaseModel):
    """Response for GET /{adapter_type}/test."""

    adapter_type: str = ""
    healthy: bool = False
    diagnostics: List[Any] = Field(default_factory=list)
    models_available: List[Any] = Field(default_factory=list)
    response_time: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AdapterModelsResponse(BaseModel):
    """Response for GET /{adapter_type}/models."""

    adapter_type: str
    models: List[Any] = Field(default_factory=list)
    total: int = 0


class AdapterOverrideSetResponse(BaseModel):
    """Response for POST /agent/{agent_id}/override."""

    agent_id: str
    adapter_type: str


class AdapterOverrideClearResponse(BaseModel):
    """Response for DELETE /agent/{agent_id}/override."""

    agent_id: str
    cleared: bool


# ---------------------------------------------------------------------------
# skills.py / overseer_handlers.py schemas (GH #6509 Batch E)
# ---------------------------------------------------------------------------


class SkillCatalogInstallData(BaseModel):
    """Response data for POST /skills/catalog/{name}/install."""

    success: bool = True
    id: str = ""
    name: str = ""
    version: str = ""
    trust_level: str = ""


class SkillFeedbackData(BaseModel):
    """Response data for POST /skills/{name}/feedback."""

    success: bool = True
    message: str = ""


class OverseerQueryStep(BaseModel):
    """A single step in an overseer execution plan."""

    step_number: int = 0
    description: str = ""
    command: str = ""


class OverseerQueryData(BaseModel):
    """Response data for POST /overseer/query/{session_id}."""

    success: bool = True
    plan_id: str = ""
    analysis: str = ""
    steps: List[OverseerQueryStep] = Field(default_factory=list)
    message: str = ""
    error: str | None = None
