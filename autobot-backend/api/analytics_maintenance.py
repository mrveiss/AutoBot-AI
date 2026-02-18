# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced Analytics API Module - Predictive maintenance and resource optimization.

Provides API endpoints for:
- Predictive maintenance recommendations
- Resource optimization analysis
- Unified analytics dashboard
- Custom report generation

Related Issues: #59 (Advanced Analytics & Business Intelligence)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from auth_middleware import check_admin_permission
from backend.services.analytics_service import (
    MaintenancePriority,
    ResourceType,
    get_analytics_service,
)
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/advanced", tags=["analytics", "advanced"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


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

    report_type: str = Field(
        default="executive",
        description="Report type: executive, technical, cost, performance",
    )
    days: int = Field(default=30, ge=1, le=365, description="Days to include")
    include_sections: Optional[List[str]] = Field(
        default=None,
        description="Sections to include: cost, agents, behavior, maintenance, optimization",
    )


# ============================================================================
# PREDICTIVE MAINTENANCE ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_maintenance_recommendations",
    error_code_prefix="MAINT",
)
@router.get("/maintenance")
async def get_maintenance_recommendations(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get predictive maintenance recommendations.

    Analyzes system metrics and predicts potential issues before they occur.
    Returns prioritized list of maintenance actions.

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()
    recommendations = await service.get_predictive_maintenance()

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "total_recommendations": len(recommendations),
        "by_priority": {
            "critical": sum(
                1 for r in recommendations if r.priority == MaintenancePriority.CRITICAL
            ),
            "high": sum(
                1 for r in recommendations if r.priority == MaintenancePriority.HIGH
            ),
            "medium": sum(
                1 for r in recommendations if r.priority == MaintenancePriority.MEDIUM
            ),
            "low": sum(
                1 for r in recommendations if r.priority == MaintenancePriority.LOW
            ),
        },
        "recommendations": [r.to_dict() for r in recommendations],
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_maintenance_by_category",
    error_code_prefix="MAINT",
)
@router.get("/maintenance/category/{category}")
async def get_maintenance_by_category(
    category: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get maintenance recommendations for a specific category.

    Categories: agent_performance, cost_management, infrastructure, reliability

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()
    all_recommendations = await service.get_predictive_maintenance()

    filtered = [r for r in all_recommendations if r.category == category]

    return {
        "category": category,
        "total": len(filtered),
        "recommendations": [r.to_dict() for r in filtered],
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_maintenance_summary",
    error_code_prefix="MAINT",
)
@router.get("/maintenance/summary")
async def get_maintenance_summary(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get maintenance summary with action items.

    Returns a condensed view suitable for dashboard widgets.

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()
    recommendations = await service.get_predictive_maintenance()

    # Group by category
    by_category = {}
    for rec in recommendations:
        if rec.category not in by_category:
            by_category[rec.category] = []
        by_category[rec.category].append(rec)

    # Get critical items
    critical_items = [
        r for r in recommendations if r.priority == MaintenancePriority.CRITICAL
    ]

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "summary": {
            "total_items": len(recommendations),
            "requires_immediate_action": len(critical_items),
            "categories_affected": list(by_category.keys()),
        },
        "critical_actions": [
            {
                "title": r.title,
                "action": r.recommended_action,
                "component": r.affected_component,
            }
            for r in critical_items
        ],
        "by_category": {
            cat: {
                "count": len(items),
                "highest_priority": min(
                    items,
                    key=lambda x: ["critical", "high", "medium", "low"].index(
                        x.priority.value
                    ),
                ).priority.value,
            }
            for cat, items in by_category.items()
        },
    }


# ============================================================================
# RESOURCE OPTIMIZATION ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_resource_optimizations",
    error_code_prefix="OPT",
)
@router.get("/optimization")
async def get_resource_optimizations(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get resource optimization recommendations.

    Analyzes usage patterns and identifies cost and performance improvements.

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()
    optimizations = await service.get_resource_optimizations()

    # Calculate totals
    total_cost_savings = sum(
        o.expected_savings.get("cost_usd", 0) for o in optimizations
    )
    total_perf_improvement = sum(
        o.expected_savings.get("performance_percent", 0) for o in optimizations
    )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "total_recommendations": len(optimizations),
        "potential_savings": {
            "cost_usd": round(total_cost_savings, 2),
            "performance_improvement_percent": round(total_perf_improvement, 1),
        },
        "by_resource_type": {
            rt.value: sum(1 for o in optimizations if o.resource_type == rt)
            for rt in ResourceType
        },
        "recommendations": [o.to_dict() for o in optimizations],
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_optimization_by_type",
    error_code_prefix="OPT",
)
@router.get("/optimization/type/{resource_type}")
async def get_optimization_by_type(
    resource_type: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get optimizations for a specific resource type.

    Types: llm_tokens, agent_tasks, memory, cache, database

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()
    all_optimizations = await service.get_resource_optimizations()

    filtered = [o for o in all_optimizations if o.resource_type.value == resource_type]

    return {
        "resource_type": resource_type,
        "total": len(filtered),
        "recommendations": [o.to_dict() for o in filtered],
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_quick_wins",
    error_code_prefix="OPT",
)
@router.get("/optimization/quick-wins")
async def get_quick_wins(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get quick-win optimizations.

    Returns optimizations with low implementation effort and high impact.

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()
    all_optimizations = await service.get_resource_optimizations()

    # Filter for low effort, high priority
    quick_wins = [
        o
        for o in all_optimizations
        if o.implementation_effort == "low"
        and o.priority in [MaintenancePriority.HIGH, MaintenancePriority.CRITICAL]
    ]

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "total_quick_wins": len(quick_wins),
        "estimated_savings": sum(
            o.expected_savings.get("cost_usd", 0) for o in quick_wins
        ),
        "recommendations": [o.to_dict() for o in quick_wins],
    }


# ============================================================================
# UNIFIED DASHBOARD ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_unified_dashboard",
    error_code_prefix="DASH",
)
@router.get("/dashboard")
async def get_unified_dashboard(
    days: int = Query(default=30, ge=1, le=365, description="Days to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get unified analytics dashboard.

    Aggregates all analytics sources into a single comprehensive view.

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()
    dashboard = await service.get_unified_dashboard(days)

    return dashboard


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_health_status",
    error_code_prefix="HEALTH",
)
@router.get("/health")
async def get_health_status(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get system health status.

    Returns overall health score and status indicators.

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()
    dashboard = await service.get_unified_dashboard(7)  # Last 7 days for health

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "health": dashboard["health"],
        "indicators": {
            "cost_trend": dashboard["cost"]["trend"],
            "agent_success_rate": dashboard["agents"]["avg_success_rate"],
            "maintenance_issues": dashboard["maintenance"]["total_recommendations"],
            "optimization_opportunities": dashboard["optimization"][
                "total_recommendations"
            ],
        },
    }


# ============================================================================
# CUSTOM REPORT ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="generate_custom_report",
    error_code_prefix="REPORT",
)
@router.post("/report")
async def generate_custom_report(
    request: CustomReportRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Generate a custom analytics report.

    Report types:
    - executive: High-level summary with key metrics
    - technical: Detailed technical analysis
    - cost: Focus on cost metrics and optimization
    - performance: Focus on performance metrics

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=request.days)

    report = await service.generate_custom_report(
        report_type=request.report_type,
        start_date=start_date,
        end_date=end_date,
        include_sections=request.include_sections,
    )

    return report


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_executive_summary",
    error_code_prefix="REPORT",
)
@router.get("/report/executive")
async def get_executive_summary(
    days: int = Query(default=30, ge=7, le=90, description="Days to summarize"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get executive summary report.

    A quick high-level overview suitable for stakeholders.

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()

    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    report = await service.generate_custom_report(
        report_type="executive",
        start_date=start_date,
        end_date=end_date,
        include_sections=["cost", "agents", "maintenance", "optimization"],
    )

    return report


# ============================================================================
# INSIGHTS ENDPOINTS
# ============================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_insights",
    error_code_prefix="INSIGHT",
)
@router.get("/insights")
async def get_insights(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get actionable insights from analytics data.

    Combines maintenance recommendations and optimization opportunities
    into prioritized action items.

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()

    # Issue #619: Parallelize independent data fetches
    maintenance, optimizations = await asyncio.gather(
        service.get_predictive_maintenance(),
        service.get_resource_optimizations(),
    )

    # Combine and prioritize
    insights = []

    # Add critical maintenance first
    for m in maintenance:
        if m.priority in [MaintenancePriority.CRITICAL, MaintenancePriority.HIGH]:
            insights.append(
                {
                    "type": "maintenance",
                    "priority": m.priority.value,
                    "title": m.title,
                    "action": m.recommended_action,
                    "impact": m.estimated_impact,
                }
            )

    # Add high-value optimizations
    for o in optimizations:
        if (
            o.expected_savings.get("cost_usd", 0) > 5
            or o.expected_savings.get("performance_percent", 0) > 10
        ):
            insights.append(
                {
                    "type": "optimization",
                    "priority": o.priority.value,
                    "title": o.title,
                    "action": o.recommended_change,
                    "impact": f"Potential savings: ${o.expected_savings.get('cost_usd', 0):.2f}",
                }
            )

    # Sort by priority
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    insights.sort(key=lambda x: priority_order.get(x["priority"], 4))

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "total_insights": len(insights),
        "insights": insights[:10],  # Top 10 insights
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_trends_analysis",
    error_code_prefix="TREND",
)
@router.get("/trends")
async def get_trends_analysis(
    days: int = Query(default=30, ge=7, le=90, description="Days to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get trends analysis across all metrics.

    Shows how key metrics are changing over time.

    Issue #744: Requires admin authentication.
    """
    service = get_analytics_service()
    # Issue #619: Parallelize independent trend fetches
    cost_trends, agent_trends = await asyncio.gather(
        service.cost.get_cost_trends(days),
        service.agents.get_performance_trends(days=days),
    )

    return {
        "timestamp": datetime.utcnow().isoformat(),
        "period_days": days,
        "cost_trends": {
            "direction": cost_trends.get("trend", "stable"),
            "growth_rate_percent": cost_trends.get("growth_rate_percent", 0),
            "total_cost_usd": cost_trends.get("total_cost_usd", 0),
        },
        "agent_trends": {
            "total_tasks": agent_trends.get("total_tasks", 0),
            "daily_stats": agent_trends.get("daily_stats", {}),
        },
        "summary": {
            "cost_direction": cost_trends.get("trend", "stable"),
            "is_healthy": cost_trends.get("growth_rate_percent", 0) < 20,
        },
    }
