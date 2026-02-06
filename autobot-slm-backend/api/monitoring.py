# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Monitoring API Routes

API endpoints for fleet-wide monitoring, metrics aggregation, and alerts.
Related to Issue #729.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

from models.database import (
    Deployment,
    DeploymentStatus,
    EventSeverity,
    MaintenanceWindow,
    Node,
    NodeEvent,
    NodeStatus,
    Service,
    ServiceStatus,
)
from services.auth import get_current_user
from services.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/monitoring", tags=["monitoring"])


# =============================================================================
# Response Models
# =============================================================================


class NodeMetrics(BaseModel):
    """Metrics for a single node."""

    node_id: str
    hostname: str
    ip_address: str
    status: str
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    last_heartbeat: Optional[datetime] = None
    services_running: int = 0
    services_failed: int = 0


class FleetMetricsResponse(BaseModel):
    """Fleet-wide metrics aggregation."""

    total_nodes: int
    online_nodes: int
    degraded_nodes: int
    offline_nodes: int
    avg_cpu_percent: float
    avg_memory_percent: float
    avg_disk_percent: float
    total_services: int
    running_services: int
    failed_services: int
    nodes: List[NodeMetrics]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AlertItem(BaseModel):
    """Single alert item."""

    alert_id: str
    severity: str
    category: str
    message: str
    node_id: Optional[str] = None
    hostname: Optional[str] = None
    timestamp: datetime
    acknowledged: bool = False


class AlertsResponse(BaseModel):
    """Alerts aggregation response."""

    total_count: int
    critical_count: int
    warning_count: int
    info_count: int
    alerts: List[AlertItem]


class SystemHealthResponse(BaseModel):
    """Overall system health status."""

    overall_status: str  # healthy, degraded, critical
    health_score: float  # 0-100
    components: Dict[str, str]  # component -> status
    issues: List[str]
    last_check: datetime = Field(default_factory=datetime.utcnow)


class DashboardOverview(BaseModel):
    """Dashboard overview data."""

    fleet_metrics: FleetMetricsResponse
    recent_alerts: List[AlertItem]
    recent_deployments: int
    active_maintenance: int
    health_summary: SystemHealthResponse


class LogEntry(BaseModel):
    """Log entry from node events."""

    event_id: str
    node_id: str
    hostname: str
    event_type: str
    severity: str
    message: str
    timestamp: datetime


class LogsResponse(BaseModel):
    """Logs query response."""

    logs: List[LogEntry]
    total: int
    page: int
    per_page: int


# =============================================================================
# Helper Functions (Issue #729 - Refactored for function length compliance)
# =============================================================================


def _empty_fleet_metrics() -> FleetMetricsResponse:
    """Return empty fleet metrics response. Related to Issue #729."""
    return FleetMetricsResponse(
        total_nodes=0,
        online_nodes=0,
        degraded_nodes=0,
        offline_nodes=0,
        avg_cpu_percent=0.0,
        avg_memory_percent=0.0,
        avg_disk_percent=0.0,
        total_services=0,
        running_services=0,
        failed_services=0,
        nodes=[],
    )


async def _get_services_by_node(db: AsyncSession) -> Dict[str, Dict[str, int]]:
    """Query and aggregate service counts by node. Related to Issue #729."""
    services_result = await db.execute(
        select(
            Service.node_id, Service.status, func.count(Service.id).label("count")
        ).group_by(Service.node_id, Service.status)
    )
    services_by_node: Dict[str, Dict[str, int]] = {}
    for row in services_result:
        if row.node_id not in services_by_node:
            services_by_node[row.node_id] = {"running": 0, "failed": 0}
        if row.status == ServiceStatus.RUNNING.value:
            services_by_node[row.node_id]["running"] = row.count
        elif row.status == ServiceStatus.FAILED.value:
            services_by_node[row.node_id]["failed"] = row.count
    return services_by_node


def _calculate_node_status_counts(nodes: List[Node]) -> tuple:
    """Calculate online, degraded, offline node counts. Related to Issue #729."""
    online = sum(1 for n in nodes if n.status == NodeStatus.ONLINE.value)
    degraded = sum(1 for n in nodes if n.status == NodeStatus.DEGRADED.value)
    offline = sum(
        1
        for n in nodes
        if n.status in [NodeStatus.OFFLINE.value, NodeStatus.ERROR.value]
    )
    return online, degraded, offline


