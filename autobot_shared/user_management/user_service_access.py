# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Authentication and role management for the shared ``UserService`` (#15068).

Moved verbatim in behaviour from the two backends' copies, which agreed on
every line here, except ``get_user_permissions``. Both forks resolved names with
``select(role.Permission)``; ``Role`` has no such attribute, so the DB-backed
permission path raised and the RBAC middleware denied every user holding a
role with permissions. #18259 fixed it with one join through
``role_permission_query``. That is a decision change from deny to allow on the
DB-backed path, reviewed through the grant-change report
(``permission_grant_report``) rather than shipped silently.
"""

import uuid

from sqlalchemy import select

from autobot_shared.time_utils import now_utc
from autobot_shared.user_management.grant_scope import encode_grant, grants_in_scope
from autobot_shared.user_management.login_eligibility import login_refusal
from autobot_shared.user_management.models.audit import AuditResourceType, IdentityAuditAction
from autobot_shared.user_management.models.role import Role, UserRole
from autobot_shared.user_management.models.user import UserCore
from autobot_shared.user_management.role_permission_query import user_grant_rows_query
from autobot_shared.user_management.user_service_base import UserServiceBase


class UserAccessMixin(UserServiceBase):
    """Authentication and role assignment."""

    # -------------------------------------------------------------------------
    # Authentication
    # -------------------------------------------------------------------------

    async def _log_auth_failure(
        self,
        reason: str,
        ip_address: str | None,
        user_id: uuid.UUID | None = None,
        username_or_email: str | None = None,
    ) -> None:
        """Audit a failed login attempt."""
        details = {"reason": reason, "ip_address": ip_address}
        if username_or_email:
            details["username_or_email"] = username_or_email
        await self._audit_log(IdentityAuditAction.LOGIN_FAILED, AuditResourceType.USER, user_id, details)

    async def _lookup_user_for_auth(self, username_or_email: str) -> UserCore | None:
        """Find the login subject by email first, then by username."""
        user = await self.get_user_by_email(username_or_email)
        if not user:
            user = await self.get_user_by_username(username_or_email)
        return user

    async def _validate_user_can_login(self, user: UserCore, password: str, ip_address: str | None) -> bool:
        """Return True only for an active user whose password verifies."""
        refusal = login_refusal(user)
        if refusal:
            await self._log_auth_failure(refusal, ip_address, user.id)
            return False
        if not user.password_hash:
            await self._log_auth_failure("no_password_set", ip_address, user.id)
            return False
        if not self.verify_password(password, user.password_hash):
            await self._log_auth_failure("invalid_password", ip_address, user.id)
            return False
        return True

    async def authenticate(
        self,
        username_or_email: str,
        password: str,
        ip_address: str | None = None,
    ) -> UserCore | None:
        """Authenticate by username or email and password; None on failure.

        Every outcome is audited, with *ip_address* in the details.
        """
        user = await self._lookup_user_for_auth(username_or_email)
        if not user:
            await self._log_auth_failure("user_not_found", ip_address, username_or_email=username_or_email)
            return None
        if not await self._validate_user_can_login(user, password, ip_address):
            return None

        user.last_login_at = now_utc()
        await self.session.flush()
        await self._audit_log(
            IdentityAuditAction.LOGIN_SUCCESS, AuditResourceType.USER, user.id, {"ip_address": ip_address}
        )
        return user

    # -------------------------------------------------------------------------
    # Role management
    # -------------------------------------------------------------------------

    async def _clear_permission_cache(self, user_id: uuid.UUID) -> None:
        """Invalidate the user's cached permissions once the change commits.

        Scheduled as a post-commit callback to avoid the flush→publish→stale
        re-cache race (GH#7605); falls back to an immediate clear when the
        session carries no callback list (e.g. unit tests with mock sessions).
        """
        # Lazy, as in both forks: the middleware pulls in FastAPI and Redis, which
        # a caller that never changes a role should not pay for at import.
        from autobot_shared.user_management.middleware.rbac_middleware import rbac_middleware  # noqa: PLC0415

        post_cbs = self.session.info.get("_post_commit_cbs")
        if post_cbs is not None:
            post_cbs.append(lambda: rbac_middleware.clear_cache(user_id))
        else:
            await rbac_middleware.clear_cache(user_id)

    async def _find_user_role(self, user_id: uuid.UUID, role_id: uuid.UUID) -> UserRole | None:
        """Return the user→role assignment row, if any."""
        result = await self.session.execute(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role_id)
        )
        return result.scalar_one_or_none()

    async def assign_role(
        self,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
        assigned_by: uuid.UUID | None = None,
    ) -> bool:
        """Assign a role to a user; False if it was already assigned."""
        if await self._find_user_role(user_id, role_id):
            return False
        user_role = UserRole(
            user_id=user_id,
            role_id=role_id,
            assigned_by=assigned_by or self.context.user_id,
        )
        self.session.add(user_role)
        await self.session.flush()
        await self._clear_permission_cache(user_id)
        await self._audit_log(
            IdentityAuditAction.ROLE_ASSIGNED, AuditResourceType.USER, user_id, {"role_id": str(role_id)}
        )
        return True

    async def revoke_role(self, user_id: uuid.UUID, role_id: uuid.UUID) -> bool:
        """Revoke a role from a user; False if it was not assigned."""
        user_role = await self._find_user_role(user_id, role_id)
        if not user_role:
            return False
        await self.session.delete(user_role)
        await self.session.flush()
        await self._clear_permission_cache(user_id)
        await self._audit_log(
            IdentityAuditAction.ROLE_REVOKED, AuditResourceType.USER, user_id, {"role_id": str(role_id)}
        )
        return True

    async def _assign_roles(self, user_id: uuid.UUID, role_ids: list[uuid.UUID]) -> None:
        """Assign multiple roles to a user."""
        for role_id in role_ids:
            await self.assign_role(user_id, role_id)

    async def get_user_roles(self, user_id: uuid.UUID) -> list[Role]:
        """All roles assigned to a user, highest priority first."""
        result = await self.session.execute(
            select(Role).join(UserRole).where(UserRole.user_id == user_id).order_by(Role.priority.desc())
        )
        return list(result.scalars().all())

    async def get_user_permission_grants(self, user_id: uuid.UUID) -> set[str]:
        """Every scoped grant the user holds through their roles, encoded for the cache (#18259, #18338)."""
        rows = (await self.session.execute(user_grant_rows_query(user_id))).all()
        grants = (encode_grant(name, org_id, is_system) for name, org_id, is_system in rows)
        return {grant for grant in grants if grant is not None}

    async def get_user_permissions(self, user_id: uuid.UUID, org_id: uuid.UUID | None = None) -> set[str]:
        """Permission names the user holds acting in *org_id*: platform grants, plus that org's (#18338)."""
        return grants_in_scope(await self.get_user_permission_grants(user_id), org_id)
