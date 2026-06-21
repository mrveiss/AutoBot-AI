# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Analytics, cost, budget, usage, and metrics schemas.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List

from fastapi import Query
from pydantic import BaseModel, Field

from api.schemas_common import SuccessMessageResponse
from autobot_shared.status_enums import RiskLevel, Severity
from constants import PATH
from type_defs.common import Metadata

# #6689 consolidation: 5 severity-shape enums collapsed onto canonical Severity.
# Aliases preserve external API names (FastAPI / OpenAPI / frontend codegen).
ImpactLevel = Severity
IssueSeverity = Severity
CostLevel = Severity
DFASeverity = Severity


# ---------------------------------------------------------------------------
# Analytics schemas
# ---------------------------------------------------------------------------


class MetricsWorkflowResponse(BaseModel):
    """Response for GET /workflow/{workflow_id}."""

    success: bool
    workflow_id: str
    metrics: Any | None = None


class MetricsPerformanceSummaryResponse(BaseModel):
    """Response for GET /performance/summary."""

    success: bool
    performance_summary: Any | None = None


class MetricsSystemCurrentResponse(BaseModel):
    """Response for GET /system/current."""

    success: bool
    system_metrics: Any | None = None


class MetricsSystemHistoryResponse(BaseModel):
    """Response for GET /system/history."""

    success: bool
    cpu_history: List[Any]
    memory_history: List[Any]
    time_range: Dict[str, str]


class MetricsSystemSummaryResponse(BaseModel):
    """Response for GET /system/summary."""

    success: bool
    resource_summary: Any | None = None


class MetricsExportResponse(BaseModel):
    """Response for GET /export/workflow and GET /export/system."""

    success: bool
    format: str
    data: Any | None = None


class MetricsMonitoringStartResponse(BaseModel):
    """Response for POST /system/monitoring/start."""

    success: bool
    message: str
    collection_interval: Any | None = None


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
    results: Any | None = None
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
    last_analysis: str | None = None
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
    common_issues: List[Any] | None = None
    patterns_enabled: int
    average_issues: float | None = None
    total_patterns: int | None = None


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
    session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    endpoint: str | None = None
    latency_ms: float | None = None
    success: bool = True
    error_message: str | None = None
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

    target_path: str | None = Field(default_factory=lambda: str(PATH.PROJECT_ROOT))
    analysis_type: str = Field(default="full", description="full, incremental, or communication_chains")
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
    """Response for GET /bug-prediction/analyze — dual shape (success vs no_data).

    Success shape mirrors PredictionResult fields plus envelope metadata
    (status, from_cache). The no_data shape returns status="no_data" and
    a message. extra="allow" preserves backward compat with any callers
    still relying on additional pass-through fields.
    """

    model_config = {"extra": "allow"}

    status: str | None = None  # "success" or "no_data"
    timestamp: str | None = None
    total_files: int | None = None
    analyzed_files: int | None = None
    high_risk_count: int | None = None
    files: List[FileRisk] | None = None  # type: ignore[name-defined]
    from_cache: bool | None = None
    # no_data shape
    message: str | None = None


class BugPredictionCachedResponse(BaseModel):
    """Response for GET /bug-prediction/cached — dual shape (success vs no_data).

    Same shape as BugPredictionAnalysisResponse with from_cache=True on success.
    """

    model_config = {"extra": "allow"}

    status: str | None = None
    timestamp: str | None = None
    total_files: int | None = None
    analyzed_files: int | None = None
    high_risk_count: int | None = None
    files: List[FileRisk] | None = None  # type: ignore[name-defined]
    from_cache: bool | None = None
    message: str | None = None


