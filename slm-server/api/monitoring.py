# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Monitoring API Routes

API endpoints for fleet-wide monitoring, metrics aggregation, and alerts.
Related to Issue #729.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from typing_extensions import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import (
    Node,
    NodeStatus,
    Service,
    ServiceStatus,
    NodeEvent,
    EventSeverity,
    Deployment,
    DeploymentStatus,
    MaintenanceWindow,
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
# API Endpoints
# =============================================================================


@router.get("/metrics/fleet", response_model=FleetMetricsResponse)
async def get_fleet_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> FleetMetricsResponse:
    """Get aggregated metrics for the entire fleet."""
    # Get all nodes
    result = await db.execute(select(Node))
    nodes = result.scalars().all()

    if not nodes:
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

    # Count services per node
    services_result = await db.execute(
        select(
            Service.node_id,
            Service.status,
            func.count(Service.id).label("count"),
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

    # Calculate fleet metrics
    online_count = sum(1 for n in nodes if n.status == NodeStatus.ONLINE.value)
    degraded_count = sum(1 for n in nodes if n.status == NodeStatus.DEGRADED.value)
    offline_count = sum(
        1 for n in nodes
        if n.status in [NodeStatus.OFFLINE.value, NodeStatus.ERROR.value]
    )

    cpu_values = [n.cpu_percent for n in nodes if n.cpu_percent is not None]
    mem_values = [n.memory_percent for n in nodes if n.memory_percent is not None]
    disk_values = [n.disk_percent for n in nodes if n.disk_percent is not None]

    # Get total service counts
    total_services = sum(
        services_by_node.get(n.node_id, {}).get("running", 0) +
        services_by_node.get(n.node_id, {}).get("failed", 0)
        for n in nodes
    )
    running_services = sum(
        services_by_node.get(n.node_id, {}).get("running", 0)
        for n in nodes
    )
    failed_services = sum(
        services_by_node.get(n.node_id, {}).get("failed", 0)
        for n in nodes
    )

    node_metrics = [
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

    return FleetMetricsResponse(
        total_nodes=len(nodes),
        online_nodes=online_count,
        degraded_nodes=degraded_count,
        offline_nodes=offline_count,
        avg_cpu_percent=sum(cpu_values) / len(cpu_values) if cpu_values else 0.0,
        avg_memory_percent=sum(mem_values) / len(mem_values) if mem_values else 0.0,
        avg_disk_percent=sum(disk_values) / len(disk_values) if disk_values else 0.0,
        total_services=total_services,
        running_services=running_services,
        failed_services=failed_services,
        nodes=node_metrics,
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


@router.get("/alerts", response_model=AlertsResponse)
async def get_alerts(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    severity: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168),
) -> AlertsResponse:
    """Get alerts from node events within the specified time window."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Query events that represent alerts (errors, warnings, failures)
    query = select(NodeEvent).where(
        NodeEvent.created_at >= cutoff,
        NodeEvent.severity.in_([
            EventSeverity.WARNING.value,
            EventSeverity.ERROR.value,
            EventSeverity.CRITICAL.value,
        ]),
    )

    if severity:
        query = query.where(NodeEvent.severity == severity)

    query = query.order_by(NodeEvent.created_at.desc())

    result = await db.execute(query)
    events = result.scalars().all()

    # Get node info for hostnames
    node_ids = list(set(e.node_id for e in events))
    if node_ids:
        nodes_result = await db.execute(
            select(Node).where(Node.node_id.in_(node_ids))
        )
        nodes = {n.node_id: n for n in nodes_result.scalars().all()}
    else:
        nodes = {}

    alerts = [
        AlertItem(
            alert_id=e.event_id,
            severity=e.severity,
            category=e.event_type,
            message=e.message,
            node_id=e.node_id,
            hostname=nodes.get(e.node_id, type("", (), {"hostname": "unknown"})).hostname,
            timestamp=e.created_at,
        )
        for e in events
    ]

    critical_count = sum(1 for a in alerts if a.severity == EventSeverity.CRITICAL.value)
    warning_count = sum(1 for a in alerts if a.severity == EventSeverity.WARNING.value)
    info_count = sum(1 for a in alerts if a.severity == EventSeverity.INFO.value)

    return AlertsResponse(
        total_count=len(alerts),
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
        alerts=alerts[:100],  # Limit to 100 most recent
    )


@router.get("/health", response_model=SystemHealthResponse)
async def get_system_health(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> SystemHealthResponse:
    """Get overall system health assessment."""
    issues = []
    components = {}

    # Check nodes
    result = await db.execute(select(Node))
    nodes = result.scalars().all()

    if not nodes:
        return SystemHealthResponse(
            overall_status="unknown",
            health_score=0.0,
            components={"fleet": "no_nodes"},
            issues=["No nodes registered in the fleet"],
        )

    online_nodes = [n for n in nodes if n.status == NodeStatus.ONLINE.value]
    degraded_nodes = [n for n in nodes if n.status == NodeStatus.DEGRADED.value]
    offline_nodes = [
        n for n in nodes
        if n.status in [NodeStatus.OFFLINE.value, NodeStatus.ERROR.value]
    ]

    # Calculate fleet health
    if len(online_nodes) == len(nodes):
        components["fleet"] = "healthy"
    elif len(offline_nodes) == len(nodes):
        components["fleet"] = "critical"
        issues.append(f"All {len(nodes)} nodes are offline")
    elif len(offline_nodes) > 0:
        components["fleet"] = "degraded"
        issues.append(f"{len(offline_nodes)} node(s) offline")
    else:
        components["fleet"] = "healthy"

    if degraded_nodes:
        issues.append(f"{len(degraded_nodes)} node(s) in degraded state")

    # Check services
    services_result = await db.execute(
        select(Service.status, func.count(Service.id).label("count"))
        .group_by(Service.status)
    )
    service_stats = {row.status: row.count for row in services_result}
    failed_services = service_stats.get(ServiceStatus.FAILED.value, 0)
    running_services = service_stats.get(ServiceStatus.RUNNING.value, 0)
    total_services = sum(service_stats.values())

    if total_services == 0:
        components["services"] = "unknown"
    elif failed_services == 0:
        components["services"] = "healthy"
    elif failed_services / total_services > 0.3:
        components["services"] = "critical"
        issues.append(f"{failed_services} services in failed state")
    elif failed_services > 0:
        components["services"] = "degraded"
        issues.append(f"{failed_services} service(s) failed")
    else:
        components["services"] = "healthy"

    # Check recent deployments
    recent_cutoff = datetime.utcnow() - timedelta(hours=1)
    deploy_result = await db.execute(
        select(Deployment).where(
            Deployment.created_at >= recent_cutoff,
            Deployment.status == DeploymentStatus.FAILED.value,
        )
    )
    failed_deploys = len(deploy_result.scalars().all())
    if failed_deploys > 0:
        components["deployments"] = "degraded"
        issues.append(f"{failed_deploys} deployment(s) failed in last hour")
    else:
        components["deployments"] = "healthy"

    # Check maintenance windows
    now = datetime.utcnow()
    maint_result = await db.execute(
        select(MaintenanceWindow).where(
            MaintenanceWindow.start_time <= now,
            MaintenanceWindow.end_time >= now,
            MaintenanceWindow.status == "active",
        )
    )
    active_maint = len(maint_result.scalars().all())
    if active_maint > 0:
        components["maintenance"] = "active"
        issues.append(f"{active_maint} active maintenance window(s)")
    else:
        components["maintenance"] = "none"

    # Calculate overall status and score
    component_scores = {
        "healthy": 100,
        "degraded": 60,
        "critical": 20,
        "unknown": 50,
        "active": 80,
        "none": 100,
        "no_nodes": 0,
    }

    scores = [
        component_scores.get(status, 50)
        for status in components.values()
    ]
    health_score = sum(scores) / len(scores) if scores else 0

    if health_score >= 80:
        overall_status = "healthy"
    elif health_score >= 50:
        overall_status = "degraded"
    else:
        overall_status = "critical"

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

    query = select(NodeEvent).where(NodeEvent.created_at >= cutoff)

    if node_id:
        query = query.where(NodeEvent.node_id == node_id)
    if event_type:
        query = query.where(NodeEvent.event_type == event_type)
    if severity:
        query = query.where(NodeEvent.severity == severity)

    # Count total
    count_query = select(func.count(NodeEvent.id)).where(NodeEvent.created_at >= cutoff)
    if node_id:
        count_query = count_query.where(NodeEvent.node_id == node_id)
    if event_type:
        count_query = count_query.where(NodeEvent.event_type == event_type)
    if severity:
        count_query = count_query.where(NodeEvent.severity == severity)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginate
    query = query.order_by(NodeEvent.created_at.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(query)
    events = result.scalars().all()

    # Get node info
    node_ids = list(set(e.node_id for e in events))
    if node_ids:
        nodes_result = await db.execute(
            select(Node).where(Node.node_id.in_(node_ids))
        )
        nodes = {n.node_id: n for n in nodes_result.scalars().all()}
    else:
        nodes = {}

    logs = [
        LogEntry(
            event_id=e.event_id,
            node_id=e.node_id,
            hostname=nodes.get(e.node_id, type("", (), {"hostname": "unknown"})).hostname,
            event_type=e.event_type,
            severity=e.severity,
            message=e.message,
            timestamp=e.created_at,
        )
        for e in events
    ]

    return LogsResponse(
        logs=logs,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/errors")
async def get_errors(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    hours: int = Query(24, ge=1, le=168),
) -> Dict[str, Any]:
    """Get error summary and distribution."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    # Query error events
    result = await db.execute(
        select(NodeEvent).where(
            NodeEvent.created_at >= cutoff,
            NodeEvent.severity.in_([
                EventSeverity.ERROR.value,
                EventSeverity.CRITICAL.value,
            ]),
        ).order_by(NodeEvent.created_at.desc())
    )
    errors = result.scalars().all()

    # Group by type
    by_type: Dict[str, int] = {}
    by_node: Dict[str, int] = {}
    for e in errors:
        by_type[e.event_type] = by_type.get(e.event_type, 0) + 1
        by_node[e.node_id] = by_node.get(e.node_id, 0) + 1

    # Get node hostnames
    if by_node:
        nodes_result = await db.execute(
            select(Node).where(Node.node_id.in_(list(by_node.keys())))
        )
        nodes = {n.node_id: n.hostname for n in nodes_result.scalars().all()}
    else:
        nodes = {}

    by_hostname = {nodes.get(k, k): v for k, v in by_node.items()}

    return {
        "total_errors": len(errors),
        "by_type": by_type,
        "by_node": by_hostname,
        "recent_errors": [
            {
                "event_id": e.event_id,
                "node_id": e.node_id,
                "hostname": nodes.get(e.node_id, e.node_id),
                "event_type": e.event_type,
                "message": e.message,
                "timestamp": e.created_at.isoformat(),
            }
            for e in errors[:20]
        ],
        "time_window_hours": hours,
    }
