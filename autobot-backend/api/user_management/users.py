# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Users API Endpoints

REST API for user management operations.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.schemas_agent import (
    PasswordChangedResponse,
    RoleAssignmentResponse,
    RoleUpdateRequest,
    RoleUpdateResponse,
    UserCreatedResponse,
    UserDeletedResponse,
    UserSearchResponse,
    UserSearchResult,
)
from api.user_management.dependencies import (
    get_current_user,
    get_user_service,
    require_platform_admin,
    require_user_management_enabled,
)
from autobot_shared.logging_manager import get_logger
from autobot_shared.models.pagination import PaginationParams
from user_management.middleware.rate_limit import (
    PasswordChangeRateLimiter,
    RateLimitExceeded,
)
from user_management.schemas import (
    PasswordChange,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserUpdate,
)
from user_management.services import UserService
from user_management.services.user_service import (
    DuplicateUserError,
    InvalidCredentialsError,
    UserNotFoundError,
)

router = APIRouter(prefix="/users", tags=["Users"])
logger = get_logger(__name__)


# -------------------------------------------------------------------------
# User CRUD Endpoints
# -------------------------------------------------------------------------


@router.get(
    "",
    response_model=UserListResponse,
    summary="List users",
    description="List users with pagination and optional search filter.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def list_users(
    pagination: PaginationParams = Depends(),
    search: str | None = Query(None, description="Search by email, username, or name"),
    include_inactive: bool = Query(False, description="Include inactive users"),
    user_service: UserService = Depends(get_user_service),
):
    """List users with pagination."""
    users, total = await user_service.list_users(
        limit=pagination.limit,
        offset=pagination.offset,
        search=search,
        include_inactive=include_inactive,
    )

    return UserListResponse(
        users=[_user_to_response(user) for user in users],
        total=total,
        limit=pagination.limit,
        offset=pagination.offset,
    )


