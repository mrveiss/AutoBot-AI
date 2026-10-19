# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical ``UserService`` shared by both backends (#15068).

Creation, listing and profile updates, plus the assembled class. See
``user_service_base`` for how the module is split and why ``User`` is injected.
Each backend binds its concrete model::

    class UserService(SharedUserService):
        user_model = User

``_persist_user`` is the third hunk that separated the copies: the backend
inserted under a SAVEPOINT and named the colliding field on a race (#15772);
the SLM did a plain ``add``/``flush`` and surfaced an ``IntegrityError``. The
stricter SAVEPOINT version is the one both services now run.
"""

import uuid
from typing import Any, Awaitable, Callable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import QueryDefaults
from autobot_shared.time_utils import now_utc
from autobot_shared.user_management.models.audit import AuditResourceType, IdentityAuditAction
from autobot_shared.user_management.models.role import UserRole
from autobot_shared.user_management.models.user import UserCore
from autobot_shared.user_management.user_service_access import UserAccessMixin
from autobot_shared.user_management.user_service_conflict import insert_user_or_raise_duplicate
from autobot_shared.user_management.user_service_errors import DuplicateUserError, UserNotFoundError
from autobot_shared.user_management.user_service_lifecycle import UserLifecycleMixin

logger = get_logger(__name__)

UserLookup = Callable[[str], Awaitable[UserCore | None]]


class UserService(UserLifecycleMixin, UserAccessMixin):
    """User management: CRUD, authentication and roles, multi-tenant.

    Abstract in one respect: ``user_model`` is bound by each backend's subclass.
    """

    # -------------------------------------------------------------------------
    # Creation
    # -------------------------------------------------------------------------

    async def _check_duplicate_user(self, email: str, username: str, email_lower: str, username_lower: str) -> None:
        """Raise ``DuplicateUserError`` naming the field an existing user holds."""
        existing = await self._find_by_email_or_username(email, username)
        if existing:
            if existing.email.lower() == email_lower:
                raise DuplicateUserError(f"User with email '{email}' already exists", field="email")
            raise DuplicateUserError(f"User with username '{username}' already exists", field="username")

    def _build_user_object(
        self,
        email_lower: str,
        username_lower: str,
        password: str | None,
        display_name: str | None,
        username: str,
        effective_org_id: uuid.UUID | None,
        is_platform_admin: bool,
    ) -> UserCore:
        """Build an unsaved, active, unverified user."""
        return self.user_model(
            id=uuid.uuid4(),
            email=email_lower,
            username=username_lower,
            password_hash=self.hash_password(password) if password else None,
            display_name=display_name or username,
            org_id=effective_org_id,
            is_platform_admin=is_platform_admin,
            is_active=True,
            is_verified=False,
            mfa_enabled=False,
            preferences={},
        )

    async def _log_user_creation(
        self,
        user: UserCore,
        email: str,
        username: str,
        effective_org_id: uuid.UUID | None,
        is_platform_admin: bool,
    ) -> None:
        """Audit a user creation."""
        details = {
            "email": email,
            "username": username,
            "org_id": str(effective_org_id) if effective_org_id else None,
            "is_platform_admin": is_platform_admin,
        }
        await self._audit_log(IdentityAuditAction.USER_CREATED, AuditResourceType.USER, user.id, details)

    async def _persist_user(self, user: UserCore, role_ids: list[uuid.UUID] | None, email: str, username: str) -> None:
        """Insert the user SAVEPOINT-isolated against a race (#15772), then assign roles."""
        await insert_user_or_raise_duplicate(self.session, user, email, username, self._find_by_email_or_username)
        if role_ids:
            await self._assign_roles(user.id, role_ids)

    async def create_user(
        self,
        email: str,
        username: str,
        password: str | None = None,
        display_name: str | None = None,
        org_id: uuid.UUID | None = None,
        is_platform_admin: bool = False,
        role_ids: list[uuid.UUID] | None = None,
    ) -> UserCore:
        """Create a user; *org_id* defaults to the tenant context's.

        A user created without *password* cannot log in with one.

        Raises:
            DuplicateUserError: the email or username is taken, including by a
                concurrent insert that won the race.
        """
        email_lower, username_lower = email.lower(), username.lower()
        await self._check_duplicate_user(email, username, email_lower, username_lower)
        effective_org_id = org_id or self.context.org_id
        user = self._build_user_object(
            email_lower, username_lower, password, display_name, username, effective_org_id, is_platform_admin
        )
        await self._persist_user(user, role_ids, email, username)
        await self._log_user_creation(user, email, username, effective_org_id, is_platform_admin)
        logger.info("Created user: %s (id=%s)", username, user.id)
        return user

    # -------------------------------------------------------------------------
    # Listing
    # -------------------------------------------------------------------------

    def _build_user_list_base_query(self, include_inactive: bool, search: str | None) -> Any:
        """Filtered, tenant-scoped base query for ``list_users`` (Issue #576)."""
        user = self.user_model
        base_query = select(user).where(user.deleted_at.is_(None))
        if not include_inactive:
            base_query = base_query.where(user.is_active.is_(True))
        base_query = self.apply_tenant_filter(base_query, user)
        if search:
            pattern = f"%{search}%"
            base_query = base_query.where(
                or_(user.email.ilike(pattern), user.username.ilike(pattern), user.display_name.ilike(pattern))
            )
        return base_query

    async def list_users(
        self,
        limit: int = QueryDefaults.DEFAULT_PAGE_SIZE,
        offset: int = QueryDefaults.DEFAULT_OFFSET,
        include_inactive: bool = False,
        search: str | None = None,
    ) -> tuple[list[UserCore], int]:
        """Page of users, newest first, and the total matching *search*."""
        base_query = self._build_user_list_base_query(include_inactive, search)
        count_result = await self.session.execute(select(func.count()).select_from(base_query.subquery()))
        total = count_result.scalar() or 0

        user = self.user_model
        query = (
            base_query.options(selectinload(user.user_roles).selectinload(UserRole.role))
            .order_by(user.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all()), total

    # -------------------------------------------------------------------------
    # Profile updates
    # -------------------------------------------------------------------------

    async def _update_unique_field(
        self,
        user: UserCore,
        user_id: uuid.UUID,
        field_name: str,
        new_value: str,
        lookup_func: UserLookup,
        changes: dict[str, Any],
    ) -> None:
        """Update a unique field, raising ``DuplicateUserError`` if another user holds it."""
        new_value_lower = new_value.lower()
        current_value = getattr(user, field_name)
        if new_value_lower != current_value.lower():
            existing = await lookup_func(new_value)
            if existing and existing.id != user_id:
                raise DuplicateUserError(f"{field_name.title()} '{new_value}' already in use", field=field_name)
            changes[field_name] = {"old": current_value, "new": new_value_lower}
            setattr(user, field_name, new_value_lower)

    def _update_optional_profile_fields(
        self,
        user: UserCore,
        display_name: str | None,
        bio: str | None,
        avatar_url: str | None,
        preferences: dict[str, Any] | None,
        changes: dict[str, Any],
    ) -> None:
        """Apply each provided profile field; only display_name is change-tracked."""
        if display_name is not None:
            changes["display_name"] = {"old": user.display_name, "new": display_name}
            user.display_name = display_name
        if bio is not None:
            user.bio = bio
        if avatar_url is not None:
            user.avatar_url = avatar_url
        if preferences is not None:
            user.preferences = preferences

    async def _finalize_user_update(self, user: UserCore, user_id: uuid.UUID, changes: dict[str, Any]) -> None:
        """Stamp ``updated_at``, flush, and audit any tracked change."""
        user.updated_at = now_utc()
        await self.session.flush()
        if changes:
            await self._audit_log(
                IdentityAuditAction.USER_UPDATED, AuditResourceType.USER, user_id, {"changes": changes}
            )

    async def update_user(
        self,
        user_id: uuid.UUID,
        email: str | None = None,
        username: str | None = None,
        display_name: str | None = None,
        bio: str | None = None,
        avatar_url: str | None = None,
        preferences: dict[str, Any] | None = None,
    ) -> UserCore:
        """Update the provided profile fields (Issue #620).

        Raises:
            UserNotFoundError: the user does not exist.
            DuplicateUserError: the new email or username is taken.
        """
        user = await self.get_user(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")
        changes: dict[str, Any] = {}
        if email:
            await self._update_unique_field(user, user_id, "email", email, self.get_user_by_email, changes)
        if username:
            await self._update_unique_field(user, user_id, "username", username, self.get_user_by_username, changes)
        self._update_optional_profile_fields(user, display_name, bio, avatar_url, preferences, changes)
        await self._finalize_user_update(user, user_id, changes)
        return user
