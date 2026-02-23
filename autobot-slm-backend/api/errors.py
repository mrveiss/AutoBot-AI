# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Error Monitoring API Routes

Issue #563: Error Monitoring Dashboard - 13 Endpoints

Provides comprehensive error tracking, resolution, and analytics endpoints.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from models.database import EventSeverity, Node, NodeEvent, Setting
from pydantic import BaseModel, Field
from services.auth import get_current_user
from services.database import get_db
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/errors", tags=["errors"])


# =============================================================================
# Response Models
# =============================================================================


class ErrorStatistics(BaseModel):
    """Overall error statistics."""

    total_errors: int
    errors_24h: int
    errors_7d: int
    errors_30d: int
    resolved_count: int
    unresolved_count: int
    error_rate_per_hour: float
    trend: str = "stable"  # increasing, decreasing, stable


class RecentError(BaseModel):
    """Recent error entry."""

    event_id: str
    node_id: str
    hostname: str
    event_type: str
    severity: str
    message: str
    timestamp: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None


class RecentErrorsResponse(BaseModel):
    """Recent errors list with pagination."""

    errors: List[RecentError]
    total: int
    page: int
    per_page: int


class CategoryBreakdown(BaseModel):
    """Error category breakdown."""

    category: str
    count: int
    percentage: float


class CategoriesResponse(BaseModel):
    """Error categories response."""

    categories: List[CategoryBreakdown]
    total: int


class ComponentBreakdown(BaseModel):
    """Errors by component/node."""

    node_id: str
    hostname: str
    count: int
    percentage: float


class ComponentsResponse(BaseModel):
    """Errors by component response."""

    components: List[ComponentBreakdown]
    total: int


class ErrorHealthResponse(BaseModel):
    """Error subsystem health status."""

    status: str  # healthy, warning, critical
    error_rate_current: float
    error_rate_threshold_warning: int
    error_rate_threshold_critical: int
    recent_critical_count: int
    message: str


class MetricsSummary(BaseModel):
    """Error metrics summary."""

    total_errors: int
    unresolved_errors: int
    critical_errors: int
    error_rate_per_hour: float
    mean_time_to_resolve_hours: Optional[float] = None
    top_error_type: Optional[str] = None
    most_affected_node: Optional[str] = None


class TimelinePoint(BaseModel):
    """Timeline data point."""

    timestamp: datetime
    count: int
    critical: int = 0
    error: int = 0


class TimelineResponse(BaseModel):
    """Error timeline response."""

    timeline: List[TimelinePoint]
    interval: str
    start: datetime
    end: datetime


class TopError(BaseModel):
    """Top error entry."""

    event_type: str
    message: str
    count: int
    last_occurred: datetime
    affected_nodes: List[str]


class TopErrorsResponse(BaseModel):
    """Top errors response."""

    errors: List[TopError]


class AlertThresholdConfig(BaseModel):
    """Alert threshold configuration."""

    warning_threshold: int = Field(ge=1, le=1000)
    critical_threshold: int = Field(ge=1, le=1000)
    retention_days: int = Field(ge=1, le=365)


class AlertThresholdResponse(BaseModel):
    """Alert threshold response."""

    warning_threshold: int
    critical_threshold: int
    retention_days: int
    updated: bool = False


class CleanupResponse(BaseModel):
    """Cleanup operation response."""

    deleted_count: int
    retention_days: int
    message: str


class ClearResponse(BaseModel):
    """Clear operation response."""

    deleted_count: int
    message: str


class TestErrorResponse(BaseModel):
    """Test error response."""

    event_id: str
    message: str


class ResolveResponse(BaseModel):
    """Resolve operation response."""

    event_id: str
    resolved: bool
    resolved_at: datetime
    resolved_by: str


# =============================================================================
# Helper Functions (Issue #563 - Refactored for function length compliance)
# =============================================================================


async def _get_node_hostname_map(
    db: AsyncSession, node_ids: List[str]
) -> Dict[str, str]:
    """Get mapping of node_id to hostname."""
    if not node_ids:
        return {}
    result = await db.execute(select(Node).where(Node.node_id.in_(node_ids)))
    return {n.node_id: n.hostname for n in result.scalars().all()}


