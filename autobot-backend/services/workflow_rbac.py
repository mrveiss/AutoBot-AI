# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow RBAC FastAPI dependencies (#2152).

Provides per-workflow permission enforcement via FastAPI Depends():

    @router.get("/workflows/{workflow_id}/steps")
    async def get_steps(
        workflow_id: str,
        session: AsyncSession = Depends(get_db_session),
        current_user: dict = Depends(get_current_user),
        _: bool = Depends(require_workflow_permission("view")),
    ) -> None:
        ...

The dependency resolves *workflow_id* from the path parameter automatically.
Admins bypass the per-workflow check (they hold all permissions).
"""

from typing import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.logging_manager import get_logger
from services.workflow_permission_service import WorkflowPermissionService
from user_management.config import DeploymentMode, get_deployment_config

logger = get_logger(__name__)

_ADMIN_ROLES = {"admin"}


def _is_admin(user_data: dict) -> bool:
    """Return True when the user holds a system-wide admin role."""
    return user_data.get("role", "").lower() in _ADMIN_ROLES


def require_workflow_permission(action: str) -> Callable:
    """
    FastAPI dependency factory — enforce a per-workflow permission.

    Reads *workflow_id* from the request path parameters.
    Admins and single-user mode bypass the check.

    Args:
        action: Lifecycle action to enforce (view | edit | run | delete | …).

    Returns:
        An async FastAPI dependency.

    Issue #2152: Per-workflow RBAC.
    """

    async def dependency(
        request: Request,
        current_user: dict = Depends(get_current_user),
        session: AsyncSession = Depends(get_db_session),
    ) -> bool:
        """Check per-workflow permission and return True or raise 403."""
        # Single-user mode bypass
        deployment_config = get_deployment_config()
        if deployment_config.mode == DeploymentMode.SINGLE_USER:
            return True

        # System-wide admins always have access
        if _is_admin(current_user):
            return True

        workflow_id = request.path_params.get("workflow_id") or request.path_params.get("id")
        if not workflow_id:
            logger.warning("require_workflow_permission: workflow_id missing from path")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="workflow_id is required",
            )

        user_id = current_user.get("username") or current_user.get("user_id", "")
        svc = WorkflowPermissionService(session)
        allowed = await svc.check_permission(user_id, workflow_id, action)

        if not allowed:
            logger.warning(
                "Workflow permission denied: user=%s workflow=%s action=%s",
                user_id,
                workflow_id,
                action,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission '{action}' required for workflow {workflow_id}",
            )

        return True

    return dependency
