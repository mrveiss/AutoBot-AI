# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Audit and Compliance API

Issue #679: Audit logging and compliance reporting for knowledge access and modifications.
"""

from datetime import timedelta
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.schemas_knowledge import (
    ComplianceReportRequest,
    KnowledgeAuditEventsResponse,
    KnowledgeComplianceReportResponse,
    KnowledgePermissionChangesResponse,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.models.pagination import PaginationParams
from autobot_shared.time_utils import now_utc
from knowledge_factory import get_or_create_knowledge_base
from services.audit.audit import KnowledgeAuditLog  # GH#8290 Phase 2

logger = get_logger(__name__)

router = APIRouter(prefix="/knowledge/audit", tags=["knowledge-audit"])


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


@router.get("/user-activity", response_model=KnowledgeAuditEventsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_user_activity_log",
    error_code_prefix="KNOWLEDGE_AUDIT",
)
async def get_user_activity_log(
    request: Request,
    current_user: Dict = Depends(get_current_user),
    pagination: PaginationParams = Depends(),
):
    """Get audit log for current user's activity.

    Issue #679: User can view their own activity history.

    Args:
        pagination: Limit and offset for result pagination

    Returns:
        List of audit events
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        # Issue #5407: KB instance not initialized - emit counter before 503.
        logger.warning("get_user_activity_log: KB uninitialized - raising 503")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="audit_user_activity", reason="kb_uninit").inc()
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        audit_log = await _get_audit_log(kb)

        user_id = current_user.get("user_id") or current_user.get("username", "")
        events = await audit_log.get_user_activity(user_id=user_id, limit=pagination.limit, offset=pagination.offset)

        return {"events": events, "count": len(events), "user_id": user_id}

    except Exception as e:
        logger.error("Error retrieving user activity: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/fact/{fact_id}/access-log", response_model=KnowledgeAuditEventsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_fact_access_log",
    error_code_prefix="KNOWLEDGE_AUDIT",
)
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
        # Issue #5407: KB instance not initialized - emit counter before 503.
        logger.warning("get_fact_access_log: KB uninitialized - raising 503")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="audit_fact_access", reason="kb_uninit").inc()
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        # Verify user is the owner
        fact_data = await kb.redis().hget(f"fact:{fact_id}", "metadata")
        if not fact_data:
            raise HTTPException(status_code=404, detail="Fact not found")

        import json

        if isinstance(fact_data, bytes):
            fact_data = fact_data.decode("utf-8")
        metadata = json.loads(fact_data)

        user_id = current_user.get("user_id") or current_user.get("username", "")
        if metadata.get("owner_id") != user_id:
            raise HTTPException(status_code=403, detail="Only the owner can view access logs")

        # Get access log
        audit_log = await _get_audit_log(kb)
        events = await audit_log.get_fact_access_log(fact_id=fact_id, limit=limit)

        return {"events": events, "count": len(events), "fact_id": fact_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving fact access log: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/organization/audit-log", response_model=KnowledgeAuditEventsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_organization_audit_log",
    error_code_prefix="KNOWLEDGE_AUDIT",
)
async def get_organization_audit_log(
    request: Request,
    current_user: Dict = Depends(get_current_user),
    pagination: PaginationParams = Depends(),
):
    """Get audit log for the organization.

    Issue #679: Organization admins can view all organization activity.
    Issue #934: Enforce org admin role.

    Args:
        pagination: Limit and offset for result pagination

    Returns:
        List of organization audit events

    Raises:
        403: If user is not an organization admin
    """
    org_id = current_user.get("org_id")
    if not org_id:
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    user_role = current_user.get("role", "")
    if user_role not in ("admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Organization admin role required")

    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        # Issue #5407: KB instance not initialized - emit counter before 503.
        logger.warning("get_organization_audit_log: KB uninitialized - raising 503")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="audit_organization", reason="kb_uninit").inc()
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        audit_log = await _get_audit_log(kb)

        events = await audit_log.get_organization_audit_log(
            organization_id=org_id, limit=pagination.limit, offset=pagination.offset
        )

        return {
            "events": events,
            "count": len(events),
            "organization_id": org_id,
        }

    except Exception as e:
        logger.error("Error retrieving organization audit log: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Endpoints - Permission History
# =============================================================================


@router.get("/permission-changes", response_model=KnowledgePermissionChangesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_permission_changes",
    error_code_prefix="KNOWLEDGE_AUDIT",
)
async def get_permission_changes(
    request: Request,
    current_user: Dict = Depends(get_current_user),
    fact_id: str | None = Query(default=None),
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
        # Issue #5407: KB instance not initialized - emit counter before 503.
        logger.warning("get_permission_changes: KB uninitialized - raising 503")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="audit_permission_changes", reason="kb_uninit").inc()
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        audit_log = await _get_audit_log(kb)

        user_id = current_user.get("user_id") or current_user.get("username", "")
        events = await audit_log.get_permission_changes(fact_id=fact_id, user_id=user_id, limit=limit)

        return {"events": events, "count": len(events)}

    except Exception as e:
        logger.error("Error retrieving permission changes: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# =============================================================================
# Endpoints - Compliance Reporting
# =============================================================================


@router.post("/compliance-report", response_model=KnowledgeComplianceReportResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="generate_compliance_report",
    error_code_prefix="KNOWLEDGE_AUDIT",
)
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
            raise HTTPException(status_code=400, detail="User not associated with an organization")
        org_id = user_org_id

    user_role = current_user.get("role", "")
    if user_role not in ("admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Organization admin role required")

    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        # Issue #5407: KB instance not initialized - emit counter before 503.
        logger.warning("generate_compliance_report: KB uninitialized - raising 503")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="audit_compliance_report", reason="kb_uninit").inc()
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
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/compliance-summary", response_model=KnowledgeComplianceReportResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_compliance_summary",
    error_code_prefix="KNOWLEDGE_AUDIT",
)
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
        raise HTTPException(status_code=400, detail="User not associated with an organization")

    user_role = current_user.get("role", "")
    if user_role not in ("admin", "org_admin"):
        raise HTTPException(status_code=403, detail="Organization admin role required")

    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)
    if kb is None:
        # Issue #5407: KB instance not initialized - emit counter before 503.
        logger.warning("get_compliance_summary: KB uninitialized - raising 503")
        from knowledge.metrics import autobot_kb_degradation_total

        autobot_kb_degradation_total.labels(endpoint="audit_compliance_summary", reason="kb_uninit").inc()
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    try:
        end_date = now_utc()
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
        raise HTTPException(status_code=500, detail="Internal server error")
