# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
WorkflowPermissionService (#2152)

Provides per-workflow access control (grant, revoke, check) and the
append-only audit trail (log_action).

Roles and their capabilities:
  owner  — full control, can grant/revoke permissions
  editor — create, edit, delete the workflow
  runner — execute / trigger the workflow
  viewer — read-only access
"""

from typing import Any, Dict, List

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.workflow_audit import WorkflowAuditLog
from models.workflow_permission import WorkflowPermission

logger = get_logger(__name__)

# Ordered from most to least privileged; used for hierarchy checks.
ROLE_HIERARCHY = ["owner", "editor", "runner", "viewer"]

# Minimum role required for each action type.
ROLE_REQUIRED: Dict[str, str] = {
    "view": "viewer",
    "run": "runner",
    "edit": "editor",
    "create": "editor",
    "delete": "owner",
    "approve": "owner",
    "grant": "owner",
    "revoke": "owner",
}


def _role_satisfies(user_role: str, required_role: str) -> bool:
    """
    Return True when *user_role* is at least as privileged as *required_role*.

    Roles not present in ROLE_HIERARCHY are treated as unprivileged.

    Args:
        user_role: The role the user actually holds.
        required_role: The minimum role needed for the action.
    """
    try:
        user_idx = ROLE_HIERARCHY.index(user_role)
        required_idx = ROLE_HIERARCHY.index(required_role)
        return user_idx <= required_idx
    except ValueError:
        return False


class WorkflowPermissionService:
    """
    Per-workflow RBAC service (#2152).

    Each method expects a live AsyncSession injected by the caller.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Permission checks
    # ------------------------------------------------------------------

    async def check_permission(
        self,
        user_id: str,
        workflow_id: str,
        action: str,
    ) -> bool:
        """
        Return True when *user_id* may perform *action* on *workflow_id*.

        Args:
            user_id: Authenticated user identifier.
            workflow_id: Target workflow identifier.
            action: One of the keys in ROLE_REQUIRED.
        """
        required_role = ROLE_REQUIRED.get(action, "owner")
        row = await self._fetch_permission(user_id, workflow_id)
        if row is None:
            return False
        return _role_satisfies(row.role, required_role)

    async def _fetch_permission(self, user_id: str, workflow_id: str) -> WorkflowPermission | None:
        """Retrieve the permission row for (user_id, workflow_id), or None."""
        stmt = select(WorkflowPermission).where(
            WorkflowPermission.user_id == user_id,
            WorkflowPermission.workflow_id == workflow_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Permission mutations
    # ------------------------------------------------------------------

    async def grant_permission(
        self,
        workflow_id: str,
        user_id: str,
        role: str,
        granted_by: str,
    ) -> WorkflowPermission:
        """
        Grant *role* on *workflow_id* to *user_id* (upsert).

        Raises ValueError when *role* is not in ROLE_HIERARCHY.

        Args:
            workflow_id: Target workflow identifier.
            user_id: User receiving the role.
            role: One of owner | editor | runner | viewer.
            granted_by: User performing the grant.
        """
        if role not in ROLE_HIERARCHY:
            raise ValueError(f"Invalid workflow role '{role}'")

        perm = await self._fetch_permission(user_id, workflow_id)
        if perm is None:
            perm = WorkflowPermission(
                workflow_id=workflow_id,
                user_id=user_id,
                role=role,
                granted_by=granted_by,
            )
            self.session.add(perm)
            try:
                await self.session.flush()
            except IntegrityError:
                await self.session.rollback()
                perm = await self._fetch_permission(user_id, workflow_id)
                if perm is None:
                    raise
                perm.role = role
                perm.granted_by = granted_by
        else:
            perm.role = role
            perm.granted_by = granted_by
        await self.session.commit()
        await self.session.refresh(perm)
        logger.info(
            "Workflow permission granted: workflow=%s user=%s role=%s by=%s",
            workflow_id,
            user_id,
            role,
            granted_by,
        )
        return perm

    async def grant_owner(self, workflow_id: str, user_id: str) -> WorkflowPermission:
        """
        Convenience wrapper — assign owner role to the workflow creator (#2152).

        Args:
            workflow_id: Newly created workflow identifier.
            user_id: Creator's user identifier.
        """
        return await self.grant_permission(
            workflow_id=workflow_id,
            user_id=user_id,
            role="owner",
            granted_by=user_id,
        )

    async def revoke_permission(
        self,
        workflow_id: str,
        user_id: str,
        revoked_by: str,
    ) -> bool:
        """
        Remove the permission entry for *user_id* on *workflow_id*.

        Returns True when a row was deleted, False when none existed.

        Args:
            workflow_id: Target workflow identifier.
            user_id: User losing access.
            revoked_by: User performing the revocation.
        """
        stmt = delete(WorkflowPermission).where(
            WorkflowPermission.workflow_id == workflow_id,
            WorkflowPermission.user_id == user_id,
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        deleted = result.rowcount > 0
        if deleted:
            logger.info(
                "Workflow permission revoked: workflow=%s user=%s by=%s",
                workflow_id,
                user_id,
                revoked_by,
            )
        return deleted

    # ------------------------------------------------------------------
    # Permission queries
    # ------------------------------------------------------------------

    async def get_permissions(self, workflow_id: str) -> List[WorkflowPermission]:
        """
        Return all permission entries for *workflow_id*.

        Args:
            workflow_id: Target workflow identifier.
        """
        stmt = select(WorkflowPermission).where(WorkflowPermission.workflow_id == workflow_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Audit logging
    # ------------------------------------------------------------------

    async def log_action(
        self,
        user_id: str,
        workflow_id: str,
        action: str,
        details: Dict[str, Any] | None = None,
    ) -> None:
        """
        Append an audit log entry for a workflow lifecycle event (#2152).

        This method never raises; failures are logged as warnings so that
        audit errors never break the caller's happy path.

        Args:
            user_id: User performing the action.
            workflow_id: Target workflow identifier.
            action: Lifecycle action label (e.g. 'create', 'run').
            details: Optional structured metadata for the entry.
        """
        try:
            entry = WorkflowAuditLog(
                user_id=user_id,
                workflow_id=workflow_id,
                action=action,
                details=details,
            )
            self.session.add(entry)
            await self.session.commit()
        except Exception as exc:
            logger.warning(
                "Failed to write workflow audit log: workflow=%s action=%s error=%s",
                workflow_id,
                action,
                exc,
            )

    async def get_audit_log(
        self,
        workflow_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> List[WorkflowAuditLog]:
        """
        Return audit log entries for *workflow_id*, newest first.

        Args:
            workflow_id: Target workflow identifier.
            limit: Maximum rows to return (1–1000).
            offset: Pagination offset.
        """
        stmt = (
            select(WorkflowAuditLog)
            .where(WorkflowAuditLog.workflow_id == workflow_id)
            .order_by(WorkflowAuditLog.timestamp.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
