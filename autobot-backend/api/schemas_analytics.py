# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analytics, cost, budget, usage, and metrics schemas.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from api.schemas_common import SuccessMessageResponse
from constants import PATH
from type_defs.common import Metadata


# ---------------------------------------------------------------------------
# Analytics schemas
# ---------------------------------------------------------------------------

class MetricsWorkflowResponse(BaseModel):
    """Response for GET /workflow/{workflow_id}."""

    success: bool
    workflow_id: str
    metrics: Optional[Any] = None



class MetricsPerformanceSummaryResponse(BaseModel):
    """Response for GET /performance/summary."""

    success: bool
    performance_summary: Optional[Any] = None



class MetricsSystemCurrentResponse(BaseModel):
    """Response for GET /system/current."""

    success: bool
    system_metrics: Optional[Any] = None



class MetricsSystemHistoryResponse(BaseModel):
    """Response for GET /system/history."""

    success: bool
    cpu_history: List[Any]
    memory_history: List[Any]
    time_range: Dict[str, str]



class MetricsSystemSummaryResponse(BaseModel):
    """Response for GET /system/summary."""

    success: bool
    resource_summary: Optional[Any] = None



class MetricsExportResponse(BaseModel):
    """Response for GET /export/workflow and GET /export/system."""

    success: bool
    format: str
    data: Optional[Any] = None



class MetricsMonitoringStartResponse(BaseModel):
    """Response for POST /system/monitoring/start."""

    success: bool
    message: str
    collection_interval: Optional[Any] = None



class MetricsMonitoringStopResponse(SuccessMessageResponse):
    """Response for POST /system/monitoring/stop."""



class MetricsDashboardResponse(BaseModel):
    """Response for GET /dashboard."""

    success: bool
    dashboard: Dict[str, Any]



# ---------------------------------------------------------------------------
# logs.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class UsageSummaryPeriod(BaseModel):
    days: int
    start: str
    end: str



class UsageSummaryTokens(BaseModel):
    input: int
    output: int
    total: int



class UsageSummaryResponse(BaseModel):
    """Response for GET /usage/summary."""

    period: UsageSummaryPeriod
    tokens: UsageSummaryTokens
    cost_usd: float
    requests: int
    daily_costs: Dict[str, Any]
    by_model: Dict[str, Any]
    active_users: int



class UsageByUserAllResponse(BaseModel):
    """Response for GET /usage/by-user."""

    timestamp: str
    users: List[Any]
    total_users: int



class AnalyticsTrackEventResponse(BaseModel):
    """Response for POST /events/track."""

    status: str
    event_id: str
    broadcast_count: int



class AnalyticsCollectionStartResponse(BaseModel):
    """Response for POST /collection/start."""

    status: str
    message: str
    session_id: str
    metrics_collection: bool



class AnalyticsCollectionStopResponse(BaseModel):
    """Response for POST /collection/stop."""

    status: str
    message: str
    session_duration: str



class AnalyticsDashboardAnalyzeResponse(BaseModel):
    """Response for POST /dashboard/overview/analyze."""

    task_id: str
    status: str



class AnalyticsClearStuckTasksResponse(BaseModel):
    """Response for POST /dashboard/overview/tasks/clear-stuck."""

    cleared_count: int
    message: str


# ---------------------------------------------------------------------------
# npu_workers.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class CostModelEntry(BaseModel):
    model: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    call_count: int
    avg_cost_per_call: float



class CostByModelResponse(BaseModel):
    """Response for GET /cost/by-model."""

    timestamp: str
    models: List[CostModelEntry]
    total_models: int



class CostForecastPeriod(BaseModel):
    start: str
    days: int



class CostForecastBaseline(BaseModel):
    avg_daily_cost: float
    trend: str
    growth_rate_percent: float



class CostForecastValues(BaseModel):
    total_estimated_usd: float
    daily_estimates: Dict[str, Any]



class CostForecastResponse(BaseModel):
    """Response for GET /cost/forecast."""

    forecast_period: CostForecastPeriod
    baseline: CostForecastBaseline
    forecast: CostForecastValues
    confidence: str



class RecentUsageResponse(BaseModel):
    """Response for GET /cost/usage/recent."""

    count: int
    records: List[Any]



class ModelPricingEntry(BaseModel):
    model: str
    provider: str
    input_price_per_1m: float
    output_price_per_1m: float
    is_free: bool



class ModelPricingResponse(BaseModel):
    """Response for GET /cost/pricing."""

    pricing_date: str
    currency: str
    models: List[ModelPricingEntry]
    total_models: int



class CostEstimateResponse(BaseModel):
    """Response for GET /cost/estimate."""

    model: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    total_tokens: int



class BudgetAlertCreateResponse(BaseModel):
    """Response for POST /cost/budget-alert."""

    status: str
    alert: Dict[str, Any]



class BudgetAlertsListResponse(BaseModel):
    """Response for GET /cost/budget-alerts."""

    alerts: List[Any]
    count: int



class BudgetStatusResponse(BaseModel):
    """Response for GET /cost/budget-status."""

    timestamp: str
    current_costs: Dict[str, Any]
    budget_statuses: List[Any]



class AllAgentCostsResponse(BaseModel):
    """Response for GET /cost/by-agent."""

    timestamp: str
    agents: List[Any]
    total_agents: int


# ---------------------------------------------------------------------------
# analytics_architecture.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class AnalyticsArchitecturePatternsResponse(BaseModel):
    """Response for GET /architecture/patterns."""

    patterns: Dict[str, Any]
    total: int


class AnalyticsArchitectureQuickScanResponse(BaseModel):
    """Response for GET /architecture/quick-scan."""

    path: str
    files_analyzed: int
    patterns_found: Dict[str, int]
    top_patterns: List[Any]


class AnalyticsArchitectureLayersResponse(BaseModel):
    """Response for GET /architecture/layers."""

    layers: List[Any]
    total: int


