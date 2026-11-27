# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Technical Debt Calculator API Module (Issue #231)
Calculates technical debt in terms of time/cost and prioritizes fixes by ROI.

Features:
- Multi-factor debt calculation model
- Cost estimation based on developer rates
- ROI analysis for prioritization
- Trend tracking over time
- Actionable recommendations
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from api.analytics_debt_models import (
    DEBT_HOURS_ESTIMATE,
    SEVERITY_WEIGHTS,
    DebtCategory,
    DebtItem,
    DebtSeverity,
)
from api.analytics_debt_report import generate_markdown_report
from api.analytics_debt_store import (
    get_antipatterns_from_redis,
    get_debt_trend_data,
    get_latest_debt_data,
    get_problems_from_chromadb,
    store_debt_result,
)
from api.analytics_shared import no_data_response
from api.codebase_analytics.endpoints.shared import resolve_scan_root
from api.schemas_analytics import (
    AnalyticsDebtByCategoryResponse,
    AnalyticsDebtCalculateResponse,
    AnalyticsDebtReportResponse,
    AnalyticsDebtROIPrioritiesResponse,
    AnalyticsDebtSummaryResponse,
    AnalyticsDebtTrendsResponse,
    DebtCalculationRequest,
)
from api.schemas_common import DataResponse
from api.source_scope import SourceIdQuery, require_source_id
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["technical-debt", "analytics"])  # Prefix set in router_registry

async def calculate_debt_from_analysis(analysis_data: Dict[str, Any], hourly_rate: float = 75.0) -> Dict[str, Any]:
    """
    Calculate technical debt from codebase analysis data.
    Issue #281: Refactored from 163 lines to use extracted helper methods.

    Args:
        analysis_data: Data from codebase analytics
        hourly_rate: Developer hourly rate for cost calculation

    Returns:
        Comprehensive debt analysis
    """
    debt_items: List[DebtItem] = []

    # Process all data sources (Issue #281: uses helpers)
    debt_items.extend(_process_anti_patterns(analysis_data.get("anti_patterns", [])))
    debt_items.extend(_process_problems(analysis_data.get("problems", [])))
    debt_items.extend(_process_hardcodes(analysis_data.get("hardcodes", [])))
    debt_items.extend(_process_complexity(analysis_data.get("complexity", {})))

    # Calculate aggregations (Issue #281: uses helper)
    aggregations = _calculate_debt_aggregations(debt_items, hourly_rate)

    # Calculate ROI ranking (Issue #281: uses helper)
    roi_ranking = _calculate_roi_ranking(debt_items)

    return {
        "summary": {
            "total_items": len(debt_items),
            "total_hours": round(aggregations["total_hours"], 1),
            "total_cost_usd": round(aggregations["total_cost"], 2),
            "by_category": aggregations["by_category"],
            "by_severity": aggregations["by_severity"],
            "hourly_rate": hourly_rate,
        },
        "top_files": aggregations["top_files"],
        "roi_ranking": roi_ranking,
        "items": [item.to_dict() for item in debt_items],
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
    }


def _map_severity(severity_str: str) -> DebtSeverity:
    """Map string severity to enum"""
    mapping = {
        "critical": DebtSeverity.CRITICAL,
        "high": DebtSeverity.HIGH,
        "medium": DebtSeverity.MEDIUM,
        "low": DebtSeverity.LOW,
    }
    return mapping.get(severity_str.lower(), DebtSeverity.MEDIUM)


def _map_problem_to_category(problem_type: str) -> DebtCategory:
    """Map problem type to debt category"""
    mapping = {
        "long_function": DebtCategory.CODE_COMPLEXITY,
        "long_method": DebtCategory.CODE_COMPLEXITY,
        "god_class": DebtCategory.ANTI_PATTERNS,
        "duplicate_code": DebtCategory.CODE_DUPLICATION,
        "missing_docstring": DebtCategory.MISSING_DOCS,
        "debug_code": DebtCategory.DEAD_CODE,
        "security": DebtCategory.SECURITY_ISSUES,
        "performance": DebtCategory.PERFORMANCE_ISSUES,
    }
    return mapping.get(problem_type.lower(), DebtCategory.ANTI_PATTERNS)


def _get_fix_complexity(pattern_type: str | None) -> str:
    """Estimate fix complexity for a pattern type"""
    hard_patterns = {"god_class", "spaghetti_code", "circular_dependency"}
    medium_patterns = {"long_method", "feature_envy", "duplicate_code"}

    if pattern_type:
        pattern_lower = pattern_type.lower()
        if pattern_lower in hard_patterns:
            return "hard"
        if pattern_lower in medium_patterns:
            return "medium"
    return "easy"