def _calculate_resource_averages(nodes: List[Node]) -> tuple:
    """Calculate average CPU, memory, disk percentages. Related to Issue #729."""
    cpu_vals = [n.cpu_percent for n in nodes if n.cpu_percent is not None]
    mem_vals = [n.memory_percent for n in nodes if n.memory_percent is not None]
    disk_vals = [n.disk_percent for n in nodes if n.disk_percent is not None]
    return (
        sum(cpu_vals) / len(cpu_vals) if cpu_vals else 0.0,
        sum(mem_vals) / len(mem_vals) if mem_vals else 0.0,
        sum(disk_vals) / len(disk_vals) if disk_vals else 0.0,
    )


def _build_node_metrics(
    nodes: List[Node], services_by_node: Dict[str, Dict[str, int]]
) -> List[NodeMetrics]:
    """Build NodeMetrics list from nodes and service data. Related to Issue #729."""
    return [
        NodeMetrics(
            node_id=n.node_id,
            hostname=n.hostname,
            ip_address=n.ip_address,
            status=n.status,
            cpu_percent=n.cpu_percent or 0.0,
            memory_percent=n.memory_percent or 0.0,
            disk_percent=n.disk_percent or 0.0,
            last_heartbeat=n.last_heartbeat,
            services_running=services_by_node.get(n.node_id, {}).get("running", 0),
            services_failed=services_by_node.get(n.node_id, {}).get("failed", 0),
        )
        for n in nodes
    ]


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/metrics/fleet", response_model=FleetMetricsResponse)
async def get_fleet_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> FleetMetricsResponse:
    """Get aggregated metrics for the entire fleet."""
    result = await db.execute(select(Node))
    nodes = result.scalars().all()

    if not nodes:
        return _empty_fleet_metrics()

    services_by_node = await _get_services_by_node(db)
    online, degraded, offline = _calculate_node_status_counts(nodes)
    avg_cpu, avg_mem, avg_disk = _calculate_resource_averages(nodes)

    # Calculate service totals
    total_svc = sum(
        services_by_node.get(n.node_id, {}).get("running", 0)
        + services_by_node.get(n.node_id, {}).get("failed", 0)
        for n in nodes
    )
    running_svc = sum(
        services_by_node.get(n.node_id, {}).get("running", 0) for n in nodes
    )
    failed_svc = sum(
        services_by_node.get(n.node_id, {}).get("failed", 0) for n in nodes
    )

    return FleetMetricsResponse(
        total_nodes=len(nodes),
        online_nodes=online,
        degraded_nodes=degraded,
        offline_nodes=offline,
        avg_cpu_percent=avg_cpu,
        avg_memory_percent=avg_mem,
        avg_disk_percent=avg_disk,
        total_services=total_svc,
        running_services=running_svc,
        failed_services=failed_svc,
        nodes=_build_node_metrics(nodes, services_by_node),
    )


