# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.auth_middleware import check_admin_permission
from src.utils.error_boundaries import ErrorCategory, with_error_handling
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
router = APIRouter(
    tags=["technical-debt", "analytics"]
)  # Prefix set in router_registry

# Redis key prefix
DEBT_PREFIX = "debt:"


def _no_data_response(
    message: str = "No technical debt analysis data. Run codebase indexing first.",
) -> dict:
    """
    Standardized no-data response for debt analytics (Issue #543).

    Args:
        message: Custom message explaining why no data is available

    Returns:
        Dictionary with no_data status and empty structures
    """
    return {
        "status": "no_data",
        "message": message,
        "summary": {},
        "items": [],
        "total_hours": 0,
    }


class DebtCategory(str, Enum):
    """Categories of technical debt"""

    CODE_COMPLEXITY = "code_complexity"
    CODE_DUPLICATION = "code_duplication"
    MISSING_TESTS = "missing_tests"
    MISSING_DOCS = "missing_docs"
    ANTI_PATTERNS = "anti_patterns"
    SECURITY_ISSUES = "security_issues"
    PERFORMANCE_ISSUES = "performance_issues"
    OUTDATED_DEPS = "outdated_dependencies"
    HARDCODED_VALUES = "hardcoded_values"
    DEAD_CODE = "dead_code"


class DebtSeverity(str, Enum):
    """Severity levels for debt items"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class DebtItem:
    """Individual technical debt item"""

    category: DebtCategory
    severity: DebtSeverity
    file_path: str
    line_number: Optional[int]
    description: str
    estimated_hours: float
    fix_complexity: str  # easy, medium, hard
    business_impact: str  # high, medium, low
    recommendation: str
    tags: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert technical debt item to serializable dictionary."""
        return {
            "category": self.category.value,
            "severity": self.severity.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "description": self.description,
            "estimated_hours": self.estimated_hours,
            "fix_complexity": self.fix_complexity,
            "business_impact": self.business_impact,
            "recommendation": self.recommendation,
            "tags": self.tags,
        }


class DebtCalculationRequest(BaseModel):
    """Request for debt calculation"""

    target_path: str = Field(default=".", description="Path to analyze")
    hourly_rate: float = Field(default=75.0, description="Developer hourly rate in USD")
    include_categories: List[str] = Field(
        default=[], description="Categories to include (empty = all)"
    )


class DebtSummary(BaseModel):
    """Summary of technical debt"""

    total_items: int
    total_hours: float
    total_cost_usd: float
    by_category: Dict[str, int]
    by_severity: Dict[str, int]
    top_files: List[Dict[str, Any]]
    roi_ranking: List[Dict[str, Any]]
    timestamp: str


# Debt calculation weights
SEVERITY_WEIGHTS = {
    DebtSeverity.CRITICAL: 4.0,
    DebtSeverity.HIGH: 2.0,
    DebtSeverity.MEDIUM: 1.0,
    DebtSeverity.LOW: 0.5,
}

# Estimated hours per debt type
DEBT_HOURS_ESTIMATE = {
    DebtCategory.CODE_COMPLEXITY: 2.0,
    DebtCategory.CODE_DUPLICATION: 1.5,
    DebtCategory.MISSING_TESTS: 1.0,
    DebtCategory.MISSING_DOCS: 0.5,
    DebtCategory.ANTI_PATTERNS: 3.0,
    DebtCategory.SECURITY_ISSUES: 4.0,
    DebtCategory.PERFORMANCE_ISSUES: 2.5,
    DebtCategory.OUTDATED_DEPS: 1.0,
    DebtCategory.HARDCODED_VALUES: 0.5,
    DebtCategory.DEAD_CODE: 0.5,
}


def get_debt_redis():
    """Get Redis client for debt data storage"""
    return get_redis_client(database="analytics")


async def calculate_debt_from_analysis(
    analysis_data: Dict[str, Any], hourly_rate: float = 75.0
) -> Dict[str, Any]:
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
        "timestamp": datetime.now().isoformat(),
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