class AnalyticsArchitectureDiagramResponse(BaseModel):
    """Response for GET /architecture/diagram."""

    format: str
    diagram: str


class AnalyticsArchitectureConsistencyResponse(BaseModel):
    """Response for GET /architecture/consistency."""

    consistency_results: List[Any]
    total_checked: int


class AnalyticsArchitectureHealthResponse(BaseModel):
    """Response for GET /architecture/health."""

    status: str
    available_patterns: int
    templates_loaded: int
    deprecated: bool
    use_instead: str


# ---------------------------------------------------------------------------
# analytics_bug_prediction.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class BugPredictionAnalyzeResponse(BaseModel):
    """Response for POST /bug-prediction/analyze."""

    task_id: str
    status: str


class BugPredictionStatusResponse(BaseModel):
    """Response for GET /bug-prediction/status/{task_id}.

    Shape from BackgroundTaskManager.get_status() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class BugPredictionClearStuckResponse(BaseModel):
    """Response for POST /bug-prediction/tasks/clear-stuck."""

    cleared_count: int
    message: str


class BugPredictionRiskFactorsResponse(BaseModel):
    """Response for GET /bug-prediction/factors."""

    factors: List[Any]
    total_weight: float
    scoring: Dict[str, str]


class BugPredictionRecordBugResponse(BaseModel):
    """Response for POST /bug-prediction/record-bug."""

    status: str
    bug: Dict[str, Any]
    message: str


# ---------------------------------------------------------------------------
# analytics_code.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class AnalyticsCodeIndexResponse(BaseModel):
    """Response for POST /analytics/code/index."""

    status: str
    request: Dict[str, Any]
    results: Optional[Any] = None
    cached_for_reuse: bool


class AnalyticsCodeStatusResponse(BaseModel):
    """Response for GET /analytics/code/status.

    Shape varies based on available tools — extra fields allowed.
    """

    model_config = {"extra": "allow"}

    tools_available: Dict[str, bool]


class AnalyticsCodeQualityAssessmentResponse(BaseModel):
    """Response for GET /analytics/quality/assessment."""

    overall_score: float
    maintainability: float
    testability: float
    documentation: float
    complexity: float
    security: float
    performance: float
    timestamp: str


class AnalyticsCodeQualityMetricsResponse(BaseModel):
    """Response for GET /analytics/code/quality-metrics.

    Varies between no-analysis and full-analysis paths — extra allowed.
    """

    model_config = {"extra": "allow"}


class AnalyticsCodeCommunicationChainsResponse(BaseModel):
    """Response for GET /analytics/code/communication-chains.

    Varies between no-analysis and full paths — extra allowed.
    """

    model_config = {"extra": "allow"}


class AnalyticsCodeQualityScoreResponse(BaseModel):
    """Response for GET /analytics/code/metrics/quality-score."""

    overall_score: float
    grade: str
    quality_factors: Dict[str, Any]
    recommendations: List[Any]
    last_analysis: Optional[str] = None
    codebase_metrics: Dict[str, Any]


# ---------------------------------------------------------------------------
# analytics_continuous_learning.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class ContinuousLearningStartStopResponse(BaseModel):
    """Response for POST /continuous-learning/start and /stop.

    Shape from engine.start()/stop() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class ContinuousLearningStatusResponse(BaseModel):
    """Response for GET /continuous-learning/status.

    Shape from engine.get_status() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class ContinuousLearningFeedbackResponse(BaseModel):
    """Response for POST /continuous-learning/feedback.

    Shape from engine.submit_feedback() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class ContinuousLearningRetrainResponse(BaseModel):
    """Response for POST /continuous-learning/retrain.

    Shape from engine.trigger_retrain() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class ContinuousLearningInsightsResponse(BaseModel):
    """Response for GET /continuous-learning/insights."""

    insights: List[Any]
    total: int


class ContinuousLearningGenerateInsightsResponse(BaseModel):
    """Response for POST /continuous-learning/insights/generate."""

    generated: int
    insights: List[Any]


class ContinuousLearningUpdateConfigResponse(BaseModel):
    """Response for PUT /continuous-learning/config."""

    updated: bool
    config: Dict[str, Any]


class ContinuousLearningHealthResponse(BaseModel):
    """Response for GET /continuous-learning/health."""

    status: str
    running: bool
    initialized: bool


# ---------------------------------------------------------------------------
# analytics_maintenance.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class MaintenanceRecommendationsResponse(BaseModel):
    """Response for GET /maintenance."""

    timestamp: str
    total_recommendations: int
    by_priority: Dict[str, int]
    recommendations: List[Any]


class MaintenanceByCategoryResponse(BaseModel):
    """Response for GET /maintenance/category/{category}."""

    category: str
    total: int
    recommendations: List[Any]


class MaintenanceSummaryResponse(BaseModel):
    """Response for GET /maintenance/summary."""

    timestamp: str
    summary: Dict[str, Any]
    critical_actions: List[Any]
    by_category: Dict[str, Any]


class OptimizationRecommendationsResponse(BaseModel):
    """Response for GET /optimization."""

    timestamp: str
    total_recommendations: int
    potential_savings: Dict[str, Any]
    by_resource_type: Dict[str, int]
    recommendations: List[Any]


class OptimizationByTypeResponse(BaseModel):
    """Response for GET /optimization/type/{resource_type}."""

    resource_type: str
    total: int
    recommendations: List[Any]


class OptimizationQuickWinsResponse(BaseModel):
    """Response for GET /optimization/quick-wins."""

    timestamp: str
    total_quick_wins: int
    estimated_savings: float
    recommendations: List[Any]


class MaintenanceDashboardResponse(BaseModel):
    """Response for GET /maintenance/dashboard.

    Shape from service.get_unified_dashboard() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class MaintenanceHealthStatusResponse(BaseModel):
    """Response for GET /maintenance/health."""

    timestamp: str
    health: Dict[str, Any]
    indicators: Dict[str, Any]


