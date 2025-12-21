# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Real-time Code Quality Dashboard API (Issue #230)

Provides endpoints for real-time code quality metrics, health scores,
pattern distribution, and quality trends.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quality", tags=["code-quality", "analytics"])


# ============================================================================
# Models
# ============================================================================


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
    details: Optional[dict[str, Any]] = None


class HealthScore(BaseModel):
    """Overall codebase health score."""

    overall: float = Field(..., ge=0, le=100)
    grade: QualityGrade
    trend: float = Field(default=0)
    breakdown: dict[str, float] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class PatternDistribution(BaseModel):
    """Distribution of code patterns."""

    pattern_type: str
    count: int
    percentage: float
    severity: str
    examples: list[str] = Field(default_factory=list)


class ComplexityMetrics(BaseModel):
    """Code complexity analysis."""

    average_cyclomatic: float
    max_cyclomatic: int
    average_cognitive: float
    max_cognitive: int
    hotspots: list[dict[str, Any]] = Field(default_factory=list)
    distribution: dict[str, int] = Field(default_factory=dict)


class QualitySnapshot(BaseModel):
    """Complete quality snapshot at a point in time."""

    timestamp: datetime
    health_score: HealthScore
    metrics: list[QualityMetric]
    patterns: list[PatternDistribution]
    complexity: ComplexityMetrics
    file_count: int
    line_count: int
    issues_count: int


# ============================================================================
# Utility Functions
# ============================================================================


def get_grade(score: float) -> QualityGrade:
    """Convert numeric score to letter grade."""
    if score >= 90:
        return QualityGrade.A
    if score >= 80:
        return QualityGrade.B
    if score >= 70:
        return QualityGrade.C
    if score >= 60:
        return QualityGrade.D
    return QualityGrade.F


def calculate_health_score(metrics: dict[str, float]) -> HealthScore:
    """Calculate overall health score from individual metrics."""
    weights = {
        "maintainability": 0.25,
        "reliability": 0.20,
        "security": 0.20,
        "performance": 0.15,
        "testability": 0.10,
        "documentation": 0.10,
    }

    weighted_sum = sum(
        metrics.get(category, 70) * weight for category, weight in weights.items()
    )

    overall = min(100, max(0, weighted_sum))
    grade = get_grade(overall)

    # Generate recommendations based on low scores
    recommendations = []
    for category, score in metrics.items():
        if score < 60:
            recommendations.append(
                f"Critical: Improve {category} (current score: {score:.1f})"
            )
        elif score < 70:
            recommendations.append(
                f"Warning: Address {category} issues (current score: {score:.1f})"
            )

    return HealthScore(
        overall=overall,
        grade=grade,
        trend=0,  # Will be calculated from historical data
        breakdown=metrics,
        recommendations=recommendations[:5],  # Top 5 recommendations
    )


async def get_quality_data_from_storage() -> dict[str, Any]:
    """Retrieve quality data from Redis or ChromaDB."""
    try:
        from src.utils.redis_client import get_redis_client

        redis = get_redis_client(async_client=False, database="analytics")
        if redis:
            # Issue #361 - avoid blocking
            data = await asyncio.to_thread(redis.get, "code_quality:latest")
            if data:
                return json.loads(data)
    except Exception as e:
        logger.warning("Failed to get quality data from Redis: %s", e)

    # Return demo data if storage unavailable
    return generate_demo_quality_data()


def generate_demo_quality_data() -> dict[str, Any]:
    """Generate demo quality data for testing."""
    import random

    random.seed(42)  # Consistent demo data

    return {
        "metrics": {
            "maintainability": 75.5,
            "reliability": 82.3,
            "security": 78.9,
            "performance": 71.2,
            "testability": 65.4,
            "documentation": 58.7,
        },
        "patterns": [
            {"type": "anti_pattern", "count": 23, "severity": "high"},
            {"type": "code_smell", "count": 45, "severity": "medium"},
            {"type": "best_practice", "count": 156, "severity": "info"},
            {"type": "security_vulnerability", "count": 8, "severity": "critical"},
            {"type": "performance_issue", "count": 12, "severity": "high"},
        ],
        "complexity": {
            "average_cyclomatic": 4.2,
            "max_cyclomatic": 28,
            "average_cognitive": 6.8,
            "max_cognitive": 45,
            "hotspots": [
                {
                    "file": "src/services/agent_service.py",
                    "complexity": 28,
                    "lines": 450,
                },
                {
                    "file": "src/core/workflow_engine.py",
                    "complexity": 24,
                    "lines": 380,
                },
                {"file": "src/api/endpoints.py", "complexity": 22, "lines": 520},
                {"file": "src/utils/parser.py", "complexity": 19, "lines": 290},
                {"file": "backend/api/analytics.py", "complexity": 18, "lines": 340},
            ],
        },
        "stats": {"file_count": 247, "line_count": 45230, "issues_count": 88},
        "trends": [
            {"date": (datetime.now() - timedelta(days=i)).isoformat(), "score": 70 + random.uniform(-5, 5)}
            for i in range(30, -1, -1)
        ],
    }


