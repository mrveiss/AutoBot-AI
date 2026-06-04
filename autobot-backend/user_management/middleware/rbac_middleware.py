# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RBAC Middleware

Role-Based Access Control middleware for FastAPI endpoints.
Provides database-driven permission checking with Redis-backed caching.
"""

import asyncio
import json
import time
import uuid
from functools import wraps
from typing import Callable, List, Set

from fastapi import HTTPException, Request, status

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from constants.ttl_constants import TTL_5_MINUTES
from user_management.config import get_deployment_config
from user_management.database import db_session_context
from user_management.services import TenantContext, UserService

logger = get_logger(__name__)

_PUBSUB_CHANNEL = "autobot:rbac:invalidate"
_REDIS_KEY_PREFIX = "rbac:perm:"

# L1 per-worker cache — invalidated immediately on this worker via clear_cache,
# and on all other workers via the pub/sub listener below.
_permission_cache: dict[str, tuple[Set[str], float]] = {}
CACHE_TTL_SECONDS = TTL_5_MINUTES

_listener_task: asyncio.Task | None = None


async def _run_invalidation_listener() -> None:
    """Subscribe to the RBAC invalidation channel and clear L1 on each message."""
    while True:
        try:
            redis = await get_async_redis_client()
            if redis is None:
                await asyncio.sleep(5)
                continue
            pubsub = redis.pubsub()
            await pubsub.subscribe(_PUBSUB_CHANNEL)
            logger.info("RBAC cache: subscribed to %s", _PUBSUB_CHANNEL)
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                    user_id_str = data.get("user_id")
                    if user_id_str:
                        _permission_cache.pop(user_id_str, None)
                    else:
                        _permission_cache.clear()
                except Exception:
                    logger.exception("RBAC invalidation listener: error processing message")
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("RBAC invalidation listener: reconnecting in 5s")
            try:
                await pubsub.unsubscribe(_PUBSUB_CHANNEL)
                await pubsub.aclose()
            except Exception:
                pass
            await asyncio.sleep(5)


async def _ensure_listener_started() -> None:
    global _listener_task
    if _listener_task is None or _listener_task.done():
        _listener_task = asyncio.create_task(_run_invalidation_listener())


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
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None = None,
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

        await _ensure_listener_started()

        cache_key = str(user_id)

        # L1: check local per-worker cache
        if cache_key in _permission_cache:
            permissions, timestamp = _permission_cache[cache_key]
            if time.time() - timestamp < CACHE_TTL_SECONDS:
                return permissions

        # L2: check Redis shared cache
        redis = await get_async_redis_client()
        if redis is not None:
            raw = await redis.get(f"{_REDIS_KEY_PREFIX}{cache_key}")
            if raw is not None:
                permissions = set(json.loads(raw))
                _permission_cache[cache_key] = (permissions, time.time())
                return permissions

        # Fetch from database and populate both caches
        if self._config.postgres_enabled:
            try:
                async with db_session_context() as session:
                    context = TenantContext(org_id=org_id, user_id=user_id)
                    user_service = UserService(session, context)
                    permissions = await user_service.get_user_permissions(user_id)

                    _permission_cache[cache_key] = (permissions, time.time())
                    if redis is not None:
                        await redis.setex(
                            f"{_REDIS_KEY_PREFIX}{cache_key}",
                            CACHE_TTL_SECONDS,
                            json.dumps(list(permissions)),
                        )
                    return permissions

            except Exception as e:
                logger.warning("Failed to fetch permissions from database: %s", e)
                return set()

        return set()

    async def check_permission(
        self,
        user_id: uuid.UUID | None,
        permission: str,
        org_id: uuid.UUID | None = None,
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
        user_id: uuid.UUID | None,
        permissions: List[str],
        org_id: uuid.UUID | None = None,
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
        user_id: uuid.UUID | None,
        permissions: List[str],
        org_id: uuid.UUID | None = None,
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

    async def clear_cache(self, user_id: uuid.UUID | None = None) -> None:
        """
        Clear permission cache for one user or all users.

        Deletes from the L1 local dict, the Redis L2 key, and publishes an
        invalidation message so all other uvicorn workers clear their L1.

        Args:
            user_id: If provided, clear only for this user. Otherwise clear all.
        """
        # Clear L1
        if user_id:
            _permission_cache.pop(str(user_id), None)
        else:
            _permission_cache.clear()

        # Clear Redis L2 and notify other workers
        redis = await get_async_redis_client()
        if redis is not None:
            if user_id:
                await redis.delete(f"{_REDIS_KEY_PREFIX}{user_id}")
            else:
                pipeline = redis.pipeline()
                async for key in redis.scan_iter(f"{_REDIS_KEY_PREFIX}*"):
                    pipeline.delete(key)
                await pipeline.execute()
            payload = json.dumps({"user_id": str(user_id)} if user_id else {})
            await redis.publish(_PUBSUB_CHANNEL, payload)
            logger.debug("RBAC cache invalidated for user=%s", user_id)


# Global RBAC middleware instance
rbac_middleware = RBACMiddleware()


def _extract_request(args: tuple, request: Request | None) -> Request:
    """
    Extract Request object from function arguments.

    Issue #620: Extracted from permission decorators to reduce duplication.

    Args:
        args: Positional arguments
        request: Request from kwargs (may be None)

    Returns:
        Request object

    Raises:
        HTTPException: 500 if Request not found
    """
    if request is None:
        for arg in args:
            if isinstance(arg, Request):
                return arg

    if request is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Request object not found",
        )
    return request


def _extract_user_context(
    request: Request,
) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    """
    Extract user_id and org_id from request state.

    Issue #620: Extracted from permission decorators to reduce duplication.

    Args:
        request: FastAPI Request object

    Returns:
        Tuple of (user_id, org_id), either may be None
    """
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

    return user_id, org_id


def _require_authentication(user_id: uuid.UUID | None, permissions_desc: str) -> None:
    """
    Check that user is authenticated, raise 401 if not.

    Issue #620: Extracted from permission decorators to reduce duplication.
    Issue #744: Return 401 for unauthenticated users.

    Args:
        user_id: User UUID (None if not authenticated)
        permissions_desc: Description of required permissions for logging

    Raises:
        HTTPException: 401 if user_id is None
    """
    if user_id is None:
        logger.warning("Authentication required for permission: %s", permissions_desc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


def require_permission(permission: str):
    """
    Decorator to require a specific permission for an endpoint.

    Issue #620: Refactored to use extracted helper functions.

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
            # Issue #620: Use extracted helpers
            request = _extract_request(args, request)
            user_id, org_id = _extract_user_context(request)
            _require_authentication(user_id, permission)

            # Check permission
            has_permission = await rbac_middleware.check_permission(user_id, permission, org_id)

            if not has_permission:
                logger.warning("Permission denied: user=%s, permission=%s", user_id, permission)
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

    Issue #620: Refactored to use extracted helper functions.

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
            # Issue #620: Use extracted helpers
            request = _extract_request(args, request)
            user_id, org_id = _extract_user_context(request)
            _require_authentication(user_id, str(permissions))

            has_permission = await rbac_middleware.check_any_permission(user_id, permissions, org_id)

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

    Issue #620: Refactored to use extracted helper functions.

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
            # Issue #620: Use extracted helpers
            request = _extract_request(args, request)
            user_id, org_id = _extract_user_context(request)
            _require_authentication(user_id, str(permissions))

            has_permission = await rbac_middleware.check_all_permissions(user_id, permissions, org_id)

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
