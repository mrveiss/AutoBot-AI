# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from autobot_shared.ssot_constants import TTL_5_MINUTES
from user_management.config import get_deployment_config
from user_management.database import db_session_context
from user_management.models.audit import AuditAction, AuditLog, AuditResourceType
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

    # ------------------------------------------------------------------
    # Cache helpers (#12925)
    #
    # One accessor pair for the whole L1->L2 path, so a cache read or write
    # cannot drift between call sites. SLM carried these as unused methods
    # against a second key prefix (`slm:perm:`); they are wired in here
    # against the canonical ``_REDIS_KEY_PREFIX`` instead of being dropped,
    # so there is exactly one cache and one set of keys.
    # ------------------------------------------------------------------

    @staticmethod
    def _redis_key(user_id: uuid.UUID | str) -> str:
        """Canonical L2 key for *user_id* — one prefix, repo-wide."""
        return f"{_REDIS_KEY_PREFIX}{user_id}"

    async def _cache_get(self, user_id: uuid.UUID) -> Set[str] | None:
        """Read permissions from L1, then L2. Returns None on a miss.

        An L2 hit repopulates L1, so the next request on this worker skips
        the round-trip.
        """
        cache_key = str(user_id)

        entry = _permission_cache.get(cache_key)
        if entry is not None:
            permissions, timestamp = entry
            if time.time() - timestamp < CACHE_TTL_SECONDS:
                return permissions

        redis = await get_async_redis_client()
        if redis is not None:
            try:
                raw = await redis.get(self._redis_key(cache_key))
            except Exception as exc:
                logger.warning("RBAC: Redis cache read failed: %s", exc)
                return None
            if raw is not None:
                permissions = set(json.loads(raw))
                _permission_cache[cache_key] = (permissions, time.time())
                return permissions

        return None

    async def _cache_set(self, user_id: uuid.UUID, permissions: Set[str]) -> None:
        """Populate L1 and L2. A Redis failure leaves L1 populated."""
        cache_key = str(user_id)
        _permission_cache[cache_key] = (permissions, time.time())

        redis = await get_async_redis_client()
        if redis is not None:
            try:
                await redis.setex(
                    self._redis_key(cache_key),
                    CACHE_TTL_SECONDS,
                    json.dumps(list(permissions)),
                )
            except Exception as exc:
                logger.warning("RBAC: Redis cache write failed: %s", exc)

    async def _cache_delete(self, user_id: uuid.UUID) -> None:
        """Drop one user from L1 and L2 on this worker."""
        cache_key = str(user_id)
        _permission_cache.pop(cache_key, None)

        redis = await get_async_redis_client()
        if redis is not None:
            try:
                await redis.delete(self._redis_key(cache_key))
            except Exception as exc:
                logger.warning("RBAC: Redis cache delete failed: %s", exc)

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

        cached = await self._cache_get(user_id)
        if cached is not None:
            return cached

        if self._config.postgres_enabled:
            try:
                async with db_session_context() as session:
                    context = TenantContext(org_id=org_id, user_id=user_id)
                    user_service = UserService(session, context)
                    permissions = await user_service.get_user_permissions(user_id)

                    await self._cache_set(user_id, permissions)
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

        # #11794: awaited, for BOTH paths — the single-user path previously
        # never touched Redis L2 / pub-sub at all (other uvicorn workers kept
        # serving stale permissions after a role change), and the all-users
        # path was fire-and-forget so callers could observe stale state right
        # after clear_cache() returned.
        await self._clear_all_redis_keys(user_id)

    async def _clear_all_redis_keys(self, user_id: "uuid.UUID | None") -> None:
        """Delete the L2 key(s) and tell every other worker to drop L1."""
        redis = await get_async_redis_client()
        if redis is None:
            return
        if user_id:
            await redis.delete(self._redis_key(user_id))
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


async def _emit_permission_denied_audit(
    user_id: uuid.UUID | None,
    permission: str,
    path: str,
    *,
    org_id: uuid.UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Persist a permission-denied event to the audit trail (#12925).

    Ported from autobot-slm-backend, which has recorded denials since GH #6511
    while this backend recorded nothing — a 403 left no user, permission, path
    or IP behind, so there was no trail to investigate probing against.

    Belt-and-suspenders: the warning is logged first and unconditionally, so a
    DB failure cannot make the denial disappear entirely. The write is caught
    and does NOT propagate — a failing audit must never convert a clean 403
    into a 500.
    """
    logger.warning("Permission denied: user=%s org=%s permission=%s path=%s", user_id, org_id, permission, path)
    try:
        async with db_session_context() as session:
            entry = AuditLog(
                id=uuid.uuid4(),
                user_id=user_id,
                org_id=org_id,
                action=AuditAction.PERMISSION_DENIED,
                resource_type=AuditResourceType.ENDPOINT,
                outcome="denied",
                details={"permission": permission, "path": path},
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.add(entry)
    except Exception as exc:
        logger.error("RBAC: failed to persist permission-denied audit entry: %s", exc)


def _request_audit_context(request: Request) -> tuple[str, str | None, str | None]:
    """Extract (path, ip_address, user_agent) for an audit entry (#12925)."""
    return (
        str(request.url.path),
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
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
                _path, _ip, _ua = _request_audit_context(request)
                await _emit_permission_denied_audit(
                    user_id,
                    permission,
                    _path,
                    org_id=org_id,
                    ip_address=_ip,
                    user_agent=_ua,
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
                _path, _ip, _ua = _request_audit_context(request)
                await _emit_permission_denied_audit(
                    user_id,
                    str(permissions),
                    _path,
                    org_id=org_id,
                    ip_address=_ip,
                    user_agent=_ua,
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
                _path, _ip, _ua = _request_audit_context(request)
                await _emit_permission_denied_audit(
                    user_id,
                    str(permissions),
                    _path,
                    org_id=org_id,
                    ip_address=_ip,
                    user_agent=_ua,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"All of these permissions required: {permissions}",
                )

            return await func(*args, request=request, **kwargs)

        return wrapper

    return decorator
