# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Audit Log Query API for AutoBot

Provides secure endpoints for querying and analyzing security audit logs.
Access restricted to admin users only.

Endpoints:
- GET /api/audit/logs - Query audit logs with filters
- GET /api/audit/statistics - Get audit logging statistics
- GET /api/audit/session/{session_id} - Get audit trail for specific session
- GET /api/audit/user/{user_id} - Get audit trail for specific user
- GET /api/audit/failures - Get failed/denied operations for security monitoring
- POST /api/audit/cleanup - Trigger cleanup of old audit logs (admin only)
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from backend.services.audit_logger import AuditResult, get_audit_logger
from auth_middleware import auth_middleware
from utils.catalog_http_exceptions import (
    raise_auth_error,
    raise_server_error,
    raise_validation_error,
)
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

router = APIRouter(prefix="/api/audit", tags=["audit"])
logger = logging.getLogger(__name__)


class AuditQueryRequest(BaseModel):
    """Audit log query parameters"""

    start_time: Optional[datetime] = Field(None, description="Start of time range")
    end_time: Optional[datetime] = Field(None, description="End of time range")
    operation: Optional[str] = Field(None, description="Filter by operation type")
    user_id: Optional[str] = Field(None, description="Filter by user")
    session_id: Optional[str] = Field(None, description="Filter by session")
    vm_name: Optional[str] = Field(None, description="Filter by VM source")
    result: Optional[AuditResult] = Field(None, description="Filter by result")
    limit: int = Field(100, ge=1, le=1000, description="Maximum entries to return")
    offset: int = Field(0, ge=0, description="Pagination offset")


class AuditQueryResponse(BaseModel):
    """Audit log query response"""

    success: bool
    total_returned: int
    has_more: bool
    entries: List[dict]
    query: dict


class AuditStatisticsResponse(BaseModel):
    """Audit statistics response"""

    success: bool
    statistics: dict
    vm_info: dict


class CleanupRequest(BaseModel):
    """Audit log cleanup request"""

    days_to_keep: int = Field(90, ge=7, le=365, description="Days of logs to retain")
    confirm: bool = Field(False, description="Confirm cleanup operation")


def check_admin_permission(request: Request) -> bool:
    """Check if user has admin permission for audit log access"""
    try:
        # Get user from auth middleware
        user_data = auth_middleware.get_user_from_request(request)

        if not user_data:
            raise_auth_error(
                "AUTH_0002", "Authentication required for audit log access"
            )

        # Check for admin role
        # Issue #744: Require explicit role - no guest fallback for security
        user_role = user_data.get("role")
        if not user_role:
            raise_auth_error("AUTH_0002", "User role not assigned - access denied")
        if user_role != "admin":
            raise_auth_error(
                "AUTH_0003", "Admin permission required for audit log access"
            )

        return True

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Permission check failed: %s", e)
        raise_server_error("API_0003", "Permission check error")