def _get_business_impact(severity: DebtSeverity) -> str:
    """Map severity to business impact"""
    mapping = {
        DebtSeverity.CRITICAL: "high",
        DebtSeverity.HIGH: "high",
        DebtSeverity.MEDIUM: "medium",
        DebtSeverity.LOW: "low",
    }
    return mapping.get(severity, "medium")


# =============================================================================
# Issue #281: Helper functions for calculate_debt_from_analysis
# =============================================================================


def _process_anti_patterns(anti_patterns: List[Dict[str, Any]]) -> List[DebtItem]:
    """Process anti-patterns into debt items (Issue #281: extracted helper)."""
    debt_items = []
    for pattern in anti_patterns:
        severity = _map_severity(pattern.get("severity", "medium"))
        debt_items.append(
            DebtItem(
                category=DebtCategory.ANTI_PATTERNS,
                severity=severity,
                file_path=pattern.get("file_path", "unknown"),
                line_number=pattern.get("line_number"),
                description=pattern.get("description", "Anti-pattern detected"),
                estimated_hours=DEBT_HOURS_ESTIMATE[DebtCategory.ANTI_PATTERNS] * SEVERITY_WEIGHTS[severity],
                fix_complexity=_get_fix_complexity(pattern.get("type")),
                business_impact=_get_business_impact(severity),
                recommendation=pattern.get("recommendation", "Refactor to fix pattern"),
                tags=[pattern.get("type", "unknown")],
            )
        )
    return debt_items


def _process_problems(problems: List[Dict[str, Any]]) -> List[DebtItem]:
    """Process code problems into debt items (Issue #281: extracted helper)."""
    debt_items = []
    for problem in problems:
        category = _map_problem_to_category(problem.get("type", ""))
        severity = _map_severity(problem.get("severity", "medium"))
        debt_items.append(
            DebtItem(
                category=category,
                severity=severity,
                file_path=problem.get("file_path", "unknown"),
                line_number=problem.get("line_number"),
                description=problem.get("description", "Code issue detected"),
                estimated_hours=DEBT_HOURS_ESTIMATE.get(category, 1.0) * SEVERITY_WEIGHTS[severity],
                fix_complexity=problem.get("fix_complexity", "medium"),
                business_impact=_get_business_impact(severity),
                recommendation=problem.get("suggestion", "Fix the issue"),
                tags=[problem.get("type", "unknown")],
            )
        )
    return debt_items


def _process_hardcodes(hardcodes: List[Dict[str, Any]]) -> List[DebtItem]:
    """Process hardcoded values into debt items (Issue #281: extracted helper)."""
    debt_items = []
    for hardcode in hardcodes:
        debt_items.append(
            DebtItem(
                category=DebtCategory.HARDCODED_VALUES,
                severity=DebtSeverity.MEDIUM,
                file_path=hardcode.get("file_path", "unknown"),
                line_number=hardcode.get("line"),
                description=f"Hardcoded {hardcode.get('type', 'value')}: {hardcode.get('value', '')}",
                estimated_hours=DEBT_HOURS_ESTIMATE[DebtCategory.HARDCODED_VALUES],
                fix_complexity="easy",
                business_impact="low",
                recommendation="Extract to configuration or constants",
                tags=[hardcode.get("type", "unknown")],
            )
        )
    return debt_items


def _process_complexity(complexity_data: Dict[str, Any]) -> List[DebtItem]:
    """Process complexity issues into debt items (Issue #281: extracted helper)."""
    debt_items = []
    for file_path, complexity in complexity_data.items():
        if complexity > 10:
            severity = (
                DebtSeverity.CRITICAL
                if complexity > 20
                else DebtSeverity.HIGH if complexity > 15 else DebtSeverity.MEDIUM
            )
            debt_items.append(
                DebtItem(
                    category=DebtCategory.CODE_COMPLEXITY,
                    severity=severity,
                    file_path=file_path,
                    line_number=None,
                    description=f"High cyclomatic complexity: {complexity}",
                    estimated_hours=DEBT_HOURS_ESTIMATE[DebtCategory.CODE_COMPLEXITY] * SEVERITY_WEIGHTS[severity],
                    fix_complexity="hard",
                    business_impact=_get_business_impact(severity),
                    recommendation="Refactor into smaller, focused functions",
                    tags=["complexity", "refactoring"],
                )
            )
    return debt_items


