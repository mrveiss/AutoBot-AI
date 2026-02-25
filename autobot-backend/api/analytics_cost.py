# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Cost Analytics API Module - LLM cost tracking and analysis endpoints.

Provides API endpoints for:
- Cost summaries by time period
- Cost breakdown by model/provider
- Session cost tracking
- Cost trend analysis
- Budget management

Related Issues: #59 (Advanced Analytics & Business Intelligence)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from auth_middleware import check_admin_permission
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from services.llm_cost_tracker import MODEL_PRICING, get_cost_tracker

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cost", tags=["analytics", "cost"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class CostSummaryResponse(BaseModel):
    """Cost summary response model"""

    period: dict
    total_cost_usd: float
    daily_costs: dict
    by_model: dict
    avg_daily_cost: float


class CostTrendResponse(BaseModel):
    """Cost trend response model"""

    period_days: int
    total_cost_usd: float
    daily_costs: dict
    trend: str
    growth_rate_percent: float
    avg_daily_cost: float


class SessionCostResponse(BaseModel):
    """Session cost response model"""

    session_id: str
    found: bool
    cost_usd: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    error: Optional[str] = None


class BudgetAlertRequest(BaseModel):
    """Budget alert configuration request"""

    name: str = Field(..., description="Alert name")
    threshold_usd: float = Field(..., gt=0, description="Budget threshold in USD")
    period: str = Field(
        ..., pattern="^(daily|weekly|monthly)$", description="Alert period"
    )
    notify_at_percent: List[int] = Field(
        default=[50, 75, 90, 100], description="Percentages to notify at"
    )
    enabled: bool = Field(default=True, description="Whether alert is enabled")


class ModelPricingInfo(BaseModel):
    """Model pricing information"""

    model: str
    input_price_per_1m: float
    output_price_per_1m: float
    provider: str


class UsageRecordResponse(BaseModel):
    """Usage record response model"""

    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: str
    session_id: Optional[str]
    success: bool