class MaintenanceCustomReportResponse(BaseModel):
    """Response for POST /maintenance/report and GET /maintenance/report/executive.

    Shape from service.generate_custom_report() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class MaintenanceInsightsResponse(BaseModel):
    """Response for GET /maintenance/insights."""

    timestamp: str
    total_insights: int
    insights: List[Any]


class MaintenanceTrendsResponse(BaseModel):
    """Response for GET /maintenance/trends."""

    timestamp: str
    period_days: int
    cost_trends: Dict[str, Any]
    agent_trends: Dict[str, Any]
    summary: Dict[str, Any]


# ---------------------------------------------------------------------------
# analytics_pattern_learning.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class PatternLearningFeedbackResponse(BaseModel):
    """Response for POST /pattern-learning/feedback.

    Shape from engine.submit_feedback() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class PatternLearningConfidenceResponse(BaseModel):
    """Response for GET /pattern-learning/confidence."""

    scores: List[Any]
    total: int


class PatternLearningActiveLearningResponse(BaseModel):
    """Response for GET /pattern-learning/active-learning."""

    queries: List[Any]
    total: int


class PatternLearningRegisterResponse(BaseModel):
    """Response for POST /pattern-learning/patterns.

    Shape from engine.register_pattern() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class PatternLearningHistoryResponse(BaseModel):
    """Response for GET /pattern-learning/patterns/{pattern_id}/history."""

    pattern_id: str
    history: List[Any]
    total: int


class PatternLearningLearnCycleResponse(BaseModel):
    """Response for POST /pattern-learning/learn.

    Shape from engine.run_learning_cycle() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class PatternLearningHealthResponse(BaseModel):
    """Response for GET /pattern-learning/health."""

    status: str
    initialized: bool
    learning_phase: str
    total_patterns: int
    total_feedback: int


# ---------------------------------------------------------------------------
# analytics_performance.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class PerformanceAnalyzeContentResponse(BaseModel):
    """Response for POST /performance/analyze-content.

    Returns list[PerformanceIssue]; each item is a model_dump() dict.
    """

    model_config = {"extra": "allow"}


class PerformancePatternsListResponse(BaseModel):
    """Response for GET /performance/patterns.

    Returns list[PatternDefinition].
    """

    model_config = {"extra": "allow"}


