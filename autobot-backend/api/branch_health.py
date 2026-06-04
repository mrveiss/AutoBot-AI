# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Branch Health Monitoring API (Issue #4112).

Exposes branch health metrics including divergence, staleness,
and file conflict density for branch management and alerts.
"""

from typing import List

from fastapi import APIRouter, Depends

from api.schemas_system import BranchDivergenceResponse, BranchHealthResponse
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from utils.branch_metrics import BranchMetrics, BranchMetricsCollector

router = APIRouter(
    tags=["branch_health", "monitoring"],
    dependencies=[Depends(check_admin_permission)],
)
logger = get_logger(__name__)


@router.get("/branch-health/all", response_model=List[BranchHealthResponse])
@with_error_handling(
    category=ErrorCategory.INFRASTRUCTURE,
    operation="get_all_branch_health",
    error_code_prefix="BRANCH_HEALTH",
)
async def get_all_branch_health(
    repo_path: str | None = None,
    base_branch: str = "Dev_new_gui",
) -> List[BranchHealthResponse]:
    """
    Get health metrics for all branches.

    Returns branches sorted by health score (worst first).
    Requires admin permission.

    Args:
        repo_path: Git repository path (defaults to AUTOBOT_CODE_SOURCE env var)
        base_branch: Base branch for divergence calculation

    Returns:
        List of branch health metrics
    """
    resolved_path = repo_path if repo_path is not None else str(config.path.code_source_path)
    collector = BranchMetricsCollector(resolved_path, base_branch)
    metrics = await collector.analyze_all_branches()

    return [_metrics_to_response(m) for m in metrics]


@router.get("/branch-health/unhealthy", response_model=List[BranchHealthResponse])
@with_error_handling(
    category=ErrorCategory.INFRASTRUCTURE,
    operation="get_unhealthy_branch_health",
    error_code_prefix="BRANCH_HEALTH",
)
async def get_unhealthy_branch_health(
    repo_path: str | None = None,
    base_branch: str = "Dev_new_gui",
    threshold: float = 50.0,
) -> List[BranchHealthResponse]:
    """
    Get branches with health scores below threshold.

    Useful for identifying branches needing intervention.
    Requires admin permission.

    Args:
        repo_path: Git repository path (defaults to AUTOBOT_CODE_SOURCE env var)
        base_branch: Base branch for divergence calculation
        threshold: Health score threshold (0-100, default 50)

    Returns:
        List of unhealthy branches
    """
    resolved_path = repo_path if repo_path is not None else str(config.path.code_source_path)
    collector = BranchMetricsCollector(resolved_path, base_branch)
    all_metrics = await collector.analyze_all_branches()

    unhealthy = [m for m in all_metrics if m.health_score < threshold]

    return [_metrics_to_response(m) for m in unhealthy]


@router.get("/branch-health/diverged", response_model=List[BranchHealthResponse])
@with_error_handling(
    category=ErrorCategory.INFRASTRUCTURE,
    operation="get_diverged_branch_health",
    error_code_prefix="BRANCH_HEALTH",
)
async def get_diverged_branch_health(
    repo_path: str | None = None,
    base_branch: str = "Dev_new_gui",
    threshold: int = 20,
) -> List[BranchHealthResponse]:
    """
    Get branches with high divergence from base.

    Identifies branches that may have merge conflicts.
    Requires admin permission.

    Args:
        repo_path: Git repository path (defaults to AUTOBOT_CODE_SOURCE env var)
        base_branch: Base branch for divergence calculation
        threshold: Minimum commits diverged (default 20)

    Returns:
        List of highly diverged branches sorted by divergence
    """
    resolved_path = repo_path if repo_path is not None else str(config.path.code_source_path)
    collector = BranchMetricsCollector(resolved_path, base_branch)
    all_metrics = await collector.analyze_all_branches()

    diverged = [m for m in all_metrics if m.divergence.total_commits_diverged > threshold]
    diverged.sort(key=lambda m: m.divergence.total_commits_diverged, reverse=True)

    return [_metrics_to_response(m) for m in diverged]


@router.get("/branch-health/stale", response_model=List[BranchHealthResponse])
@with_error_handling(
    category=ErrorCategory.INFRASTRUCTURE,
    operation="get_stale_branch_health",
    error_code_prefix="BRANCH_HEALTH",
)
async def get_stale_branch_health(
    repo_path: str | None = None,
    base_branch: str = "Dev_new_gui",
    threshold_days: int = 30,
) -> List[BranchHealthResponse]:
    """
    Get branches with no activity for more than threshold days.

    Useful for identifying abandoned branches.
    Requires admin permission.

    Args:
        repo_path: Git repository path (defaults to AUTOBOT_CODE_SOURCE env var)
        base_branch: Base branch for divergence calculation
        threshold_days: Staleness threshold in days (default 30)

    Returns:
        List of stale branches sorted by age (oldest first)
    """
    resolved_path = repo_path if repo_path is not None else str(config.path.code_source_path)
    collector = BranchMetricsCollector(resolved_path, base_branch, threshold_days)
    all_metrics = await collector.analyze_all_branches()

    stale = [m for m in all_metrics if m.is_stale]
    stale.sort(key=lambda m: m.days_since_activity, reverse=True)

    return [_metrics_to_response(m) for m in stale]


def _metrics_to_response(metrics: BranchMetrics) -> BranchHealthResponse:
    """Convert internal BranchMetrics to API response."""
    return BranchHealthResponse(
        branch=metrics.branch,
        divergence=BranchDivergenceResponse(
            branch=metrics.divergence.branch,
            ahead=metrics.divergence.ahead,
            behind=metrics.divergence.behind,
            total_commits_diverged=metrics.divergence.total_commits_diverged,
            conflicting_files=metrics.divergence.conflicting_files,
        ),
        days_since_activity=metrics.days_since_activity,
        is_stale=metrics.is_stale,
        health_score=round(metrics.health_score, 2),
        last_activity=(metrics.last_activity.isoformat() if metrics.last_activity else None),
    )