# ============================================================================
# COST SUMMARY ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cost_summary",
    error_code_prefix="COST",
)
@router.get("/summary", response_model=CostSummaryResponse)
async def get_cost_summary(
    days: int = Query(
        default=30, ge=1, le=365, description="Number of days to analyze"
    ),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get cost summary for the specified time period.

    Returns total costs, daily breakdown, and per-model costs.

    Issue #744: Requires admin authentication.
    """
    tracker = get_cost_tracker()
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    summary = await tracker.get_cost_summary(start_date, end_date)

    return CostSummaryResponse(
        period=summary.get("period", {}),
        total_cost_usd=summary.get("total_cost_usd", 0),
        daily_costs=summary.get("daily_costs", {}),
        by_model=summary.get("by_model", {}),
        avg_daily_cost=summary.get("avg_daily_cost", 0),
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cost_by_model",
    error_code_prefix="COST",
)
@router.get("/by-model")
async def get_cost_by_model(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get cost breakdown by LLM model.

    Returns aggregated costs, token counts, and call counts per model.

    Issue #744: Requires admin authentication.
    """
    tracker = get_cost_tracker()
    summary = await tracker.get_cost_summary()

    by_model = summary.get("by_model", {})

    # Sort by cost descending
    sorted_models = sorted(
        by_model.items(), key=lambda x: x[1].get("cost_usd", 0), reverse=True
    )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "models": [
            {
                "model": model,
                "cost_usd": data.get("cost_usd", 0),
                "input_tokens": data.get("input_tokens", 0),
                "output_tokens": data.get("output_tokens", 0),
                "call_count": data.get("call_count", 0),
                "avg_cost_per_call": (
                    round(
                        data.get("cost_usd", 0) / max(data.get("call_count", 1), 1), 6
                    )
                ),
            }
            for model, data in sorted_models
        ],
        "total_models": len(sorted_models),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cost_by_session",
    error_code_prefix="COST",
)
@router.get("/by-session/{session_id}", response_model=SessionCostResponse)
async def get_cost_by_session(
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get cost breakdown for a specific session.

    Returns total cost and token usage for the given session.

    Issue #744: Requires admin authentication.
    """
    tracker = get_cost_tracker()
    result = await tracker.get_cost_by_session(session_id)

    return SessionCostResponse(
        session_id=result.get("session_id", session_id),
        found=result.get("found", False),
        cost_usd=result.get("cost_usd"),
        input_tokens=result.get("input_tokens"),
        output_tokens=result.get("output_tokens"),
        error=result.get("error"),
    )


# ============================================================================
# TREND ANALYSIS ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cost_trends",
    error_code_prefix="COST",
)
@router.get("/trends", response_model=CostTrendResponse)
async def get_cost_trends(
    days: int = Query(
        default=30, ge=7, le=365, description="Number of days to analyze"
    ),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get cost trend analysis.

    Returns daily costs, trend direction (increasing/decreasing/stable),
    and growth rate percentage.

    Issue #744: Requires admin authentication.
    """
    tracker = get_cost_tracker()
    trends = await tracker.get_cost_trends(days)

    return CostTrendResponse(
        period_days=trends.get("period_days", days),
        total_cost_usd=trends.get("total_cost_usd", 0),
        daily_costs=trends.get("daily_costs", {}),
        trend=trends.get("trend", "stable"),
        growth_rate_percent=trends.get("growth_rate_percent", 0),
        avg_daily_cost=trends.get("avg_daily_cost", 0),
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_cost_forecast",
    error_code_prefix="COST",
)
@router.get("/forecast")
async def get_cost_forecast(
    days_to_forecast: int = Query(
        default=30, ge=1, le=90, description="Days to forecast"
    ),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get cost forecast based on recent trends.

    Uses recent usage patterns to estimate future costs.

    Issue #744: Requires admin authentication.
    """
    tracker = get_cost_tracker()

    # Get last 30 days for baseline
    trends = await tracker.get_cost_trends(30)

    avg_daily = trends.get("avg_daily_cost", 0)
    growth_rate = trends.get("growth_rate_percent", 0) / 100

    # Simple linear forecast with growth rate
    forecasted_costs = {}
    start_date = datetime.utcnow()

    for day in range(1, days_to_forecast + 1):
        future_date = start_date + timedelta(days=day)
        date_str = future_date.strftime("%Y-%m-%d")
        # Apply growth rate compounded
        daily_factor = 1 + (growth_rate * day / 30)
        forecasted_costs[date_str] = round(avg_daily * daily_factor, 4)

    total_forecast = sum(forecasted_costs.values())

    return {
        "forecast_period": {
            "start": start_date.isoformat(),
            "days": days_to_forecast,
        },
        "baseline": {
            "avg_daily_cost": avg_daily,
            "trend": trends.get("trend", "stable"),
            "growth_rate_percent": growth_rate * 100,
        },
        "forecast": {
            "total_estimated_usd": round(total_forecast, 2),
            "daily_estimates": forecasted_costs,
        },
        "confidence": "medium" if abs(growth_rate) < 0.1 else "low",
    }


# ============================================================================
# USAGE HISTORY ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_recent_usage",
    error_code_prefix="COST",
)
@router.get("/usage/recent")
async def get_recent_usage(
    limit: int = Query(
        default=100, ge=1, le=1000, description="Number of records to return"
    ),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get recent LLM usage records.

    Returns the most recent API calls with cost information.

    Issue #744: Requires admin authentication.
    """
    tracker = get_cost_tracker()
    records = await tracker.get_recent_usage(limit)

    return {
        "count": len(records),
        "records": records,
    }


# ============================================================================
# PRICING INFORMATION ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_model_pricing",
    error_code_prefix="COST",
)
@router.get("/pricing")
async def get_model_pricing(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get current model pricing information.

    Returns pricing per 1M tokens for all supported models.

    Issue #744: Requires admin authentication.
    """
    pricing_list = []

    for model, prices in MODEL_PRICING.items():
        # Cache model.lower() to avoid repeated computation (Issue #323)
        model_lower = model.lower()
        # Determine provider from model name
        if "claude" in model_lower:
            provider = "anthropic"
        elif "gpt" in model_lower or model.startswith("o1"):
            provider = "openai"
        elif "gemini" in model_lower:
            provider = "google"
        else:
            provider = "local"

        pricing_list.append(
            {
                "model": model,
                "provider": provider,
                "input_price_per_1m": prices["input"],
                "output_price_per_1m": prices["output"],
                "is_free": prices["input"] == 0 and prices["output"] == 0,
            }
        )

    # Sort by provider then by price
    pricing_list.sort(key=lambda x: (x["provider"], -x["input_price_per_1m"]))

    return {
        "pricing_date": "2025-01-01",
        "currency": "USD",
        "models": pricing_list,
        "total_models": len(pricing_list),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="calculate_cost_estimate",
    error_code_prefix="COST",
)
@router.get("/estimate")
async def calculate_cost_estimate(
    model: str = Query(..., description="Model name"),
    input_tokens: int = Query(..., ge=0, description="Number of input tokens"),
    output_tokens: int = Query(..., ge=0, description="Number of output tokens"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Calculate estimated cost for a given model and token counts.

    Useful for cost estimation before making API calls.

    Issue #744: Requires admin authentication.
    """
    tracker = get_cost_tracker()
    cost = tracker.calculate_cost(model, input_tokens, output_tokens)

    return {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": cost,
        "total_tokens": input_tokens + output_tokens,
    }


# ============================================================================
# BUDGET MANAGEMENT ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="set_budget_alert",
    error_code_prefix="COST",
)
@router.post("/budget-alert")
async def set_budget_alert(
    alert: BudgetAlertRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Configure a budget alert.

    Set thresholds to receive notifications when spending approaches limits.

    Issue #744: Requires admin authentication.
    """
    # Store in Redis for persistence
    tracker = get_cost_tracker()
    redis = await tracker.get_redis()

    alert_data = {
        "name": alert.name,
        "threshold_usd": alert.threshold_usd,
        "period": alert.period,
        "notify_at_percent": alert.notify_at_percent,
        "enabled": alert.enabled,
        "created_at": datetime.utcnow().isoformat(),
    }

    import json

    await redis.hset(tracker.BUDGET_ALERTS_KEY, alert.name, json.dumps(alert_data))

    return {
        "status": "created",
        "alert": alert_data,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_budget_alerts",
    error_code_prefix="COST",
)
@router.get("/budget-alerts")
async def get_budget_alerts(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get all configured budget alerts.

    Issue #744: Requires admin authentication.
    """
    tracker = get_cost_tracker()
    redis = await tracker.get_redis()

    import json

    alerts_data = await redis.hgetall(tracker.BUDGET_ALERTS_KEY)
    alerts = []

    for name, data in alerts_data.items():
        name_str = name if isinstance(name, str) else name.decode("utf-8")
        data_str = data if isinstance(data, str) else data.decode("utf-8")
        alert = json.loads(data_str)
        alert["name"] = name_str
        alerts.append(alert)

    return {
        "alerts": alerts,
        "count": len(alerts),
    }


def _calculate_alert_status(name: str, data: str, current_costs: dict) -> dict:
    """
    Calculate budget status for a single alert.

    Issue #620: Extracted from get_budget_status.

    Args:
        name: Alert name (may be bytes)
        data: Alert data JSON (may be bytes)
        current_costs: Current costs by period

    Returns:
        Status dict for the alert
    """
    import json

    name_str = name if isinstance(name, str) else name.decode("utf-8")
    data_str = data if isinstance(data, str) else data.decode("utf-8")
    alert = json.loads(data_str)

    period = alert.get("period", "monthly")
    threshold = alert.get("threshold_usd", 0)
    current = current_costs.get(period, 0)

    percent_used = (current / threshold) * 100 if threshold > 0 else 0

    return {
        "name": name_str,
        "period": period,
        "threshold_usd": threshold,
        "current_usd": current,
        "percent_used": round(percent_used, 2),
        "status": (
            "exceeded"
            if percent_used >= 100
            else "warning"
            if percent_used >= 75
            else "ok"
        ),
        "remaining_usd": max(threshold - current, 0),
    }


async def _get_current_costs(tracker, today: datetime) -> dict:
    """
    Get current costs for daily, weekly, and monthly periods.

    Issue #620: Extracted from get_budget_status.
    Issue #619: Uses parallel fetches for performance.

    Args:
        tracker: Cost tracker instance
        today: Current date/time

    Returns:
        Dict with daily, weekly, monthly costs
    """
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    daily_summary, weekly_summary, monthly_summary = await asyncio.gather(
        tracker.get_cost_summary(today.replace(hour=0, minute=0, second=0), today),
        tracker.get_cost_summary(week_start, today),
        tracker.get_cost_summary(month_start, today),
    )

    return {
        "daily": daily_summary.get("total_cost_usd", 0),
        "weekly": weekly_summary.get("total_cost_usd", 0),
        "monthly": monthly_summary.get("total_cost_usd", 0),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_budget_status",
    error_code_prefix="COST",
)
@router.get("/budget-status")
async def get_budget_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get current budget status against all configured alerts.

    Issue #744: Requires admin authentication.
    Issue #620: Refactored to use extracted helper methods.
    """
    tracker = get_cost_tracker()
    redis = await tracker.get_redis()
    today = datetime.utcnow()

    # Get alerts and current costs (Issue #620: uses helper)
    alerts_data = await redis.hgetall(tracker.BUDGET_ALERTS_KEY)
    current_costs = await _get_current_costs(tracker, today)

    # Calculate status for each alert (Issue #620: uses helper)
    statuses = [
        _calculate_alert_status(name, data, current_costs)
        for name, data in alerts_data.items()
    ]

    return {
        "timestamp": today.isoformat(),
        "current_costs": current_costs,
        "budget_statuses": statuses,
    }
