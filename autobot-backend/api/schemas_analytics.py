# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Analytics, cost, budget, usage, and metrics schemas.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from api.schemas_common import SuccessMessageResponse


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
# files.py schemas  (Issue #5317)
# ---------------------------------------------------------------------------
