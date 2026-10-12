# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Foundation of the shared ``UserService`` (#15068).

Both backends carried their own ``user_service.py``. The copies were the same
class apart from four hunks, each of which one side had and the other lacked.
They now share one implementation, split across modules to stay under the
600-line ceiling:

- ``user_service_base`` (this module): model binding, the two per-service
  hooks, password utilities, lookups and audit logging.
- ``user_service_lifecycle``: password change, (de)activation, deletion.
- ``user_service_access``: authentication and role management.
- ``user_service``: creation, listing and profile updates, and the assembled
  ``UserService``.

The concrete ``User`` differs per backend (the backend's carries activity
relationships the SLM must not gain, #12647), so it is **injected**, as
``OrganizationService`` does: each backend subclasses ``UserService`` and binds
``user_model``. ``Role``/``UserRole``/``AuditLog`` are already one shared class.
"""

import secrets
import uuid
from typing import Any, ClassVar

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autobot_shared.auth.jwt_core import hash_password, verify_password
from autobot_shared.user_management.audit_rows import audit_row
from autobot_shared.user_management.base_service import BaseService, TenantContext
from autobot_shared.user_management.models.role import UserRole
from autobot_shared.user_management.models.user import UserCore


class UserServiceBase(BaseService):
    """Model binding, hooks and shared helpers for ``UserService``."""

    #: Concrete ``User`` mapping for this backend; a subclass of ``UserCore``.
    user_model: ClassVar[type[UserCore]]

    def __init__(self, session: AsyncSession, context: TenantContext | None = None):
        """Initialize the service, failing fast if ``user_model`` is unbound.

        Raises:
            TypeError: the subclass did not bind ``user_model``. Failing here
                beats an ``AttributeError`` inside a query that hides the cause.
        """
        if getattr(type(self), "user_model", None) is None:
            raise TypeError(
                f"{type(self).__name__} must bind 'user_model' — see "
                "autobot_shared/user_management/user_service_base.py (#15068)"
            )
        super().__init__(session, context)

    # -------------------------------------------------------------------------
    # Per-service hooks — no-ops here, supplied by a backend that has the means
    # -------------------------------------------------------------------------

    async def invalidate_other_sessions(self, user_id: uuid.UUID, current_token: str | None) -> int:
        """Revoke this user's other sessions after a password change.

        The password epoch already revokes every session in both services; this
        hook is for a service with a session store of its own (the backend's
        ``SessionService``). Returns how many sessions it invalidated.
        """
        return 0

    async def reassign_memory(self, user_id: uuid.UUID, reassign_to: uuid.UUID) -> dict[str, Any]:
        """Transfer ownership of the user's memory records before deletion.

        Only the backend owns memory records. Returns per-store counts.
        """
        return {}

    # -------------------------------------------------------------------------
    # Password utilities
    # -------------------------------------------------------------------------

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a plain-text password with bcrypt."""
        return hash_password(password)

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """Return True if *password* matches the bcrypt *password_hash*."""
        return verify_password(password, password_hash)

    @staticmethod
    def generate_temp_password() -> str:
        """Generate a secure temporary password."""
        return secrets.token_urlsafe(16)

    # -------------------------------------------------------------------------
    # Lookups
    # -------------------------------------------------------------------------

    def _user_with_roles(self) -> Any:
        """SELECT of non-deleted users with their roles eagerly loaded."""
        user = self.user_model
        return (
            select(user)
            .options(selectinload(user.user_roles).selectinload(UserRole.role))
            .where(user.deleted_at.is_(None))
        )

    async def get_user(self, user_id: uuid.UUID) -> UserCore | None:
        """Get a user by ID, tenant-filtered; None if absent or deleted."""
        query = self._user_with_roles().where(self.user_model.id == user_id)
        query = self.apply_tenant_filter(query, self.user_model)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> UserCore | None:
        """Get a user by email, case-insensitive.

        Not tenant-filtered: login looks users up before a tenant is known.
        """
        query = self._user_with_roles().where(func.lower(self.user_model.email) == email.lower())
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> UserCore | None:
        """Get a user by username, case-insensitive.

        Not tenant-filtered: login looks users up before a tenant is known.
        """
        query = self._user_with_roles().where(func.lower(self.user_model.username) == username.lower())
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _find_by_email_or_username(self, email: str, username: str) -> UserCore | None:
        """Find any user (deleted included) holding this email or username."""
        user = self.user_model
        result = await self.session.execute(
            select(user).where(
                or_(
                    func.lower(user.email) == email.lower(),
                    func.lower(user.username) == username.lower(),
                )
            )
        )
        return result.scalar_one_or_none()

    async def _audit_log(
        self,
        action: str,
        resource_type: str,
        resource_id: uuid.UUID | None,
        details: dict[str, Any],
        outcome: str = "success",
    ) -> None:
        """Add an audit entry; the caller owns the transaction, so no flush."""
        audit_entry = audit_row(
            org_id=self.context.org_id,
            user_id=self.context.user_id,
            action=action,
            resource_type=resource_type,
            resource=resource_id,
            outcome=outcome,
            details=details,
        )
        self.session.add(audit_entry)
