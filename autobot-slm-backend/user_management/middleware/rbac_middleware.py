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
import logging
import time
import uuid
from functools import wraps
from typing import Callable, List, Optional, Set, Union

from fastapi import HTTPException, Request, status

from autobot_shared.redis_client import get_async_redis_client
from user_management.config import get_deployment_config
from user_management.database import db_session_context
from user_management.models.role import Permission
from user_management.services import TenantContext, UserService

logger = logging.getLogger(__name__)

_PUBSUB_CHANNEL = "autobot:rbac:invalidate"
_REDIS_KEY_PREFIX = "rbac:perm:"

# L1 per-worker cache — invalidated immediately on this worker via clear_cache,
# and on all other workers via the pub/sub listener below.
_permission_cache: dict[str, tuple[Set[str], float]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes

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

    Permission lookups hit Redis first (when configured), then fall through to
    the user-management database.  Cache invalidation on role changes is
    handled by ``clear_cache``.
    """

    def __init__(self):
        self._config = get_deployment_config()

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _redis_key(user_id: uuid.UUID) -> str:
        return f"slm:perm:{user_id}"

    async def _cache_get(self, user_id: uuid.UUID) -> Optional[Set[str]]:
        r = await get_async_redis_client()
        if r is not None:
            try:
                raw = await r.get(self._redis_key(user_id))
                if raw is not None:
                    return set(json.loads(raw))
            except Exception as exc:
                logger.warning("RBAC: Redis cache read failed: %s", exc)
        else:
            import time

            entry = _permission_cache.get(str(user_id))
            if entry and time.time() - entry[1] < CACHE_TTL_SECONDS:
                return set(entry[0])
        return None

    async def _cache_set(self, user_id: uuid.UUID, permissions: Set[str]) -> None:
        r = await get_async_redis_client()
        if r is not None:
            try:
                await r.set(
                    self._redis_key(user_id),
                    json.dumps(list(permissions)),
                    ex=CACHE_TTL_SECONDS,
                )
            except Exception as exc:
                logger.warning("RBAC: Redis cache write failed: %s", exc)
        else:
            import time

            _permission_cache[str(user_id)] = (frozenset(permissions), time.time())

    async def _cache_delete(self, user_id: uuid.UUID) -> None:
        r = await get_async_redis_client()
        if r is not None:
            try:
                await r.delete(self._redis_key(user_id))
            except Exception as exc:
                logger.warning("RBAC: Redis cache delete failed: %s", exc)
        _permission_cache.pop(str(user_id), None)

    # ------------------------------------------------------------------
    # Permission resolution
    # ------------------------------------------------------------------

    async def get_user_permissions(
        self,
        user_id: uuid.UUID | None,
        org_id: uuid.UUID | None = None,
    ) -> Set[str]:
        """Return the full permission set for *user_id* (Redis → DB → empty)."""
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
            except Exception as exc:
                logger.warning("RBAC: failed to fetch permissions from database: %s", exc)

        return set()

    async def check_permission(
        self,
        user_id: uuid.UUID | None,
        permission: str,
        org_id: uuid.UUID | None = None,
    ) -> bool:
        perm_str = permission.value if isinstance(permission, Permission) else permission
        permissions = await self.get_user_permissions(user_id, org_id)
        return perm_str in permissions or "allow_all" in permissions

    async def check_any_permission(
        self,
        user_id: uuid.UUID | None,
        permissions: List[str],
        org_id: uuid.UUID | None = None,
    ) -> bool:
        user_permissions = await self.get_user_permissions(user_id, org_id)
        if "allow_all" in user_permissions:
            return True
        perm_strs = {p.value if isinstance(p, Permission) else p for p in permissions}
        return bool(perm_strs & user_permissions)

    async def check_all_permissions(
        self,
        user_id: uuid.UUID | None,
        permissions: List[str],
        org_id: uuid.UUID | None = None,
    ) -> bool:
        user_permissions = await self.get_user_permissions(user_id, org_id)
        if "allow_all" in user_permissions:
            return True
        perm_strs = {p.value if isinstance(p, Permission) else p for p in permissions}
        return perm_strs.issubset(user_permissions)

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
            # Clear entire fallback; Redis keys expire naturally.
            _permission_cache.clear()
            asyncio.ensure_future(self._clear_all_redis_keys(None))

    async def _clear_all_redis_keys(self, user_id: "uuid.UUID | None") -> None:
        r = await get_async_redis_client()
        if r is None:
            return
        try:
            keys = await r.keys("slm:perm:*")
            if keys:
                await r.delete(*keys)
        except Exception as exc:
            logger.warning("RBAC: failed to clear all Redis permission keys: %s", exc)

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


# Global instance
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
        logger.warning("RBAC: authentication required for permission: %s", permissions_desc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


# ---------------------------------------------------------------------------
# Audit helper (stub — replace with real audit sink when available)
# ---------------------------------------------------------------------------


async def _emit_permission_denied_audit(user_id: object, permission: str, path: str) -> None:
    logger.warning("Permission denied: user=%s permission=%s path=%s", user_id, permission, path)


# ---------------------------------------------------------------------------
# Decorator factories
# ---------------------------------------------------------------------------


def require_permission(permission: Union[Permission, str]):
    """Decorator requiring a specific permission on the endpoint.

    Accepts both the canonical ``Permission`` enum and raw strings.
    Denied access emits an audit log entry (GH #6511).
    """
    perm_str = permission.value if isinstance(permission, Permission) else permission

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            request = _extract_request(args, request)
            user_id, org_id = _extract_user_context(request)
            _require_authentication(user_id, perm_str)

            has_perm = await rbac_middleware.check_permission(user_id, perm_str, org_id)
            if not has_perm:
                logger.warning("RBAC: permission denied user=%s perm=%s", user_id, perm_str)
                asyncio.ensure_future(_emit_permission_denied_audit(user_id, perm_str, str(request.url.path)))
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission '{perm_str}' required",
                )

            return await func(*args, request=request, **kwargs)

        return wrapper

    return decorator


def require_any_permission(permissions: List[Union[Permission, str]]):
    """Decorator requiring any one of the given permissions."""
    perm_strs = [p.value if isinstance(p, Permission) else p for p in permissions]

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            request = _extract_request(args, request)
            user_id, org_id = _extract_user_context(request)
            _require_authentication(user_id, str(perm_strs))

            has_perm = await rbac_middleware.check_any_permission(user_id, permissions, org_id)
            if not has_perm:
                logger.warning("RBAC: permission denied user=%s required_any=%s", user_id, perm_strs)
                asyncio.ensure_future(_emit_permission_denied_audit(user_id, str(perm_strs), str(request.url.path)))
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"One of these permissions required: {perm_strs}",
                )

            return await func(*args, request=request, **kwargs)

        return wrapper

    return decorator


def require_all_permissions(permissions: List[Union[Permission, str]]):
    """Decorator requiring all of the given permissions."""
    perm_strs = [p.value if isinstance(p, Permission) else p for p in permissions]

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            request = _extract_request(args, request)
            user_id, org_id = _extract_user_context(request)
            _require_authentication(user_id, str(perm_strs))

            has_perm = await rbac_middleware.check_all_permissions(user_id, permissions, org_id)
            if not has_perm:
                logger.warning("RBAC: permission denied user=%s required_all=%s", user_id, perm_strs)
                asyncio.ensure_future(_emit_permission_denied_audit(user_id, str(perm_strs), str(request.url.path)))
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"All of these permissions required: {perm_strs}",
                )

            return await func(*args, request=request, **kwargs)

        return wrapper

    return decorator