async def _get_error_counts_by_period(db: AsyncSession) -> Dict[str, int]:
    """Get error counts for different time periods."""
    now = datetime.utcnow()
    cutoffs = {
        "24h": now - timedelta(hours=24),
        "7d": now - timedelta(days=7),
        "30d": now - timedelta(days=30),
    }

    counts = {}
    for period, cutoff in cutoffs.items():
        result = await db.execute(
            select(func.count(NodeEvent.id)).where(
                NodeEvent.created_at >= cutoff,
                NodeEvent.severity.in_(
                    [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
                ),
            )
        )
        counts[period] = result.scalar() or 0

    return counts


async def _calculate_error_trend(db: AsyncSession) -> str:
    """Calculate error trend based on recent vs previous period."""
    now = datetime.utcnow()
    recent_cutoff = now - timedelta(hours=12)
    prev_cutoff = now - timedelta(hours=24)

    # Recent 12 hours
    recent_result = await db.execute(
        select(func.count(NodeEvent.id)).where(
            NodeEvent.created_at >= recent_cutoff,
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            ),
        )
    )
    recent_count = recent_result.scalar() or 0

    # Previous 12 hours
    prev_result = await db.execute(
        select(func.count(NodeEvent.id)).where(
            NodeEvent.created_at >= prev_cutoff,
            NodeEvent.created_at < recent_cutoff,
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            ),
        )
    )
    prev_count = prev_result.scalar() or 0

    if recent_count > prev_count * 1.2:
        return "increasing"
    elif recent_count < prev_count * 0.8:
        return "decreasing"
    return "stable"


