# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analytics, cost, budget, usage, and metrics schemas.
"""

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