def _calculate_debt_aggregations(debt_items: List[DebtItem], hourly_rate: float) -> Dict[str, Any]:
    """Calculate totals, category/severity groupings, and top files (Issue #281: extracted)."""
    total_hours = sum(item.estimated_hours for item in debt_items)
    total_cost = total_hours * hourly_rate

    # Group by category
    by_category: Dict[str, int] = {}
    for item in debt_items:
        cat = item.category.value
        by_category[cat] = by_category.get(cat, 0) + 1

    # Group by severity
    by_severity: Dict[str, int] = {}
    for item in debt_items:
        sev = item.severity.value
        by_severity[sev] = by_severity.get(sev, 0) + 1

    # Find top files by debt
    file_debt: Dict[str, float] = {}
    for item in debt_items:
        file_debt[item.file_path] = file_debt.get(item.file_path, 0) + item.estimated_hours

    top_files = sorted(
        [{"file": f, "hours": h, "cost_usd": h * hourly_rate} for f, h in file_debt.items()],
        key=lambda x: x["hours"],
        reverse=True,
    )[:10]

    return {
        "total_hours": total_hours,
        "total_cost": total_cost,
        "by_category": by_category,
        "by_severity": by_severity,
        "top_files": top_files,
    }


def _calculate_roi_ranking(debt_items: List[DebtItem]) -> List[Dict[str, Any]]:
    """Calculate ROI ranking for debt items (Issue #281: extracted helper)."""
    roi_items = []
    for item in debt_items:
        # ROI = impact / effort
        impact_score = {"high": 3, "medium": 2, "low": 1}.get(item.business_impact, 1)
        effort_score = {"easy": 1, "medium": 2, "hard": 3}.get(item.fix_complexity, 2)
        roi = impact_score / effort_score

        roi_items.append(
            {
                "file_path": item.file_path,
                "category": item.category.value,
                "description": item.description[:100],
                "roi_score": round(roi, 2),
                "estimated_hours": item.estimated_hours,
                "fix_complexity": item.fix_complexity,
                "business_impact": item.business_impact,
            }
        )

    # Sort by ROI (highest first)
    return sorted(roi_items, key=lambda x: x["roi_score"], reverse=True)[:20]


async def _require_scoped_source(source_id: str) -> str:
    """The validated source id, once it resolves to a checkout (#22198); never the install tree."""
    await resolve_scan_root(require_source_id(source_id, "technical-debt request"))
    return source_id


