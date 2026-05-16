# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Analytics API Module - Agent performance tracking endpoints.

Provides API endpoints for:
- Agent performance metrics
- Task history per agent
- Agent comparison and rankings
- Performance trends

Related Issues: #59 (Advanced Analytics & Business Intelligence)
"""

from fastapi import APIRouter, Depends, Query

from api.schemas_analytics import (
    AgentAllPerformanceResponse,
    AgentComparisonResponse,
    AgentHistoryResponse,
    AgentMetricsResponse,
    AgentPerformanceTrendsResponse,
    AgentRecentTasksResponse,
    AgentRecommendationsResponse,
    AgentTaskCompleteResponse,
    AgentTaskStartResponse,
    AgentTypesResponse,
    CompleteTaskRequest,
    TrackTaskRequest,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.agent_analytics import AgentType, TaskStatus, get_agent_analytics

logger = get_logger(__name__)
router = APIRouter(prefix="/agents", tags=["analytics", "agents"])


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


# ============================================================================
# AGENT METRICS ENDPOINTS
# ============================================================================


@router.get("/performance", response_model=AgentAllPerformanceResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_all_agents_performance",
    error_code_prefix="ANALYTICS_AGENTS",
)
async def get_all_agents_performance(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get performance metrics for all agents.

    Returns aggregated metrics including success rates, durations, and task counts.

    Issue #744: Requires admin authentication.
    """
    analytics = get_agent_analytics()
    metrics_list = await analytics.get_all_agents_metrics()

    return {
        "agents": [m.to_dict() for m in metrics_list],
        "total_agents": len(metrics_list),
        "summary": {
            "total_tasks": sum(m.total_tasks for m in metrics_list),
            "total_completed": sum(m.completed_tasks for m in metrics_list),
            "total_failed": sum(m.failed_tasks for m in metrics_list),
            "avg_success_rate": (
                round(sum(m.success_rate for m in metrics_list) / len(metrics_list), 2) if metrics_list else 0
            ),
        },
    }