@router.get(
    "/search",
    response_model=UserSearchResponse,
    summary="Search users for sharing",
    description=(
        "Search users by name or username for use in sharing dialogs. "
        "Safe to call in all deployment modes — returns empty list with "
        "available=False when user management is not enabled. Issue #2072."
    ),
)
async def search_users_for_sharing(
    q: str = Query("", description="Search query (name or username)"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
) -> UserSearchResponse:
    """Search users by name/username for the knowledge sharing dialog.

    Works in all deployment modes:
    - single_user: Returns available=False with an empty list.
    - multi-user with postgres: Returns matching users from the database.
    """
    from user_management.config import DeploymentMode, get_deployment_config

    config = get_deployment_config()

    if config.mode == DeploymentMode.SINGLE_USER:
        logger.debug("search_users_for_sharing: single_user mode, returning unavailable")
        return UserSearchResponse(
            users=[],
            available=False,
            message="User search is not available in single-user mode",
        )

    if not config.postgres_enabled:
        logger.debug("search_users_for_sharing: postgres disabled, returning unavailable")
        return UserSearchResponse(
            users=[],
            available=False,
            message="User search requires database support",
        )

    return await _search_users_from_db(q, limit)


async def _search_users_from_db(q: str, limit: int) -> UserSearchResponse:
    """Perform a database user search and return sharing-compatible results.

    Issue #2072: Helper that performs the actual DB search so the main
    endpoint stays within the 30-line target.
    """
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    try:
        async for session in get_async_session():
            context = TenantContext(org_id=None, user_id=None, is_platform_admin=True)
            service = UserService(session, context)
            search_term = q.strip() if q.strip() else None
            users, _ = await service.list_users(
                limit=limit,
                offset=0,
                search=search_term,
                include_inactive=False,
            )
            results = [
                UserSearchResult(
                    id=str(user.id),
                    name=user.display_name or user.username,
                    type="user",
                )
                for user in users
            ]
            logger.debug("search_users_for_sharing: found %d results for %r", len(results), q)
            return UserSearchResponse(
                users=results,
                available=True,
                message="",
            )
    except Exception:
        logger.exception("search_users_for_sharing: database query failed")
        return UserSearchResponse(
            users=[],
            available=False,
            message="User search temporarily unavailable",
        )

    return UserSearchResponse(users=[], available=True, message="")


@router.post(
    "",
    response_model=UserCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create user",
    description="Create a new user account.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def create_user(
    user_data: UserCreate,
    user_service: UserService = Depends(get_user_service),
):
    """Create a new user."""
    try:
        user = await user_service.create_user(
            email=user_data.email,
            username=user_data.username,
            password=user_data.password,
            display_name=user_data.display_name,
            org_id=user_data.org_id,
            role_ids=user_data.role_ids,
        )

        return UserCreatedResponse(
            message=f"User '{user.username}' created successfully",
            user=_user_to_response(user),
        )

    except DuplicateUserError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Internal server error",
        )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user",
    description="Get the currently authenticated user's profile.",
    # Note: No require_user_management_enabled - /me works in all modes
)
async def get_current_user_profile(
    current_user: dict = Depends(get_current_user),
):
    """Get current user's profile.

    Works in all deployment modes:
    - single_user: Returns default admin user (no DB required)
    - Other modes: Returns user from database or session
    """
    from user_management.config import DeploymentMode, get_deployment_config

    config = get_deployment_config()
    username = current_user.get("username")

    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unable to identify current user",
        )

    # In single_user mode, return synthetic user without DB access
    if config.mode == DeploymentMode.SINGLE_USER:
        return UserResponse(
            id=uuid.uuid4(),  # Generate consistent ID based on username
            email=current_user.get("email", f"{username}@autobot.local"),
            username=username,
            display_name=username.title(),
            is_active=True,
            is_verified=True,
            mfa_enabled=False,
            is_platform_admin=True,  # Single user is always admin
            preferences={},
            roles=[],
            created_at=None,
            updated_at=None,
        )

    # In other modes, try to fetch from database
    if config.postgres_enabled:
        pass

        # This will need the Request object, so we handle it differently
        # For now, return session-based user if no DB

    # Fallback: Return user from session data (config-based user)
    return UserResponse(
        id=uuid.uuid4(),
        email=current_user.get("email", f"{username}@autobot.local"),
        username=username,
        display_name=username.title(),
        is_active=True,
        is_verified=True,
        mfa_enabled=False,
        is_platform_admin=current_user.get("role") == "admin" or current_user.get("is_platform_admin", False),
        preferences={},
        roles=[],
        created_at=None,
        updated_at=None,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Get user",
    description="Get a specific user by ID.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def get_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
):
    """Get user by ID."""
    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    return _user_to_response(user)


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Update user",
    description="Update a user's profile.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def update_user(
    user_id: uuid.UUID,
    user_data: UserUpdate,
    user_service: UserService = Depends(get_user_service),
):
    """Update user profile."""
    try:
        user = await user_service.update_user(
            user_id=user_id,
            email=user_data.email,
            username=user_data.username,
            display_name=user_data.display_name,
            bio=user_data.bio,
            avatar_url=user_data.avatar_url,
            preferences=user_data.preferences,
        )

        return _user_to_response(user)

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    except DuplicateUserError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Internal server error",
        )


@router.delete(
    "/{user_id}",
    response_model=UserDeletedResponse,
    summary="Delete user",
    description="Delete a user account (soft delete by default).",
    dependencies=[Depends(require_user_management_enabled)],
)
async def delete_user(
    user_id: uuid.UUID,
    hard_delete: bool = Query(False, description="Permanently delete user"),
    user_service: UserService = Depends(get_user_service),
):
    """Delete user account."""
    try:
        await user_service.delete_user(user_id, hard_delete=hard_delete)
        return UserDeletedResponse(
            message=f"User {user_id} deleted successfully",
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )


# -------------------------------------------------------------------------
# User Status Endpoints
# -------------------------------------------------------------------------


@router.post(
    "/{user_id}/activate",
    response_model=UserResponse,
    summary="Activate user",
    description="Activate a deactivated user account.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def activate_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
):
    """Activate user account."""
    try:
        await user_service.activate_user(user_id)
        user = await user_service.get_user(user_id)
        return _user_to_response(user)

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )


@router.post(
    "/{user_id}/deactivate",
    response_model=UserResponse,
    summary="Deactivate user",
    description="Deactivate a user account.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def deactivate_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
):
    """Deactivate user account."""
    try:
        await user_service.deactivate_user(user_id)
        user = await user_service.get_user(user_id)
        return _user_to_response(user)

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )


# -------------------------------------------------------------------------
# Password Management
# -------------------------------------------------------------------------