async def _get_setting_value(db: AsyncSession, key: str, default: int) -> int:
    """Get setting value from database with default fallback."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting and setting.value:
        try:
            return int(setting.value)
        except ValueError:
            pass
    return default


async def _set_setting_value(db: AsyncSession, key: str, value: int, desc: str) -> None:
    """Set or update a setting value."""
    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = str(value)
    else:
        db.add(Setting(key=key, value=str(value), value_type="int", description=desc))


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/statistics", response_model=ErrorStatistics)
async def get_error_statistics(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ErrorStatistics:
    """Get overall error statistics."""
    # Get total errors
    total_result = await db.execute(
        select(func.count(NodeEvent.id)).where(
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            )
        )
    )
    total = total_result.scalar() or 0

    # Get period counts
    counts = await _get_error_counts_by_period(db)

    # Get resolved/unresolved counts
    resolved_result = await db.execute(
        select(func.count(NodeEvent.id)).where(
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            ),
            NodeEvent.resolved.is_(True),
        )
    )
    resolved = resolved_result.scalar() or 0

    # Calculate error rate (errors per hour in last 24h)
    error_rate = counts["24h"] / 24.0 if counts["24h"] > 0 else 0.0

    # Get trend
    trend = await _calculate_error_trend(db)

    return ErrorStatistics(
        total_errors=total,
        errors_24h=counts["24h"],
        errors_7d=counts["7d"],
        errors_30d=counts["30d"],
        resolved_count=resolved,
        unresolved_count=total - resolved,
        error_rate_per_hour=round(error_rate, 2),
        trend=trend,
    )


def _build_recent_error_queries(severity: Optional[str], resolved: Optional[bool]):
    """Helper for get_recent_errors. Ref: #1088."""
    query = select(NodeEvent).where(
        NodeEvent.severity.in_(
            [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
        )
    )
    count_query = select(func.count(NodeEvent.id)).where(
        NodeEvent.severity.in_(
            [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
        )
    )
    if severity:
        query = query.where(NodeEvent.severity == severity)
        count_query = count_query.where(NodeEvent.severity == severity)
    if resolved is not None:
        query = query.where(NodeEvent.resolved == resolved)
        count_query = count_query.where(NodeEvent.resolved == resolved)
    return query, count_query


def _build_recent_error_list(events, hostnames: Dict[str, str]) -> List[RecentError]:
    """Helper for get_recent_errors. Ref: #1088."""
    return [
        RecentError(
            event_id=e.event_id,
            node_id=e.node_id,
            hostname=hostnames.get(e.node_id, e.node_id),
            event_type=e.event_type,
            severity=e.severity,
            message=e.message,
            timestamp=e.created_at,
            resolved=e.resolved or False,
            resolved_at=e.resolved_at,
            resolved_by=e.resolved_by,
        )
        for e in events
    ]


@router.get("/recent", response_model=RecentErrorsResponse)
async def get_recent_errors(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    severity: Optional[str] = Query(None),
    resolved: Optional[bool] = Query(None),
) -> RecentErrorsResponse:
    """Get recent error list with pagination."""
    query, count_query = _build_recent_error_queries(severity, resolved)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    query = (
        query.order_by(NodeEvent.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    events = result.scalars().all()

    node_ids = list(set(e.node_id for e in events))
    hostnames = await _get_node_hostname_map(db, node_ids)
    errors = _build_recent_error_list(events, hostnames)

    return RecentErrorsResponse(
        errors=errors, total=total, page=page, per_page=per_page
    )


@router.get("/categories", response_model=CategoriesResponse)
async def get_error_categories(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    hours: int = Query(24, ge=1, le=720),
) -> CategoriesResponse:
    """Get error categories breakdown."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    result = await db.execute(
        select(NodeEvent.event_type, func.count(NodeEvent.id).label("count"))
        .where(
            NodeEvent.created_at >= cutoff,
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            ),
        )
        .group_by(NodeEvent.event_type)
        .order_by(func.count(NodeEvent.id).desc())
    )

    rows = result.all()
    total = sum(r.count for r in rows)

    categories = [
        CategoryBreakdown(
            category=r.event_type,
            count=r.count,
            percentage=round(r.count / total * 100, 1) if total > 0 else 0.0,
        )
        for r in rows
    ]

    return CategoriesResponse(categories=categories, total=total)


@router.get("/components", response_model=ComponentsResponse)
async def get_error_components(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    hours: int = Query(24, ge=1, le=720),
) -> ComponentsResponse:
    """Get errors by component/node."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    result = await db.execute(
        select(NodeEvent.node_id, func.count(NodeEvent.id).label("count"))
        .where(
            NodeEvent.created_at >= cutoff,
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            ),
        )
        .group_by(NodeEvent.node_id)
        .order_by(func.count(NodeEvent.id).desc())
    )

    rows = result.all()
    total = sum(r.count for r in rows)

    node_ids = [r.node_id for r in rows]
    hostnames = await _get_node_hostname_map(db, node_ids)

    components = [
        ComponentBreakdown(
            node_id=r.node_id,
            hostname=hostnames.get(r.node_id, r.node_id),
            count=r.count,
            percentage=round(r.count / total * 100, 1) if total > 0 else 0.0,
        )
        for r in rows
    ]

    return ComponentsResponse(components=components, total=total)


@router.get("/health", response_model=ErrorHealthResponse)
async def get_error_health(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> ErrorHealthResponse:
    """Get error subsystem health status."""
    # Get thresholds from settings
    warning_threshold = await _get_setting_value(
        db, "error_alert_threshold_warning", 20
    )
    critical_threshold = await _get_setting_value(
        db, "error_alert_threshold_critical", 50
    )

    # Calculate current error rate (errors in last hour)
    cutoff = datetime.utcnow() - timedelta(hours=1)
    result = await db.execute(
        select(func.count(NodeEvent.id)).where(
            NodeEvent.created_at >= cutoff,
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            ),
        )
    )
    error_rate = result.scalar() or 0

    # Count recent critical errors
    critical_result = await db.execute(
        select(func.count(NodeEvent.id)).where(
            NodeEvent.created_at >= cutoff,
            NodeEvent.severity == EventSeverity.CRITICAL.value,
        )
    )
    critical_count = critical_result.scalar() or 0

    # Determine status
    if error_rate >= critical_threshold or critical_count >= 5:
        health_status = "critical"
        message = f"High error rate: {error_rate} errors/hour (threshold: {critical_threshold})"
    elif error_rate >= warning_threshold or critical_count >= 2:
        health_status = "warning"
        message = f"Elevated error rate: {error_rate} errors/hour (threshold: {warning_threshold})"
    else:
        health_status = "healthy"
        message = f"Error rate normal: {error_rate} errors/hour"

    return ErrorHealthResponse(
        status=health_status,
        error_rate_current=float(error_rate),
        error_rate_threshold_warning=warning_threshold,
        error_rate_threshold_critical=critical_threshold,
        recent_critical_count=critical_count,
        message=message,
    )


@router.post("/clear", response_model=ClearResponse)
async def clear_errors(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
    severity: Optional[str] = Query(None),
    older_than_hours: Optional[int] = Query(None, ge=1),
) -> ClearResponse:
    """Clear error history."""
    query = delete(NodeEvent).where(
        NodeEvent.severity.in_(
            [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
        )
    )

    if severity:
        query = delete(NodeEvent).where(NodeEvent.severity == severity)
    if older_than_hours:
        cutoff = datetime.utcnow() - timedelta(hours=older_than_hours)
        query = query.where(NodeEvent.created_at < cutoff)

    result = await db.execute(query)
    await db.commit()

    deleted = result.rowcount
    logger.info("User %s cleared %d errors", user.get("username", "unknown"), deleted)

    return ClearResponse(deleted_count=deleted, message=f"Cleared {deleted} error(s)")


@router.post("/test-error", response_model=TestErrorResponse)
async def create_test_error(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
    severity: str = Query("error", regex="^(error|critical)$"),
) -> TestErrorResponse:
    """Generate test error for validation."""
    event_id = f"test-{uuid.uuid4().hex[:12]}"

    event = NodeEvent(
        event_id=event_id,
        node_id="test-node",
        event_type="test_error",
        severity=severity,
        message=f"Test error generated by {user.get('username', 'unknown')} for validation",
        details={"generated_by": user.get("username"), "purpose": "testing"},
    )
    db.add(event)
    await db.commit()

    logger.info(
        "Test error created: %s by %s", event_id, user.get("username", "unknown")
    )

    return TestErrorResponse(
        event_id=event_id, message="Test error created successfully"
    )


async def _get_metrics_total_and_unresolved(db: AsyncSession):
    """Helper for get_metrics_summary. Ref: #1088."""
    total_result = await db.execute(
        select(func.count(NodeEvent.id)).where(
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            )
        )
    )
    total = total_result.scalar() or 0

    unresolved_result = await db.execute(
        select(func.count(NodeEvent.id)).where(
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            ),
            NodeEvent.resolved.is_(False),
        )
    )
    unresolved = unresolved_result.scalar() or 0
    return total, unresolved


async def _get_metrics_top_type_and_node(db: AsyncSession):
    """Helper for get_metrics_summary. Ref: #1088."""
    top_type_result = await db.execute(
        select(NodeEvent.event_type)
        .where(
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            )
        )
        .group_by(NodeEvent.event_type)
        .order_by(func.count(NodeEvent.id).desc())
        .limit(1)
    )
    top_type = top_type_result.scalar_one_or_none()

    top_node_result = await db.execute(
        select(NodeEvent.node_id)
        .where(
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            )
        )
        .group_by(NodeEvent.node_id)
        .order_by(func.count(NodeEvent.id).desc())
        .limit(1)
    )
    top_node = top_node_result.scalar_one_or_none()
    return top_type, top_node


