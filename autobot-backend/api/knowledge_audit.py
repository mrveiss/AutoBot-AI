# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Audit and Compliance API

Issue #679: Audit logging and compliance reporting for knowledge access and modifications.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from knowledge.audit_log import AuditEventType, KnowledgeAuditLog
from knowledge_factory import get_or_create_knowledge_base
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge/audit", tags=["knowledge-audit"])


# =============================================================================
# Pydantic Models
# =============================================================================


class AuditEvent(BaseModel):
    """Audit event model."""

    id: str
    type: AuditEventType
    user_id: str
    fact_id: Optional[str] = None
    organization_id: Optional[str] = None
    details: dict = Field(default_factory=dict)
    ip_address: Optional[str] = None
    timestamp: str


class ComplianceReportRequest(BaseModel):
    """Request for compliance report."""

    start_date: datetime = Field(description="Report start date")
    end_date: datetime = Field(description="Report end date")
    organization_id: Optional[str] = Field(
        default=None, description="Organization ID (defaults to user's org)"
    )


# =============================================================================
# Helper Functions
# =============================================================================


async def _get_audit_log(kb) -> KnowledgeAuditLog:
    """Get or create audit log instance."""
    if not hasattr(kb, "audit_log") or kb.audit_log is None:
        kb.audit_log = KnowledgeAuditLog(kb.redis_client)
    return kb.audit_log


# =============================================================================
# Endpoints - Activity Logs
# =============================================================================


@router.get("/user-activity")
async def get_user_activity_log(
    request: Request,
    current_user: Dict = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Get audit log for current user's activity.

    Issue #679: User can view their own activity history.

    Args:
        limit: Maximum events to return
        offset: Pagination offset

    Returns:
        List of audit events
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        audit_log = await _get_audit_log(kb)

        user_id = current_user.get("user_id") or current_user.get("username", "")
        events = await audit_log.get_user_activity(
            user_id=user_id, limit=limit, offset=offset
        )

        return {"events": events, "count": len(events), "user_id": user_id}

    except Exception as e:
        logger.error("Error retrieving user activity: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve activity: {e}")


@router.get("/fact/{fact_id}/access-log")
async def get_fact_access_log(
    fact_id: str,
    request: Request,
    current_user: Dict = Depends(get_current_user),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Get access log for a specific fact.

    Issue #679: Fact owners can view who accessed their knowledge.

    Args:
        fact_id: Fact ID
        limit: Maximum events to return

    Returns:
        List of access events for the fact

    Raises:
        403: If user is not the owner
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        # Verify user is the owner
        fact_data = await kb.aioredis_client.hget(f"fact:{fact_id}", "metadata")
        if not fact_data:
            raise HTTPException(status_code=404, detail="Fact not found")

        import json

        if isinstance(fact_data, bytes):
            fact_data = fact_data.decode("utf-8")
        metadata = json.loads(fact_data)

        user_id = current_user.get("user_id") or current_user.get("username", "")
        if metadata.get("owner_id") != user_id:
            raise HTTPException(
                status_code=403, detail="Only the owner can view access logs"
            )

        # Get access log
        audit_log = await _get_audit_log(kb)
        events = await audit_log.get_fact_access_log(fact_id=fact_id, limit=limit)

        return {"events": events, "count": len(events), "fact_id": fact_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving fact access log: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve access log: {e}"
        )


@router.get("/organization/audit-log")
async def get_organization_audit_log(
    request: Request,
    current_user: Dict = Depends(get_current_user),
    limit: int = Query(default=1000, ge=1, le=10000),
    offset: int = Query(default=0, ge=0),
):
    """Get audit log for the organization.

    Issue #679: Organization admins can view all organization activity.
    Issue #934: Enforce org admin role.

    Args:
        limit: Maximum events to return
        offset: Pagination offset

    Returns:
        List of organization audit events

    Raises:
        403: If user is not an organization admin
    """
    org_id = current_user.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=400, detail="User not associated with an organization"
        )

    user_role = current_user.get("role", "")
    if user_role not in ("admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Organization admin role required")

    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        audit_log = await _get_audit_log(kb)

        events = await audit_log.get_organization_audit_log(
            organization_id=org_id, limit=limit, offset=offset
        )

        return {
            "events": events,
            "count": len(events),
            "organization_id": org_id,
        }

    except Exception as e:
        logger.error("Error retrieving organization audit log: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve audit log: {e}"
        )


# =============================================================================
# Endpoints - Permission History
# =============================================================================


@router.get("/permission-changes")
async def get_permission_changes(
    request: Request,
    current_user: Dict = Depends(get_current_user),
    fact_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
):
    """Get history of permission changes.

    Issue #679: Track who shared/unshared knowledge and when.

    Args:
        fact_id: Optional fact ID to filter by
        limit: Maximum events to return

    Returns:
        List of permission change events
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        audit_log = await _get_audit_log(kb)

        user_id = current_user.get("user_id") or current_user.get("username", "")
        events = await audit_log.get_permission_changes(
            fact_id=fact_id, user_id=user_id, limit=limit
        )

        return {"events": events, "count": len(events)}

    except Exception as e:
        logger.error("Error retrieving permission changes: %s", e)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve permission changes: {e}"
        )


# =============================================================================
# Endpoints - Compliance Reporting
# =============================================================================


@router.post("/compliance-report")
async def generate_compliance_report(
    report_request: ComplianceReportRequest,
    request: Request,
    current_user: Dict = Depends(get_current_user),
):
    """Generate compliance report for an organization.

    Issue #679: Organization admins can generate compliance reports.
    Issue #934: Enforce org admin role.

    Args:
        report_request: Report parameters

    Returns:
        Compliance report with activity statistics

    Raises:
        403: If user is not an organization admin
    """
    # Determine organization ID
    org_id = report_request.organization_id
    if not org_id:
        user_org_id = current_user.get("org_id")
        if not user_org_id:
            raise HTTPException(
                status_code=400, detail="User not associated with an organization"
            )
        org_id = user_org_id

    user_role = current_user.get("role", "")
    if user_role not in ("admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Organization admin role required")

    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        audit_log = await _get_audit_log(kb)

        report = await audit_log.generate_compliance_report(
            organization_id=org_id,
            start_date=report_request.start_date,
            end_date=report_request.end_date,
        )

        logger.info(
            "Generated compliance report for org %s: %d events",
            org_id,
            report["total_events"],
        )

        return report

    except Exception as e:
        logger.error("Error generating compliance report: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {e}")


@router.get("/compliance-summary")
async def get_compliance_summary(
    request: Request,
    current_user: Dict = Depends(get_current_user),
    days: int = Query(default=30, ge=1, le=365),
):
    """Get compliance summary for the last N days.

    Issue #679: Quick overview of organization activity for compliance.
    Issue #934: Enforce org admin role.

    Args:
        days: Number of days to include (default: 30)

    Returns:
        Summary statistics for the period
    """
    org_id = current_user.get("org_id")
    if not org_id:
        raise HTTPException(
            status_code=400, detail="User not associated with an organization"
        )

    user_role = current_user.get("role", "")
    if user_role not in ("admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Organization admin role required")

    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        audit_log = await _get_audit_log(kb)

        report = await audit_log.generate_compliance_report(
            organization_id=org_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Add summary period
        report["summary_period_days"] = days

        return report

    except Exception as e:
        logger.error("Error generating compliance summary: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {e}")
