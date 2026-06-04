# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RBAC Middleware

Role-Based Access Control middleware for FastAPI endpoints.
Provides database-driven permission checking backed by Redis (GH #6511).

Cache strategy
--------------
When ``SLM_REDIS_URL`` is set the middleware stores each user's permission set
in Redis under ``slm:perm:{user_id}`` with a 5-minute TTL.  On Redis failure
the middleware falls back to a per-process dict so a Redis outage cannot
take down auth entirely, but the fallback is ephemeral and non-shared.

Use ``RBACMiddleware.clear_cache(user_id)`` after every role-change write so
stale permission sets are not served until TTL expiry.

Audit events
------------
Every denied permission check emits an ``AuditLog`` row (action=
``permission_denied``) to the user-management database via a fire-and-forget
``asyncio.Task``.  Failures in the audit write are logged at WARNING level and
never bubble up to the caller (GH #6511).
"""

import asyncio
import json
import logging
import uuid
from functools import wraps
from typing import Callable, List, Optional, Set, Union

from fastapi import HTTPException, Request, status

from autobot_shared.auth.permissions import Permission  # canonical enum (GH #6511)
from user_management.config import get_deployment_config
from user_management.database import db_session_context
from user_management.services import TenantContext, UserService

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 300  # 5 minutes — matches old in-process TTL


# ---------------------------------------------------------------------------
# Redis client helper (lazy, optional)
# ---------------------------------------------------------------------------

_redis_client = None
_redis_init_attempted = False


async def _get_redis():
    """Return an asyncio Redis client, or None when Redis is not configured."""
    global _redis_client, _redis_init_attempted
    if _redis_init_attempted:
        return _redis_client

    _redis_init_attempted = True
    try:
        from config import settings

        if not settings.redis_url:
            return None
        import redis.asyncio as aioredis

        _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _redis_client.ping()
        logger.info("RBAC: Redis permission cache connected at %s", settings.redis_url)
    except Exception as exc:
        logger.warning("RBAC: Redis not available, using in-process fallback: %s", exc)
        _redis_client = None
    return _redis_client


# In-process fallback: user_id → (frozenset(permissions), timestamp)
_fallback_cache: dict[str, tuple[frozenset, float]] = {}


# ---------------------------------------------------------------------------
# Audit helper (fire-and-forget)
# ---------------------------------------------------------------------------


async def _emit_permission_denied_audit(
    user_id: Optional[uuid.UUID],
    permission: str,
    endpoint: str,
) -> None:
    """Write a permission_denied audit row; swallow all errors."""
    try:
        from user_management.models.audit import AuditAction, AuditLog, AuditResourceType

        async with db_session_context() as session:
            log = AuditLog(
                user_id=user_id,
                action=AuditAction.PERMISSION_DENIED,
                resource_type=AuditResourceType.ENDPOINT,
                outcome="denied",
                details={"permission_required": permission, "endpoint": endpoint},
            )
            session.add(log)
            await session.commit()
    except Exception as exc:
        logger.warning("RBAC: failed to write permission_denied audit log: %s", exc)


# ---------------------------------------------------------------------------
# RBACMiddleware
# ---------------------------------------------------------------------------


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
        r = await _get_redis()
        if r is not None:
            try:
                raw = await r.get(self._redis_key(user_id))
                if raw is not None:
                    return set(json.loads(raw))
            except Exception as exc:
                logger.warning("RBAC: Redis cache read failed: %s", exc)
        else:
            import time

            entry = _fallback_cache.get(str(user_id))
            if entry and time.time() - entry[1] < CACHE_TTL_SECONDS:
                return set(entry[0])
        return None

    async def _cache_set(self, user_id: uuid.UUID, permissions: Set[str]) -> None:
        r = await _get_redis()
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

            _fallback_cache[str(user_id)] = (frozenset(permissions), time.time())

    async def _cache_delete(self, user_id: uuid.UUID) -> None:
        r = await _get_redis()
        if r is not None:
            try:
                await r.delete(self._redis_key(user_id))
            except Exception as exc:
                logger.warning("RBAC: Redis cache delete failed: %s", exc)
        _fallback_cache.pop(str(user_id), None)

    # ------------------------------------------------------------------
    # Permission resolution
    # ------------------------------------------------------------------

    async def get_user_permissions(
        self,
        user_id: Optional[uuid.UUID],
        org_id: Optional[uuid.UUID] = None,
    ) -> Set[str]:
        """Return the full permission set for *user_id* (Redis → DB → empty)."""
        if not user_id:
            return set()

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
            except Exception as exc:
                logger.warning("RBAC: failed to fetch permissions from database: %s", exc)

        return set()

    async def check_permission(
        self,
        user_id: Optional[uuid.UUID],
        permission: Union[Permission, str],
        org_id: Optional[uuid.UUID] = None,
    ) -> bool:
        perm_str = permission.value if isinstance(permission, Permission) else permission
        permissions = await self.get_user_permissions(user_id, org_id)
        return perm_str in permissions or "allow_all" in permissions

    async def check_any_permission(
        self,
        user_id: Optional[uuid.UUID],
        permissions: List[Union[Permission, str]],
        org_id: Optional[uuid.UUID] = None,
    ) -> bool:
        user_permissions = await self.get_user_permissions(user_id, org_id)
        if "allow_all" in user_permissions:
            return True
        perm_strs = {p.value if isinstance(p, Permission) else p for p in permissions}
        return bool(perm_strs & user_permissions)

    async def check_all_permissions(
        self,
        user_id: Optional[uuid.UUID],
        permissions: List[Union[Permission, str]],
        org_id: Optional[uuid.UUID] = None,
    ) -> bool:
        user_permissions = await self.get_user_permissions(user_id, org_id)
        if "allow_all" in user_permissions:
            return True
        perm_strs = {p.value if isinstance(p, Permission) else p for p in permissions}
        return perm_strs.issubset(user_permissions)

    def clear_cache(self, user_id: Optional[uuid.UUID] = None) -> None:
        """Schedule cache invalidation.  Safe to call from sync code."""
        if user_id:
            asyncio.ensure_future(self._cache_delete(user_id))
        else:
            # Clear entire fallback; Redis keys expire naturally.
            _fallback_cache.clear()
            asyncio.ensure_future(self._clear_all_redis_keys())

    async def _clear_all_redis_keys(self) -> None:
        r = await _get_redis()
        if r is None:
            return
        try:
            keys = await r.keys("slm:perm:*")
            if keys:
                await r.delete(*keys)
        except Exception as exc:
            logger.warning("RBAC: failed to clear all Redis permission keys: %s", exc)


# Global instance
rbac_middleware = RBACMiddleware()


# ---------------------------------------------------------------------------
# Request context helpers (unchanged signatures)
# ---------------------------------------------------------------------------


def _extract_request(args: tuple, request: Optional[Request]) -> Request:
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
) -> tuple[Optional[uuid.UUID], Optional[uuid.UUID]]:
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


def _require_authentication(user_id: Optional[uuid.UUID], permissions_desc: str) -> None:
    if user_id is None:
        logger.warning("RBAC: authentication required for permission: %s", permissions_desc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )


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