def _get_fix_complexity(pattern_type: Optional[str]) -> str:
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
                estimated_hours=DEBT_HOURS_ESTIMATE[DebtCategory.ANTI_PATTERNS]
                * SEVERITY_WEIGHTS[severity],
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
                estimated_hours=DEBT_HOURS_ESTIMATE.get(category, 1.0)
                * SEVERITY_WEIGHTS[severity],
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
                else DebtSeverity.HIGH
                if complexity > 15
                else DebtSeverity.MEDIUM
            )
            debt_items.append(
                DebtItem(
                    category=DebtCategory.CODE_COMPLEXITY,
                    severity=severity,
                    file_path=file_path,
                    line_number=None,
                    description=f"High cyclomatic complexity: {complexity}",
                    estimated_hours=DEBT_HOURS_ESTIMATE[DebtCategory.CODE_COMPLEXITY]
                    * SEVERITY_WEIGHTS[severity],
                    fix_complexity="hard",
                    business_impact=_get_business_impact(severity),
                    recommendation="Refactor into smaller, focused functions",
                    tags=["complexity", "refactoring"],
                )
            )
    return debt_items


def _calculate_debt_aggregations(
    debt_items: List[DebtItem], hourly_rate: float
) -> Dict[str, Any]:
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
        file_debt[item.file_path] = (
            file_debt.get(item.file_path, 0) + item.estimated_hours
        )

    top_files = sorted(
        [
            {"file": f, "hours": h, "cost_usd": h * hourly_rate}
            for f, h in file_debt.items()
        ],
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


def _extract_problem_from_meta(meta: Dict[str, Any]) -> Dict[str, Any]:
    """Extract problem data from metadata (Issue #315 - extracted helper)."""
    return {
        "type": meta.get("problem_type", "unknown"),
        "severity": meta.get("severity", "medium"),
        "file_path": meta.get("file_path", "unknown"),
        "line_number": (
            int(meta.get("line_number", 0)) if meta.get("line_number") else None
        ),
        "description": meta.get("description", ""),
        "suggestion": meta.get("suggestion", ""),
    }


def _get_problems_from_chromadb(code_collection) -> List[Dict[str, Any]]:
    """Get problems from ChromaDB collection (Issue #315 - extracted helper)."""
    if not code_collection:
        return []
    try:
        problems_result = code_collection.get(
            where={"type": "problem"}, include=["metadatas"]
        )
        if not problems_result.get("metadatas"):
            return []
        return [
            _extract_problem_from_meta(meta) for meta in problems_result["metadatas"]
        ]
    except Exception as e:
        logger.warning("ChromaDB query failed: %s", e)
        return []


async def _get_antipatterns_from_redis(redis_client) -> List[Dict[str, Any]]:
    """Get anti-patterns from Redis (Issue #315 - extracted helper)."""
    if not redis_client:
        return []
    try:
        # Issue #361 - avoid blocking
        ap_data = await asyncio.to_thread(
            redis_client.get, "antipattern:latest_results"
        )
        if not ap_data:
            return []
        if isinstance(ap_data, bytes):
            ap_data = ap_data.decode("utf-8")
        ap_results = json.loads(ap_data)
        return ap_results.get("anti_patterns", [])
    except Exception as e:
        logger.warning("Redis anti-pattern fetch failed: %s", e)
        return []


def _store_debt_result(debt_result: Dict[str, Any]) -> None:
    """Store debt calculation result in Redis (Issue #315 - extracted helper)."""
    debt_redis = get_debt_redis()
    if not debt_redis:
        return
    try:
        key = f"{DEBT_PREFIX}calculation:{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        debt_redis.set(key, json.dumps(debt_result), ex=86400 * 30)  # Keep 30 days
        debt_redis.set(f"{DEBT_PREFIX}latest", key)
    except Exception as e:
        logger.warning("Failed to store debt calculation: %s", e)


def _decode_redis_value(value: Any) -> Optional[str]:
    """Decode Redis value to string if bytes (Issue #315 - extracted helper)."""
    if value is None:
        return None
    return value.decode("utf-8") if isinstance(value, bytes) else value


def _get_latest_debt_data() -> Optional[Dict[str, Any]]:
    """Get latest debt data from Redis (Issue #315 - extracted helper)."""
    redis_client = get_debt_redis()
    if not redis_client:
        return None
    try:
        latest_key = _decode_redis_value(redis_client.get(f"{DEBT_PREFIX}latest"))
        if not latest_key:
            return None
        debt_data = _decode_redis_value(redis_client.get(latest_key))
        if not debt_data:
            return None
        return json.loads(debt_data)
    except Exception as e:
        logger.warning("Redis fetch failed: %s", e)
        return None


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="calculate_debt",
    error_code_prefix="DEBT",
)
@router.post("/calculate")
async def calculate_technical_debt(
    request: DebtCalculationRequest, admin_check: bool = Depends(check_admin_permission)
):
    """
    Calculate technical debt for the codebase (Issue #315 - refactored).
    Issue #744: Requires admin authentication.

    Analyzes code quality issues and estimates remediation cost.
    """
    try:
        from backend.api.codebase_analytics import (
            get_code_collection,
            get_redis_connection,
        )

        code_collection = get_code_collection()
        redis_client = await get_redis_connection()

        analysis_data = {
            "anti_patterns": await _get_antipatterns_from_redis(redis_client),
            "problems": _get_problems_from_chromadb(code_collection),
            "hardcodes": [],
            "complexity": {},
        }

        debt_result = await calculate_debt_from_analysis(
            analysis_data, request.hourly_rate
        )
        _store_debt_result(debt_result)

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
            status_code=500, content={"status": "error", "message": str(e)}
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_debt_summary",
    error_code_prefix="DEBT",
)
@router.get("/summary")
async def get_debt_summary(admin_check: bool = Depends(check_admin_permission)):
    """
    Get summary of current technical debt (Issue #543 - refactored).
    Issue #744: Requires admin authentication.

    Returns high-level metrics for dashboard display.
    """
    data = _get_latest_debt_data()

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
        _no_data_response("No debt analysis found. Run POST /calculate first.")
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_debt_by_category",
    error_code_prefix="DEBT",
)
@router.get("/by-category/{category}")
async def get_debt_by_category(
    category: str, admin_check: bool = Depends(check_admin_permission)
):
    """
    Get technical debt items filtered by category (Issue #315 - refactored).
    Issue #744: Requires admin authentication.

    Args:
        category: Debt category to filter by
    """
    data = _get_latest_debt_data()

    if data:
        items = [
            item for item in data.get("items", []) if item.get("category") == category
        ]
        return JSONResponse(
            {
                "status": "success",
                "category": category,
                "items": items,
                "count": len(items),
            }
        )

    return JSONResponse(
        {"status": "no_data", "message": "No debt analysis found", "items": []}
    )