@router.post(
    "/{user_id}/change-password",
    response_model=PasswordChangedResponse,
    summary="Change password",
    description="Change a user's password.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def change_password(
    user_id: uuid.UUID,
    password_data: PasswordChange,
    user_service: UserService = Depends(get_user_service),
    current_user: dict = Depends(get_current_user),
):
    """Change user password with rate limiting and session invalidation."""
    rate_limiter = PasswordChangeRateLimiter()

    # Check rate limit before attempting password change
    try:
        await rate_limiter.check_rate_limit(user_id)
    except RateLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Internal server error",
        )

    try:
        # Extract current token to preserve this session
        current_token = current_user.get("token")

        await user_service.change_password(
            user_id=user_id,
            current_password=password_data.current_password,
            new_password=password_data.new_password,
            require_current=password_data.current_password is not None,
            current_token=current_token,
        )

        # Record successful attempt (clears rate limit counter)
        await rate_limiter.record_attempt(user_id, success=True)

        return PasswordChangedResponse(
            message="Password changed successfully",
        )

    except UserNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )
    except InvalidCredentialsError:
        # Record failed attempt
        await rate_limiter.record_attempt(user_id, success=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
        )


# -------------------------------------------------------------------------
# Role Management
# -------------------------------------------------------------------------


@router.post(
    "/{user_id}/roles/{role_id}",
    response_model=RoleAssignmentResponse,
    summary="Assign role",
    description="Assign a role to a user.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def assign_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
):
    """Assign role to user."""
    assigned = await user_service.assign_role(user_id, role_id)
    if not assigned:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Role already assigned to user",
        )

    return RoleAssignmentResponse(
        message="Role assigned successfully",
        role_id=role_id,
    )


@router.delete(
    "/{user_id}/roles/{role_id}",
    response_model=RoleAssignmentResponse,
    summary="Revoke role",
    description="Revoke a role from a user.",
    dependencies=[Depends(require_user_management_enabled)],
)
async def revoke_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
):
    """Revoke role from user."""
    revoked = await user_service.revoke_role(user_id, role_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not assigned to user",
        )

    return RoleAssignmentResponse(
        message="Role revoked successfully",
        role_id=role_id,
    )


# -------------------------------------------------------------------------
# Role-by-name Management (#1801)
# -------------------------------------------------------------------------


@router.put(
    "/{user_id}/role",
    response_model=RoleUpdateResponse,
    summary="Set user role by name",
    description=(
        "Replace all system roles for a user with the named role (admin, user, readonly). "
        "Requires admin privilege. Issue #1801."
    ),
    dependencies=[
        Depends(require_user_management_enabled),
        Depends(require_platform_admin),
    ],
)
async def set_user_role(
    user_id: uuid.UUID,
    body: RoleUpdateRequest,
    user_service: UserService = Depends(get_user_service),
):
    """Set a user's system role by name, replacing previous system role assignments."""
    from sqlalchemy import delete, select

    from user_management.models.role import Role, UserRole

    user = await user_service.get_user(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found",
        )

    # Resolve target role from system roles
    session = user_service.session
    target_role_result = await session.execute(select(Role).where(Role.name == body.role, Role.is_system.is_(True)))
    target_role = target_role_result.scalar_one_or_none()
    if not target_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"System role '{body.role}' not found",
        )

    # Remove all existing system role assignments for this user
    system_role_ids_result = await session.execute(select(Role.id).where(Role.is_system.is_(True)))
    system_role_ids = [r for (r,) in system_role_ids_result.all()]
    if system_role_ids:
        await session.execute(
            delete(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id.in_(system_role_ids),
            )
        )
        await session.flush()

    # Assign the new role
    await user_service.assign_role(user_id, target_role.id)

    return RoleUpdateResponse(
        message=f"Role updated to '{body.role}' for user {user.username}",
        username=user.username,
        role=body.role,
    )


# -------------------------------------------------------------------------
# Helper Functions
# -------------------------------------------------------------------------


def _user_to_response(user) -> UserResponse:
    """Convert User model to UserResponse schema."""
    from user_management.schemas.user import RoleResponse

    roles = []
    if hasattr(user, "roles") and user.roles:
        for user_role in user.roles:
            if hasattr(user_role, "role") and user_role.role:
                roles.append(
                    RoleResponse(
                        id=user_role.role.id,
                        name=user_role.role.name,
                        description=user_role.role.description,
                        is_system=user_role.role.is_system,
                    )
                )

    return UserResponse(
        id=user.id,
        email=user.email,
        username=user.username,
        display_name=user.display_name,
        bio=user.bio,
        avatar_url=user.avatar_url,
        org_id=user.org_id,
        is_active=user.is_active,
        is_verified=user.is_verified,
        mfa_enabled=user.mfa_enabled,
        is_platform_admin=user.is_platform_admin,
        preferences=user.preferences or {},
        roles=roles,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )
