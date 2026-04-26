# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent config, memory, and LLM schemas.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


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


# ---------------------------------------------------------------------------
# voice.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------