@router.post("/calculate", response_model=DataResponse[AnalyticsDebtCalculateResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="calculate_technical_debt",
    error_code_prefix="ANALYTICS_DEBT",
)
async def calculate_technical_debt(
    request: DebtCalculationRequest,
    source_id: SourceIdQuery,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Calculate technical debt for the codebase (Issue #315 - refactored).
    Issue #744: Requires admin authentication.

    Analyzes code quality issues and estimates remediation cost.
    """
    await _require_scoped_source(source_id)
    try:
        from api.codebase_analytics import get_code_collection, get_redis_connection

        code_collection = get_code_collection()
        redis_client = await get_redis_connection()

        analysis_data = {
            "anti_patterns": await get_antipatterns_from_redis(redis_client, source_id),
            "problems": get_problems_from_chromadb(code_collection, source_id),
            "hardcodes": [],
            "complexity": {},
        }

        debt_result = await calculate_debt_from_analysis(analysis_data, request.hourly_rate)
        store_debt_result(debt_result, source_id)

        return JSONResponse(
            {
                "status": "success",
                "data": debt_result,
                "target_path": request.target_path,
            }
        )

    except Exception as e:
        logger.error("Debt calculation failed: %s", e)
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": "Internal server error"},
        )


@router.get("/summary", response_model=DataResponse[AnalyticsDebtSummaryResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_debt_summary",
    error_code_prefix="ANALYTICS_DEBT",
)
async def get_debt_summary(source_id: SourceIdQuery, admin_check: bool = Depends(check_admin_permission)):
    """
    Get summary of current technical debt (Issue #543 - refactored).
    Issue #744: Requires admin authentication.

    Returns high-level metrics for dashboard display.
    """
    await _require_scoped_source(source_id)
    data = get_latest_debt_data(source_id)

    if data:
        return JSONResponse(
            {
                "status": "success",
                "summary": data.get("summary", {}),
                "top_files": data.get("top_files", [])[:5],
                "roi_ranking": data.get("roi_ranking", [])[:5],
                "timestamp": data.get("timestamp"),
            }
        )

    # Return no_data response if no analysis exists (Issue #543)
    return JSONResponse(
        no_data_response(
            "No debt analysis found. Run POST /calculate first.",
            summary={},
            items=[],
            total_hours=0,
        )
    )


@router.get("/by-category/{category}", response_model=DataResponse[AnalyticsDebtByCategoryResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_debt_by_category",
    error_code_prefix="ANALYTICS_DEBT",
)
async def get_debt_by_category(
    category: str, source_id: SourceIdQuery, admin_check: bool = Depends(check_admin_permission)
):
    """
    Get technical debt items filtered by category (Issue #315 - refactored).
    Issue #744: Requires admin authentication.

    Args:
        category: Debt category to filter by
    """
    await _require_scoped_source(source_id)
    data = get_latest_debt_data(source_id)

    if data:
        items = [item for item in data.get("items", []) if item.get("category") == category]
        return JSONResponse(
            {
                "status": "success",
                "category": category,
                "items": items,
                "count": len(items),
            }
        )

    return JSONResponse({"status": "no_data", "message": "No debt analysis found", "items": []})


def _calculate_trend_change(trend_data: List[Dict[str, Any]]) -> tuple:
    """Calculate trend change direction (Issue #315 - extracted helper)."""
    if len(trend_data) < 2:
        return {"items": 0, "hours": 0, "cost": 0}, "unknown"

    first, last = trend_data[0], trend_data[-1]
    change = {
        "items": last["total_items"] - first["total_items"],
        "hours": round(last["total_hours"] - first["total_hours"], 1),
        "cost": round(last["total_cost_usd"] - first["total_cost_usd"], 2),
    }
    direction = "improving" if change["items"] < 0 else "worsening" if change["items"] > 0 else "stable"
    return change, direction


@router.get("/trends", response_model=DataResponse[AnalyticsDebtTrendsResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_debt_trends",
    error_code_prefix="ANALYTICS_DEBT",
)
async def get_debt_trends(
    source_id: SourceIdQuery,
    days: int = Query(default=30, ge=1, le=365),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get technical debt trends over time (Issue #315 - refactored).
    Issue #744: Requires admin authentication.

    Shows how debt has changed over the specified period.
    """
    await _require_scoped_source(source_id)
    trend_data = get_debt_trend_data(source_id)
    trend_data.sort(key=lambda x: x.get("timestamp", ""))

    change, direction = _calculate_trend_change(trend_data)

    return JSONResponse(
        {
            "status": "success",
            "trends": trend_data,
            "data_points": len(trend_data),
            "change": change,
            "direction": direction,
        }
    )


@router.get("/roi-priorities", response_model=DataResponse[AnalyticsDebtROIPrioritiesResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_roi_priorities",
    error_code_prefix="ANALYTICS_DEBT",
)
async def get_roi_priorities(
    source_id: SourceIdQuery,
    limit: int = Query(default=20, ge=1, le=100),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get debt items prioritized by ROI (Issue #315 - refactored).
    Issue #744: Requires admin authentication.

    Quick wins (high impact, low effort) are ranked first.
    """
    await _require_scoped_source(source_id)
    data = get_latest_debt_data(source_id)

    if data:
        roi_ranking = data.get("roi_ranking", [])
        return JSONResponse(
            {
                "status": "success",
                "priorities": roi_ranking[:limit],
                "total_available": len(roi_ranking),
            }
        )

    return JSONResponse({"status": "no_data", "message": "No debt analysis found", "priorities": []})


@router.get("/report", response_model=DataResponse[AnalyticsDebtReportResponse])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_debt_report",
    error_code_prefix="ANALYTICS_DEBT",
)
async def get_debt_report(
    source_id: SourceIdQuery,
    format: str = Query(default="json", description="json or markdown"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Generate a comprehensive debt report (Issue #398: refactored).
    Issue #744: Requires admin authentication.
    """
    await _require_scoped_source(source_id)
    debt_data = get_latest_debt_data(source_id)

    if not debt_data:
        return JSONResponse(
            {
                "status": "no_data",
                "message": "No debt analysis found. Run POST /calculate first.",
            }
        )

    if format == "markdown":
        return JSONResponse(
            {
                "status": "success",
                "format": "markdown",
                "report": generate_markdown_report(debt_data),
            }
        )

    return JSONResponse({"status": "success", "format": "json", "data": debt_data})
