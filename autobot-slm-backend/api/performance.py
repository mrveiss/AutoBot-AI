# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Performance Monitoring API Routes

Comprehensive performance monitoring: distributed tracing, SLO management,
alert rules, and Prometheus-compatible metrics export.
Issue #752 - Comprehensive Performance Monitoring.
"""

import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from models.database import AlertRule, Node, PerformanceTrace, SLODefinition, TraceSpan
from pydantic import BaseModel, Field
from services.auth import get_current_user
from services.database import get_db
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/performance", tags=["performance"])


# =============================================================================
# Response Models
# =============================================================================


class TraceSpanModel(BaseModel):
    """Trace span data model."""

    span_id: str
    trace_id: str
    parent_span_id: Optional[str] = None
    name: str
    service_name: str
    node_id: Optional[str] = None
    status: str
    duration_ms: float
    start_time: datetime
    end_time: datetime
    attributes: Optional[Dict[str, Any]] = None


class PerformanceTraceModel(BaseModel):
    """Performance trace data model."""

    trace_id: str
    name: str
    source_node_id: Optional[str] = None
    status: str
    duration_ms: float
    span_count: int
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    created_at: datetime


class TraceDetailResponse(BaseModel):
    """Detailed trace with all spans."""

    trace: PerformanceTraceModel
    spans: List[TraceSpanModel]


class TracesListResponse(BaseModel):
    """Paginated trace list response."""

    traces: List[PerformanceTraceModel]
    total: int
    page: int
    per_page: int


class SLOModel(BaseModel):
    """SLO definition model."""

    slo_id: str
    name: str
    description: Optional[str] = None
    target_percent: float
    metric_type: str
    threshold_value: float
    threshold_unit: str
    window_days: int
    node_id: Optional[str] = None
    enabled: bool
    current_compliance: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class SLOCreateRequest(BaseModel):
    """SLO creation request."""

    name: str
    description: Optional[str] = None
    target_percent: float = Field(ge=0, le=100)
    metric_type: str
    threshold_value: float
    threshold_unit: str
    window_days: int = 30
    node_id: Optional[str] = None
    enabled: bool = True


class AlertRuleModel(BaseModel):
    """Alert rule model."""

    rule_id: str
    name: str
    description: Optional[str] = None
    metric_type: str
    condition: str
    threshold: float
    duration_seconds: int
    severity: str
    node_id: Optional[str] = None
    notification_channels: Optional[List[str]] = None
    enabled: bool
    last_triggered: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class AlertRuleCreateRequest(BaseModel):
    """Alert rule creation request."""

    name: str
    description: Optional[str] = None
    metric_type: str
    condition: str = Field(pattern="^(gt|lt|gte|lte|eq)$")
    threshold: float
    duration_seconds: int = 300
    severity: str = "warning"
    node_id: Optional[str] = None
    notification_channels: Optional[List[str]] = None
    enabled: bool = True


class AlertRuleUpdateRequest(BaseModel):
    """Alert rule update request."""

    name: Optional[str] = None
    description: Optional[str] = None
    metric_type: Optional[str] = None
    condition: Optional[str] = Field(None, pattern="^(gt|lt|gte|lte|eq)$")
    threshold: Optional[float] = None
    duration_seconds: Optional[int] = None
    severity: Optional[str] = None
    node_id: Optional[str] = None
    notification_channels: Optional[List[str]] = None
    enabled: Optional[bool] = None


class NodeMetricsResponse(BaseModel):
    """Per-node performance metrics."""

    node_id: str
    hostname: str
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    error_rate_percent: float
    throughput_rpm: float
    total_traces: int


class PerformanceOverviewResponse(BaseModel):
    """Overall performance overview."""

    avg_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    throughput_rpm: float
    error_rate_percent: float
    total_traces: int
    active_slos: int
    slo_compliance_percent: float
    top_slow_traces: List[Dict[str, Any]]


# =============================================================================
# Helper Functions (Issue #752)
# =============================================================================


def _parse_json_field(value: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse JSON string field to dict. Helper for performance.py (Issue #752)."""
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _serialize_json_field(value: Optional[Any]) -> Optional[str]:
    """Serialize value to JSON string. Helper for performance.py (Issue #752)."""
    if not value:
        return None
    try:
        return json.dumps(value)
    except (TypeError, ValueError):
        return None


def _calculate_percentile(values: List[float], percentile: int) -> float:
    """Calculate percentile from sorted values. Helper for performance.py (Issue #752)."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    index = int(len(sorted_vals) * percentile / 100)
    return sorted_vals[min(index, len(sorted_vals) - 1)]


async def _get_node_hostname(db: AsyncSession, node_id: str) -> str:
    """Get hostname for node_id. Helper for performance.py (Issue #752)."""
    result = await db.execute(select(Node.hostname).where(Node.node_id == node_id))
    hostname = result.scalar_one_or_none()
    return hostname or node_id


def _trace_to_model(trace: PerformanceTrace) -> PerformanceTraceModel:
    """Convert PerformanceTrace to model. Helper for performance.py (Issue #752)."""
    return PerformanceTraceModel(
        trace_id=trace.trace_id,
        name=trace.name,
        source_node_id=trace.source_node_id,
        status=trace.status,
        duration_ms=trace.duration_ms,
        span_count=trace.span_count,
        error_message=trace.error_message,
        metadata=_parse_json_field(trace.metadata_json),
        created_at=trace.created_at,
    )


def _span_to_model(span: TraceSpan) -> TraceSpanModel:
    """Convert TraceSpan to model. Helper for performance.py (Issue #752)."""
    return TraceSpanModel(
        span_id=span.span_id,
        trace_id=span.trace_id,
        parent_span_id=span.parent_span_id,
        name=span.name,
        service_name=span.service_name,
        node_id=span.node_id,
        status=span.status,
        duration_ms=span.duration_ms,
        start_time=span.start_time,
        end_time=span.end_time,
        attributes=_parse_json_field(span.attributes_json),
    )


def _slo_to_model(slo: SLODefinition, compliance: Optional[float]) -> SLOModel:
    """Convert SLODefinition to model. Helper for performance.py (Issue #752)."""
    return SLOModel(
        slo_id=slo.slo_id,
        name=slo.name,
        description=slo.description,
        target_percent=slo.target_percent,
        metric_type=slo.metric_type,
        threshold_value=slo.threshold_value,
        threshold_unit=slo.threshold_unit,
        window_days=slo.window_days,
        node_id=slo.node_id,
        enabled=slo.enabled,
        current_compliance=compliance,
        created_at=slo.created_at,
        updated_at=slo.updated_at,
    )


def _alert_rule_to_model(rule: AlertRule) -> AlertRuleModel:
    """Convert AlertRule to model. Helper for performance.py (Issue #752)."""
    channels = None
    if rule.notification_channels:
        try:
            channels = json.loads(rule.notification_channels)
        except json.JSONDecodeError:
            channels = None
    return AlertRuleModel(
        rule_id=rule.rule_id,
        name=rule.name,
        description=rule.description,
        metric_type=rule.metric_type,
        condition=rule.condition,
        threshold=rule.threshold,
        duration_seconds=rule.duration_seconds,
        severity=rule.severity,
        node_id=rule.node_id,
        notification_channels=channels,
        enabled=rule.enabled,
        last_triggered=rule.last_triggered,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


async def _calculate_slo_compliance(
    db: AsyncSession, slo: SLODefinition
) -> Optional[float]:
    """Calculate SLO compliance percentage. Helper for performance.py (Issue #752)."""
    cutoff = datetime.utcnow() - timedelta(days=slo.window_days)
    query = select(PerformanceTrace).where(PerformanceTrace.created_at >= cutoff)
    if slo.node_id:
        query = query.where(PerformanceTrace.source_node_id == slo.node_id)

    result = await db.execute(query)
    traces = result.scalars().all()

    if not traces:
        return None

    if slo.metric_type == "latency":
        compliant = sum(1 for t in traces if t.duration_ms <= slo.threshold_value)
    elif slo.metric_type == "availability":
        compliant = sum(1 for t in traces if t.status == "ok")
    elif slo.metric_type == "error_rate":
        error_count = sum(1 for t in traces if t.status == "error")
        error_rate = (error_count / len(traces)) * 100
        compliant = sum(1 for _ in [error_rate] if error_rate <= slo.threshold_value)
        return (compliant / 1) * 100 if compliant else 0.0
    else:
        return None

    return (compliant / len(traces)) * 100


def _generate_prometheus_metrics(
    traces: List[PerformanceTrace], slos: List[SLODefinition]
) -> str:
    """Generate Prometheus text format. Helper for performance.py (Issue #752)."""
    lines = []
    lines.append("# HELP autobot_trace_duration_ms Trace duration in milliseconds")
    lines.append("# TYPE autobot_trace_duration_ms histogram")

    for trace in traces[:100]:
        labels = f'{{trace_id="{trace.trace_id}",status="{trace.status}"}}'
        lines.append(f"autobot_trace_duration_ms{labels} {trace.duration_ms}")

    lines.append("# HELP autobot_slo_compliance_percent SLO compliance percentage")
    lines.append("# TYPE autobot_slo_compliance_percent gauge")

    for slo in slos:
        if slo.enabled:
            labels = f'{{slo_id="{slo.slo_id}",name="{slo.name}"}}'
            lines.append(f"autobot_slo_compliance_percent{labels} 0")

    return "\n".join(lines)


def _build_empty_overview() -> PerformanceOverviewResponse:
    """Build empty performance overview. Helper for performance.py (Issue #752)."""
    return PerformanceOverviewResponse(
        avg_latency_ms=0.0,
        p95_latency_ms=0.0,
        p99_latency_ms=0.0,
        throughput_rpm=0.0,
        error_rate_percent=0.0,
        total_traces=0,
        active_slos=0,
        slo_compliance_percent=0.0,
        top_slow_traces=[],
    )


async def _fetch_active_slos_count(db: AsyncSession) -> int:
    """Fetch count of active SLOs. Helper for performance.py (Issue #752)."""
    result = await db.execute(
        select(SLODefinition).where(SLODefinition.enabled.is_(True))
    )
    return len(result.scalars().all())


async def _fetch_top_slow_traces(
    db: AsyncSession, cutoff: datetime, limit: int
) -> List[Dict[str, Any]]:
    """Fetch top slow traces. Helper for performance.py (Issue #752)."""
    result = await db.execute(
        select(PerformanceTrace)
        .where(PerformanceTrace.created_at >= cutoff)
        .order_by(desc(PerformanceTrace.duration_ms))
        .limit(limit)
    )
    traces = result.scalars().all()
    return [
        {"trace_id": t.trace_id, "name": t.name, "duration_ms": t.duration_ms}
        for t in traces
    ]


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/overview", response_model=PerformanceOverviewResponse)
async def get_performance_overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    hours: int = Query(24, ge=1, le=168),
) -> PerformanceOverviewResponse:
    """Get performance overview with aggregated metrics."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(PerformanceTrace).where(PerformanceTrace.created_at >= cutoff)
    )
    traces = result.scalars().all()

    if not traces:
        return _build_empty_overview()

    durations = [t.duration_ms for t in traces]
    errors = sum(1 for t in traces if t.status == "error")
    time_span_minutes = (datetime.utcnow() - cutoff).total_seconds() / 60

    active_slos = await _fetch_active_slos_count(db)
    top_slow_traces = await _fetch_top_slow_traces(db, cutoff, 10)

    return PerformanceOverviewResponse(
        avg_latency_ms=sum(durations) / len(durations),
        p95_latency_ms=_calculate_percentile(durations, 95),
        p99_latency_ms=_calculate_percentile(durations, 99),
        throughput_rpm=len(traces) / time_span_minutes
        if time_span_minutes > 0
        else 0.0,
        error_rate_percent=(errors / len(traces)) * 100,
        total_traces=len(traces),
        active_slos=active_slos,
        slo_compliance_percent=100.0,
        top_slow_traces=top_slow_traces,
    )


@router.get("/traces", response_model=TracesListResponse)
async def get_traces(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    hours: int = Query(24, ge=1, le=168),
    status_filter: Optional[str] = Query(None, alias="status"),
    node_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> TracesListResponse:
    """Get paginated list of traces with optional filters."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    query = select(PerformanceTrace).where(PerformanceTrace.created_at >= cutoff)

    if status_filter:
        query = query.where(PerformanceTrace.status == status_filter)
    if node_id:
        query = query.where(PerformanceTrace.source_node_id == node_id)

    count_result = await db.execute(
        select(func.count(PerformanceTrace.id)).select_from(query.subquery())
    )
    total = count_result.scalar() or 0

    query = query.order_by(desc(PerformanceTrace.created_at))
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    traces = result.scalars().all()

    return TracesListResponse(
        traces=[_trace_to_model(t) for t in traces],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/traces/{trace_id}", response_model=TraceDetailResponse)
async def get_trace_detail(
    trace_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> TraceDetailResponse:
    """Get detailed trace with all spans."""
    trace_result = await db.execute(
        select(PerformanceTrace).where(PerformanceTrace.trace_id == trace_id)
    )
    trace = trace_result.scalar_one_or_none()

    if not trace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Trace {trace_id} not found",
        )

    spans_result = await db.execute(
        select(TraceSpan).where(TraceSpan.trace_id == trace_id)
    )
    spans = spans_result.scalars().all()

    return TraceDetailResponse(
        trace=_trace_to_model(trace), spans=[_span_to_model(s) for s in spans]
    )


@router.get("/slos", response_model=List[SLOModel])
async def get_slos(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> List[SLOModel]:
    """Get all SLO definitions with current compliance."""
    result = await db.execute(select(SLODefinition))
    slos = result.scalars().all()

    slo_models = []
    for slo in slos:
        compliance = await _calculate_slo_compliance(db, slo)
        slo_models.append(_slo_to_model(slo, compliance))

    return slo_models


@router.post("/slos", response_model=SLOModel, status_code=status.HTTP_201_CREATED)
async def create_slo(
    request: SLOCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> SLOModel:
    """Create a new SLO definition."""
    slo = SLODefinition(
        slo_id=str(uuid.uuid4()),
        name=request.name,
        description=request.description,
        target_percent=request.target_percent,
        metric_type=request.metric_type,
        threshold_value=request.threshold_value,
        threshold_unit=request.threshold_unit,
        window_days=request.window_days,
        node_id=request.node_id,
        enabled=request.enabled,
    )

    db.add(slo)
    await db.commit()
    await db.refresh(slo)

    compliance = await _calculate_slo_compliance(db, slo)
    return _slo_to_model(slo, compliance)


@router.delete("/slos/{slo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slo(
    slo_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """Delete an SLO definition."""
    result = await db.execute(
        select(SLODefinition).where(SLODefinition.slo_id == slo_id)
    )
    slo = result.scalar_one_or_none()

    if not slo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SLO {slo_id} not found",
        )

    await db.delete(slo)
    await db.commit()


@router.get("/alerts/rules", response_model=List[AlertRuleModel])
async def get_alert_rules(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> List[AlertRuleModel]:
    """Get all alert rules."""
    result = await db.execute(select(AlertRule))
    rules = result.scalars().all()
    return [_alert_rule_to_model(r) for r in rules]


@router.post(
    "/alerts/rules", response_model=AlertRuleModel, status_code=status.HTTP_201_CREATED
)
async def create_alert_rule(
    request: AlertRuleCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AlertRuleModel:
    """Create a new alert rule."""
    rule = AlertRule(
        rule_id=str(uuid.uuid4()),
        name=request.name,
        description=request.description,
        metric_type=request.metric_type,
        condition=request.condition,
        threshold=request.threshold,
        duration_seconds=request.duration_seconds,
        severity=request.severity,
        node_id=request.node_id,
        notification_channels=_serialize_json_field(request.notification_channels),
        enabled=request.enabled,
    )

    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return _alert_rule_to_model(rule)


@router.put("/alerts/rules/{rule_id}", response_model=AlertRuleModel)
async def update_alert_rule(
    rule_id: str,
    request: AlertRuleUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AlertRuleModel:
    """Update an existing alert rule."""
    result = await db.execute(select(AlertRule).where(AlertRule.rule_id == rule_id))
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert rule {rule_id} not found",
        )

    if request.name is not None:
        rule.name = request.name
    if request.description is not None:
        rule.description = request.description
    if request.metric_type is not None:
        rule.metric_type = request.metric_type
    if request.condition is not None:
        rule.condition = request.condition
    if request.threshold is not None:
        rule.threshold = request.threshold
    if request.duration_seconds is not None:
        rule.duration_seconds = request.duration_seconds
    if request.severity is not None:
        rule.severity = request.severity
    if request.node_id is not None:
        rule.node_id = request.node_id
    if request.notification_channels is not None:
        rule.notification_channels = _serialize_json_field(
            request.notification_channels
        )
    if request.enabled is not None:
        rule.enabled = request.enabled

    await db.commit()
    await db.refresh(rule)
    return _alert_rule_to_model(rule)


@router.delete("/alerts/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert_rule(
    rule_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """Delete an alert rule."""
    result = await db.execute(select(AlertRule).where(AlertRule.rule_id == rule_id))
    rule = result.scalar_one_or_none()

    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert rule {rule_id} not found",
        )

    await db.delete(rule)
    await db.commit()


@router.get("/metrics/node/{node_id}", response_model=NodeMetricsResponse)
async def get_node_metrics(
    node_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    hours: int = Query(24, ge=1, le=168),
) -> NodeMetricsResponse:
    """Get performance metrics for a specific node."""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    result = await db.execute(
        select(PerformanceTrace).where(
            PerformanceTrace.source_node_id == node_id,
            PerformanceTrace.created_at >= cutoff,
        )
    )
    traces = result.scalars().all()

    if not traces:
        hostname = await _get_node_hostname(db, node_id)
        return NodeMetricsResponse(
            node_id=node_id,
            hostname=hostname,
            avg_latency_ms=0.0,
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
            p99_latency_ms=0.0,
            error_rate_percent=0.0,
            throughput_rpm=0.0,
            total_traces=0,
        )

    durations = [t.duration_ms for t in traces]
    errors = sum(1 for t in traces if t.status == "error")
    time_span_minutes = (datetime.utcnow() - cutoff).total_seconds() / 60
    hostname = await _get_node_hostname(db, node_id)

    return NodeMetricsResponse(
        node_id=node_id,
        hostname=hostname,
        avg_latency_ms=sum(durations) / len(durations),
        p50_latency_ms=_calculate_percentile(durations, 50),
        p95_latency_ms=_calculate_percentile(durations, 95),
        p99_latency_ms=_calculate_percentile(durations, 99),
        error_rate_percent=(errors / len(traces)) * 100,
        throughput_rpm=len(traces) / time_span_minutes
        if time_span_minutes > 0
        else 0.0,
        total_traces=len(traces),
    )


@router.get("/metrics/prometheus")
async def get_prometheus_metrics(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Export metrics in Prometheus text format."""
    cutoff = datetime.utcnow() - timedelta(hours=1)
    traces_result = await db.execute(
        select(PerformanceTrace).where(PerformanceTrace.created_at >= cutoff)
    )
    traces = traces_result.scalars().all()

    slos_result = await db.execute(select(SLODefinition))
    slos = slos_result.scalars().all()

    metrics_text = _generate_prometheus_metrics(traces, slos)
    return Response(content=metrics_text, media_type="text/plain")