class PerformancePatternDetailResponse(BaseModel):
    """Response for GET /performance/patterns/{pattern_id}.

    Shape of PatternDefinition — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class PerformancePatternToggleResponse(BaseModel):
    """Response for POST /performance/patterns/{pattern_id}/toggle."""

    pattern_id: str
    enabled: bool
    message: str


class PerformanceHistoryResponse(BaseModel):
    """Response for GET /performance/history.

    Returns list[PerformanceAnalysisResult] — opaque; use Any list.
    """

    model_config = {"extra": "allow"}


class PerformanceSummaryResponse(BaseModel):
    """Response for GET /performance/summary."""

    total_analyses: int
    average_score: float
    common_issues: Optional[List[Any]] = None
    patterns_enabled: int
    average_issues: Optional[float] = None
    total_patterns: Optional[int] = None


class PerformanceCategoriesResponse(BaseModel):
    """Response for GET /performance/categories.

    Returns list[dict] with category/name/enabled/disabled/total/high_impact keys.
    """

    model_config = {"extra": "allow"}


class PerformanceHotspotsResponse(BaseModel):
    """Response for GET /performance/hotspots.

    Returns list[dict] with file/issues/total_issues/severity_breakdown keys.
    """

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# analytics_export.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class ExportFormatsResponse(BaseModel):
    """Response for GET /export/formats."""

    formats: List[Any]


# ---------------------------------------------------------------------------
# usage.py schemas  (Issue #5912)
# ---------------------------------------------------------------------------



class UsageByUserSingleResponse(BaseModel):
    """Response for GET /usage/by-user/{user_id}.

    Shape from tracker.get_cost_by_user() — opaque; extra allowed.
    """

    model_config = {"extra": "allow"}


class UsageMyUsageResponse(BaseModel):
    """Response for GET /usage/me.

    Extends get_cost_by_user() with recent_requests list; extra allowed.
    """

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# files.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------



class CostTrackingRecordResponse(BaseModel):
    """Per-request cost tracking record returned by cost analytics endpoints (#5936).

    Renamed from analytics_cost.UsageRecordResponse to avoid collision with
    schemas_common.UsageRecordResponse (which is the POST /usage/record confirmation).
    """

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    endpoint: Optional[str] = None
    latency_ms: Optional[float] = None
    success: bool = True
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = {}



class UsageRecentResponse(BaseModel):
    """Response for GET /cost/usage/recent — typed wrapper around CostTrackingRecordResponse (#5976)."""

    count: int
    records: List[CostTrackingRecordResponse]


# ---------------------------------------------------------------------------
# analytics_agents.py schemas  (Issue #5960)
# ---------------------------------------------------------------------------



class AgentAllPerformanceResponse(BaseModel):
    """Response for GET /agents/performance."""

    agents: List[Any]
    total_agents: int
    summary: Dict[str, Any]



class AgentHistoryResponse(BaseModel):
    """Response for GET /agents/{agent_id}/history."""

    agent_id: str
    tasks: List[Any]
    count: int



class AgentRecentTasksResponse(BaseModel):
    """Response for GET /agents/tasks/recent."""

    tasks: List[Any]
    count: int



class AgentComparisonResponse(BaseModel):
    """Response for GET /agents/comparison — opaque analytics.compare_agents() result."""

    model_config = {"extra": "allow"}



class AgentRecommendationsResponse(BaseModel):
    """Response for GET /agents/recommendations."""

    recommendations: List[Any]
    total_agents_analyzed: int
    agents_with_issues: int



class AgentPerformanceTrendsResponse(BaseModel):
    """Response for GET /agents/trends — opaque analytics.get_performance_trends() result."""

    model_config = {"extra": "allow"}



class AgentTypesResponse(BaseModel):
    """Response for GET /agents/types."""

    types: List[str]
    statuses: List[str]



class AgentTaskStartResponse(BaseModel):
    """Response for POST /agents/tasks/start."""

    status: str
    task: Dict[str, Any]



class AgentTaskCompleteResponse(BaseModel):
    """Response for POST /agents/tasks/complete.

    Two shapes: task found (status+task) or not found (status+message).
    """

    model_config = {"extra": "allow"}

    status: str


# ---------------------------------------------------------------------------
# analytics.py schemas  (Issue #5960)
# ---------------------------------------------------------------------------



class AnalyticsDetailedHealthResponse(BaseModel):
    """Response for GET /analytics/system/health-detailed — opaque composite."""

    model_config = {"extra": "allow"}



class AnalyticsPerformanceMetricsResponse(BaseModel):
    """Response for GET /analytics/performance/metrics — opaque collector result."""

    model_config = {"extra": "allow"}



class AnalyticsCommunicationPatternsResponse(BaseModel):
    """Response for GET /analytics/communication/patterns — opaque controller result."""

    model_config = {"extra": "allow"}



class AnalyticsUsageStatisticsResponse(BaseModel):
    """Response for GET /analytics/usage/statistics — opaque controller result."""

    model_config = {"extra": "allow"}



class AnalyticsRealtimeMetricsResponse(BaseModel):
    """Response for GET /analytics/realtime/metrics — opaque metrics snapshot."""

    model_config = {"extra": "allow"}



class AnalyticsHistoricalTrendsResponse(BaseModel):
    """Response for GET /analytics/trends/historical — opaque trend result."""

    model_config = {"extra": "allow"}



class AnalyticsStatusResponse(BaseModel):
    """Response for GET /analytics/status — opaque status dict."""

    model_config = {"extra": "allow"}



class AnalyticsRootCauseResponse(BaseModel):
    """Response for GET /analytics/root-cause/{task_id} — opaque RootCauseReport dict."""

    model_config = {"extra": "allow"}



class AnalyticsDashboardStatusResponse(BaseModel):
    """Response for GET /analytics/dashboard/overview/status/{task_id} — opaque task dict."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# analytics_behavior.py schemas  (Issue #5960)
# ---------------------------------------------------------------------------



class BehaviorTrackEventResponse(BaseModel):
    """Response for POST /behavior/track."""

    status: str
    event_type: str
    feature: str
    timestamp: str



class BehaviorRecentEventsResponse(BaseModel):
    """Response for GET /behavior/events/recent."""

    count: int
    events: List[Any]



class BehaviorFeatureMetricsResponse(BaseModel):
    """Response for GET /behavior/features — opaque analytics result."""

    model_config = {"extra": "allow"}



class BehaviorFeatureComparisonResponse(BaseModel):
    """Response for GET /behavior/features/comparison."""

    model_config = {"extra": "allow"}



class BehaviorEngagementResponse(BaseModel):
    """Response for GET /behavior/engagement — opaque analytics result."""

    model_config = {"extra": "allow"}



class BehaviorDailyStatsResponse(BaseModel):
    """Response for GET /behavior/stats/daily — opaque analytics result."""

    model_config = {"extra": "allow"}



class BehaviorHeatmapResponse(BaseModel):
    """Response for GET /behavior/stats/heatmap — opaque analytics result."""

    model_config = {"extra": "allow"}



class BehaviorPeakUsageResponse(BaseModel):
    """Response for GET /behavior/stats/peak."""

    model_config = {"extra": "allow"}



class BehaviorSummaryResponse(BaseModel):
    """Response for GET /behavior/summary."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# analytics_cost.py remaining schemas  (Issue #5960)
# ---------------------------------------------------------------------------



class SingleAgentCostResponse(BaseModel):
    """Response for GET /cost/by-agent/{agent_id} — opaque tracker result + budget."""

    model_config = {"extra": "allow"}



class AgentBudgetSetResponse(BaseModel):
    """Response for PUT /cost/by-agent/{agent_id}/budget — opaque tracker result."""

    model_config = {"extra": "allow"}



class AgentBudgetStatusResponse(BaseModel):
    """Response for GET /cost/by-agent/{agent_id}/budget — opaque tracker result."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# analytics_models.py classes (merged from analytics_models.py — Issue #5996)
# ---------------------------------------------------------------------------


class AnalyticsOverview(BaseModel):
    """Comprehensive analytics dashboard overview model"""

    timestamp: str
    system_health: Metadata
    performance_metrics: Metadata
    communication_patterns: Metadata
    code_analysis_status: Metadata
    usage_statistics: Metadata
    realtime_metrics: Metadata
    trends: Metadata


class CommunicationPattern(BaseModel):
    """Communication pattern analysis model"""

    endpoint: str
    frequency: int
    avg_response_time: float
    error_rate: float
    last_accessed: str
    pattern_type: str = Field(description="API, WebSocket, or Internal")


class CodeAnalysisRequest(BaseModel):
    """Code analysis request model"""

    target_path: Optional[str] = Field(default_factory=lambda: str(PATH.PROJECT_ROOT))
    analysis_type: str = Field(
        default="full", description="full, incremental, or communication_chains"
    )
    include_metrics: bool = True


class PerformanceMetrics(BaseModel):
    """Performance metrics model"""

    response_times: List[float]
    throughput: float
    error_rates: Metadata
    resource_utilization: Metadata
    bottlenecks: List[str]


class RealTimeEvent(BaseModel):
    """Real-time analytics event model"""

    event_type: str
    timestamp: str
    data: Metadata
    severity: str = "info"


# ---------------------------------------------------------------------------
# analytics_bug_prediction.py — GET endpoint schemas (Issue #5983)
# ---------------------------------------------------------------------------


class BugPredictionAnalysisResponse(BaseModel):
    """Response for GET /bug-prediction/analyze — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class BugPredictionCachedResponse(BaseModel):
    """Response for GET /bug-prediction/cached — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class BugPredictionHighRiskResponse(BaseModel):
    """Response for GET /bug-prediction/high-risk — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class BugPredictionFileResponse(BaseModel):
    """Response for GET /bug-prediction/file/{file_path} — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class BugPredictionHeatmapResponse(BaseModel):
    """Response for GET /bug-prediction/heatmap — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class BugPredictionTrendsResponse(BaseModel):
    """Response for GET /bug-prediction/trends — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class BugPredictionSummaryResponse(BaseModel):
    """Response for GET /bug-prediction/summary — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# analytics_code_generation.py — endpoint schemas (Issue #5983)
# ---------------------------------------------------------------------------


class CodeGenerationHealthResponse(BaseModel):
    """Response for GET /code-generation/health."""

    status: str
    service: str
    deprecated: bool
    use_instead: str
    features: List[str]
    supported_languages: List[str]
    refactoring_types: List[str]


class CodeGenerationValidateResponse(BaseModel):
    """Response for POST /code-generation/validate."""

    is_valid: bool
    errors: List[str]
    warnings: List[str]
    ast_info: Optional[Metadata] = None
    language: str


class CodeGenerationVersionsResponse(BaseModel):
    """Response for GET /code-generation/versions/{file_path}."""

    file_path: str
    versions: List[Metadata]
    count: int


class CodeGenerationStatsResponse(BaseModel):
    """Response for GET /code-generation/stats — dual shape (success vs error)."""

    model_config = {"extra": "allow"}


class RefactoringTypeItem(BaseModel):
    """Individual refactoring type entry."""

    id: str
    name: str
    description: str


class CodeGenerationRefactoringTypesResponse(BaseModel):
    """Response for GET /code-generation/refactoring-types."""

    types: List[RefactoringTypeItem]


# ---------------------------------------------------------------------------
# analytics_code_review.py — list endpoint schemas (Issue #5983)
# ---------------------------------------------------------------------------


class CodeReviewPatternItem(BaseModel):
    """Individual code review pattern entry."""

    id: str
    name: str
    category: str
    severity: str
    message: str
    suggestion: str
    has_regex: bool


class CodeReviewCategoryItem(BaseModel):
    """Individual code review category entry."""

    id: str
    name: str
    description: str
    icon: str


# ---------------------------------------------------------------------------
# analytics_conversation.py — endpoint schemas (Issue #5983)
# ---------------------------------------------------------------------------


class ConversationIntentsResponse(BaseModel):
    """Response for GET /conversation/intents."""

    model_config = {"extra": "allow"}


class ConversationFlowsResponse(BaseModel):
    """Response for GET /conversation/flows."""

    model_config = {"extra": "allow"}


class ConversationBottlenecksResponse(BaseModel):
    """Response for GET /conversation/bottlenecks."""

    model_config = {"extra": "allow"}


class ConversationDistributionResponse(BaseModel):
    """Response for GET /conversation/distribution."""

    model_config = {"extra": "allow"}


class ConversationDetectIntentResponse(BaseModel):
    """Response for POST /conversation/detect-intent."""

    message: str
    detected_intent: str
    intent_name: str
    confidence: float


# ---------------------------------------------------------------------------
# analytics_dfa.py — endpoint schemas (Issue #5983)
# ---------------------------------------------------------------------------


class DfaVulnerabilityItem(BaseModel):
    """Individual vulnerability entry in DFA analysis."""

    model_config = {"extra": "allow"}


class DfaVulnerabilitiesResponse(BaseModel):
    """Response for POST /dfa/vulnerabilities."""

    file_path: str
    total_vulnerabilities: int
    vulnerabilities: List[DfaVulnerabilityItem]


class DfaSourceItem(BaseModel):
    """Individual taint source entry."""

    name: str
    source_type: str
    taint_level: str


class DfaSourcesResponse(BaseModel):
    """Response for GET /dfa/sources."""

    sources: List[DfaSourceItem]


class DfaSinkItem(BaseModel):
    """Individual taint sink entry."""

    name: str
    sink_type: str
    vulnerability_type: str
    severity: str


class DfaSinksResponse(BaseModel):
    """Response for GET /dfa/sinks."""

    sinks: List[DfaSinkItem]


class DfaSanitizersResponse(BaseModel):
    """Response for GET /dfa/sanitizers."""

    sanitizers: List[str]


class DfaHealthResponse(BaseModel):
    """Response for GET /dfa/health."""

    status: str
    service: str
    deprecated: bool
    use_instead: str
    features: List[str]


# ---------------------------------------------------------------------------
# analytics_log_patterns.py — endpoint schemas (Issue #5983)
# ---------------------------------------------------------------------------


class LogPatternDetailResponse(BaseModel):
    """Response for GET /log-patterns/pattern/{pattern_id}."""

    model_config = {"extra": "allow"}


class LogPatternHotspotsResponse(BaseModel):
    """Response for GET /log-patterns/hotspots."""

    model_config = {"extra": "allow"}


class LogPatternStatsResponse(BaseModel):
    """Response for GET /log-patterns/stats."""

    model_config = {"extra": "allow"}


class LogPatternRealtimeResponse(BaseModel):
    """Response for GET /log-patterns/realtime."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# analytics_quality.py — endpoint schemas (Issue #5983)
# ---------------------------------------------------------------------------


class QualityHealthScoreResponse(BaseModel):
    """Response for GET /quality/health-score — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class QualityMetricsResponse(BaseModel):
    """Response for GET /quality/metrics — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class QualityPatternsResponse(BaseModel):
    """Response for GET /quality/patterns — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class QualityComplexityResponse(BaseModel):
    """Response for GET /quality/complexity — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class QualityTrendsResponse(BaseModel):
    """Response for GET /quality/trends — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class QualitySnapshotResponse(BaseModel):
    """Response for GET /quality/snapshot — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


class QualityDrillDownResponse(BaseModel):
    """Response for GET /quality/drill-down/{category} — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}


# ---------------------------------------------------------------------------
# analytics_precommit schemas (#6042)
# ---------------------------------------------------------------------------


class CheckSeverity(str, Enum):
    """Severity levels for pre-commit checks."""

    BLOCK = "block"
    WARN = "warn"
    INFO = "info"


class CheckCategory(str, Enum):
    """Categories of pre-commit checks."""

    SECURITY = "security"
    QUALITY = "quality"
    STYLE = "style"
    DEBUG = "debug"
    DOCS = "docs"


class CheckResult(BaseModel):
    """Result of a single check."""

    check_id: str
    name: str
    category: CheckCategory
    severity: CheckSeverity
    passed: bool
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    snippet: Optional[str] = None
    suggestion: Optional[str] = None


class CommitCheckResult(BaseModel):
    """Result of checking staged files."""

    passed: bool
    total_checks: int
    passed_checks: int
    failed_checks: int
    warnings: int
    blocked: bool
    duration_ms: float
    results: List[CheckResult]
    files_checked: List[str]
    timestamp: str


class HookConfig(BaseModel):
    """Configuration for pre-commit hooks."""

    enabled: bool = True
    fast_mode: bool = True
    timeout_seconds: int = Field(default=5, ge=1, le=30)
    bypass_keyword: str = "[skip-hooks]"
    enabled_checks: List[str] = Field(default_factory=list)
    disabled_checks: List[str] = Field(default_factory=list)


class CheckDefinition(BaseModel):
    """Definition of a check rule."""

    id: str
    name: str
    category: CheckCategory
    severity: CheckSeverity
    pattern: str
    description: str
    suggestion: str
    file_patterns: List[str] = Field(default_factory=lambda: ["*"])
    enabled: bool = True


class HookStatus(BaseModel):
    """Status of installed hooks."""

    installed: bool
    path: Optional[str] = None
    version: Optional[str] = None
    last_run: Optional[str] = None
    config: HookConfig


class CheckToggleResponse(BaseModel):
    """Response for POST /checks/{check_id}/toggle."""

    check_id: str
    enabled: bool
    message: str


class HookConfigUpdateResponse(BaseModel):
    """Response for POST /config — echoes back the new config."""

    message: str
    config: HookConfig


class HookInstallResponse(BaseModel):
    """Response for POST /install and POST /uninstall."""

    success: bool
    message: str
    path: Optional[str] = None


class CommonIssueItem(BaseModel):
    """Single issue entry in the summary common_issues list."""

    check_id: str
    count: int
    name: str


class PrecommitSummaryResponse(BaseModel):
    """Response for GET /summary."""

    total_runs: int
    pass_rate: float
    average_duration_ms: float
    common_issues: List[CommonIssueItem]
    checks_enabled: Optional[int] = None
    total_checks: Optional[int] = None


class PrecommitCategoryItem(BaseModel):
    """Single category entry for GET /categories."""

    category: str
    enabled: int
    disabled: int
    total: int


# ---------------------------------------------------------------------------
# error_monitoring schemas (#6042)
# ---------------------------------------------------------------------------


class ErrorMonitoringDataResponse(BaseModel):
    """Generic envelope for endpoints returning {"status": str, "data": Any}."""

    status: str
    data: Optional[Any] = None


class ErrorMonitoringClearResponse(BaseModel):
    """Response for POST /clear."""

    status: str
    message: str


class ErrorMonitoringTestErrorResponse(BaseModel):
    """Response for POST /test-error."""

    status: str
    message: str
    error_caught: Optional[str] = None
    error_type: Optional[str] = None


class ErrorMonitoringResolveResponse(BaseModel):
    """Response for POST /metrics/resolve/{trace_id}."""

    status: str
    message: str


class ErrorMonitoringAlertThresholdResponse(BaseModel):
    """Response for POST /metrics/alert-threshold."""

    status: str
    message: str
    threshold_key: str
    threshold: int


class ErrorMonitoringCleanupResponse(BaseModel):
    """Response for POST /metrics/cleanup."""

    status: str
    message: str
    removed_count: int


class TestErrorRequest(BaseModel):
    error_type: str = "ValueError"
    message: str = "Test error for error boundary system"


class AlertThresholdRequest(BaseModel):
    component: str
    error_code: Optional[str] = None
    threshold: int


# ---------------------------------------------------------------------------
# rum.py schemas (#6042)
# ---------------------------------------------------------------------------


class RumEvent(BaseModel):
    type: str
    timestamp: str
    sessionId: str
    url: str
    userAgent: str
    data: Metadata = {}


class RumConfig(BaseModel):
    enabled: bool = False
    error_tracking: bool = True
    performance_monitoring: bool = True
    interaction_tracking: bool = False
    session_recording: bool = False
    sample_rate: int = 100
    max_events_per_session: int = 1000
    debug_mode: bool = False
    log_to_backend: bool = True
    log_level: str = "info"


class RumPageMetrics(BaseModel):
    """Page performance metrics from frontend."""

    page: str
    load_time_seconds: Optional[float] = None
    fcp_seconds: Optional[float] = None
    lcp_seconds: Optional[float] = None
    tti_seconds: Optional[float] = None
    dom_loaded_seconds: Optional[float] = None


class RumApiCallMetric(BaseModel):
    """Frontend API call metric."""

    endpoint: str
    method: str
    status: str
    latency_seconds: float
    is_slow: bool = False
    is_timeout: bool = False
    error_type: Optional[str] = None


class RumJsErrorMetric(BaseModel):
    """JavaScript error metric."""

    error_type: str
    page: str
    is_rejection: bool = False
    component: Optional[str] = None


class RumUserActionMetric(BaseModel):
    """User action/interaction metric."""

    action_type: str
    page: str
    form_name: Optional[str] = None
    form_status: Optional[str] = None


class RumSessionMetric(BaseModel):
    """Session metric."""

    event: str
    duration_seconds: Optional[float] = None


class RumWebSocketMetric(BaseModel):
    """WebSocket event metric from frontend."""

    event: str
    direction: Optional[str] = None
    event_type: Optional[str] = None


class RumResourceMetric(BaseModel):
    """Resource load metric."""

    resource_type: str
    load_time_seconds: float
    is_slow: bool = False


class RumCriticalIssueMetric(BaseModel):
    """Critical issue from frontend."""

    issue_type: str


class RumMetrics(BaseModel):
    """Batch of RUM metrics from frontend. Issue #476: Used for Prometheus metrics export."""

    session_id: str
    timestamp: str
    page_metrics: Optional[RumPageMetrics] = None
    api_calls: Optional[List[RumApiCallMetric]] = None
    js_errors: Optional[List[RumJsErrorMetric]] = None
    user_actions: Optional[List[RumUserActionMetric]] = None
    session: Optional[RumSessionMetric] = None
    websocket_events: Optional[List[RumWebSocketMetric]] = None
    resources: Optional[List[RumResourceMetric]] = None
    critical_issues: Optional[List[RumCriticalIssueMetric]] = None


# analytics_cost.py schemas (#6042)


class CostSummaryResponse(BaseModel):
    period: dict
    total_cost_usd: float
    daily_costs: dict
    by_model: dict
    avg_daily_cost: float


class CostTrendResponse(BaseModel):
    period_days: int
    total_cost_usd: float
    daily_costs: dict
    trend: str
    growth_rate_percent: float
    avg_daily_cost: float


class SessionCostResponse(BaseModel):
    session_id: str
    found: bool
    cost_usd: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    error: Optional[str] = None


class BudgetAlertRequest(BaseModel):
    name: str = Field(..., description="Alert name")
    threshold_usd: float = Field(..., gt=0, description="Budget threshold in USD")
    period: str = Field(..., pattern="^(daily|weekly|monthly)$", description="Alert period")
    notify_at_percent: List[int] = Field(default=[50, 75, 90, 100])
    enabled: bool = Field(default=True)


class ModelPricingInfo(BaseModel):
    model: str
    input_price_per_1m: float
    output_price_per_1m: float
    provider: str


class AgentBudgetRequest(BaseModel):
    budget_monthly_usd: float = Field(..., gt=0, description="Monthly budget in USD")


class AgentCostResponse(BaseModel):
    agent_id: str
    found: bool = False
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    call_count: int = 0


# ---------------------------------------------------------------------------
# analytics_code_generation.py enums + schemas
# ---------------------------------------------------------------------------


class RefactoringType(str, Enum):
    """Types of code refactoring operations"""

    EXTRACT_FUNCTION = "extract_function"
    RENAME_VARIABLE = "rename_variable"
    SIMPLIFY_CONDITIONAL = "simplify_conditional"
    REMOVE_DUPLICATION = "remove_duplication"
    ADD_TYPE_HINTS = "add_type_hints"
    IMPROVE_NAMING = "improve_naming"
    OPTIMIZE_LOOPS = "optimize_loops"
    ADD_DOCSTRINGS = "add_docstrings"
    CLEAN_IMPORTS = "clean_imports"
    GENERAL = "general"


class CodeLanguage(str, Enum):
    """Supported programming languages"""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    VUE = "vue"


class GenerationStatus(str, Enum):
    """Status of code generation request"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class CodeGenerationRequest(BaseModel):
    """Request model for code generation"""

    description: str = Field(..., description="Natural language description of code to generate")
    language: CodeLanguage = Field(default=CodeLanguage.PYTHON, description="Target language")
    context: Optional[str] = Field(None, description="Additional context or requirements")
    file_path: Optional[str] = Field(None, description="Target file path for context")
    existing_code: Optional[str] = Field(None, description="Existing code to integrate with")


class RefactoringRequest(BaseModel):
    """Request model for code refactoring"""

    code: str = Field(..., description="Code to refactor")
    refactoring_type: RefactoringType = Field(default=RefactoringType.GENERAL)
    language: CodeLanguage = Field(default=CodeLanguage.PYTHON)
    file_path: Optional[str] = Field(None, description="Source file path for context")
    preserve_comments: bool = Field(default=True)
    preserve_formatting: bool = Field(default=False)


class CodeGenValidationRequest(BaseModel):
    """Request model for code validation"""

    code: str = Field(..., description="Code to validate")
    language: CodeLanguage = Field(default=CodeLanguage.PYTHON)


class CodeGenRollbackRequest(BaseModel):
    """Request model for code rollback"""

    file_path: str = Field(..., description="File to rollback")
    version_id: Optional[str] = Field(None, description="Specific version to rollback to")


class CodeGenerationResponse(BaseModel):
    """Response model for code generation"""

    success: bool
    generated_code: Optional[str] = None
    validation: Optional[Dict[str, Any]] = None
    tokens_used: int = 0
    processing_time: float = 0.0
    error: Optional[str] = None


class RefactoringResponse(BaseModel):
    """Response model for refactoring"""

    success: bool
    original_code: str
    refactored_code: Optional[str] = None
    diff: Optional[str] = None
    changes: List[str] = []
    validation: Optional[Dict[str, Any]] = None
    tokens_used: int = 0
    processing_time: float = 0.0
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# analytics_pattern_learning.py enums + schemas
# ---------------------------------------------------------------------------


class FeedbackType(str, Enum):
    """Types of feedback developers can provide."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    MISSED = "missed"
    PARTIAL = "partial"
    IRRELEVANT = "irrelevant"


class PatternCategory(str, Enum):
    """Categories of patterns for organization."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    CODE_QUALITY = "code_quality"
    ARCHITECTURE = "architecture"
    ERROR_HANDLING = "error_handling"
    CONCURRENCY = "concurrency"
    DATA_FLOW = "data_flow"
    CONTROL_FLOW = "control_flow"
    STYLE = "style"
    DOCUMENTATION = "documentation"


class LearningPhase(str, Enum):
    """Phases of the active learning pipeline."""

    COLLECTING = "collecting"
    ANALYZING = "analyzing"
    TRAINING = "training"
    VALIDATING = "validating"
    DEPLOYED = "deployed"


class ConfidenceLevel(str, Enum):
    """Human-readable confidence levels."""

    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class PatternFeedback(BaseModel):
    """Feedback for a specific pattern match."""

    pattern_id: str = Field(..., description="Unique identifier for the pattern")
    feedback_type: FeedbackType = Field(..., description="Type of feedback")
    file_path: str = Field(..., description="File where pattern was detected")
    line_number: int = Field(..., description="Line number of pattern match")
    code_snippet: Optional[str] = Field(None, description="Code snippet context")
    developer_comment: Optional[str] = Field(None, description="Developer notes")
    suggested_fix: Optional[str] = Field(None, description="Suggested improvement")
    timestamp: Optional[datetime] = Field(None, description="Feedback timestamp")


class PatternDefinition(BaseModel):
    """Definition of a learnable pattern."""

    pattern_id: str = Field(..., description="Unique pattern identifier")
    name: str = Field(..., description="Human-readable pattern name")
    description: str = Field(..., description="Pattern description")
    category: PatternCategory = Field(..., description="Pattern category")
    regex_patterns: List[str] = Field(default_factory=list, description="Regex patterns")
    ast_patterns: List[str] = Field(default_factory=list, description="AST pattern descriptions")
    examples: List[str] = Field(default_factory=list, description="Example matches")
    counter_examples: List[str] = Field(default_factory=list, description="Non-matching examples")
    severity: str = Field(default="medium", description="Pattern severity")
    enabled: bool = Field(default=True, description="Whether pattern is active")


class ConfidenceScore(BaseModel):
    """Confidence score for a pattern."""

    pattern_id: str
    score: float = Field(..., ge=0.0, le=1.0)
    level: ConfidenceLevel
    total_feedback: int
    correct_count: int
    incorrect_count: int
    last_updated: datetime
    trend: str


class PatternLearningMetrics(BaseModel):
    """Metrics for the pattern learning pipeline."""

    total_patterns: int
    total_feedback: int
    average_confidence: float
    high_confidence_patterns: int
    low_confidence_patterns: int
    patterns_improved: int
    patterns_degraded: int
    feedback_by_type: Dict[str, int]
    feedback_by_category: Dict[str, int]
    learning_rate: float
    last_training_run: Optional[datetime]


class ActiveLearningQuery(BaseModel):
    """Query for active learning suggestions."""

    pattern_id: str
    code_snippet: str
    predicted_match: bool
    confidence: float
    question: str


class PatternUpdate(BaseModel):
    """Update to a pattern based on learning."""

    pattern_id: str
    update_type: str
    old_value: Optional[Any]
    new_value: Optional[Any]
    reason: str
    applied_at: datetime


# ---------------------------------------------------------------------------
# analytics_continuous_learning.py enums + schemas
# ---------------------------------------------------------------------------


class LearningEventType(str, Enum):
    """Types of learning events."""

    FILE_CHANGE = "file_change"
    PATTERN_DETECTED = "pattern_detected"
    FEEDBACK_RECEIVED = "feedback_received"
    MODEL_UPDATED = "model_updated"
    INSIGHT_GENERATED = "insight_generated"
    THRESHOLD_CROSSED = "threshold_crossed"
    ANOMALY_DETECTED = "anomaly_detected"


class MonitoringState(str, Enum):
    """States of the monitoring system."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"


class InsightType(str, Enum):
    """Types of generated insights."""

    NEW_PATTERN = "new_pattern"
    PATTERN_EVOLUTION = "pattern_evolution"
    FALSE_POSITIVE_TREND = "false_positive_trend"
    PERFORMANCE_IMPROVEMENT = "performance_improvement"
    DEVELOPER_PREFERENCE = "developer_preference"
    CODE_QUALITY_TREND = "code_quality_trend"
    SECURITY_CONCERN = "security_concern"


class RetrainingReason(str, Enum):
    """Reasons for triggering model retraining."""

    SCHEDULED = "scheduled"
    FEEDBACK_THRESHOLD = "feedback_threshold"
    ACCURACY_DROP = "accuracy_drop"
    NEW_PATTERNS = "new_patterns"
    MANUAL = "manual"


class LearningEvent(BaseModel):
    """An event in the learning system."""

    event_id: str
    event_type: LearningEventType
    timestamp: datetime
    source: str
    data: Dict[str, Any]
    processed: bool = False


class LearningInsight(BaseModel):
    """A generated insight."""

    insight_id: str
    insight_type: InsightType
    title: str
    description: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    data: Dict[str, Any]
    recommendations: List[str]
    generated_at: datetime
    expires_at: Optional[datetime] = None


class ContinuousLearningMetrics(BaseModel):
    """Metrics for the continuous learning system."""

    total_events_processed: int
    events_last_hour: int
    events_last_day: int
    patterns_learned: int
    patterns_updated: int
    false_positives_reduced: int
    accuracy_improvement: float
    last_retrain: Optional[datetime]
    next_scheduled_retrain: Optional[datetime]
    insights_generated: int
    active_insights: int


class LearningMonitoringStatus(BaseModel):
    """Status of the monitoring system."""

    state: MonitoringState
    started_at: Optional[datetime]
    uptime_seconds: int
    files_monitored: int
    directories_watched: List[str]
    events_queue_size: int
    last_event_time: Optional[datetime]


class RetrainingRequest(BaseModel):
    """Request for model retraining."""

    reason: RetrainingReason = RetrainingReason.MANUAL
    force: bool = False
    patterns_to_focus: Optional[List[str]] = None


class LearningConfig(BaseModel):
    """Configuration for the learning system."""

    monitoring_enabled: bool = True
    auto_retrain_enabled: bool = True
    insight_generation_enabled: bool = True
    monitored_paths: List[str] = Field(default_factory=lambda: ["backend/", "src/"])
    scan_interval_seconds: int = 300
    retrain_interval_hours: int = 24
    feedback_threshold: int = 50
    accuracy_threshold: float = 0.7