@router.get("/metrics/summary", response_model=MetricsSummary)
async def get_metrics_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> MetricsSummary:
    """Get aggregated error metrics summary."""
    total, unresolved = await _get_metrics_total_and_unresolved(db)

    # Critical count (last 24h)
    cutoff = datetime.utcnow() - timedelta(hours=24)
    critical_result = await db.execute(
        select(func.count(NodeEvent.id)).where(
            NodeEvent.created_at >= cutoff,
            NodeEvent.severity == EventSeverity.CRITICAL.value,
        )
    )
    critical = critical_result.scalar() or 0

    counts = await _get_error_counts_by_period(db)
    error_rate = counts["24h"] / 24.0 if counts["24h"] > 0 else 0.0

    top_type, top_node = await _get_metrics_top_type_and_node(db)

    return MetricsSummary(
        total_errors=total,
        unresolved_errors=unresolved,
        critical_errors=critical,
        error_rate_per_hour=round(error_rate, 2),
        top_error_type=top_type,
        most_affected_node=top_node,
    )


def _make_timeline_point(bucket_start, bucket_end, events) -> TimelinePoint:
    """Helper for get_error_timeline. Ref: #1088."""
    bucket_events = [e for e in events if bucket_start <= e.created_at < bucket_end]
    return TimelinePoint(
        timestamp=bucket_start,
        count=len(bucket_events),
        critical=sum(
            1 for e in bucket_events if e.severity == EventSeverity.CRITICAL.value
        ),
        error=sum(1 for e in bucket_events if e.severity == EventSeverity.ERROR.value),
    )


def _build_timeline_points(
    events, start, hours: int, interval: str
) -> List[TimelinePoint]:
    """Helper for get_error_timeline. Ref: #1088."""
    timeline = []
    if interval == "hour":
        for h in range(hours):
            bucket_start = start + timedelta(hours=h)
            bucket_end = bucket_start + timedelta(hours=1)
            timeline.append(_make_timeline_point(bucket_start, bucket_end, events))
    else:
        for d in range(hours // 24):
            bucket_start = start + timedelta(days=d)
            bucket_end = bucket_start + timedelta(days=1)
            timeline.append(_make_timeline_point(bucket_start, bucket_end, events))
    return timeline


@router.get("/metrics/timeline", response_model=TimelineResponse)
async def get_error_timeline(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    hours: int = Query(24, ge=1, le=168),
    interval: str = Query("hour", regex="^(hour|day)$"),
) -> TimelineResponse:
    """Get error timeline data."""
    now = datetime.utcnow()
    start = now - timedelta(hours=hours)

    result = await db.execute(
        select(NodeEvent)
        .where(
            NodeEvent.created_at >= start,
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            ),
        )
        .order_by(NodeEvent.created_at)
    )
    events = result.scalars().all()

    timeline = _build_timeline_points(events, start, hours, interval)

    return TimelineResponse(timeline=timeline, interval=interval, start=start, end=now)