class BugPredictionHighRiskResponse(BaseModel):
    """Response for GET /bug-prediction/high-risk — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}

    status: str | None = None
    timestamp: str | None = None
    files: List[FileRisk] | None = None  # type: ignore[name-defined]
    high_risk_count: int | None = None
    message: str | None = None


class BugPredictionFileResponse(BaseModel):
    """Response for GET /bug-prediction/file/{file_path} — dual shape (success vs no_data)."""

    model_config = {"extra": "allow"}

    status: str | None = None
    timestamp: str | None = None
    file: FileRisk | None = None  # type: ignore[name-defined]
    message: str | None = None


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
    ast_info: Metadata | None = None
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
    file: str | None = None
    line: int | None = None
    snippet: str | None = None
    suggestion: str | None = None


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
    path: str | None = None
    version: str | None = None
    last_run: str | None = None
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
    path: str | None = None


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
    checks_enabled: int | None = None
    total_checks: int | None = None


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
    data: Any | None = None


class ErrorMonitoringClearResponse(BaseModel):
    """Response for POST /clear."""

    status: str
    message: str


class ErrorMonitoringTestErrorResponse(BaseModel):
    """Response for POST /test-error."""

    status: str
    message: str
    error_caught: str | None = None
    error_type: str | None = None


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
    error_code: str | None = None
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
    load_time_seconds: float | None = None
    fcp_seconds: float | None = None
    lcp_seconds: float | None = None
    tti_seconds: float | None = None
    dom_loaded_seconds: float | None = None


class RumApiCallMetric(BaseModel):
    """Frontend API call metric."""

    endpoint: str
    method: str
    status: str
    latency_seconds: float
    is_slow: bool = False
    is_timeout: bool = False
    error_type: str | None = None


class RumJsErrorMetric(BaseModel):
    """JavaScript error metric."""

    error_type: str
    page: str
    is_rejection: bool = False
    component: str | None = None


class RumUserActionMetric(BaseModel):
    """User action/interaction metric."""

    action_type: str
    page: str
    form_name: str | None = None
    form_status: str | None = None


class RumSessionMetric(BaseModel):
    """Session metric."""

    event: str
    duration_seconds: float | None = None


class RumWebSocketMetric(BaseModel):
    """WebSocket event metric from frontend."""

    event: str
    direction: str | None = None
    event_type: str | None = None


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
    page_metrics: RumPageMetrics | None = None
    api_calls: List[RumApiCallMetric] | None = None
    js_errors: List[RumJsErrorMetric] | None = None
    user_actions: List[RumUserActionMetric] | None = None
    session: RumSessionMetric | None = None
    websocket_events: List[RumWebSocketMetric] | None = None
    resources: List[RumResourceMetric] | None = None
    critical_issues: List[RumCriticalIssueMetric] | None = None


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
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    error: str | None = None


class BudgetAlertRequest(BaseModel):
    name: str = Field(..., description="Alert name")
    threshold_usd: float = Field(..., gt=0, description="Budget threshold in USD")
    period: str = Field(..., pattern="^(daily|weekly|monthly)$", description="Alert period")
    notify_at_percent: List[int] = Field(default=[50, 75, 90, 100])
    enabled: bool = Field(default=True)


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
    context: str | None = Field(None, description="Additional context or requirements")
    file_path: str | None = Field(None, description="Target file path for context")
    existing_code: str | None = Field(None, description="Existing code to integrate with")


class RefactoringRequest(BaseModel):
    """Request model for code refactoring"""

    code: str = Field(..., description="Code to refactor")
    refactoring_type: RefactoringType = Field(default=RefactoringType.GENERAL)
    language: CodeLanguage = Field(default=CodeLanguage.PYTHON)
    file_path: str | None = Field(None, description="Source file path for context")
    preserve_comments: bool = Field(default=True)
    preserve_formatting: bool = Field(default=False)


class CodeGenValidationRequest(BaseModel):
    """Request model for code validation"""

    code: str = Field(..., description="Code to validate")
    language: CodeLanguage = Field(default=CodeLanguage.PYTHON)


class CodeGenRollbackRequest(BaseModel):
    """Request model for code rollback"""

    file_path: str = Field(..., description="File to rollback")
    version_id: str | None = Field(None, description="Specific version to rollback to")


class CodeGenerationResponse(BaseModel):
    """Response model for code generation"""

    success: bool
    generated_code: str | None = None
    validation: Dict[str, Any] | None = None
    tokens_used: int = 0
    processing_time: float = 0.0
    error: str | None = None


class RefactoringResponse(BaseModel):
    """Response model for refactoring"""

    success: bool
    original_code: str
    refactored_code: str | None = None
    diff: str | None = None
    changes: List[str] = []
    validation: Dict[str, Any] | None = None
    tokens_used: int = 0
    processing_time: float = 0.0
    error: str | None = None


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
    code_snippet: str | None = Field(None, description="Code snippet context")
    developer_comment: str | None = Field(None, description="Developer notes")
    suggested_fix: str | None = Field(None, description="Suggested improvement")
    timestamp: datetime | None = Field(None, description="Feedback timestamp")


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
    last_training_run: datetime | None


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
    old_value: Any | None
    new_value: Any | None
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
    expires_at: datetime | None = None


class ContinuousLearningMetrics(BaseModel):
    """Metrics for the continuous learning system."""

    total_events_processed: int
    events_last_hour: int
    events_last_day: int
    patterns_learned: int
    patterns_updated: int
    false_positives_reduced: int
    accuracy_improvement: float
    last_retrain: datetime | None
    next_scheduled_retrain: datetime | None
    insights_generated: int
    active_insights: int


class LearningMonitoringStatus(BaseModel):
    """Status of the monitoring system."""

    state: MonitoringState
    started_at: datetime | None
    uptime_seconds: int
    files_monitored: int
    directories_watched: List[str]
    events_queue_size: int
    last_event_time: datetime | None


class RetrainingRequest(BaseModel):
    """Request for model retraining."""

    reason: RetrainingReason = RetrainingReason.MANUAL
    force: bool = False
    patterns_to_focus: List[str] | None = None


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


# ---------------------------------------------------------------------------
# analytics_evolution.py schemas
# ---------------------------------------------------------------------------


class EvolutionQualitySnapshot(BaseModel):
    """A point-in-time quality snapshot."""

    timestamp: str
    overall_score: float = Field(ge=0, le=100)
    maintainability: float = Field(ge=0, le=100)
    testability: float = Field(ge=0, le=100)
    documentation: float = Field(ge=0, le=100)
    complexity: float = Field(ge=0, le=100)
    security: float = Field(ge=0, le=100)
    performance: float = Field(ge=0, le=100)
    total_files: int = 0
    total_lines: int = 0
    total_functions: int = 0
    total_classes: int = 0
    anti_patterns_count: int = 0
    problems_count: int = 0


class PatternSnapshot(BaseModel):
    """Pattern adoption snapshot."""

    timestamp: str
    pattern_type: str
    count: int
    severity_distribution: Dict[str, int] = {}
    top_files: List[str] = []


class EvolutionTimelineRequest(BaseModel):
    """Request for timeline data."""

    start_date: str | None = None
    end_date: str | None = None
    granularity: str = "daily"
    metrics: List[str] = ["overall_score", "complexity", "maintainability"]


class EvolutionAnalysisRequest(BaseModel):
    """Request to trigger code evolution analysis."""

    repo_path: str = Field(description="Path to git repository to analyze")
    start_date: str | None = Field(None, description="Start date for analysis (ISO format)")
    end_date: str | None = Field(None, description="End date for analysis (ISO format)")
    commit_limit: int = Field(100, description="Maximum number of commits to analyze", ge=1, le=1000)


class EvolutionAnalysisResponse(BaseModel):
    """Response from evolution analysis."""

    status: str
    message: str
    commits_analyzed: int = 0
    emerging_patterns: List[Dict[str, Any]] = []
    declining_patterns: List[Dict[str, Any]] = []
    refactorings_detected: int = 0
    analysis_duration_seconds: float = 0.0


# ---------------------------------------------------------------------------
# analytics_conversation.py schemas
# ---------------------------------------------------------------------------


class IntentPattern(BaseModel):
    """Represents a detected user intent pattern."""

    intent_id: str
    intent_name: str
    pattern_regex: str
    occurrences: int
    success_rate: float
    avg_turns_to_resolve: float
    sample_queries: List[str] = Field(default_factory=list, max_length=5)


class ConversationFlow(BaseModel):
    """Represents a conversation flow path."""

    flow_id: str
    path: List[str]
    frequency: int
    avg_duration_seconds: float
    completion_rate: float
    drop_off_point: str | None = None


class ConversationMetrics(BaseModel):
    """Aggregated conversation metrics."""

    total_conversations: int
    total_messages: int
    avg_messages_per_conversation: float
    avg_conversation_duration_seconds: float
    user_satisfaction_estimate: float
    resolution_rate: float
    escalation_rate: float


class FlowBottleneck(BaseModel):
    """Represents a bottleneck in conversation flows."""

    bottleneck_id: str
    location: str
    description: str
    impact_score: float
    affected_conversations: int
    suggested_improvements: List[str]


class ConversationAnalysisResult(BaseModel):
    """Full conversation analysis result."""

    metrics: ConversationMetrics
    intent_patterns: List[IntentPattern]
    common_flows: List[ConversationFlow]
    bottlenecks: List[FlowBottleneck]
    hourly_distribution: Dict[str, int]
    analysis_period: str
    conversations_analyzed: int


# ---------------------------------------------------------------------------
# analytics_maintenance.py schemas
# ---------------------------------------------------------------------------


class MaintenanceRecommendationResponse(BaseModel):
    """Maintenance recommendation response model."""

    id: str
    title: str
    description: str
    priority: str
    category: str
    affected_component: str
    predicted_issue: str
    confidence: float
    recommended_action: str
    estimated_impact: str
    detected_at: str
    metadata: dict = Field(default_factory=dict)


class ResourceOptimizationResponse(BaseModel):
    """Resource optimization response model."""

    id: str
    resource_type: str
    title: str
    current_usage: dict
    recommended_change: str
    expected_savings: dict
    implementation_effort: str
    priority: str
    details: str


class DashboardResponse(BaseModel):
    """Unified dashboard response model."""

    generated_at: str
    period_days: int
    health: dict
    cost: dict
    agents: dict
    engagement: dict
    maintenance: dict
    optimization: dict


class CustomReportRequest(BaseModel):
    """Custom report generation request."""

    report_type: str = Field(default="executive", description="Report type: executive, technical, cost, performance")
    days: int = Field(default=30, ge=1, le=365, description="Days to include")
    include_sections: List[str] | None = Field(
        default=None,
        description="Sections to include: cost, agents, behavior, maintenance, optimization",
    )


# ---------------------------------------------------------------------------
# analytics_log_patterns.py schemas
# ---------------------------------------------------------------------------


class LogPattern(BaseModel):
    """Represents a discovered log pattern."""

    pattern_id: str
    pattern_template: str
    occurrences: int
    first_seen: str
    last_seen: str
    log_levels: List[str]
    sources: List[str]
    sample_messages: List[str] = Field(default_factory=list, max_length=5)
    frequency_per_hour: float = 0.0
    is_error_pattern: bool = False
    is_anomaly: bool = False


class LogAnomaly(BaseModel):
    """Represents a detected anomaly in logs."""

    anomaly_id: str
    anomaly_type: str
    severity: str
    description: str
    timestamp: str
    affected_sources: List[str]
    metric_before: float
    metric_after: float
    confidence: float


class LogTrend(BaseModel):
    """Represents a trend in log data."""

    trend_id: str
    metric_name: str
    direction: str
    change_percent: float
    time_period: str
    data_points: List[Dict[str, Any]]


class PatternMiningResult(BaseModel):
    """Result of pattern mining operation."""

    patterns: List[LogPattern]
    anomalies: List[LogAnomaly]
    trends: List[LogTrend]
    summary: Dict[str, Any]
    analysis_time_ms: float
    logs_analyzed: int


# ---------------------------------------------------------------------------
# analytics_agents.py schemas
# ---------------------------------------------------------------------------


class AgentMetricsResponse(BaseModel):
    """Agent metrics response model."""

    agent_id: str
    agent_type: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    cancelled_tasks: int
    timeout_tasks: int
    avg_duration_ms: float
    total_tokens_used: int
    error_rate: float
    success_rate: float
    last_activity: str | None


class TaskRecordResponse(BaseModel):
    """Task record response model."""

    agent_id: str
    agent_type: str
    task_id: str
    task_name: str
    status: str
    started_at: str
    completed_at: str | None
    duration_ms: float | None
    tokens_used: int | None
    error_message: str | None


class TrackTaskRequest(BaseModel):
    """Request to track a task start."""

    agent_id: str = Field(..., description="Unique agent identifier")
    agent_type: str = Field(..., description="Type of agent")
    task_id: str = Field(..., description="Unique task identifier")
    task_name: str = Field(..., description="Human-readable task name")
    input_size: int | None = Field(None, description="Size of input data")
    metadata: dict | None = Field(None, description="Additional metadata")


class CompleteTaskRequest(BaseModel):
    """Request to complete a task."""

    task_id: str = Field(..., description="Task identifier")
    status: str = Field(..., description="Final status (completed, failed, cancelled, timeout)")
    output_size: int | None = Field(None, description="Size of output data")
    tokens_used: int | None = Field(None, description="Tokens consumed")
    error_message: str | None = Field(None, description="Error message if failed")


# ---------------------------------------------------------------------------
# analytics_behavior.py schemas
# ---------------------------------------------------------------------------


class TrackEventRequest(BaseModel):
    """Request model for tracking user events."""

    event_type: str = Field(..., description="Type of event (page_view, click, search, etc.)")
    feature: str = Field(..., description="Feature area (chat, knowledge, tools, etc.)")
    user_id: str | None = Field(None, description="User ID if authenticated")
    session_id: str | None = Field(None, description="Session ID")
    duration_ms: int | None = Field(None, ge=0, description="Duration in milliseconds")
    metadata: dict | None = Field(default_factory=dict, description="Additional metadata")


class FeatureMetricsResponse(BaseModel):
    """Response model for feature metrics."""

    timestamp: str
    features: dict
    total_features: int


class UserJourneyResponse(BaseModel):
    """Response model for user journey."""

    session_id: str
    steps: list
    total_steps: int
    features_visited: list


# EngagementMetricsResponse retired in #9959 — the /analytics/engagement-metrics
# endpoint it served was a dead duplicate over a never-written keyspace; the
# canonical /analytics/behavior/engagement surface absorbs its functionality.


# ---------------------------------------------------------------------------
# analytics_performance.py enums + schemas
# ---------------------------------------------------------------------------


class PerformancePatternCategory(str, Enum):
    """Categories of performance patterns."""

    QUERY = "query"
    LOOP = "loop"
    ASYNC = "async"
    CACHE = "cache"
    MEMORY = "memory"
    IO = "io"


class PerformanceIssue(BaseModel):
    """A detected performance issue."""

    id: str
    pattern_id: str
    name: str
    category: PerformancePatternCategory
    impact: ImpactLevel
    file: str
    line: int
    column: int = 0
    description: str
    suggestion: str
    code_snippet: str | None = None
    estimated_impact: str | None = None


class PerformanceAnalysisResult(BaseModel):
    """Result of performance analysis."""

    status: str = "success"
    total_issues: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    issues: List[PerformanceIssue]
    files_analyzed: int
    duration_ms: float
    timestamp: str
    score: int = Field(ge=0, le=100)


class PerformancePatternDefinition(BaseModel):
    """Definition of a performance pattern to detect."""

    id: str
    name: str
    category: PerformancePatternCategory
    impact: ImpactLevel
    description: str
    suggestion: str
    regex_pattern: str | None = None
    ast_check: bool = False
    enabled: bool = True


# ---------------------------------------------------------------------------
# analytics_code_review.py enums + schemas
# ---------------------------------------------------------------------------


class ReviewSeverity(str, Enum):
    """Review comment severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"
    SUGGESTION = "suggestion"


