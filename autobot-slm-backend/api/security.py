# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Security API Routes

API endpoints for security analytics, audit logs, threat detection,
and security policy management. Related to Issue #728.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from models.database import (
    AuditLog,
    Certificate,
    PolicyStatus,
    SecurityEvent,
    SecurityEventSeverity,
    SecurityEventType,
    SecurityPolicy,
)
from models.schemas import (
    AuditLogListResponse,
    AuditLogResponse,
    CertificateResponse,
    SecurityEventAcknowledge,
    SecurityEventCreate,
    SecurityEventListResponse,
    SecurityEventResolve,
    SecurityEventResponse,
    SecurityOverviewResponse,
    SecurityPolicyCreate,
    SecurityPolicyListResponse,
    SecurityPolicyResponse,
    SecurityPolicyUpdate,
    ThreatSummary,
)
from pydantic import BaseModel
from services.auth import get_current_user
from services.database import get_db
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from typing_extensions import Annotated

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/security", tags=["security"])


# =============================================================================
# Audit Log Middleware Helper
# =============================================================================


async def create_audit_log(
    db: AsyncSession,
    category: str,
    action: str,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    ip_address: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    description: Optional[str] = None,
    request_method: Optional[str] = None,
    request_path: Optional[str] = None,
    response_status: Optional[int] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    extra_data: Optional[dict] = None,
) -> AuditLog:
    """Create an audit log entry."""
    log = AuditLog(
        log_id=str(uuid.uuid4())[:16],
        user_id=user_id,
        username=username,
        ip_address=ip_address,
        category=category,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        description=description,
        request_method=request_method,
        request_path=request_path,
        response_status=response_status,
        success=success,
        error_message=error_message,
        extra_data=extra_data or {},
    )
    db.add(log)
    await db.flush()
    return log


# =============================================================================
# Security Overview
# =============================================================================


async def _get_security_event_counts(db: AsyncSession, last_24h: datetime) -> dict:
    """Get all security event counts for the overview dashboard.

    Helper for get_security_overview (Issue #665).
    """
    # Failed logins in last 24h
    failed_logins = await db.execute(
        select(func.count(SecurityEvent.id))
        .where(SecurityEvent.event_type == SecurityEventType.LOGIN_FAILURE.value)
        .where(SecurityEvent.timestamp >= last_24h)
    )
    failed_logins_count = failed_logins.scalar() or 0

    # Active threats (unresolved security events with severity >= medium)
    active_threats = await db.execute(
        select(func.count(SecurityEvent.id))
        .where(SecurityEvent.is_resolved.is_(False))
        .where(
            SecurityEvent.severity.in_(
                [
                    SecurityEventSeverity.MEDIUM.value,
                    SecurityEventSeverity.HIGH.value,
                    SecurityEventSeverity.CRITICAL.value,
                ]
            )
        )
    )
    active_threats_count = active_threats.scalar() or 0

    # Critical events
    critical_events = await db.execute(
        select(func.count(SecurityEvent.id))
        .where(SecurityEvent.is_resolved.is_(False))
        .where(SecurityEvent.severity == SecurityEventSeverity.CRITICAL.value)
    )
    critical_count = critical_events.scalar() or 0

    # Policy violations
    policy_violations = await db.execute(
        select(func.count(SecurityEvent.id))
        .where(SecurityEvent.event_type == SecurityEventType.POLICY_VIOLATION.value)
        .where(SecurityEvent.is_resolved.is_(False))
    )
    violations_count = policy_violations.scalar() or 0

    # Total events in 24h
    total_events = await db.execute(
        select(func.count(SecurityEvent.id)).where(SecurityEvent.timestamp >= last_24h)
    )
    total_events_count = total_events.scalar() or 0

    return {
        "failed_logins": failed_logins_count,
        "active_threats": active_threats_count,
        "critical": critical_count,
        "violations": violations_count,
        "total_events": total_events_count,
    }


async def _get_expiring_certificates_count(
    db: AsyncSession, now: datetime, last_30d: datetime
) -> int:
    """Get count of certificates expiring in the next 30 days.

    Helper for get_security_overview (Issue #665).
    """
    cert_expiring = await db.execute(
        select(func.count(Certificate.id))
        .where(Certificate.status == "active")
        .where(Certificate.not_after <= last_30d)
        .where(Certificate.not_after > now)
    )
    return cert_expiring.scalar() or 0