def _build_query_dict(
    start_time: Optional[str],
    end_time: Optional[str],
    operation: Optional[str],
    user_id: Optional[str],
    session_id: Optional[str],
    vm_name: Optional[str],
    result: Optional[AuditResult],
    limit: int,
    offset: int,
) -> dict:
    """Build query parameters dictionary for response.

    Issue #665: Extracted from query_audit_logs to reduce function length.
    """
    return {
        "start_time": start_time,
        "end_time": end_time,
        "operation": operation,
        "user_id": user_id,
        "session_id": session_id,
        "vm_name": vm_name,
        "result": result,
        "limit": limit,
        "offset": offset,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="query_audit_logs",
    error_code_prefix="AUDIT",
)
@router.get("/logs", response_model=AuditQueryResponse)
async def query_audit_logs(
    request: Request,
    start_time: Optional[str] = Query(None, description="Start time (ISO format)"),
    end_time: Optional[str] = Query(None, description="End time (ISO format)"),
    operation: Optional[str] = Query(None, description="Operation filter"),
    user_id: Optional[str] = Query(None, description="User filter"),
    session_id: Optional[str] = Query(None, description="Session filter"),
    vm_name: Optional[str] = Query(None, description="VM filter"),
    result: Optional[AuditResult] = Query(None, description="Result filter"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    admin_check: bool = Depends(check_admin_permission),
):
    """Query audit logs with filters. Issue #665: Refactored with helper.

    Requires admin permission. Filters: operation, user_id, session_id, vm_name, result.
    Time format: ISO 8601. Pagination: limit (1-1000), offset.
    """
    try:
        audit_logger = await get_audit_logger()
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None

        entries = await audit_logger.query(
            start_time=start_dt,
            end_time=end_dt,
            operation=operation,
            user_id=user_id,
            session_id=session_id,
            vm_name=vm_name,
            result=result,
            limit=limit + 1,
            offset=offset,
        )

        has_more = len(entries) > limit
        if has_more:
            entries = entries[:limit]

        return AuditQueryResponse(
            success=True,
            total_returned=len(entries),
            has_more=has_more,
            entries=[e.to_response_dict() for e in entries],
            query=_build_query_dict(
                start_time,
                end_time,
                operation,
                user_id,
                session_id,
                vm_name,
                result,
                limit,
                offset,
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Audit log query failed: %s", e)
        raise_server_error("API_0003", f"Audit log query error: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_audit_statistics",
    error_code_prefix="AUDIT",
)
@router.get("/statistics", response_model=AuditStatisticsResponse)
async def get_audit_statistics(
    request: Request, admin_check: bool = Depends(check_admin_permission)
):
    """
    Get audit logging statistics

    Requires admin permission. Returns overall audit system health and metrics.
    """
    try:
        audit_logger = await get_audit_logger()
        stats = await audit_logger.get_statistics()

        return AuditStatisticsResponse(
            success=True,
            statistics=stats,
            vm_info={
                "vm_source": audit_logger.vm_source,
                "vm_name": audit_logger.vm_name,
            },
        )

    except Exception as e:
        logger.error("Failed to get audit statistics: %s", e)
        raise_server_error("API_0003", f"Statistics error: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_session_audit_trail",
    error_code_prefix="AUDIT",
)
@router.get("/session/{session_id}", response_model=AuditQueryResponse)
async def get_session_audit_trail(
    request: Request,
    session_id: str,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get complete audit trail for a specific session

    Requires admin permission. Returns all audit entries associated with
    the specified session ID, sorted by timestamp.
    """
    try:
        audit_logger = await get_audit_logger()

        # Query last 30 days for session activity
        end_time = datetime.now()
        start_time = end_time - timedelta(days=30)

        entries = await audit_logger.query(
            start_time=start_time, end_time=end_time, session_id=session_id, limit=1000
        )

        # Issue #372: Use model method to reduce feature envy
        entry_dicts = [e.to_response_dict() for e in entries]

        return AuditQueryResponse(
            success=True,
            total_returned=len(entry_dicts),
            has_more=False,
            entries=entry_dicts,
            query={"session_id": session_id},
        )

    except Exception as e:
        logger.error("Session audit trail query failed: %s", e)
        raise_server_error("API_0003", f"Session audit query error: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_user_audit_trail",
    error_code_prefix="AUDIT",
)
@router.get("/user/{user_id}", response_model=AuditQueryResponse)
async def get_user_audit_trail(
    request: Request,
    user_id: str,
    days: int = Query(7, ge=1, le=90, description="Days of history to retrieve"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get audit trail for a specific user

    Requires admin permission. Returns all audit entries for the specified
    user within the requested time period.
    """
    try:
        audit_logger = await get_audit_logger()

        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        entries = await audit_logger.query(
            start_time=start_time, end_time=end_time, user_id=user_id, limit=1000
        )

        # Issue #372: Use model method to reduce feature envy
        entry_dicts = [e.to_response_dict() for e in entries]

        return AuditQueryResponse(
            success=True,
            total_returned=len(entry_dicts),
            has_more=False,
            entries=entry_dicts,
            query={"user_id": user_id, "days": days},
        )

    except Exception as e:
        logger.error("User audit trail query failed: %s", e)
        raise_server_error("API_0003", f"User audit query error: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_failed_operations",
    error_code_prefix="AUDIT",
)
@router.get("/failures", response_model=AuditQueryResponse)
async def get_failed_operations(
    request: Request,
    hours: int = Query(24, ge=1, le=168, description="Hours of history to check"),
    result_filter: AuditResult = Query("denied", description="Result type to filter"),
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Get failed or denied operations for security monitoring

    Requires admin permission. Returns audit entries for operations that
    failed or were denied, useful for security incident analysis.

    **Result Types:**
    - denied: Permission denied / unauthorized
    - failed: Operation failed
    - error: System error occurred
    """
    try:
        audit_logger = await get_audit_logger()

        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)

        entries = await audit_logger.query(
            start_time=start_time, end_time=end_time, result=result_filter, limit=500
        )

        # Issue #372: Use model method to reduce feature envy
        entry_dicts = [e.to_response_dict() for e in entries]

        return AuditQueryResponse(
            success=True,
            total_returned=len(entry_dicts),
            has_more=False,
            entries=entry_dicts,
            query={"result_filter": result_filter, "hours": hours},
        )

    except Exception as e:
        logger.error("Failed operations query error: %s", e)
        raise_server_error("API_0003", f"Failed operations query error: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="cleanup_old_logs",
    error_code_prefix="AUDIT",
)
@router.post("/cleanup")
async def cleanup_old_logs(
    request: Request,
    cleanup_request: CleanupRequest,
    admin_check: bool = Depends(check_admin_permission),
):
    """
    Trigger cleanup of old audit logs

    Requires admin permission and confirmation. Deletes audit logs older
    than the specified retention period.

    **WARNING:** This operation is irreversible. Deleted logs cannot be recovered.
    """
    try:
        if not cleanup_request.confirm:
            raise_validation_error(
                "API_0001", "Cleanup requires confirmation (set 'confirm' to true)"
            )

        audit_logger = await get_audit_logger()

        # Perform cleanup
        await audit_logger.cleanup_old_logs(days_to_keep=cleanup_request.days_to_keep)

        return {
            "success": True,
            "message": (
                f"Audit logs older than {cleanup_request.days_to_keep} days have been deleted"
            ),
            "days_retained": cleanup_request.days_to_keep,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Audit log cleanup failed: %s", e)
        raise_server_error("API_0003", f"Cleanup error: {str(e)}")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_operation_types",
    error_code_prefix="AUDIT",
)
@router.get("/operations")
async def list_operation_types(
    request: Request, admin_check: bool = Depends(check_admin_permission)
):
    """
    List all available operation types for filtering

    Returns categorized list of all security operations that can be
    audited and filtered.
    """
    try:
        from backend.services.audit_logger import OPERATION_CATEGORIES

        # Group operations by category
        categories = {}
        for operation, category in OPERATION_CATEGORIES.items():
            if category not in categories:
                categories[category] = []
            categories[category].append(operation)

        return {
            "success": True,
            "categories": categories,
            "total_operations": len(OPERATION_CATEGORIES),
        }

    except Exception as e:
        logger.error("Failed to list operations: %s", e)
        raise_server_error("API_0003", f"Operation listing error: {str(e)}")