class ReviewCategory(str, Enum):
    """Categories of review findings."""

    SECURITY = "security"
    PERFORMANCE = "performance"
    STYLE = "style"
    BUG_RISK = "bug_risk"
    MAINTAINABILITY = "maintainability"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    BEST_PRACTICE = "best_practice"


class ReviewComment(BaseModel):
    """A single review comment."""

    id: str
    file_path: str
    line_number: int
    severity: ReviewSeverity
    category: ReviewCategory
    message: str
    suggestion: str | None = None
    code_snippet: str | None = None
    pattern_id: str | None = None


class ReviewResult(BaseModel):
    """Complete review result for a diff or PR."""

    id: str
    timestamp: datetime
    files_reviewed: int
    total_comments: int
    comments: List[ReviewComment] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    score: float = Field(..., ge=0, le=100)


class PatternToggleRequest(BaseModel):
    """Request model for toggling pattern preference."""

    pattern_id: str
    enabled: bool


# ---------------------------------------------------------------------------
# analytics_cfg.py enums + schemas
# ---------------------------------------------------------------------------


class NodeType(str, Enum):
    """Types of CFG nodes."""

    ENTRY = "entry"
    EXIT = "exit"
    STATEMENT = "statement"
    CONDITION = "condition"
    LOOP_HEADER = "loop_header"
    LOOP_BODY = "loop_body"
    TRY_BLOCK = "try_block"
    EXCEPT_HANDLER = "except_handler"
    FINALLY_BLOCK = "finally_block"
    FUNCTION_DEF = "function_def"
    CLASS_DEF = "class_def"
    RETURN = "return"
    RAISE = "raise"
    BREAK = "break"
    CONTINUE = "continue"
    PASS = "pass"  # nosec B105 - CFG statement type enum value, not a password