@router.get("/performance/{agent_id}", response_model=AgentMetricsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_performance",
    error_code_prefix="ANALYTICS_AGENTS",
)
async def get_agent_performance(
    agent_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get performance metrics for a specific agent.

    Args:
        agent_id: Unique agent identifier
    """
    analytics = get_agent_analytics()
    metrics = await analytics.get_agent_metrics(agent_id)

    if not metrics:
        return AgentMetricsResponse(
            agent_id=agent_id,
            agent_type="unknown",
            total_tasks=0,
            completed_tasks=0,
            failed_tasks=0,
            cancelled_tasks=0,
            timeout_tasks=0,
            avg_duration_ms=0,
            total_tokens_used=0,
            error_rate=0,
            success_rate=0,
            last_activity=None,
        )

    return AgentMetricsResponse(**metrics.to_dict())


# ============================================================================
# TASK HISTORY ENDPOINTS
# ============================================================================


@router.get("/{agent_id}/history", response_model=AgentHistoryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_history",
    error_code_prefix="ANALYTICS_AGENTS",
)
async def get_agent_history(
    agent_id: str,
    limit: int = Query(default=100, ge=1, le=1000, description="Max records to return"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get task history for a specific agent.

    Returns recent tasks executed by this agent.

    Issue #744: Requires admin authentication.
    """
    analytics = get_agent_analytics()
    history = await analytics.get_agent_history(agent_id, limit)

    return {
        "agent_id": agent_id,
        "tasks": history,
        "count": len(history),
    }


@router.get("/tasks/recent", response_model=AgentRecentTasksResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_recent_tasks",
    error_code_prefix="ANALYTICS_AGENTS",
)
async def get_recent_tasks(
    limit: int = Query(default=100, ge=1, le=1000, description="Max records to return"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get recent tasks across all agents.

    Returns the most recent task executions.

    Issue #744: Requires admin authentication.
    """
    analytics = get_agent_analytics()
    tasks = await analytics.get_recent_tasks(limit)

    return {
        "tasks": tasks,
        "count": len(tasks),
    }


# ============================================================================
# AGENT COMPARISON ENDPOINTS
# ============================================================================


@router.get("/comparison", response_model=AgentComparisonResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="compare_agents",
    error_code_prefix="ANALYTICS_AGENTS",
)
async def compare_agents(
    agent_ids: str | None = Query(None, description="Comma-separated agent IDs to compare (all if not specified)"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Compare performance across agents.

    Returns rankings by success rate, speed, and volume.

    Issue #744: Requires admin authentication.
    """
    analytics = get_agent_analytics()

    ids_list = None
    if agent_ids:
        ids_list = [aid.strip() for aid in agent_ids.split(",")]

    comparison = await analytics.compare_agents(ids_list)

    return comparison


def _check_agent_metrics(metrics) -> list:
    """
    Check agent metrics and generate recommendations.

    (Issue #398: extracted helper)
    """
    recommendations = []

    if metrics.error_rate > 10:
        recommendations.append(
            {
                "type": "high_error_rate",
                "severity": "high" if metrics.error_rate > 25 else "medium",
                "message": f"Error rate of {metrics.error_rate:.1f}% exceeds threshold",
                "suggestion": "Review error logs and improve error handling",
            }
        )

    if metrics.avg_duration_ms > 30000:
        recommendations.append(
            {
                "type": "slow_performance",
                "severity": "medium",
                "message": f"Average duration of {metrics.avg_duration_ms/1000:.1f}s is high",
                "suggestion": "Consider optimizing task processing or increasing resources",
            }
        )

    if metrics.total_tasks > 10:
        timeout_rate = (metrics.timeout_tasks / metrics.total_tasks) * 100
        if timeout_rate > 5:
            recommendations.append(
                {
                    "type": "timeout_issues",
                    "severity": "high" if timeout_rate > 15 else "medium",
                    "message": f"Timeout rate of {timeout_rate:.1f}% indicates issues",
                    "suggestion": "Increase timeout limits or optimize long-running operations",
                }
            )

    if metrics.total_tasks > 0 and metrics.last_activity:
        from datetime import timedelta

        from autobot_shared.time_utils import now_utc, parse_utc_iso

        try:
            last = parse_utc_iso(metrics.last_activity)
            if now_utc() - last > timedelta(days=7):
                recommendations.append(
                    {
                        "type": "low_activity",
                        "severity": "low",
                        "message": "No activity in the last 7 days",
                        "suggestion": "Check if agent is properly configured and active",
                    }
                )
        except Exception as e:
            logger.debug("Invalid date format in activity check: %s", e)

    return recommendations


@router.get("/recommendations", response_model=AgentRecommendationsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_recommendations",
    error_code_prefix="ANALYTICS_AGENTS",
)
async def get_agent_recommendations(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get optimization recommendations for agents.

    Analyzes performance patterns and suggests improvements.

    (Issue #398: refactored to use extracted helpers)

    Issue #744: Requires admin authentication.
    """
    analytics = get_agent_analytics()
    metrics_list = await analytics.get_all_agents_metrics()

    recommendations = []

    for metrics in metrics_list:
        agent_recs = _check_agent_metrics(metrics)
        if agent_recs:
            recommendations.append(
                {
                    "agent_id": metrics.agent_id,
                    "agent_type": metrics.agent_type,
                    "recommendations": agent_recs,
                }
            )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda x: min(severity_order.get(r["severity"], 3) for r in x["recommendations"]))

    return {
        "recommendations": recommendations,
        "total_agents_analyzed": len(metrics_list),
        "agents_with_issues": len(recommendations),
    }


# ============================================================================
# PERFORMANCE TRENDS ENDPOINTS
# ============================================================================


@router.get("/trends", response_model=AgentPerformanceTrendsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_performance_trends",
    error_code_prefix="ANALYTICS_AGENTS",
)
async def get_performance_trends(
    agent_id: str | None = Query(None, description="Specific agent ID (all if not specified)"),
    days: int = Query(default=7, ge=1, le=90, description="Number of days to analyze"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get performance trends over time.

    Returns daily metrics showing performance changes.

    Issue #744: Requires admin authentication.
    """
    analytics = get_agent_analytics()
    trends = await analytics.get_performance_trends(agent_id, days)

    return trends


@router.get("/types", response_model=AgentTypesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_agent_types",
    error_code_prefix="ANALYTICS_AGENTS",
)
async def get_agent_types(
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get list of available agent types.

    Returns all defined agent type categories.

    Issue #744: Requires admin authentication.
    """
    return {
        "types": [t.value for t in AgentType],
        "statuses": [s.value for s in TaskStatus],
    }


# ============================================================================
# TASK TRACKING ENDPOINTS
# ============================================================================


@router.post("/tasks/start", response_model=AgentTaskStartResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="track_task_start",
    error_code_prefix="ANALYTICS_AGENTS",
)
async def track_task_start(
    request: TrackTaskRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Track the start of an agent task.

    Call this when an agent begins executing a task.

    Issue #744: Requires admin authentication.
    """
    analytics = get_agent_analytics()
    record = await analytics.track_task_start(
        agent_id=request.agent_id,
        agent_type=request.agent_type,
        task_id=request.task_id,
        task_name=request.task_name,
        input_size=request.input_size,
        metadata=request.metadata,
    )

    return {
        "status": "tracking",
        "task": record.to_dict(),
    }


@router.post("/tasks/complete", response_model=AgentTaskCompleteResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="track_task_complete",
    error_code_prefix="ANALYTICS_AGENTS",
)
async def track_task_complete(
    request: CompleteTaskRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Track task completion.

    Call this when an agent finishes executing a task.

    Issue #744: Requires admin authentication.
    """
    analytics = get_agent_analytics()

    # Map status string to enum
    try:
        status = TaskStatus(request.status)
    except ValueError:
        status = TaskStatus.COMPLETED if request.status == "success" else TaskStatus.FAILED

    record = await analytics.track_task_complete(
        task_id=request.task_id,
        status=status,
        output_size=request.output_size,
        tokens_used=request.tokens_used,
        error_message=request.error_message,
    )

    if record:
        return {
            "status": "completed",
            "task": record.to_dict(),
        }
    else:
        return {
            "status": "not_found",
            "message": f"Task {request.task_id} not found or already completed",
        }