@router.get("/metrics/node/{node_id}", response_model=NodeMetrics)
async def get_node_metrics(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> NodeMetrics:
    """Get metrics for a specific node."""
    result = await db.execute(select(Node).where(Node.node_id == node_id))
    node = result.scalar_one_or_none()

    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    # Get service counts
    services_result = await db.execute(
        select(Service.status, func.count(Service.id).label("count"))
        .where(Service.node_id == node_id)
        .group_by(Service.status)
    )
    running = 0
    failed = 0
    for row in services_result:
        if row.status == ServiceStatus.RUNNING.value:
            running = row.count
        elif row.status == ServiceStatus.FAILED.value:
            failed = row.count

    return NodeMetrics(
        node_id=node.node_id,
        hostname=node.hostname,
        ip_address=node.ip_address,
        status=node.status,
        cpu_percent=node.cpu_percent or 0.0,
        memory_percent=node.memory_percent or 0.0,
        disk_percent=node.disk_percent or 0.0,
        last_heartbeat=node.last_heartbeat,
        services_running=running,
        services_failed=failed,
    )


# Alerts constants (Issue #729 - avoid magic numbers)
MAX_ALERTS_RETURNED = 100
MAX_RECENT_ERRORS = 20


async def _get_node_hostname_map(
    db: AsyncSession, node_ids: List[str]
) -> Dict[str, str]:
    """Get mapping of node_id to hostname. Related to Issue #729."""
    if not node_ids:
        return {}
    nodes_result = await db.execute(select(Node).where(Node.node_id.in_(node_ids)))
    return {n.node_id: n.hostname for n in nodes_result.scalars().all()}


def _get_hostname(nodes: Dict[str, Any], node_id: str) -> str:
    """Get hostname from nodes dict with fallback. Related to Issue #729."""
    node = nodes.get(node_id)
    return (
        node.hostname
        if hasattr(node, "hostname")
        else node
        if isinstance(node, str)
        else "unknown"
    )


def _events_to_alerts(events: List[Any], nodes: Dict[str, Any]) -> List[AlertItem]:
    """Convert NodeEvent list to AlertItem list. Related to Issue #729."""
    return [
        AlertItem(
            alert_id=e.event_id,
            severity=e.severity,
            category=e.event_type,
            message=e.message,
            node_id=e.node_id,
            hostname=_get_hostname(nodes, e.node_id),
            timestamp=e.created_at,
        )
        for e in events
    ]


@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    severity: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168),
) -> AlertsResponse:
    """Get alerts from node events within the specified time window."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    query = select(NodeEvent).where(
        NodeEvent.created_at >= cutoff,
        NodeEvent.severity.in_(
            [
                EventSeverity.WARNING.value,
                EventSeverity.ERROR.value,
                EventSeverity.CRITICAL.value,
            ]
        ),
    )
    if severity:
        query = query.where(NodeEvent.severity == severity)
    query = query.order_by(NodeEvent.created_at.desc())

    result = await db.execute(query)
    events = result.scalars().all()

    node_ids = list(set(e.node_id for e in events))
    nodes_result = (
        await db.execute(select(Node).where(Node.node_id.in_(node_ids)))
        if node_ids
        else None
    )
    nodes = {n.node_id: n for n in nodes_result.scalars().all()} if nodes_result else {}

    alerts = _events_to_alerts(events, nodes)

    return AlertsResponse(
        total_count=len(alerts),
        critical_count=sum(
            1 for a in alerts if a.severity == EventSeverity.CRITICAL.value
        ),
        warning_count=sum(
            1 for a in alerts if a.severity == EventSeverity.WARNING.value
        ),
        info_count=sum(1 for a in alerts if a.severity == EventSeverity.INFO.value),
        alerts=alerts[:MAX_ALERTS_RETURNED],
    )


# Health check constants (Issue #729 - avoid magic numbers)
FAILED_SERVICES_CRITICAL_THRESHOLD = 0.3  # 30% failed services = critical
HEALTH_SCORE_HEALTHY_THRESHOLD = 80
HEALTH_SCORE_DEGRADED_THRESHOLD = 50
COMPONENT_SCORES = {
    "healthy": 100,
    "degraded": 60,
    "critical": 20,
    "unknown": 50,
    "active": 80,
    "none": 100,
    "no_nodes": 0,
}


def _assess_fleet_health(
    nodes: List[Node], online: List[Node], degraded: List[Node], offline: List[Node]
) -> tuple:
    """Assess fleet component health and issues. Related to Issue #729."""
    issues = []
    if len(online) == len(nodes):
        status = "healthy"
    elif len(offline) == len(nodes):
        status = "critical"
        issues.append(f"All {len(nodes)} nodes are offline")
    elif len(offline) > 0:
        status = "degraded"
        issues.append(f"{len(offline)} node(s) offline")
    else:
        status = "healthy"
    if degraded:
        issues.append(f"{len(degraded)} node(s) in degraded state")
    return status, issues


def _assess_services_health(service_stats: Dict[str, int]) -> tuple:
    """Assess services component health. Related to Issue #729."""
    failed = service_stats.get(ServiceStatus.FAILED.value, 0)
    total = sum(service_stats.values())
    issues = []
    if total == 0:
        return "unknown", issues
    if failed == 0:
        return "healthy", issues
    if failed / total > FAILED_SERVICES_CRITICAL_THRESHOLD:
        issues.append(f"{failed} services in failed state")
        return "critical", issues
    if failed > 0:
        issues.append(f"{failed} service(s) failed")
        return "degraded", issues
    return "healthy", issues


