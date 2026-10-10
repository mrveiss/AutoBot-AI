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
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any, Callable, List, Set

from fastapi import Request

from autobot_shared.logging_manager import get_logger
from autobot_shared.monitoring.metrics.audit import record_audit_write_failure_safely
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_constants import TTL_5_MINUTES
from autobot_shared.user_management.models.audit import AuditAction, AuditLog, AuditResourceType

logger = get_logger(__name__)


class RBACNotConfiguredError(RuntimeError):
    """Raised when the middleware runs before a service injected its dependencies."""


@dataclass(frozen=True)
class RBACDependencies:
    """What the shared middleware needs from the service that hosts it (#18088).

    The session factory, the user service and the deployment config are per-service
    (each binds its own engine and settings), so the shared module takes them as
    arguments instead of importing `user_management.*` -- which would resolve to
    whichever service's package is on `sys.path`. Same pattern as `async_session_scope`.
    """

    db_session_context: Callable[[], AbstractAsyncContextManager[Any]]
    user_service_cls: Callable[..., Any]
    tenant_context_cls: Callable[..., Any]
    get_deployment_config: Callable[[], Any]


_dependencies: RBACDependencies | None = None


def configure_rbac(dependencies: RBACDependencies) -> None:
    """Inject the hosting service's objects. Each service's shim calls this once.

    Re-configuring drops the singleton's cached deployment config, so it is re-read
    through the new getter; swapping in a different object is logged, the same one is not.
    """
    global _dependencies
    if _dependencies is not None and _dependencies is not dependencies:
        logger.warning("RBAC: configure_rbac() replaced already-injected dependencies; resetting cached config")
    _dependencies = dependencies
    rbac_middleware._config = None


def _require_dependencies() -> RBACDependencies:
    """The injected dependencies, or a loud failure -- never a silent allow or deny."""
    if _dependencies is None:
        raise RBACNotConfiguredError(
            "RBAC middleware used before configure_rbac(); import it through the service's "
            "user_management.middleware.rbac_middleware shim, which wires its dependencies."
        )
    return _dependencies


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
                # redis 8.1.0 HAS aclose() (runtime-verified); the stub omits it.
                await pubsub.aclose()  # type: ignore[attr-defined]
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
        """Initialize RBAC middleware; the deployment config resolves on first use."""
        self._config = None

    def _deployment_config(self):
        """The service's deployment config, read through the injected getter once."""
        if self._config is None:
            self._config = _require_dependencies().get_deployment_config()
        return self._config

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

        Raises:
            RBACNotConfiguredError: on a cache MISS before configure_rbac(). An L1/L2 hit
                returns the real cached permissions first, which is not fail-open.
        """
        if not user_id:
            return set()

        await _ensure_listener_started()

        cached = await self._cache_get(user_id)
        if cached is not None:
            return cached

        deps = _require_dependencies()  # outside the try: a missing wiring must not read as "no permissions"
        if self._deployment_config().postgres_enabled:
            try:
                async with deps.db_session_context() as session:
                    context = deps.tenant_context_cls(org_id=org_id, user_id=user_id)
                    user_service = deps.user_service_cls(session, context)
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
    deps = _require_dependencies()  # outside the try: an unwired audit must fail loudly
    try:
        async with deps.db_session_context() as session:
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
        # #14750: this handler is byte-identical to the SLM's, which #14674
        # instrumented — same bug, same audit_logs table, one backend counting
        # dropped records and the other silent. Keep swallowing, since a failing
        # audit must never turn a clean 403 into a 500, but stop letting the loss
        # be invisible.
        record_audit_write_failure_safely(AuditAction.PERMISSION_DENIED, type(exc).__name__)


def _request_audit_context(request: Request) -> tuple[str, str | None, str | None]:
    """Extract (path, ip_address, user_agent) for an audit entry (#12925)."""
    return (
        str(request.url.path),
        request.client.host if request.client else None,
        request.headers.get("user-agent"),
    )