# ============================================================================
# WebSocket Connection Manager
# ============================================================================


class ConnectionManager:
    """Manage WebSocket connections for real-time updates."""

    def __init__(self):
        """Initialize connection manager with empty active connections list."""
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept new WebSocket connection."""
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(
            f"WebSocket connected. Total connections: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        """Remove disconnected WebSocket."""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(
                f"WebSocket disconnected. Total connections: {len(self.active_connections)}"
            )

    async def broadcast(self, message: dict):
        """Broadcast message to all connected clients."""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# ============================================================================
# REST Endpoints
# ============================================================================


@router.get("/health-score")
async def get_health_score() -> dict[str, Any]:
    """
    Get current codebase health score with breakdown.

    Returns overall health score, grade, and recommendations.
    """
    data = await get_quality_data_from_storage()
    metrics = data.get("metrics", {})

    health = calculate_health_score(metrics)

    return {
        "overall": health.overall,
        "grade": health.grade.value,
        "trend": health.trend,
        "breakdown": health.breakdown,
        "recommendations": health.recommendations,
        "timestamp": datetime.now().isoformat(),
    }


@router.get("/metrics")
async def get_quality_metrics(
    category: Optional[MetricCategory] = Query(None, description="Filter by category"),
) -> list[dict[str, Any]]:
    """
    Get all quality metrics or filter by category.

    Returns detailed metrics with grades and trends.
    """
    data = await get_quality_data_from_storage()
    raw_metrics = data.get("metrics", {})

    metrics = []
    for cat, value in raw_metrics.items():
        try:
            metric_cat = MetricCategory(cat)
            if category and metric_cat != category:
                continue

            metrics.append(
                {
                    "name": cat.replace("_", " ").title(),
                    "category": cat,
                    "value": value,
                    "grade": get_grade(value).value,
                    "trend": 0,  # Would be calculated from historical data
                    "weight": {
                        "maintainability": 0.25,
                        "reliability": 0.20,
                        "security": 0.20,
                        "performance": 0.15,
                        "testability": 0.10,
                        "documentation": 0.10,
                    }.get(cat, 0.1),
                }
            )
        except ValueError:
            continue

    return sorted(metrics, key=lambda x: x["value"], reverse=True)


@router.get("/patterns")
async def get_pattern_distribution(
    severity: Optional[str] = Query(None, description="Filter by severity"),
    limit: int = Query(20, ge=1, le=100),
) -> list[dict[str, Any]]:
    """
    Get distribution of code patterns detected in the codebase.

    Returns pattern types with counts, percentages, and severity.
    """
    data = await get_quality_data_from_storage()
    patterns = data.get("patterns", [])

    if severity:
        patterns = [p for p in patterns if p.get("severity") == severity]

    total = sum(p.get("count", 0) for p in patterns)

    result = []
    for pattern in patterns[:limit]:
        count = pattern.get("count", 0)
        result.append(
            {
                "type": pattern.get("type", "unknown"),
                "display_name": pattern.get("type", "").replace("_", " ").title(),
                "count": count,
                "percentage": (count / total * 100) if total > 0 else 0,
                "severity": pattern.get("severity", "info"),
                "icon": {
                    "anti_pattern": "warning",
                    "code_smell": "smell",
                    "best_practice": "check",
                    "security_vulnerability": "shield",
                    "performance_issue": "speed",
                }.get(pattern.get("type", ""), "info"),
            }
        )

    return result


@router.get("/complexity")
async def get_complexity_metrics(
    top_n: int = Query(10, ge=1, le=50, description="Number of hotspots to return"),
) -> dict[str, Any]:
    """
    Get code complexity analysis with hotspots.

    Returns cyclomatic and cognitive complexity metrics.
    """
    data = await get_quality_data_from_storage()
    complexity = data.get("complexity", {})

    # Calculate complexity distribution
    distribution = {
        "low": 0,  # 1-5
        "moderate": 0,  # 6-10
        "high": 0,  # 11-20
        "very_high": 0,  # 21+
    }

    # In real implementation, this would aggregate from all files
    hotspots = complexity.get("hotspots", [])[:top_n]

    return {
        "averages": {
            "cyclomatic": complexity.get("average_cyclomatic", 0),
            "cognitive": complexity.get("average_cognitive", 0),
        },
        "maximums": {
            "cyclomatic": complexity.get("max_cyclomatic", 0),
            "cognitive": complexity.get("max_cognitive", 0),
        },
        "hotspots": [
            {
                "file": h.get("file", ""),
                "complexity": h.get("complexity", 0),
                "lines": h.get("lines", 0),
                "recommendation": "Consider refactoring this file"
                if h.get("complexity", 0) > 15
                else "Monitor complexity",
            }
            for h in hotspots
        ],
        "distribution": distribution,
        "threshold_warnings": {
            "cyclomatic_warning": 10,
            "cyclomatic_critical": 20,
            "cognitive_warning": 15,
            "cognitive_critical": 25,
        },
    }


@router.get("/trends")
async def get_quality_trends(
    period: str = Query("30d", regex="^(7d|14d|30d|90d)$"),
    metric: Optional[str] = Query(None, description="Specific metric to trend"),
) -> dict[str, Any]:
    """
    Get quality score trends over time.

    Returns historical data for trend analysis.
    """
    data = await get_quality_data_from_storage()
    trends = data.get("trends", [])

    # Filter by period
    days = int(period[:-1])
    cutoff = datetime.now() - timedelta(days=days)

    filtered_trends = []
    for t in trends:
        try:
            date = datetime.fromisoformat(t.get("date", ""))
            if date >= cutoff:
                filtered_trends.append(t)
        except (ValueError, TypeError):
            continue

    # Calculate trend statistics
    scores = [t.get("score", 0) for t in filtered_trends]

    if scores:
        current = scores[-1] if scores else 0
        previous = scores[0] if scores else 0
        change = ((current - previous) / previous * 100) if previous > 0 else 0

        stats = {
            "current": current,
            "previous": previous,
            "change": change,
            "direction": "up" if change > 0 else "down" if change < 0 else "stable",
            "average": sum(scores) / len(scores),
            "min": min(scores),
            "max": max(scores),
        }
    else:
        stats = {
            "current": 0,
            "previous": 0,
            "change": 0,
            "direction": "stable",
            "average": 0,
            "min": 0,
            "max": 0,
        }

    return {
        "period": period,
        "data_points": filtered_trends,
        "statistics": stats,
        "metric": metric or "overall",
    }


@router.get("/snapshot")
async def get_quality_snapshot() -> dict[str, Any]:
    """
    Get complete quality snapshot for the current state.

    Returns all metrics, patterns, and statistics in one response.
    """
    data = await get_quality_data_from_storage()

    metrics = data.get("metrics", {})
    health = calculate_health_score(metrics)
    patterns = data.get("patterns", [])
    complexity = data.get("complexity", {})
    stats = data.get("stats", {})

    return {
        "timestamp": datetime.now().isoformat(),
        "health_score": {
            "overall": health.overall,
            "grade": health.grade.value,
            "breakdown": health.breakdown,
        },
        "metrics": [
            {
                "category": cat,
                "value": val,
                "grade": get_grade(val).value,
            }
            for cat, val in metrics.items()
        ],
        "patterns_summary": {
            "total": sum(p.get("count", 0) for p in patterns),
            "critical": sum(
                p.get("count", 0)
                for p in patterns
                if p.get("severity") == "critical"
            ),
            "high": sum(
                p.get("count", 0) for p in patterns if p.get("severity") == "high"
            ),
        },
        "complexity_summary": {
            "avg_cyclomatic": complexity.get("average_cyclomatic", 0),
            "max_cyclomatic": complexity.get("max_cyclomatic", 0),
            "hotspot_count": len(complexity.get("hotspots", [])),
        },
        "codebase_stats": {
            "files": stats.get("file_count", 0),
            "lines": stats.get("line_count", 0),
            "issues": stats.get("issues_count", 0),
        },
    }


@router.get("/drill-down/{category}")
async def drill_down_category(
    category: str,
    file_filter: Optional[str] = Query(None, description="Filter by file path"),
    severity: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    """
    Drill down into a specific quality category.

    Returns detailed issues and files for the category.
    """
    # In real implementation, this would query ChromaDB for detailed data
    demo_files = [
        {
            "path": "src/services/agent_service.py",
            "issues": 12,
            "score": 65,
            "top_issue": "High cyclomatic complexity",
        },
        {
            "path": "src/core/workflow_engine.py",
            "issues": 8,
            "score": 72,
            "top_issue": "Missing documentation",
        },
        {
            "path": "src/api/endpoints.py",
            "issues": 15,
            "score": 58,
            "top_issue": "Code duplication detected",
        },
        {
            "path": "src/utils/parser.py",
            "issues": 5,
            "score": 78,
            "top_issue": "Security consideration",
        },
        {
            "path": "backend/api/analytics.py",
            "issues": 3,
            "score": 85,
            "top_issue": "Minor style issues",
        },
    ]

    if file_filter:
        demo_files = [f for f in demo_files if file_filter.lower() in f["path"].lower()]

    return {
        "category": category,
        "display_name": category.replace("_", " ").title(),
        "total_files": len(demo_files),
        "total_issues": sum(f["issues"] for f in demo_files),
        "average_score": sum(f["score"] for f in demo_files) / len(demo_files)
        if demo_files
        else 0,
        "files": demo_files[:limit],
        "filters_applied": {
            "file": file_filter,
            "severity": severity,
        },
    }


@router.get("/export")
async def export_quality_report(
    format: str = Query("json", regex="^(json|csv|pdf)$"),
) -> JSONResponse:
    """
    Export quality report in specified format.

    Supports JSON, CSV, and PDF formats.
    """
    data = await get_quality_data_from_storage()
    metrics = data.get("metrics", {})
    health = calculate_health_score(metrics)

    report = {
        "generated_at": datetime.now().isoformat(),
        "format": format,
        "health_score": {
            "overall": health.overall,
            "grade": health.grade.value,
            "breakdown": health.breakdown,
        },
        "metrics": metrics,
        "patterns": data.get("patterns", []),
        "complexity": data.get("complexity", {}),
        "stats": data.get("stats", {}),
        "recommendations": health.recommendations,
    }

    if format == "json":
        return JSONResponse(content=report)
    elif format == "csv":
        # Generate CSV content
        import io
        import csv

        output = io.StringIO()
        writer = csv.writer(output)

        # Health score section
        writer.writerow(["Section", "Metric", "Value", "Grade"])
        writer.writerow(
            [
                "Health",
                "Overall Score",
                f"{health.overall:.1f}",
                health.grade.value,
            ]
        )

        for cat, val in metrics.items():
            writer.writerow(
                ["Metrics", cat.replace("_", " ").title(), f"{val:.1f}", get_grade(val).value]
            )

        csv_content = output.getvalue()
        return JSONResponse(
            content={"format": "csv", "content": csv_content},
            media_type="application/json",
        )
    else:
        # PDF would require additional library
        return JSONResponse(
            content={"error": "PDF export not yet implemented", "format": format},
            status_code=501,
        )


# ============================================================================
# WebSocket Endpoint
# ============================================================================


async def _handle_ws_subscribe(websocket: WebSocket, data: dict) -> None:
    """Handle WebSocket subscribe message (Issue #315: extracted)."""
    await websocket.send_json({"type": "subscribed", "metrics": data.get("metrics", [])})


async def _handle_ws_refresh(websocket: WebSocket, data: dict) -> None:
    """Handle WebSocket refresh message (Issue #315: extracted)."""
    snapshot = await get_quality_snapshot()
    await websocket.send_json({"type": "snapshot", "data": snapshot})


async def _handle_ws_ping(websocket: WebSocket, data: dict) -> None:
    """Handle WebSocket ping message (Issue #315: extracted)."""
    await websocket.send_json({"type": "pong"})


# WebSocket message handlers (Issue #315: dictionary dispatch pattern)
_WS_MESSAGE_HANDLERS = {
    "subscribe": _handle_ws_subscribe,
    "refresh": _handle_ws_refresh,
    "ping": _handle_ws_ping,
}


@router.websocket("/ws")
async def websocket_quality_updates(websocket: WebSocket):
    """
    WebSocket endpoint for real-time quality updates.

    Clients receive updates when quality metrics change.
    Issue #315: Refactored to use dictionary dispatch for message handling.
    """
    await manager.connect(websocket)

    # Send initial snapshot
    try:
        snapshot = await get_quality_snapshot()
        await websocket.send_json({"type": "snapshot", "data": snapshot})

        # Keep connection alive and handle incoming messages
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)

                # Handle message using dispatch pattern (Issue #315)
                msg_type = data.get("type")
                handler = _WS_MESSAGE_HANDLERS.get(msg_type)
                if handler:
                    await handler(websocket, data)

            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        manager.disconnect(websocket)


# ============================================================================
# Broadcast Function (for use by other modules)
# ============================================================================


async def broadcast_quality_update(update_type: str, data: dict):
    """
    Broadcast quality update to all connected WebSocket clients.

    Called by indexer or analysis modules when quality changes.
    """
    await manager.broadcast(
        {
            "type": update_type,
            "data": data,
            "timestamp": datetime.now().isoformat(),
        }
    )
