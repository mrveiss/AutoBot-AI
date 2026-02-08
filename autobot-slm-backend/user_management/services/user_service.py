# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Service

Business logic for user management operations including CRUD,
authentication, and role assignment.
"""

import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import bcrypt
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from user_management.models import Role, User, UserRole
from user_management.models.audit import AuditAction, AuditLog, AuditResourceType
from user_management.services.base_service import BaseService, TenantContext

logger = logging.getLogger(__name__)


class UserServiceError(Exception):
    """Base exception for user service errors."""


class UserNotFoundError(UserServiceError):
    """Raised when user is not found."""


class DuplicateUserError(UserServiceError):
    """Raised when attempting to create a duplicate user."""


class InvalidCredentialsError(UserServiceError):
    """Raised when authentication fails."""


class UserService(BaseService):
    """
    User management service.

    Provides CRUD operations and authentication for users with
    multi-tenancy support.
    """

    # Password hashing configuration
    BCRYPT_ROUNDS = 12

    def __init__(self, session: AsyncSession, context: Optional[TenantContext] = None):
        """Initialize user service."""
        super().__init__(session, context)

    # -------------------------------------------------------------------------
    # Password Utilities
    # -------------------------------------------------------------------------

    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            Bcrypt hash string
        """
        salt = bcrypt.gensalt(rounds=UserService.BCRYPT_ROUNDS)
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        Verify password against hash.

        Args:
            password: Plain text password
            password_hash: Bcrypt hash to verify against

        Returns:
            True if password matches
        """
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"), password_hash.encode("utf-8")
            )
        except Exception as e:
            logger.error("Password verification error: %s", e)
            return False

    @staticmethod
    def generate_temp_password() -> str:
        """Generate a secure temporary password."""
        return secrets.token_urlsafe(16)

    # -------------------------------------------------------------------------
    # User CRUD Operations
    # -------------------------------------------------------------------------

    async def _check_duplicate_user(
        self, email: str, username: str, email_lower: str, username_lower: str
    ) -> None:
        """Issue #665: Extracted from create_user to reduce function length."""
        existing = await self._find_by_email_or_username(email, username)
        if existing:
            if existing.email.lower() == email_lower:
                raise DuplicateUserError(f"User with email '{email}' already exists")
            raise DuplicateUserError(f"User with username '{username}' already exists")

    def _build_user_object(
        self,
        email_lower: str,
        username_lower: str,
        password: Optional[str],
        display_name: Optional[str],
        username: str,
        effective_org_id: Optional[uuid.UUID],
        is_platform_admin: bool,
    ) -> User:
        """Build User model instance with provided attributes. Issue #620."""
        return User(
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
        user: User,
        email: str,
        username: str,
        effective_org_id: Optional[uuid.UUID],
        is_platform_admin: bool,
    ) -> None:
        """Log audit entry for user creation. Issue #620."""
        await self._audit_log(
            action=AuditAction.USER_CREATED,
            resource_type=AuditResourceType.USER,
            resource_id=user.id,
            details={
                "email": email,
                "username": username,
                "org_id": str(effective_org_id) if effective_org_id else None,
                "is_platform_admin": is_platform_admin,
            },
        )

    async def _persist_user(
        self, user: User, role_ids: Optional[List[uuid.UUID]]
    ) -> None:
        """Add user to session and assign roles. Issue #620."""
        self.session.add(user)
        await self.session.flush()
        if role_ids:
            await self._assign_roles(user.id, role_ids)

    async def create_user(
        self,
        email: str,
        username: str,
        password: Optional[str] = None,
        display_name: Optional[str] = None,
        org_id: Optional[uuid.UUID] = None,
        is_platform_admin: bool = False,
        role_ids: Optional[List[uuid.UUID]] = None,
    ) -> User:
        """
        Create a new user. Issue #620.

        Args:
            email: User email (unique)
            username: Username (unique)
            password: Optional password (if None, user cannot login with password)
            display_name: Optional display name
            org_id: Organization ID (uses context if not provided)
            is_platform_admin: Whether user is a platform admin
            role_ids: List of role IDs to assign

        Returns:
            Created User instance

        Raises:
            DuplicateUserError: If email or username already exists
        """
        email_lower = email.lower()
        username_lower = username.lower()
        await self._check_duplicate_user(email, username, email_lower, username_lower)

        effective_org_id = org_id or self.context.org_id
        user = self._build_user_object(
            email_lower,
            username_lower,
            password,
            display_name,
            username,
            effective_org_id,
            is_platform_admin,
        )
        await self._persist_user(user, role_ids)
        await self._log_user_creation(
            user, email, username, effective_org_id, is_platform_admin
        )
        logger.info("Created user: %s (id=%s)", username, user.id)
        return user

    async def get_user(self, user_id: uuid.UUID) -> Optional[User]:
        """
        Get user by ID.

        Args:
            user_id: User UUID

        Returns:
            User instance or None
        """
        query = (
            select(User)
            .options(selectinload(User.roles).selectinload(UserRole.role))
            .where(User.id == user_id)
            .where(User.deleted_at.is_(None))
        )
        query = self.apply_tenant_filter(query, User)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        Get user by email address.

        Args:
            email: Email address (case-insensitive)

        Returns:
            User instance or None
        """
        query = (
            select(User)
            .options(selectinload(User.roles).selectinload(UserRole.role))
            .where(func.lower(User.email) == email.lower())
            .where(User.deleted_at.is_(None))
        )
        # Don't apply tenant filter for email lookup (used in login)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_user_by_username(self, username: str) -> Optional[User]:
        """
        Get user by username.

        Args:
            username: Username (case-insensitive)

        Returns:
            User instance or None
        """
        query = (
            select(User)
            .options(selectinload(User.roles).selectinload(UserRole.role))
            .where(func.lower(User.username) == username.lower())
            .where(User.deleted_at.is_(None))
        )
        # Don't apply tenant filter for username lookup (used in login)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    def _build_user_list_base_query(
        self, include_inactive: bool, search: Optional[str]
    ):
        """Build filtered base query for user listing.

        Helper for list_users (Issue #576).
        """
        base_query = select(User).where(User.deleted_at.is_(None))

        if not include_inactive:
            base_query = base_query.where(User.is_active.is_(True))

        base_query = self.apply_tenant_filter(base_query, User)

        if search:
            search_pattern = f"%{search}%"
            base_query = base_query.where(
                or_(
                    User.email.ilike(search_pattern),
                    User.username.ilike(search_pattern),
                    User.display_name.ilike(search_pattern),
                )
            )
        return base_query

    async def list_users(
        self,
        limit: int = 50,
        offset: int = 0,
        include_inactive: bool = False,
        search: Optional[str] = None,
    ) -> tuple[List[User], int]:
        """List users with pagination and optional search filtering."""
        base_query = self._build_user_list_base_query(include_inactive, search)

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        # Get paginated results
        query = (
            base_query.options(selectinload(User.roles).selectinload(UserRole.role))
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(query)
        users = list(result.scalars().all())

        return users, total

    async def _update_unique_field(
        self,
        user: User,
        user_id: uuid.UUID,
        field_name: str,
        new_value: str,
        lookup_func,
        changes: dict,
    ) -> None:
        """Update a unique field with duplicate check. Issue #620."""
        new_value_lower = new_value.lower()
        current_value = getattr(user, field_name)

        if new_value_lower != current_value.lower():
            existing = await lookup_func(new_value)
            if existing and existing.id != user_id:
                raise DuplicateUserError(
                    f"{field_name.title()} '{new_value}' already in use"
                )
            changes[field_name] = {"old": current_value, "new": new_value_lower}
            setattr(user, field_name, new_value_lower)

    def _update_optional_profile_fields(
        self,
        user: User,
        display_name: Optional[str],
        bio: Optional[str],
        avatar_url: Optional[str],
        preferences: Optional[dict],
        changes: dict,
    ) -> None:
        """Update optional profile fields on user object. Issue #620.

        Args:
            user: User object to update
            display_name: New display name if provided
            bio: New bio if provided
            avatar_url: New avatar URL if provided
            preferences: New preferences dict if provided
            changes: Dictionary to track changes for audit
        """
        if display_name is not None:
            changes["display_name"] = {"old": user.display_name, "new": display_name}
            user.display_name = display_name

        if bio is not None:
            user.bio = bio

        if avatar_url is not None:
            user.avatar_url = avatar_url

        if preferences is not None:
            user.preferences = preferences

    async def _finalize_user_update(
        self, user: User, user_id: uuid.UUID, changes: dict
    ) -> None:
        """Finalize user update with timestamp and audit logging. Issue #620."""
        user.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        if changes:
            await self._audit_log(
                action=AuditAction.USER_UPDATED,
                resource_type=AuditResourceType.USER,
                resource_id=user_id,
                details={"changes": changes},
            )

    async def update_user(
        self,
        user_id: uuid.UUID,
        email: Optional[str] = None,
        username: Optional[str] = None,
        display_name: Optional[str] = None,
        bio: Optional[str] = None,
        avatar_url: Optional[str] = None,
        preferences: Optional[dict] = None,
    ) -> User:
        """
        Update user profile fields.

        Args:
            user_id: User ID to update
            email: New email (optional)
            username: New username (optional)
            display_name: New display name (optional)
            bio: New bio (optional)
            avatar_url: New avatar URL (optional)
            preferences: New preferences dict (optional)

        Returns:
            Updated User instance. Issue #620.
        """
        user = await self.get_user(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        changes = {}

        if email:
            await self._update_unique_field(
                user, user_id, "email", email, self.get_user_by_email, changes
            )

        if username:
            await self._update_unique_field(
                user, user_id, "username", username, self.get_user_by_username, changes
            )

        self._update_optional_profile_fields(
            user, display_name, bio, avatar_url, preferences, changes
        )

        await self._finalize_user_update(user, user_id, changes)
        return user

    async def change_password(
        self,
        user_id: uuid.UUID,
        current_password: Optional[str],
        new_password: str,
        require_current: bool = True,
    ) -> bool:
        """
        Change user password.

        Args:
            user_id: User ID
            current_password: Current password (for verification)
            new_password: New password
            require_current: Whether to require current password verification

        Returns:
            True if password changed

        Raises:
            UserNotFoundError: If user not found
            InvalidCredentialsError: If current password is wrong
        """
        user = await self.get_user(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        if require_current and user.password_hash:
            if not current_password or not self.verify_password(
                current_password, user.password_hash
            ):
                raise InvalidCredentialsError("Current password is incorrect")

        user.password_hash = self.hash_password(new_password)
        user.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        await self._audit_log(
            action=AuditAction.PASSWORD_CHANGED,
            resource_type=AuditResourceType.USER,
            resource_id=user_id,
            details={"method": "user_initiated"},
        )

        return True

    async def deactivate_user(self, user_id: uuid.UUID) -> bool:
        """
        Deactivate a user account.

        Args:
            user_id: User ID to deactivate

        Returns:
            True if deactivated

        Raises:
            UserNotFoundError: If user not found
        """
        user = await self.get_user(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        user.is_active = False
        user.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        await self._audit_log(
            action=AuditAction.USER_DEACTIVATED,
            resource_type=AuditResourceType.USER,
            resource_id=user_id,
            details={},
        )

        logger.info("Deactivated user: %s", user_id)
        return True

    async def activate_user(self, user_id: uuid.UUID) -> bool:
        """
        Activate a user account.

        Args:
            user_id: User ID to activate

        Returns:
            True if activated

        Raises:
            UserNotFoundError: If user not found
        """
        user = await self.get_user(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        user.is_active = True
        user.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        await self._audit_log(
            action=AuditAction.USER_ACTIVATED,
            resource_type=AuditResourceType.USER,
            resource_id=user_id,
            details={},
        )

        logger.info("Activated user: %s", user_id)
        return True

    async def delete_user(self, user_id: uuid.UUID, hard_delete: bool = False) -> bool:
        """
        Delete a user account.

        Args:
            user_id: User ID to delete
            hard_delete: If True, permanently delete; otherwise soft delete

        Returns:
            True if deleted

        Raises:
            UserNotFoundError: If user not found
        """
        user = await self.get_user(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        if hard_delete:
            await self.session.delete(user)
        else:
            user.deleted_at = datetime.now(timezone.utc)
            user.is_active = False

        await self.session.flush()

        await self._audit_log(
            action=AuditAction.USER_DELETED,
            resource_type=AuditResourceType.USER,
            resource_id=user_id,
            details={"hard_delete": hard_delete},
        )

        logger.info("Deleted user: %s (hard=%s)", user_id, hard_delete)
        return True

    # -------------------------------------------------------------------------
    # Authentication
    # -------------------------------------------------------------------------

    async def _log_auth_failure(
        self,
        reason: str,
        ip_address: Optional[str],
        user_id: Optional[uuid.UUID] = None,
        username_or_email: Optional[str] = None,
    ) -> None:
        """Issue #665: Extracted from authenticate to reduce function length."""
        details = {"reason": reason, "ip_address": ip_address}
        if username_or_email:
            details["username_or_email"] = username_or_email
        await self._audit_log(
            action=AuditAction.LOGIN_FAILED,
            resource_type=AuditResourceType.USER,
            resource_id=user_id,
            details=details,
        )

    async def _lookup_user_for_auth(self, username_or_email: str) -> Optional[User]:
        """Issue #665: Extracted from authenticate to reduce function length."""
        user = await self.get_user_by_email(username_or_email)
        if not user:
            user = await self.get_user_by_username(username_or_email)
        return user

    async def _validate_user_can_login(
        self, user: User, password: str, ip_address: Optional[str]
    ) -> bool:
        """Issue #665: Extracted from authenticate to reduce function length."""
        if not user.is_active:
            await self._log_auth_failure("account_inactive", ip_address, user.id)
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
        ip_address: Optional[str] = None,
    ) -> Optional[User]:
        """
        Authenticate user with username/email and password.

        Args:
            username_or_email: Username or email
            password: Password to verify
            ip_address: Client IP for audit logging

        Returns:
            User instance if authenticated, None otherwise
        """
        user = await self._lookup_user_for_auth(username_or_email)
        if not user:
            await self._log_auth_failure(
                "user_not_found", ip_address, username_or_email=username_or_email
            )
            return None

        if not await self._validate_user_can_login(user, password, ip_address):
            return None

        # Update last login
        user.last_login_at = datetime.now(timezone.utc)
        await self.session.flush()

        await self._audit_log(
            action=AuditAction.LOGIN_SUCCESS,
            resource_type=AuditResourceType.USER,
            resource_id=user.id,
            details={"ip_address": ip_address},
        )
        return user

    # -------------------------------------------------------------------------
    # Role Management
    # -------------------------------------------------------------------------

    async def assign_role(
        self,
        user_id: uuid.UUID,
        role_id: uuid.UUID,
        assigned_by: Optional[uuid.UUID] = None,
    ) -> bool:
        """
        Assign a role to a user.

        Args:
            user_id: User ID
            role_id: Role ID to assign
            assigned_by: User ID who assigned the role

        Returns:
            True if role assigned
        """
        # Check if already assigned
        existing = await self.session.execute(
            select(UserRole).where(
                UserRole.user_id == user_id, UserRole.role_id == role_id
            )
        )
        if existing.scalar_one_or_none():
            return False  # Already assigned

        user_role = UserRole(
            user_id=user_id,
            role_id=role_id,
            assigned_by=assigned_by or self.context.user_id,
        )
        self.session.add(user_role)
        await self.session.flush()

        await self._audit_log(
            action=AuditAction.ROLE_ASSIGNED,
            resource_type=AuditResourceType.USER,
            resource_id=user_id,
            details={"role_id": str(role_id)},
        )

        return True

    async def revoke_role(self, user_id: uuid.UUID, role_id: uuid.UUID) -> bool:
        """
        Revoke a role from a user.

        Args:
            user_id: User ID
            role_id: Role ID to revoke

        Returns:
            True if role revoked
        """
        result = await self.session.execute(
            select(UserRole).where(
                UserRole.user_id == user_id, UserRole.role_id == role_id
            )
        )
        user_role = result.scalar_one_or_none()
        if not user_role:
            return False

        await self.session.delete(user_role)
        await self.session.flush()

        await self._audit_log(
            action=AuditAction.ROLE_REVOKED,
            resource_type=AuditResourceType.USER,
            resource_id=user_id,
            details={"role_id": str(role_id)},
        )

        return True

    async def get_user_roles(self, user_id: uuid.UUID) -> List[Role]:
        """
        Get all roles assigned to a user.

        Args:
            user_id: User ID

        Returns:
            List of Role instances
        """
        result = await self.session.execute(
            select(Role)
            .join(UserRole)
            .where(UserRole.user_id == user_id)
            .order_by(Role.priority.desc())
        )
        return list(result.scalars().all())

    async def get_user_permissions(self, user_id: uuid.UUID) -> set[str]:
        """
        Get all permission names for a user.

        Args:
            user_id: User ID

        Returns:
            Set of permission names
        """
        roles = await self.get_user_roles(user_id)
        permissions = set()

        for role in roles:
            # Load permissions for each role
            result = await self.session.execute(
                select(Role)
                .options(selectinload(Role.role_permissions))
                .where(Role.id == role.id)
            )
            role_with_perms = result.scalar_one_or_none()
            if role_with_perms:
                for rp in role_with_perms.role_permissions:
                    # Get permission name
                    perm_result = await self.session.execute(
                        select(role.Permission).where(
                            role.Permission.id == rp.permission_id
                        )
                    )
                    perm = perm_result.scalar_one_or_none()
                    if perm:
                        permissions.add(perm.name)

        return permissions

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    async def _find_by_email_or_username(
        self, email: str, username: str
    ) -> Optional[User]:
        """Find user by email or username."""
        # Cache lower() values to avoid repeated calls
        email_lower = email.lower()
        username_lower = username.lower()
        result = await self.session.execute(
            select(User).where(
                or_(
                    func.lower(User.email) == email_lower,
                    func.lower(User.username) == username_lower,
                )
            )
        )
        return result.scalar_one_or_none()

    async def _assign_roles(
        self, user_id: uuid.UUID, role_ids: List[uuid.UUID]
    ) -> None:
        """Assign multiple roles to a user."""
        for role_id in role_ids:
            await self.assign_role(user_id, role_id)

    async def _audit_log(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[uuid.UUID],
        details: dict,
        outcome: str = "success",
    ) -> None:
        """
        Create audit log entry.

        Args:
            action: Action performed
            resource_type: Type of resource affected
            resource_id: ID of resource affected
            details: Additional details
            outcome: Outcome (success/failure)
        """
        audit_entry = AuditLog(
            id=uuid.uuid4(),
            org_id=self.context.org_id,
            user_id=self.context.user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            details=details,
        )
        self.session.add(audit_entry)
        # Don't flush here - let the caller manage the transaction