def _get_debt_trend_data() -> List[Dict[str, Any]]:
    """Get historical debt trend data from Redis.

    Issue #315: Extracted helper.
    Issue #561: Fixed N+1 query pattern - now uses pipeline batching.
    """
    redis_client = get_debt_redis()
    if not redis_client:
        return []

    trend_data = []
    try:
        # Issue #561: Collect all keys first, then batch fetch with pipeline
        keys = []
        for key in redis_client.scan_iter(match=f"{DEBT_PREFIX}calculation:*"):
            keys.append(_decode_redis_value(key))

        if not keys:
            return []

        # Batch fetch all values using pipeline (eliminates N+1 pattern)
        pipe = redis_client.pipeline()
        for key_str in keys:
            pipe.get(key_str)
        results = pipe.execute()

        for data in results:
            if not data:
                continue
            data_str = _decode_redis_value(data)
            calc = json.loads(data_str)
            summary = calc.get("summary", {})
            trend_data.append(
                {
                    "timestamp": calc.get("timestamp"),
                    "total_items": summary.get("total_items", 0),
                    "total_hours": summary.get("total_hours", 0),
                    "total_cost_usd": summary.get("total_cost_usd", 0),
                }
            )
    except Exception as e:
        logger.warning("Redis trend fetch failed: %s", e)
    return trend_data


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
    direction = (
        "improving"
        if change["items"] < 0
        else "worsening"
        if change["items"] > 0
        else "stable"
    )
    return change, direction


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_debt_trends",
    error_code_prefix="DEBT",
)
@router.get("/trends")
async def get_debt_trends(
    days: int = Query(default=30, ge=1, le=365),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get technical debt trends over time (Issue #315 - refactored).
    Issue #744: Requires admin authentication.

    Shows how debt has changed over the specified period.
    """
    trend_data = _get_debt_trend_data()
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_roi_priorities",
    error_code_prefix="DEBT",
)
@router.get("/roi-priorities")
async def get_roi_priorities(
    limit: int = Query(default=20, ge=1, le=100),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get debt items prioritized by ROI (Issue #315 - refactored).
    Issue #744: Requires admin authentication.

    Quick wins (high impact, low effort) are ranked first.
    """
    data = _get_latest_debt_data()

    if data:
        roi_ranking = data.get("roi_ranking", [])
        return JSONResponse(
            {
                "status": "success",
                "priorities": roi_ranking[:limit],
                "total_available": len(roi_ranking),
            }
        )

    return JSONResponse(
        {"status": "no_data", "message": "No debt analysis found", "priorities": []}
    )


def _build_debt_executive_summary(debt_data: dict) -> str:
    """Build executive summary section of report (Issue #398: extracted)."""
    summary = debt_data.get("summary", {})
    return f"""# Technical Debt Report

**Generated:** {debt_data.get('timestamp', 'N/A')}

## Executive Summary

| Metric | Value |
|--------|-------|
| Total Debt Items | {summary.get('total_items', 0)} |
| Estimated Hours | {summary.get('total_hours', 0):.1f} |
| Estimated Cost | ${summary.get('total_cost_usd', 0):,.2f} |
| Hourly Rate Used | ${summary.get('hourly_rate', 75)}/hr |
"""


def _build_debt_tables(debt_data: dict) -> str:
    """Build severity, category, files, and ROI tables (Issue #398: extracted)."""
    summary = debt_data.get("summary", {})

    # Severity section
    severity_rows = [
        f"| {sev.capitalize()} | {count} |"
        for sev, count in summary.get("by_severity", {}).items()
    ]
    result = (
        "\n## Debt by Severity\n\n| Severity | Count |\n|----------|-------|\n"
        + "\n".join(severity_rows)
        + "\n"
    )

    # Category section
    category_rows = [
        f"| {cat.replace('_', ' ').title()} | {count} |"
        for cat, count in summary.get("by_category", {}).items()
    ]
    result += (
        "\n## Debt by Category\n\n| Category | Count |\n|----------|-------|\n"
        + "\n".join(category_rows)
        + "\n"
    )

    # Top files section
    file_rows = [
        f"| {f.get('file', 'unknown')[-50:]} | {f.get('hours', 0):.1f} | ${f.get('cost_usd', 0):.2f} |"
        for f in debt_data.get("top_files", [])[:10]
    ]
    result += (
        "\n## Top Files by Debt\n\n| File | Hours | Cost |\n|------|-------|------|\n"
        + "\n".join(file_rows)
        + "\n"
    )

    # ROI priorities section
    roi_rows = []
    for item in debt_data.get("roi_ranking", [])[:10]:
        desc = item.get("description", "")[:40]
        roi = item.get("roi_score", 0)
        hours = item.get("estimated_hours", 0)
        complexity = item.get("fix_complexity", "unknown")
        roi_rows.append(f"| {desc}... | {roi} | {hours:.1f} | {complexity} |")
    result += (
        "\n## Top ROI Priorities (Quick Wins)\n\n"
        "| Description | ROI | Hours | Complexity |\n"
        "|-------------|-----|-------|------------|\n" + "\n".join(roi_rows) + "\n"
    )

    return result


def _build_debt_recommendations() -> str:
    """Build recommendations section (Issue #398: extracted)."""
    return """
## Recommendations

1. **Start with Quick Wins**: Address items with high ROI scores first
2. **Focus on Critical Issues**: Prioritize critical severity items
3. **Track Progress**: Run debt calculation regularly to monitor trends
4. **Set Targets**: Aim to reduce total debt hours by 10% per sprint
"""


def _generate_markdown_report(debt_data: dict) -> str:
    """Generate complete markdown debt report (Issue #398: extracted)."""
    return (
        _build_debt_executive_summary(debt_data)
        + _build_debt_tables(debt_data)
        + _build_debt_recommendations()
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_debt_report",
    error_code_prefix="DEBT",
)
@router.get("/report")
async def get_debt_report(
    format: str = Query(default="json", description="json or markdown"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Generate a comprehensive debt report (Issue #398: refactored).
    Issue #744: Requires admin authentication.
    """
    debt_data = _get_latest_debt_data()

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
                "report": _generate_markdown_report(debt_data),
            }
        )

    return JSONResponse({"status": "success", "format": "json", "data": debt_data})
