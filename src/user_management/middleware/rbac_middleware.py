# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RBAC Middleware

Role-Based Access Control middleware for FastAPI endpoints.
Provides database-driven permission checking with caching.
"""

import logging
import uuid
from functools import wraps
from typing import Callable, List, Optional, Set

from fastapi import Depends, HTTPException, Request, status

from src.user_management.config import DeploymentMode, get_deployment_config
from src.user_management.database import db_session_context
from src.user_management.services import TenantContext, UserService

logger = logging.getLogger(__name__)

# Permission cache (user_id -> permissions set)
# In production, use Redis for distributed caching
_permission_cache: dict[str, tuple[Set[str], float]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


class RBACMiddleware:
    """
    Role-Based Access Control middleware.

    Provides permission checking against the database with caching.
    Falls back to config-based roles when database is not available.
    """

    def __init__(self):
        """Initialize RBAC middleware."""
        self._config = get_deployment_config()

    async def get_user_permissions(
        self,
        user_id: Optional[uuid.UUID],
        org_id: Optional[uuid.UUID] = None,
    ) -> Set[str]:
        """
        Get all permissions for a user.

        Args:
            user_id: User UUID
            org_id: Organization UUID for tenant context

        Returns:
            Set of permission names
        """
        if not user_id:
            return set()

        # Check cache first
        cache_key = str(user_id)
        if cache_key in _permission_cache:
            permissions, timestamp = _permission_cache[cache_key]
            import time

            if time.time() - timestamp < CACHE_TTL_SECONDS:
                return permissions

        # Fetch from database
        if self._config.postgres_enabled:
            try:
                async with db_session_context() as session:
                    context = TenantContext(org_id=org_id, user_id=user_id)
                    user_service = UserService(session, context)
                    permissions = await user_service.get_user_permissions(user_id)

                    # Cache the result
                    import time

                    _permission_cache[cache_key] = (permissions, time.time())
                    return permissions

            except Exception as e:
                logger.warning("Failed to fetch permissions from database: %s", e)
                return set()

        return set()

    async def check_permission(
        self,
        user_id: Optional[uuid.UUID],
        permission: str,
        org_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user_id: User UUID
            permission: Permission name to check
            org_id: Organization UUID

        Returns:
            True if user has permission
        """
        permissions = await self.get_user_permissions(user_id, org_id)
        return permission in permissions or "allow_all" in permissions

    async def check_any_permission(
        self,
        user_id: Optional[uuid.UUID],
        permissions: List[str],
        org_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """
        Check if user has any of the specified permissions.

        Args:
            user_id: User UUID
            permissions: List of permission names
            org_id: Organization UUID

        Returns:
            True if user has any of the permissions
        """
        user_permissions = await self.get_user_permissions(user_id, org_id)
        if "allow_all" in user_permissions:
            return True
        return bool(set(permissions) & user_permissions)

    async def check_all_permissions(
        self,
        user_id: Optional[uuid.UUID],
        permissions: List[str],
        org_id: Optional[uuid.UUID] = None,
    ) -> bool:
        """
        Check if user has all of the specified permissions.

        Args:
            user_id: User UUID
            permissions: List of permission names
            org_id: Organization UUID

        Returns:
            True if user has all of the permissions
        """
        user_permissions = await self.get_user_permissions(user_id, org_id)
        if "allow_all" in user_permissions:
            return True
        return set(permissions).issubset(user_permissions)

    def clear_cache(self, user_id: Optional[uuid.UUID] = None):
        """
        Clear permission cache.

        Args:
            user_id: If provided, clear only for this user. Otherwise clear all.
        """
        if user_id:
            cache_key = str(user_id)
            if cache_key in _permission_cache:
                del _permission_cache[cache_key]
        else:
            _permission_cache.clear()


# Global RBAC middleware instance
rbac_middleware = RBACMiddleware()


def require_permission(permission: str):
    """
    Decorator to require a specific permission for an endpoint.

    Usage:
        @router.get("/admin/users")
        @require_permission("users.read")
        async def list_users(request: Request):
            ...

    Args:
        permission: Permission name required
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            # Extract request from args if not in kwargs
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Request object not found",
                )

            # Get user context from request state
            user_id = None
            org_id = None

            if hasattr(request.state, "user"):
                user_data = request.state.user
                if "user_id" in user_data:
                    try:
                        user_id = uuid.UUID(user_data["user_id"])
                    except (ValueError, TypeError):
                        pass
                if "org_id" in user_data:
                    try:
                        org_id = uuid.UUID(user_data["org_id"])
                    except (ValueError, TypeError):
                        pass

            # Check permission
            has_permission = await rbac_middleware.check_permission(
                user_id, permission, org_id
            )

            if not has_permission:
                logger.warning(
                    "Permission denied: user=%s, permission=%s", user_id, permission
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission '{permission}' required",
                )

            return await func(*args, request=request, **kwargs)

        return wrapper

    return decorator


def require_any_permission(permissions: List[str]):
    """
    Decorator to require any of the specified permissions.

    Usage:
        @router.get("/content")
        @require_any_permission(["content.read", "content.admin"])
        async def get_content(request: Request):
            ...

    Args:
        permissions: List of permission names (any one is sufficient)
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Request object not found",
                )

            user_id = None
            org_id = None

            if hasattr(request.state, "user"):
                user_data = request.state.user
                if "user_id" in user_data:
                    try:
                        user_id = uuid.UUID(user_data["user_id"])
                    except (ValueError, TypeError):
                        pass
                if "org_id" in user_data:
                    try:
                        org_id = uuid.UUID(user_data["org_id"])
                    except (ValueError, TypeError):
                        pass

            has_permission = await rbac_middleware.check_any_permission(
                user_id, permissions, org_id
            )

            if not has_permission:
                logger.warning(
                    "Permission denied: user=%s, required_any=%s",
                    user_id,
                    permissions,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"One of these permissions required: {permissions}",
                )

            return await func(*args, request=request, **kwargs)

        return wrapper

    return decorator


def require_all_permissions(permissions: List[str]):
    """
    Decorator to require all of the specified permissions.

    Usage:
        @router.delete("/admin/users/{user_id}")
        @require_all_permissions(["users.read", "users.delete"])
        async def delete_user(request: Request, user_id: str):
            ...

    Args:
        permissions: List of permission names (all are required)
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Request object not found",
                )

            user_id = None
            org_id = None

            if hasattr(request.state, "user"):
                user_data = request.state.user
                if "user_id" in user_data:
                    try:
                        user_id = uuid.UUID(user_data["user_id"])
                    except (ValueError, TypeError):
                        pass
                if "org_id" in user_data:
                    try:
                        org_id = uuid.UUID(user_data["org_id"])
                    except (ValueError, TypeError):
                        pass

            has_permission = await rbac_middleware.check_all_permissions(
                user_id, permissions, org_id
            )

            if not has_permission:
                logger.warning(
                    "Permission denied: user=%s, required_all=%s",
                    user_id,
                    permissions,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"All of these permissions required: {permissions}",
                )

            return await func(*args, request=request, **kwargs)

        return wrapper

    return decorator