class EdgeType(str, Enum):
    """Types of CFG edges."""

    SEQUENTIAL = "sequential"
    TRUE_BRANCH = "true_branch"
    FALSE_BRANCH = "false_branch"
    LOOP_BACK = "loop_back"
    BREAK_OUT = "break_out"
    CONTINUE_BACK = "continue_back"
    EXCEPTION = "exception"
    FINALLY = "finally"
    RETURN_EDGE = "return_edge"


class IssueType(str, Enum):
    """Types of control flow issues."""

    UNREACHABLE_CODE = "unreachable_code"
    INFINITE_LOOP = "infinite_loop"
    POTENTIAL_INFINITE_LOOP = "potential_infinite_loop"
    DEAD_BRANCH = "dead_branch"
    COMPLEX_CONDITION = "complex_condition"
    HIGH_CYCLOMATIC_COMPLEXITY = "high_cyclomatic_complexity"
    DEEP_NESTING = "deep_nesting"
    MISSING_RETURN = "missing_return"
    EMPTY_EXCEPT = "empty_except"
    BARE_EXCEPT = "bare_except"


class CFGAnalyzeRequest(BaseModel):
    """Request to analyze source code."""

    source_code: str = Field(..., description="Python source code to analyze")
    file_path: str = Field(default="", description="Optional file path for context")


class CFGAnalyzeFileRequest(BaseModel):
    """Request to analyze a file."""

    file_path: str = Field(..., description="Path to Python file")


class CFGResponse(BaseModel):
    """Response containing CFG analysis."""

    success: bool
    graphs: List[Dict[str, Any]]
    summary: Dict[str, Any]
    issues: List[Dict[str, Any]]
    analysis_time_ms: float


# ---------------------------------------------------------------------------
# analytics_llm_patterns.py enums + schemas
# ---------------------------------------------------------------------------


class PromptCategory(str, Enum):
    """Categories of LLM prompts."""

    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    DOCUMENTATION = "documentation"
    ANALYSIS = "analysis"
    CHAT = "chat"
    TASK_PLANNING = "task_planning"
    TRANSLATION = "translation"
    SUMMARIZATION = "summarization"
    UNKNOWN = "unknown"


class OptimizationType(str, Enum):
    """Types of optimization opportunities."""

    CACHE_PROMPT = "cache_prompt"
    USE_SMALLER_MODEL = "use_smaller_model"
    REDUCE_CONTEXT = "reduce_context"
    BATCH_REQUESTS = "batch_requests"
    TEMPLATE_REUSE = "template_reuse"


class PromptAnalysisRequest(BaseModel):
    """Request for prompt analysis."""

    prompt: str = Field(..., description="The prompt to analyze")
    model: str | None = Field(None, description="Model used or planned")


class UsageRecordRequest(BaseModel):
    """Request to record LLM usage."""

    prompt: str = Field(..., description="The prompt sent")
    model: str = Field(..., description="Model used")
    input_tokens: int = Field(..., description="Input token count")
    output_tokens: int = Field(..., description="Output token count")
    response_time: float = Field(..., description="Response time in seconds")
    success: bool = Field(default=True)
    session_id: str | None = Field(None)

    def to_record_dict(
        self,
        prompt_hash: str,
        prompt_preview: str,
        category_value: str,
        cost: float,
    ) -> Dict[str, Any]:
        """Convert to record dictionary for storage."""
        from datetime import datetime, timezone

        return {
            "prompt_hash": prompt_hash,
            "prompt_preview": prompt_preview,
            "category": category_value,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost": cost,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "response_time": self.response_time,
            "success": self.success,
            "session_id": self.session_id,
        }


class DateRangeParams:
    """FastAPI ``Depends()`` helper for endpoints accepting a date-range filter.

    Use as a query-param dependency to consolidate the recurring
    ``start_date: str | None = Query(None, ...)`` /
    ``end_date: str | None = Query(None, ...)`` pair across analytics
    endpoints (#7110, #6624 follow-up).

    Example usage::

        from fastapi import Depends
        from api.schemas_analytics import DateRangeParams

        @router.get("/timeline")
        async def get_timeline(
            date_range: DateRangeParams = Depends(),
            ...
        ):
            start_ts, end_ts = _parse_date_range(date_range.start_date, date_range.end_date)
            ...

    NOTE: this is intentionally a regular Python class (not Pydantic
    ``BaseModel``) because FastAPI's ``Depends()`` only treats class fields
    as **query** parameters when the class has a plain ``__init__`` —
    Pydantic models would be treated as request bodies. See FastAPI's
    "classes as dependencies" tutorial.
    """

    def __init__(
        self,
        start_date: Annotated[str | None, Query(description="Start date (YYYY-MM-DD)")] = None,
        end_date: Annotated[str | None, Query(description="End date (YYYY-MM-DD)")] = None,
    ):
        self.start_date = start_date
        self.end_date = end_date


# ---------------------------------------------------------------------------
# analytics_quality.py enums + schemas
# ---------------------------------------------------------------------------


class QualityGrade(str, Enum):
    """Quality grades from A to F."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


class MetricCategory(str, Enum):
    """Categories of quality metrics."""

    MAINTAINABILITY = "maintainability"
    RELIABILITY = "reliability"
    SECURITY = "security"
    PERFORMANCE = "performance"
    TESTABILITY = "testability"
    DOCUMENTATION = "documentation"


class QualityMetric(BaseModel):
    """Individual quality metric."""

    name: str
    category: MetricCategory
    value: float = Field(..., ge=0, le=100)
    grade: QualityGrade
    trend: float = Field(default=0, description="Percentage change from previous period")
    details: Dict[str, Any] | None = None


class HealthScore(BaseModel):
    """Overall codebase health score."""

    overall: float = Field(..., ge=0, le=100)
    grade: QualityGrade
    trend: float = Field(default=0)
    breakdown: Dict[str, float] = Field(default_factory=dict)
    recommendations: List[str] = Field(default_factory=list)


class PatternDistribution(BaseModel):
    """Distribution of code patterns."""

    pattern_type: str
    count: int
    percentage: float
    severity: str
    examples: List[str] = Field(default_factory=list)


class ComplexityMetrics(BaseModel):
    """Code complexity analysis."""

    average_cyclomatic: float
    max_cyclomatic: int
    average_cognitive: float
    max_cognitive: int
    hotspots: List[Dict[str, Any]] = Field(default_factory=list)
    distribution: Dict[str, int] = Field(default_factory=dict)


class QualitySnapshot(BaseModel):
    """Complete quality snapshot at a point in time."""

    timestamp: datetime
    health_score: HealthScore
    metrics: List[QualityMetric]
    patterns: List[PatternDistribution]
    complexity: ComplexityMetrics
    file_count: int
    line_count: int
    issues_count: int


# ---------------------------------------------------------------------------
# analytics_architecture.py enums + schemas
# ---------------------------------------------------------------------------


class PatternType(str, Enum):
    """Types of architectural patterns."""

    FACTORY = "factory"
    ABSTRACT_FACTORY = "abstract_factory"
    SINGLETON = "singleton"
    BUILDER = "builder"
    PROTOTYPE = "prototype"
    ADAPTER = "adapter"
    BRIDGE = "bridge"
    COMPOSITE = "composite"
    DECORATOR = "decorator"
    FACADE = "facade"
    PROXY = "proxy"
    OBSERVER = "observer"
    STRATEGY = "strategy"
    COMMAND = "command"
    STATE = "state"
    TEMPLATE_METHOD = "template_method"
    CHAIN_OF_RESPONSIBILITY = "chain_of_responsibility"
    MVC = "mvc"
    MVP = "mvp"
    MVVM = "mvvm"
    REPOSITORY = "repository"
    SERVICE_LAYER = "service_layer"
    DEPENDENCY_INJECTION = "dependency_injection"
    AUTOBOT_ROUTER = "autobot_router"
    AUTOBOT_SERVICE = "autobot_service"
    AUTOBOT_MANAGER = "autobot_manager"
    AUTOBOT_HANDLER = "autobot_handler"
    REDIS_CACHING = "redis_caching"
    MCP_TOOL = "mcp_tool"


class ConsistencyLevel(str, Enum):
    """Levels of pattern consistency."""

    CONSISTENT = "consistent"
    MOSTLY_CONSISTENT = "mostly_consistent"
    INCONSISTENT = "inconsistent"
    UNKNOWN = "unknown"


class PatternMatch(BaseModel):
    """A detected pattern match."""

    pattern_type: PatternType
    file_path: str
    class_name: str | None = None
    function_name: str | None = None
    line_number: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    indicators_found: List[str]
    code_snippet: str | None = None


class PatternConsistency(BaseModel):
    """Pattern consistency analysis."""

    pattern_type: PatternType
    consistency_level: ConsistencyLevel
    total_instances: int
    consistent_instances: int
    violations: List[Dict[str, Any]]
    recommendations: List[str]


class ArchitectureLayer(BaseModel):
    """An architectural layer in the system."""

    name: str
    description: str
    components: List[str]
    dependencies: List[str]
    patterns_used: List[PatternType]


class ArchitectureReport(BaseModel):
    """Complete architecture analysis report."""

    timestamp: datetime
    total_files_analyzed: int
    patterns_detected: Dict[str, int]
    pattern_matches: List[PatternMatch]
    consistency_analysis: List[PatternConsistency]
    layers: List[ArchitectureLayer]
    recommendations: List[str]
    mermaid_diagram: str


class ArchitectureAnalysisRequest(BaseModel):
    """Request for architecture analysis."""

    paths: List[str] = Field(default_factory=lambda: ["backend/", "src/"], description="Paths to analyze")
    patterns_to_detect: List[PatternType] | None = Field(None, description="Specific patterns to look for")
    include_autobot_patterns: bool = Field(True, description="Include AutoBot-specific patterns")
    generate_diagram: bool = Field(True, description="Generate Mermaid diagram")


# ---------------------------------------------------------------------------
# analytics_dfa.py enums + schemas
# ---------------------------------------------------------------------------


class TaintLevel(str, Enum):
    """Taint levels for data flow tracking."""

    UNTAINTED = "untainted"
    PARTIALLY_TAINTED = "partially_tainted"
    TAINTED = "tainted"
    SANITIZED = "sanitized"


class SourceType(str, Enum):
    """Types of data sources."""

    USER_INPUT = "user_input"
    EXTERNAL_API = "external_api"
    DATABASE = "database"
    FILE = "file"
    ENVIRONMENT = "environment"
    NETWORK = "network"
    PARAMETER = "parameter"
    CONSTANT = "constant"


class SinkType(str, Enum):
    """Types of data sinks."""

    DATABASE_QUERY = "database_query"
    FILE_WRITE = "file_write"
    NETWORK_SEND = "network_send"
    SUBPROCESS = "subprocess"
    EVAL = "eval"
    HTML_OUTPUT = "html_output"
    LOG_OUTPUT = "log_output"
    RETURN_VALUE = "return_value"


class VulnerabilityType(str, Enum):
    """Types of security vulnerabilities."""

    SQL_INJECTION = "sql_injection"
    XSS = "xss"
    COMMAND_INJECTION = "command_injection"
    PATH_TRAVERSAL = "path_traversal"
    CODE_INJECTION = "code_injection"
    DATA_EXPOSURE = "data_exposure"
    INSECURE_DESERIALIZATION = "insecure_deserialization"
    HARDCODED_SECRET = "hardcoded_secret"  # nosec B105


class DFAAnalyzeRequest(BaseModel):
    """Request model for code analysis."""

    source_code: str = Field(..., description="Python source code to analyze")
    file_path: str = Field(default="<unknown>", description="File path for context")


class DFAAnalyzeFileRequest(BaseModel):
    """Request model for file analysis."""

    file_path: str = Field(..., description="Path to Python file to analyze")


class VariableDefResponse(BaseModel):
    """Response model for variable definition."""

    name: str
    line: int
    column: int
    scope: str
    taint_level: str
    source_type: str | None


class VulnerabilityResponse(BaseModel):
    """Response model for vulnerability."""

    vulnerability_type: str
    severity: str
    line: int
    column: int
    description: str
    tainted_variable: str
    sink_function: str
    recommendation: str


class DataFlowResponse(BaseModel):
    """Response model for data flow analysis."""

    name: str
    definitions_count: int
    uses_count: int
    edges_count: int
    vulnerabilities_count: int
    definitions: List[VariableDefResponse]
    vulnerabilities: List[VulnerabilityResponse]


class DFAAnalysisResponse(BaseModel):
    """Response model for complete data-flow analysis."""

    file_path: str
    analyzed_at: str
    graphs: List[DataFlowResponse]
    total_definitions: int
    total_uses: int
    total_vulnerabilities: int
    tainted_variables: List[str]


class TaintSummary(BaseModel):
    """Summary of taint analysis."""

    tainted_sources: int
    dangerous_sinks: int
    vulnerabilities_by_type: Dict[str, int]
    vulnerabilities_by_severity: Dict[str, int]
    tainted_variables: List[str]


# ---------------------------------------------------------------------------
# analytics_embedding_patterns.py schemas
# ---------------------------------------------------------------------------


class EmbeddingUsageRequest(BaseModel):
    """Request to record embedding usage."""

    operation_type: str = Field(default="document_vectorization", description="Type of embedding operation")
    model: str = Field(..., description="Embedding model used")
    provider: str = Field(default="ollama", description="Embedding provider")
    token_count: int = Field(..., description="Total tokens processed")
    document_count: int = Field(default=1, description="Number of documents processed")
    batch_size: int = Field(default=1, description="Batch size used")
    processing_time: float = Field(..., description="Processing time in seconds")
    success: bool = Field(default=True, description="Whether operation succeeded")
    source: str | None = Field(None, description="Source of the operation")
    metadata: Dict[str, Any] | None = Field(None, description="Additional metadata")

    def to_usage_record(self, operation_id: str, cost: float) -> Dict[str, Any]:
        """Convert to usage record dict for storage."""
        from datetime import datetime, timezone

        return {
            "operation_id": operation_id,
            "operation_type": self.operation_type,
            "model": self.model,
            "provider": self.provider,
            "token_count": self.token_count,
            "document_count": self.document_count,
            "batch_size": self.batch_size,
            "processing_time": self.processing_time,
            "success": self.success,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "cost": cost,
            "source": self.source or "unknown",
            "metadata": self.metadata or {},
        }

    def get_tokens_per_second(self) -> float:
        if self.processing_time > 0:
            return self.token_count / self.processing_time
        return 0

    def get_log_summary(self) -> str:
        return f"{self.document_count} docs, {self.token_count} tokens, " f"{self.processing_time:.3f}s"


class EmbeddingStatsBody(BaseModel):
    """Inner stats body returned by EmbeddingPatternAnalyzer.get_stats()."""

    total_operations: int
    total_tokens: int
    total_documents: int
    total_cost: float
    avg_processing_time: float
    success_rate: float
    avg_batch_size: float
    tokens_per_second: float
    period_days: int


class EmbeddingStatsResponse(BaseModel):
    """Envelope response for GET /api/analytics/embedding-patterns/stats —
    matches the dict shape returned by EmbeddingPatternAnalyzer.get_stats().
    Also covers the error shape via extra="allow"."""

    model_config = {"extra": "allow"}

    status: str = Field(..., description="success | error")
    stats: EmbeddingStatsBody | None = None
    timestamp: str | None = None
    # error shape
    error: str | None = None


# ---------------------------------------------------------------------------
# usage.py schemas
# ---------------------------------------------------------------------------


class UsageRecordEndpointRequest(BaseModel):
    """Request body for POST /api/usage/record.

    Renamed from UsageRecordRequest in #6636 to disambiguate from the
    LLM-analytics UsageRecordRequest at line 2845, which has a different
    shape (prompt-based) and is used by analytics_llm_patterns.py and
    llm_shared/interface.py. The previous shadowing caused silent
    Pydantic validation failures in LLM usage tracking
    (logged as non-critical and swallowed)."""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    session_id: str | None = None
    user_id: str | None = None
    agent_id: str | None = None
    latency_ms: float | None = None
    success: bool = True


# ---------------------------------------------------------------------------
# analytics_debt.py schemas
# ---------------------------------------------------------------------------


class DebtCalculationRequest(BaseModel):
    """Request for technical debt calculation."""

    target_path: str = Field(default=".", description="Path to analyze")
    hourly_rate: float = Field(default=75.0, description="Developer hourly rate in USD")
    include_categories: List[str] = Field(default_factory=list, description="Categories to include (empty = all)")


class DebtSummary(BaseModel):
    """Summary of technical debt."""

    total_items: int
    total_hours: float
    total_cost_usd: float
    by_category: Dict[str, int]
    by_severity: Dict[str, int]
    top_files: List[Dict[str, Any]]
    roi_ranking: List[Dict[str, Any]]
    timestamp: str


# ---------------------------------------------------------------------------
# analytics_bug_prediction.py schemas
# ---------------------------------------------------------------------------

# RiskLevel is the canonical Severity enum (#6689 consolidation).
# Imported above; keep module-level so Pydantic field annotations resolve.


class RiskFactor(str, Enum):
    """Factors contributing to bug risk."""

    COMPLEXITY = "complexity"
    CHANGE_FREQUENCY = "change_frequency"
    CODE_AGE = "code_age"
    TEST_COVERAGE = "test_coverage"
    BUG_HISTORY = "bug_history"
    AUTHOR_EXPERIENCE = "author_experience"
    FILE_SIZE = "file_size"
    DEPENDENCY_COUNT = "dependency_count"


class FileRisk(BaseModel):
    """Bug risk assessment for a file. Matches FileRiskAssessment.to_dict()
    output from code_intelligence/bug_predictor.py."""

    file_path: str
    risk_score: float = Field(..., ge=0, le=100)
    risk_level: RiskLevel
    factors: Dict[str, float] = Field(default_factory=dict)
    factor_details: List[Dict[str, Any]] | None = None
    bug_count_history: int = 0
    last_bug_date: str | None = None
    prevention_tips: List[str] = Field(default_factory=list)
    suggested_tests: List[str] = Field(default_factory=list)
    recommendation: str = ""


class PredictionResult(BaseModel):
    """Bug prediction result for the codebase. Matches PredictionResult.to_dict()
    output from code_intelligence/bug_predictor.py."""

    timestamp: str = Field(..., description="ISO format timestamp")
    total_files: int
    analyzed_files: int = 0
    high_risk_count: int
    predicted_bugs: int = 0
    accuracy_score: float | None = None
    accuracy_available: bool = False
    risk_distribution: Dict[str, int] = Field(default_factory=dict)
    files: List[FileRisk] = Field(default_factory=list)
    top_risk_factors: List[Dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# analytics_evolution.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class AnalyticsEvolutionTimelineResponse(BaseModel):
    """Response for GET /timeline."""

    timeline: List[Dict[str, Any]] = Field(default_factory=list)
    total_snapshots: int = 0
    date_range: Dict[str, Any] = Field(default_factory=dict)
    granularity: str = "daily"
    metrics_available: List[str] = Field(default_factory=list)


class AnalyticsEvolutionPatternsResponse(BaseModel):
    """Response for GET /patterns."""

    status: str
    patterns: Dict[str, Any] = Field(default_factory=dict)
    pattern_types: List[str] = Field(default_factory=list)
    date_range: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsEvolutionTrendsResponse(BaseModel):
    """Response for GET /trends."""

    status: str
    trends: Dict[str, Any] = Field(default_factory=dict)
    period_days: int = 30
    snapshot_count: int = 0
    analysis_timestamp: str = ""


class AnalyticsEvolutionSnapshotResponse(BaseModel):
    """Response for POST /snapshot."""

    status: str
    message: str = ""
    snapshot: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsEvolutionPatternSnapshotResponse(BaseModel):
    """Response for POST /pattern-snapshot."""

    status: str
    message: str = ""
    snapshot: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsEvolutionExportResponse(BaseModel):
    """Response for GET /export (JSON format path)."""

    status: str
    export_format: str = "json"
    data: List[EvolutionQualitySnapshot] = Field(default_factory=list)
    record_count: int = 0
    exported_at: str = ""


class AnalyticsEvolutionSummaryResponse(BaseModel):
    """Response for GET /summary."""

    total_snapshots: int = 0
    date_range: Dict[str, Any] = Field(default_factory=dict)
    latest_scores: Dict[str, Any] = Field(default_factory=dict)
    trend_direction: str = "unknown"
    pattern_counts: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# analytics_debt.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class AnalyticsDebtCalculateResponse(BaseModel):
    """Response for POST /calculate."""

    status: str
    data: Dict[str, Any] = Field(default_factory=dict)
    target_path: str | None = None


class AnalyticsDebtSummaryResponse(BaseModel):
    """Response for GET /summary."""

    status: str
    summary: Dict[str, Any] = Field(default_factory=dict)
    top_files: List[Dict[str, Any]] = Field(default_factory=list)
    roi_ranking: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: str | None = None


class AnalyticsDebtByCategoryResponse(BaseModel):
    """Response for GET /by-category/{category}."""

    status: str
    category: str = ""
    items: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class AnalyticsDebtTrendsResponse(BaseModel):
    """Response for GET /trends."""

    status: str
    trends: List[Dict[str, Any]] = Field(default_factory=list)
    data_points: int = 0
    change: Dict[str, Any] = Field(default_factory=dict)
    direction: str = "unknown"


class AnalyticsDebtROIPrioritiesResponse(BaseModel):
    """Response for GET /roi-priorities."""

    status: str
    priorities: List[Dict[str, Any]] = Field(default_factory=list)
    total_available: int = 0


class AnalyticsDebtReportResponse(BaseModel):
    """Response for GET /report."""

    status: str
    format: str = "json"
    data: Dict[str, Any] | None = None
    report: str | None = None


# ---------------------------------------------------------------------------
# bi_export_endpoints.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class SavedReportDeleteResponse(BaseModel):
    """Response for DELETE /reports/saved/{report_id}."""

    report_id: str
    deleted: bool


class SavedReportRunResponse(BaseModel):
    """Response for POST /reports/saved/{report_id}/run."""

    status: str = ""
    report_id: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# analytics_cfg.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class AnalyticsCFGAnalyzeResponse(BaseModel):
    """Response for POST /analyze."""

    success: bool
    graphs: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    issues: List[Dict[str, Any]] = Field(default_factory=list)
    analysis_time_ms: float = 0.0


class AnalyticsCFGComplexityResponse(BaseModel):
    """Response for POST /complexity."""

    success: bool
    metrics: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsCFGUnreachableResponse(BaseModel):
    """Response for POST /unreachable."""

    success: bool
    unreachable_code: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class AnalyticsCFGInfiniteLoopsResponse(BaseModel):
    """Response for POST /infinite-loops."""

    success: bool
    loop_issues: List[Dict[str, Any]] = Field(default_factory=list)
    definite_infinite: int = 0
    potential_infinite: int = 0


# ---------------------------------------------------------------------------
# analytics_reporting.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class AnalyticsReportingReportResponse(BaseModel):
    """Response for GET /report."""

    status: str
    generated_at: str = ""
    summary: Dict[str, Any] = Field(default_factory=dict)
    quality: Dict[str, Any] = Field(default_factory=dict)
    categories: Dict[str, Any] = Field(default_factory=dict)
    top_files: List[Any] = Field(default_factory=list)
    technical_debt: Dict[str, Any] = Field(default_factory=dict)
    performance: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsReportingSummaryResponse(BaseModel):
    """Response for GET /summary."""

    health_score: float = 0.0
    grade: str = "N/A"
    total_issues: int = 0
    high_priority: int = 0
    timestamp: str = ""


class AnalyticsReportingTrendsResponse(BaseModel):
    """Response for GET /trends."""

    status: str
    message: str = ""
    data: List[Any] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# analytics_embedding_patterns.py schemas (GH #6509 Batch D)
# ---------------------------------------------------------------------------


class AnalyticsEmbeddingRecordResponse(BaseModel):
    """Response for POST /record."""

    status: str = ""
    message: str | None = None
    data: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsEmbeddingModelComparisonResponse(BaseModel):
    """Response for GET /model-comparison."""

    status: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


class AnalyticsEmbeddingOptimizationResponse(BaseModel):
    """Response for GET /optimization-recommendations."""

    status: str = ""
    data: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# analytics_code_generation.py / analytics_performance.py / analytics_quality.py
# schemas (GH #6509 Batch E)
# ---------------------------------------------------------------------------


class AnalyticsCodeGenRollbackData(BaseModel):
    """Response data for POST /codegen/rollback."""

    success: bool = True
    file_path: str = ""
    version_id: str = ""
    code: str = ""


class AnalyticsPerformanceAnalyzeData(BaseModel):
    """Response data for GET /performance/analyze."""

    total_issues: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    files_analyzed: int = 0
    duration_ms: float = 0.0
    timestamp: str = ""
    score: float = 0.0
    issues: List[Any] = Field(default_factory=list)
    status: str = ""


class AnalyticsQualityExportData(BaseModel):
    """Response data for GET /quality/export."""

    format: str = "json"
    content: Any = None
    status: str = ""
    error: str | None = None