@router.get("/metrics/top-errors", response_model=TopErrorsResponse)
async def get_top_errors(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(10, ge=1, le=50),
) -> TopErrorsResponse:
    """Get most frequent errors."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Get error counts by type and message
    result = await db.execute(
        select(
            NodeEvent.event_type,
            NodeEvent.message,
            func.count(NodeEvent.id).label("count"),
            func.max(NodeEvent.created_at).label("last_occurred"),
        )
        .where(
            NodeEvent.created_at >= cutoff,
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            ),
        )
        .group_by(NodeEvent.event_type, NodeEvent.message)
        .order_by(func.count(NodeEvent.id).desc())
        .limit(limit)
    )
    rows = result.all()

    # Get affected nodes for each error type
    top_errors = []
    for row in rows:
        nodes_result = await db.execute(
            select(NodeEvent.node_id)
            .where(
                NodeEvent.created_at >= cutoff,
                NodeEvent.event_type == row.event_type,
                NodeEvent.message == row.message,
            )
            .distinct()
        )
        affected_nodes = [n for n in nodes_result.scalars().all()]

        top_errors.append(
            TopError(
                event_type=row.event_type,
                message=row.message[:200],  # Truncate long messages
                count=row.count,
                last_occurred=row.last_occurred,
                affected_nodes=affected_nodes[:10],  # Limit nodes list
            )
        )

    return TopErrorsResponse(errors=top_errors)


@router.post("/metrics/resolve/{event_id}", response_model=ResolveResponse)
async def resolve_error(
    event_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> ResolveResponse:
    """Mark an error as resolved."""
    result = await db.execute(select(NodeEvent).where(NodeEvent.event_id == event_id))
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Error not found"
        )

    now = datetime.utcnow()
    username = user.get("username", "unknown")

    await db.execute(
        update(NodeEvent)
        .where(NodeEvent.event_id == event_id)
        .values(resolved=True, resolved_at=now, resolved_by=username)
    )
    await db.commit()

    logger.info("Error %s resolved by %s", event_id, username)

    return ResolveResponse(
        event_id=event_id, resolved=True, resolved_at=now, resolved_by=username
    )


@router.post("/metrics/alert-threshold", response_model=AlertThresholdResponse)
async def configure_alert_threshold(
    config: AlertThresholdConfig,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
) -> AlertThresholdResponse:
    """Configure error alert thresholds."""
    await _set_setting_value(
        db,
        "error_alert_threshold_warning",
        config.warning_threshold,
        "Errors per hour before warning alert",
    )
    await _set_setting_value(
        db,
        "error_alert_threshold_critical",
        config.critical_threshold,
        "Errors per hour before critical alert",
    )
    await _set_setting_value(
        db,
        "error_retention_days",
        config.retention_days,
        "Days to retain error history",
    )
    await db.commit()

    logger.info(
        "Alert thresholds updated by %s: warning=%d, critical=%d, retention=%d",
        user.get("username", "unknown"),
        config.warning_threshold,
        config.critical_threshold,
        config.retention_days,
    )

    return AlertThresholdResponse(
        warning_threshold=config.warning_threshold,
        critical_threshold=config.critical_threshold,
        retention_days=config.retention_days,
        updated=True,
    )


@router.post("/metrics/cleanup", response_model=CleanupResponse)
async def cleanup_old_errors(
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[dict, Depends(get_current_user)],
    days: Optional[int] = Query(None, ge=1, le=365),
) -> CleanupResponse:
    """Cleanup old errors based on retention policy."""
    # Get retention days from settings or use provided value
    if days is None:
        days = await _get_setting_value(db, "error_retention_days", 30)

    cutoff = datetime.utcnow() - timedelta(days=days)

    result = await db.execute(
        delete(NodeEvent).where(
            NodeEvent.created_at < cutoff,
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            ),
        )
    )
    await db.commit()

    deleted = result.rowcount
    logger.info(
        "User %s cleaned up %d errors older than %d days",
        user.get("username", "unknown"),
        deleted,
        days,
    )

    return CleanupResponse(
        deleted_count=deleted,
        retention_days=days,
        message=f"Cleaned up {deleted} error(s) older than {days} days",
    )