def _calculate_overall_health(components: Dict[str, str]) -> tuple:
    """Calculate overall health status and score. Related to Issue #729."""
    scores = [COMPONENT_SCORES.get(s, 50) for s in components.values()]
    health_score = sum(scores) / len(scores) if scores else 0
    if health_score >= HEALTH_SCORE_HEALTHY_THRESHOLD:
        return "healthy", health_score
    if health_score >= HEALTH_SCORE_DEGRADED_THRESHOLD:
        return "degraded", health_score
    return "critical", health_score


@router.get("/health", response_model=SystemHealthResponse)
async def get_system_health(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> SystemHealthResponse:
    """Get overall system health assessment."""
    result = await db.execute(select(Node))
    nodes = result.scalars().all()

    if not nodes:
        return SystemHealthResponse(
            overall_status="unknown",
            health_score=0.0,
            components={"fleet": "no_nodes"},
            issues=["No nodes registered in the fleet"],
        )

    # Categorize nodes
    online = [n for n in nodes if n.status == NodeStatus.ONLINE.value]
    degraded = [n for n in nodes if n.status == NodeStatus.DEGRADED.value]
    offline = [
        n
        for n in nodes
        if n.status in [NodeStatus.OFFLINE.value, NodeStatus.ERROR.value]
    ]

    issues = []
    components = {}

    # Assess fleet health
    components["fleet"], fleet_issues = _assess_fleet_health(
        nodes, online, degraded, offline
    )
    issues.extend(fleet_issues)

    # Assess services health
    svc_result = await db.execute(
        select(Service.status, func.count(Service.id).label("count")).group_by(
            Service.status
        )
    )
    service_stats = {row.status: row.count for row in svc_result}
    components["services"], svc_issues = _assess_services_health(service_stats)
    issues.extend(svc_issues)

    # Check recent failed deployments
    recent_cutoff = datetime.utcnow() - timedelta(hours=1)
    deploy_result = await db.execute(
        select(Deployment).where(
            Deployment.created_at >= recent_cutoff,
            Deployment.status == DeploymentStatus.FAILED.value,
        )
    )
    failed_deploys = len(deploy_result.scalars().all())
    components["deployments"] = "degraded" if failed_deploys > 0 else "healthy"
    if failed_deploys > 0:
        issues.append(f"{failed_deploys} deployment(s) failed in last hour")

    # Check active maintenance windows
    now = datetime.utcnow()
    maint_result = await db.execute(
        select(MaintenanceWindow).where(
            MaintenanceWindow.start_time <= now,
            MaintenanceWindow.end_time >= now,
            MaintenanceWindow.status == "active",
        )
    )
    active_maint = len(maint_result.scalars().all())
    components["maintenance"] = "active" if active_maint > 0 else "none"
    if active_maint > 0:
        issues.append(f"{active_maint} active maintenance window(s)")

    overall_status, health_score = _calculate_overall_health(components)

    return SystemHealthResponse(
        overall_status=overall_status,
        health_score=health_score,
        components=components,
        issues=issues,
    )


@router.get("/dashboard", response_model=DashboardOverview)
async def get_dashboard_overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> DashboardOverview:
    """Get comprehensive dashboard overview data."""
    # Get fleet metrics
    fleet_metrics = await get_fleet_metrics(db, _)

    # Get recent alerts (last 24 hours)
    alerts_response = await get_alerts(db, _, severity=None, hours=24)

    # Get health summary
    health_summary = await get_system_health(db, _)

    # Count recent deployments (last 24 hours)
    cutoff = datetime.utcnow() - timedelta(hours=24)
    deploy_result = await db.execute(
        select(func.count(Deployment.id)).where(Deployment.created_at >= cutoff)
    )
    recent_deployments = deploy_result.scalar() or 0

    # Count active maintenance
    now = datetime.utcnow()
    maint_result = await db.execute(
        select(func.count(MaintenanceWindow.id)).where(
            MaintenanceWindow.start_time <= now,
            MaintenanceWindow.end_time >= now,
            MaintenanceWindow.status.in_(["scheduled", "active"]),
        )
    )
    active_maintenance = maint_result.scalar() or 0

    return DashboardOverview(
        fleet_metrics=fleet_metrics,
        recent_alerts=alerts_response.alerts[:10],
        recent_deployments=recent_deployments,
        active_maintenance=active_maintenance,
        health_summary=health_summary,
    )


def _apply_log_filters(
    query, node_id: Optional[str], event_type: Optional[str], severity: Optional[str]
):
    """Apply optional filters to log query. Related to Issue #729."""
    if node_id:
        query = query.where(NodeEvent.node_id == node_id)
    if event_type:
        query = query.where(NodeEvent.event_type == event_type)
    if severity:
        query = query.where(NodeEvent.severity == severity)
    return query


def _events_to_log_entries(events: List[Any], nodes: Dict[str, Any]) -> List[LogEntry]:
    """Convert NodeEvent list to LogEntry list. Related to Issue #729."""
    return [
        LogEntry(
            event_id=e.event_id,
            node_id=e.node_id,
            hostname=_get_hostname(nodes, e.node_id),
            event_type=e.event_type,
            severity=e.severity,
            message=e.message,
            timestamp=e.created_at,
        )
        for e in events
    ]


@router.get("/logs", response_model=LogsResponse)
async def get_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> LogsResponse:
    """Query logs/events across the fleet."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Build and apply filters to both queries
    base_query = select(NodeEvent).where(NodeEvent.created_at >= cutoff)
    query = _apply_log_filters(base_query, node_id, event_type, severity)

    count_base = select(func.count(NodeEvent.id)).where(NodeEvent.created_at >= cutoff)
    count_query = _apply_log_filters(count_base, node_id, event_type, severity)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginate and execute
    query = (
        query.order_by(NodeEvent.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(query)
    events = result.scalars().all()

    # Get node hostnames
    node_ids = list(set(e.node_id for e in events))
    nodes_result = (
        await db.execute(select(Node).where(Node.node_id.in_(node_ids)))
        if node_ids
        else None
    )
    nodes = {n.node_id: n for n in nodes_result.scalars().all()} if nodes_result else {}

    return LogsResponse(
        logs=_events_to_log_entries(events, nodes),
        total=total,
        page=page,
        per_page=per_page,
    )


def _group_errors_by_type_and_node(errors: List[Any]) -> tuple:
    """Group errors by type and node_id. Related to Issue #729."""
    by_type: Dict[str, int] = {}
    by_node: Dict[str, int] = {}
    for e in errors:
        by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
        by_node[e.node_id] = by_node.get(e.node_id, 0) + 1
    return by_type, by_node


def _format_recent_errors(
    errors: List[Any], nodes: Dict[str, str]
) -> List[Dict[str, Any]]:
    """Format recent errors for response. Related to Issue #729."""
    return [
        {
            "event_id": e.event_id,
            "node_id": e.node_id,
            "hostname": nodes.get(e.node_id, e.node_id),
            "event_type": e.event_type,
            "message": e.message,
            "timestamp": e.created_at.isoformat(),
        }
        for e in errors[:MAX_RECENT_ERRORS]
    ]


@router.get("/errors", deprecated=True)
async def get_errors(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    hours: int = Query(24, ge=1, le=168),
) -> Dict[str, Any]:
    """Get error summary and distribution.

    DEPRECATED: Use /api/errors/* endpoints instead for comprehensive error monitoring.
    - GET /api/errors/statistics - Overall statistics with trends
    - GET /api/errors/recent - Paginated error list with resolution status
    - GET /api/errors/categories - Error breakdown by type
    - GET /api/errors/components - Errors by node
    - POST /api/errors/metrics/resolve/{event_id} - Mark errors resolved
    """
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    result = await db.execute(
        select(NodeEvent)
        .where(
            NodeEvent.created_at >= cutoff,
            NodeEvent.severity.in_(
                [EventSeverity.ERROR.value, EventSeverity.CRITICAL.value]
            ),
        )
        .order_by(NodeEvent.created_at.desc())
    )
    errors = result.scalars().all()

    by_type, by_node = _group_errors_by_type_and_node(errors)
    nodes = await _get_node_hostname_map(db, list(by_node.keys()))
    by_hostname = {nodes.get(k, k): v for k, v in by_node.items()}

    return {
        "total_errors": len(errors),
        "by_type": by_type,
        "by_node": by_hostname,
        "recent_errors": _format_recent_errors(errors, nodes),
        "time_window_hours": hours,
    }