def _calculate_security_score(counts: dict, certs_expiring: int) -> float:
    """Calculate the overall security score based on event counts.

    Helper for get_security_overview (Issue #665).
    """
    score = 100.0
    score -= min(counts["active_threats"] * 5, 30)  # Max 30 points for threats
    score -= min(counts["critical"] * 10, 20)  # Max 20 points for critical
    score -= min(counts["failed_logins"] * 0.5, 10)  # Max 10 points for failed logins
    score -= min(counts["violations"] * 2, 20)  # Max 20 points for violations
    score -= min(certs_expiring * 2, 10)  # Max 10 points for expiring certs
    return max(score, 0)  # Minimum 0


@router.get("/overview", response_model=SecurityOverviewResponse)
async def get_security_overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> SecurityOverviewResponse:
    """Get security dashboard overview metrics."""
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_30d = now - timedelta(days=30)

    # Get all security event counts
    counts = await _get_security_event_counts(db, last_24h)

    # Get expiring certificates count
    certs_expiring_count = await _get_expiring_certificates_count(db, now, last_30d)

    # Calculate security score
    score = _calculate_security_score(counts, certs_expiring_count)

    # Recent events
    recent = await db.execute(
        select(SecurityEvent).order_by(SecurityEvent.timestamp.desc()).limit(10)
    )
    recent_events = recent.scalars().all()

    return SecurityOverviewResponse(
        security_score=round(score, 1),
        active_threats=counts["active_threats"],
        failed_logins_24h=counts["failed_logins"],
        policy_violations=counts["violations"],
        total_events_24h=counts["total_events"],
        critical_events=counts["critical"],
        certificates_expiring=certs_expiring_count,
        recent_events=[SecurityEventResponse.model_validate(e) for e in recent_events],
    )


# =============================================================================
# Audit Logs
# =============================================================================


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    category: Optional[str] = Query(None, description="Filter by category"),
    username: Optional[str] = Query(None, description="Filter by username"),
    action: Optional[str] = Query(None, description="Filter by action"),
    success: Optional[bool] = Query(None, description="Filter by success status"),
    since: Optional[datetime] = Query(
        None, description="Filter events after this time"
    ),
    until: Optional[datetime] = Query(
        None, description="Filter events before this time"
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> AuditLogListResponse:
    """List audit logs with optional filtering."""
    query = select(AuditLog)

    if category:
        query = query.where(AuditLog.category == category)
    if username:
        query = query.where(AuditLog.username.ilike(f"%{username}%"))
    if action:
        query = query.where(AuditLog.action.ilike(f"%{action}%"))
    if success is not None:
        query = query.where(AuditLog.success == success)
    if since:
        query = query.where(AuditLog.timestamp >= since)
    if until:
        query = query.where(AuditLog.timestamp <= until)

    # Count total
    count_query = select(func.count(AuditLog.id))
    if category:
        count_query = count_query.where(AuditLog.category == category)
    if username:
        count_query = count_query.where(AuditLog.username.ilike(f"%{username}%"))
    if action:
        count_query = count_query.where(AuditLog.action.ilike(f"%{action}%"))
    if success is not None:
        count_query = count_query.where(AuditLog.success == success)
    if since:
        count_query = count_query.where(AuditLog.timestamp >= since)
    if until:
        count_query = count_query.where(AuditLog.timestamp <= until)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginate
    query = query.order_by(AuditLog.timestamp.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    logs = result.scalars().all()

    return AuditLogListResponse(
        logs=[AuditLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/audit-logs/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> AuditLogResponse:
    """Get a specific audit log entry."""
    result = await db.execute(select(AuditLog).where(AuditLog.log_id == log_id))
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found",
        )

    return AuditLogResponse.model_validate(log)


# =============================================================================
# Security Events (Threat Detection)
# =============================================================================


def _apply_security_event_filters(
    query,
    event_type,
    severity,
    acknowledged,
    resolved,
    source_ip,
    node_id,
    since,
    until,
):
    """Helper for list_security_events. Ref: #1088."""
    if event_type:
        query = query.where(SecurityEvent.event_type == event_type)
    if severity:
        query = query.where(SecurityEvent.severity == severity)
    if acknowledged is not None:
        query = query.where(SecurityEvent.is_acknowledged == acknowledged)
    if resolved is not None:
        query = query.where(SecurityEvent.is_resolved == resolved)
    if source_ip:
        query = query.where(SecurityEvent.source_ip == source_ip)
    if node_id:
        query = query.where(
            or_(
                SecurityEvent.source_node_id == node_id,
                SecurityEvent.target_node_id == node_id,
            )
        )
    if since:
        query = query.where(SecurityEvent.timestamp >= since)
    if until:
        query = query.where(SecurityEvent.timestamp <= until)
    return query


async def _get_security_event_aggregates(db: AsyncSession) -> dict:
    """Helper for list_security_events. Ref: #1088."""
    count_result = await db.execute(select(func.count(SecurityEvent.id)))
    total = count_result.scalar() or 0

    unack_result = await db.execute(
        select(func.count(SecurityEvent.id)).where(
            SecurityEvent.is_acknowledged.is_(False)
        )
    )
    unacknowledged_count = unack_result.scalar() or 0

    critical_result = await db.execute(
        select(func.count(SecurityEvent.id))
        .where(SecurityEvent.severity == SecurityEventSeverity.CRITICAL.value)
        .where(SecurityEvent.is_resolved.is_(False))
    )
    critical_count = critical_result.scalar() or 0

    return {
        "total": total,
        "unacknowledged": unacknowledged_count,
        "critical": critical_count,
    }


@router.get("/events", response_model=SecurityEventListResponse)
async def list_security_events(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    acknowledged: Optional[bool] = Query(
        None, description="Filter by acknowledged status"
    ),
    resolved: Optional[bool] = Query(None, description="Filter by resolved status"),
    source_ip: Optional[str] = Query(None, description="Filter by source IP"),
    node_id: Optional[str] = Query(None, description="Filter by node ID"),
    since: Optional[datetime] = Query(None),
    until: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> SecurityEventListResponse:
    """List security events with filtering."""
    query = select(SecurityEvent)
    query = _apply_security_event_filters(
        query,
        event_type,
        severity,
        acknowledged,
        resolved,
        source_ip,
        node_id,
        since,
        until,
    )

    aggregates = await _get_security_event_aggregates(db)

    query = query.order_by(SecurityEvent.timestamp.desc())
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    events = result.scalars().all()

    return SecurityEventListResponse(
        events=[SecurityEventResponse.model_validate(e) for e in events],
        total=aggregates["total"],
        page=page,
        per_page=per_page,
        unacknowledged_count=aggregates["unacknowledged"],
        critical_count=aggregates["critical"],
    )


async def _get_threat_severity_counts(db: AsyncSession, since: datetime) -> dict:
    """Helper for get_threat_summary. Ref: #1088."""
    severity_counts = {}
    for sev in SecurityEventSeverity:
        result = await db.execute(
            select(func.count(SecurityEvent.id))
            .where(SecurityEvent.severity == sev.value)
            .where(SecurityEvent.timestamp >= since)
        )
        severity_counts[sev.value] = result.scalar() or 0
    return severity_counts


async def _get_threat_distribution(db: AsyncSession, since: datetime) -> tuple:
    """Helper for get_threat_summary. Ref: #1088."""
    type_result = await db.execute(
        select(SecurityEvent.event_type, func.count(SecurityEvent.id))
        .where(SecurityEvent.timestamp >= since)
        .group_by(SecurityEvent.event_type)
    )
    by_type = {row[0]: row[1] for row in type_result.all()}

    ip_result = await db.execute(
        select(SecurityEvent.source_ip, func.count(SecurityEvent.id))
        .where(SecurityEvent.source_ip.isnot(None))
        .where(SecurityEvent.timestamp >= since)
        .group_by(SecurityEvent.source_ip)
        .order_by(func.count(SecurityEvent.id).desc())
        .limit(10)
    )
    by_source_ip = {row[0]: row[1] for row in ip_result.all() if row[0]}
    return by_type, by_source_ip


@router.get("/events/summary", response_model=ThreatSummary)
async def get_threat_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    hours: int = Query(24, ge=1, le=720, description="Hours to look back"),
) -> ThreatSummary:
    """Get threat detection summary statistics."""
    since = datetime.utcnow() - timedelta(hours=hours)

    severity_counts = await _get_threat_severity_counts(db, since)
    by_type, by_source_ip = await _get_threat_distribution(db, since)

    ack_result = await db.execute(
        select(func.count(SecurityEvent.id))
        .where(SecurityEvent.is_acknowledged.is_(True))
        .where(SecurityEvent.timestamp >= since)
    )
    acknowledged = ack_result.scalar() or 0

    resolved_result = await db.execute(
        select(func.count(SecurityEvent.id))
        .where(SecurityEvent.is_resolved.is_(True))
        .where(SecurityEvent.timestamp >= since)
    )
    resolved = resolved_result.scalar() or 0

    total_result = await db.execute(
        select(func.count(SecurityEvent.id)).where(SecurityEvent.timestamp >= since)
    )
    total = total_result.scalar() or 0

    return ThreatSummary(
        total_threats=total,
        critical=severity_counts.get("critical", 0),
        high=severity_counts.get("high", 0),
        medium=severity_counts.get("medium", 0),
        low=severity_counts.get("low", 0),
        acknowledged=acknowledged,
        resolved=resolved,
        by_type=by_type,
        by_source_ip=by_source_ip,
    )


@router.post(
    "/events", response_model=SecurityEventResponse, status_code=status.HTTP_201_CREATED
)
async def create_security_event(
    event_data: SecurityEventCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> SecurityEventResponse:
    """Create a new security event."""
    event = SecurityEvent(
        event_id=str(uuid.uuid4())[:16],
        event_type=event_data.event_type,
        severity=event_data.severity,
        category=event_data.category,
        source_ip=event_data.source_ip,
        source_user=event_data.source_user,
        source_node_id=event_data.source_node_id,
        target_resource=event_data.target_resource,
        target_node_id=event_data.target_node_id,
        title=event_data.title,
        description=event_data.description,
        threat_indicator=event_data.threat_indicator,
        threat_score=event_data.threat_score,
        mitre_technique=event_data.mitre_technique,
        raw_data=event_data.raw_data,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)

    logger.info("Security event created: %s (%s)", event.event_id, event.title)
    return SecurityEventResponse.model_validate(event)


@router.get("/events/{event_id}", response_model=SecurityEventResponse)
async def get_security_event(
    event_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> SecurityEventResponse:
    """Get a specific security event."""
    result = await db.execute(
        select(SecurityEvent).where(SecurityEvent.event_id == event_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Security event not found",
        )

    return SecurityEventResponse.model_validate(event)


@router.post("/events/{event_id}/acknowledge", response_model=SecurityEventResponse)
async def acknowledge_security_event(
    event_id: str,
    ack_data: SecurityEventAcknowledge,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> SecurityEventResponse:
    """Acknowledge a security event."""
    result = await db.execute(
        select(SecurityEvent).where(SecurityEvent.event_id == event_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Security event not found",
        )

    event.is_acknowledged = True
    event.acknowledged_by = current_user.get("sub", "unknown")
    event.acknowledged_at = datetime.utcnow()

    await db.commit()
    await db.refresh(event)

    logger.info(
        "Security event acknowledged: %s by %s", event_id, event.acknowledged_by
    )
    return SecurityEventResponse.model_validate(event)


@router.post("/events/{event_id}/resolve", response_model=SecurityEventResponse)
async def resolve_security_event(
    event_id: str,
    resolve_data: SecurityEventResolve,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> SecurityEventResponse:
    """Resolve a security event."""
    result = await db.execute(
        select(SecurityEvent).where(SecurityEvent.event_id == event_id)
    )
    event = result.scalar_one_or_none()

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Security event not found",
        )

    event.is_resolved = True
    event.resolved_by = current_user.get("sub", "unknown")
    event.resolved_at = datetime.utcnow()
    event.resolution_notes = resolve_data.resolution_notes

    # Also mark as acknowledged if not already
    if not event.is_acknowledged:
        event.is_acknowledged = True
        event.acknowledged_by = event.resolved_by
        event.acknowledged_at = event.resolved_at

    await db.commit()
    await db.refresh(event)

    logger.info("Security event resolved: %s by %s", event_id, event.resolved_by)
    return SecurityEventResponse.model_validate(event)


# =============================================================================
# Security Policies
# =============================================================================


@router.get("/policies", response_model=SecurityPolicyListResponse)
async def list_security_policies(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    category: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    is_enforced: Optional[bool] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> SecurityPolicyListResponse:
    """List security policies."""
    query = select(SecurityPolicy)

    if category:
        query = query.where(SecurityPolicy.category == category)
    if status_filter:
        query = query.where(SecurityPolicy.status == status_filter)
    if is_enforced is not None:
        query = query.where(SecurityPolicy.is_enforced == is_enforced)

    # Count total
    count_query = select(func.count(SecurityPolicy.id))
    if category:
        count_query = count_query.where(SecurityPolicy.category == category)
    if status_filter:
        count_query = count_query.where(SecurityPolicy.status == status_filter)
    if is_enforced is not None:
        count_query = count_query.where(SecurityPolicy.is_enforced == is_enforced)

    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Paginate
    query = query.order_by(SecurityPolicy.name)
    query = query.offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    policies = result.scalars().all()

    return SecurityPolicyListResponse(
        policies=[SecurityPolicyResponse.model_validate(p) for p in policies],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.post(
    "/policies",
    response_model=SecurityPolicyResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_security_policy(
    policy_data: SecurityPolicyCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> SecurityPolicyResponse:
    """Create a new security policy."""
    policy = SecurityPolicy(
        policy_id=str(uuid.uuid4())[:16],
        name=policy_data.name,
        description=policy_data.description,
        category=policy_data.category,
        policy_type=policy_data.policy_type,
        rules=policy_data.rules,
        parameters=policy_data.parameters,
        applies_to_nodes=policy_data.applies_to_nodes,
        applies_to_roles=policy_data.applies_to_roles,
        status=policy_data.status,
        is_enforced=policy_data.is_enforced,
        created_by=current_user.get("sub", "unknown"),
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)

    logger.info("Security policy created: %s (%s)", policy.policy_id, policy.name)
    return SecurityPolicyResponse.model_validate(policy)


@router.get("/policies/{policy_id}", response_model=SecurityPolicyResponse)
async def get_security_policy(
    policy_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> SecurityPolicyResponse:
    """Get a specific security policy."""
    result = await db.execute(
        select(SecurityPolicy).where(SecurityPolicy.policy_id == policy_id)
    )
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Security policy not found",
        )

    return SecurityPolicyResponse.model_validate(policy)


@router.patch("/policies/{policy_id}", response_model=SecurityPolicyResponse)
async def update_security_policy(
    policy_id: str,
    policy_data: SecurityPolicyUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> SecurityPolicyResponse:
    """Update a security policy."""
    result = await db.execute(
        select(SecurityPolicy).where(SecurityPolicy.policy_id == policy_id)
    )
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Security policy not found",
        )

    update_data = policy_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if value is not None:
            setattr(policy, field, value)

    policy.updated_by = current_user.get("sub", "unknown")
    policy.version += 1

    await db.commit()
    await db.refresh(policy)

    logger.info("Security policy updated: %s", policy_id)
    return SecurityPolicyResponse.model_validate(policy)


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_security_policy(
    policy_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> None:
    """Delete a security policy."""
    result = await db.execute(
        select(SecurityPolicy).where(SecurityPolicy.policy_id == policy_id)
    )
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Security policy not found",
        )

    await db.delete(policy)
    await db.commit()

    logger.info("Security policy deleted: %s", policy_id)


@router.post("/policies/{policy_id}/activate", response_model=SecurityPolicyResponse)
async def activate_security_policy(
    policy_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> SecurityPolicyResponse:
    """Activate a security policy and enable enforcement."""
    result = await db.execute(
        select(SecurityPolicy).where(SecurityPolicy.policy_id == policy_id)
    )
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Security policy not found",
        )

    policy.status = PolicyStatus.ACTIVE.value
    policy.is_enforced = True
    policy.updated_by = current_user.get("sub", "unknown")

    await db.commit()
    await db.refresh(policy)

    logger.info("Security policy activated: %s", policy_id)
    return SecurityPolicyResponse.model_validate(policy)


@router.post("/policies/{policy_id}/deactivate", response_model=SecurityPolicyResponse)
async def deactivate_security_policy(
    policy_id: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[dict, Depends(get_current_user)],
) -> SecurityPolicyResponse:
    """Deactivate a security policy and disable enforcement."""
    result = await db.execute(
        select(SecurityPolicy).where(SecurityPolicy.policy_id == policy_id)
    )
    policy = result.scalar_one_or_none()

    if not policy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Security policy not found",
        )

    policy.status = PolicyStatus.INACTIVE.value
    policy.is_enforced = False
    policy.updated_by = current_user.get("sub", "unknown")

    await db.commit()
    await db.refresh(policy)

    logger.info("Security policy deactivated: %s", policy_id)
    return SecurityPolicyResponse.model_validate(policy)


# =============================================================================
# Certificate Expiry Monitoring (Issue #926 Phase 7)
# =============================================================================


class CertificateReport(BaseModel):
    """Incoming cert report from Ansible after deployment."""

    node_id: str
    subject: Optional[str] = None
    issuer: Optional[str] = None
    serial_number: Optional[str] = None
    fingerprint: Optional[str] = None
    not_before: Optional[str] = None
    not_after: Optional[str] = None


def _parse_openssl_date(raw: Optional[str]) -> Optional[datetime]:
    """Parse openssl date strings like 'Jan  1 00:00:00 2025 GMT'."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b  %d %H:%M:%S %Y %Z"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    # Last resort: try ISO-8601 for already-formatted inputs
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _days_until(dt: Optional[datetime]) -> Optional[int]:
    """Return days until datetime from now (negative = already expired)."""
    if dt is None:
        return None
    return (dt - datetime.utcnow()).days


@router.get("/certificates", response_model=List[CertificateResponse])
async def list_certificates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: Optional[str] = Query(None, description="Filter by node"),
    status_filter: Optional[str] = Query(None, alias="status"),
) -> List[CertificateResponse]:
    """List all fleet node certificates with expiry status."""
    query = select(Certificate)
    if node_id:
        query = query.where(Certificate.node_id == node_id)
    if status_filter:
        query = query.where(Certificate.status == status_filter)
    query = query.order_by(Certificate.not_after.asc())

    result = await db.execute(query)
    certs = result.scalars().all()

    responses = []
    now = datetime.utcnow()
    for cert in certs:
        resp = CertificateResponse.model_validate(cert)
        resp.days_until_expiry = _days_until(cert.not_after)
        # Auto-update status if expired
        if cert.not_after and cert.not_after < now and cert.status == "active":
            cert.status = "expired"
        responses.append(resp)

    await db.commit()
    return responses


@router.get("/certificates/expiring", response_model=List[CertificateResponse])
async def list_expiring_certificates(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    days: int = Query(30, ge=1, le=365, description="Expiring within N days"),
) -> List[CertificateResponse]:
    """List certificates expiring within the given number of days."""
    now = datetime.utcnow()
    threshold = now + timedelta(days=days)

    result = await db.execute(
        select(Certificate)
        .where(Certificate.not_after <= threshold)
        .where(Certificate.not_after > now)
        .where(Certificate.status == "active")
        .order_by(Certificate.not_after.asc())
    )
    certs = result.scalars().all()

    return [
        CertificateResponse.model_validate(
            cert, update={"days_until_expiry": _days_until(cert.not_after)}
        )
        for cert in certs
    ]


@router.post(
    "/certificates/report",
    response_model=CertificateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def report_certificate(
    report: CertificateReport,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> CertificateResponse:
    """Record or update a node certificate (called by Ansible after deployment)."""
    not_before_dt = _parse_openssl_date(report.not_before)
    not_after_dt = _parse_openssl_date(report.not_after)

    # Upsert: find existing cert for this node or create new
    existing = await db.execute(
        select(Certificate).where(Certificate.node_id == report.node_id)
    )
    cert = existing.scalar_one_or_none()

    if cert is None:
        cert = Certificate(
            cert_id=f"{report.node_id}-{int(datetime.utcnow().timestamp())}"
        )
        db.add(cert)

    cert.node_id = report.node_id
    cert.subject = report.subject
    cert.issuer = report.issuer
    cert.serial_number = report.serial_number
    cert.fingerprint = report.fingerprint
    cert.not_before = not_before_dt
    cert.not_after = not_after_dt
    cert.status = "active"

    await db.commit()
    await db.refresh(cert)

    logger.info(
        "Cert reported for node %s (expires %s)", report.node_id, report.not_after
    )
    resp = CertificateResponse.model_validate(cert)
    resp.days_until_expiry = _days_until(cert.not_after)
    return resp
