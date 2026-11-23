# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Errors of :mod:`services.redis_service_manager` and how it resolves the Redis node (#16346).

Split out of the manager to keep it within the file-size ceiling; ``redis_service_manager`` re-exports every name.
"""

from __future__ import annotations

import os
import time

import aiohttp

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


_NODE_CACHE_TTL_RANGE_S = (0.0, 3600.0)  # the range registered for AUTOBOT_REDIS_NODE_CACHE_TTL


def _resolve_node_cache_ttl() -> float:
    """Seconds a resolved node id is reused, from AUTOBOT_REDIS_NODE_CACHE_TTL, clamped to 0-3600 (0 disables)."""
    raw = os.getenv("AUTOBOT_REDIS_NODE_CACHE_TTL")
    try:
        value = float(raw) if raw is not None else 60.0
    except ValueError:
        logger.warning("AUTOBOT_REDIS_NODE_CACHE_TTL=%r is not a number; using 60s", raw)
        return 60.0
    if value != value:  # NaN
        return 60.0
    return min(max(value, _NODE_CACHE_TTL_RANGE_S[0]), _NODE_CACHE_TTL_RANGE_S[1])


REDIS_NODE_CACHE_TTL_S = _resolve_node_cache_ttl()
_resolved: tuple[str, float] | None = None  # (node id, monotonic expiry) of the last role-owner lookup


_cache_epoch = 0  # bumped by every clear, so a lookup that overlapped one cannot re-cache its stale answer


def clear_resolved_node() -> None:
    """Forget the cached node id (a role moved, or a test)."""
    global _resolved, _cache_epoch
    _resolved = None
    _cache_epoch += 1


#: The SLM role whose owner node runs the Redis Stack service (``role_registry``'s ``redis``).
REDIS_ROLE = "redis"


# Custom exceptions for Redis Stack service operations
class RedisServiceException(Exception):
    """Base exception for Redis Stack service operations"""


class RedisConnectionError(RedisServiceException):
    """Raised when cannot connect to Redis VM"""


class RedisNodeUnresolvedError(RedisServiceException):
    """Raised when no node can be named as the Redis host (no configured id, no node holds the role)"""


class RedisSlmAccessError(RedisServiceException):
    """Raised when the SLM refuses the backend's credential for a Redis service request"""


class RedisPermissionError(RedisServiceException):
    """Raised when user lacks permissions for operation"""


#: What the manager re-raises instead of folding into a failed or unknown result (#22030).
SLM_REFUSALS = (RedisNodeUnresolvedError, RedisSlmAccessError)


def access_error(exc: aiohttp.ClientResponseError) -> RedisSlmAccessError | None:
    """The error for a refused credential (401/403), None for any other status."""
    if exc.status in (401, 403):
        return RedisSlmAccessError(f"The SLM refused the backend's credential (HTTP {exc.status})")
    return None


async def resolve_redis_node_id(client, configured: str) -> str:
    """The node that runs Redis: the configured id, else the SLM's ``redis`` role owner (#16346).

    Never returns an empty id -- an empty one made every request go to ``/api/nodes//services``.
    """
    global _resolved
    if configured:
        return configured
    if _resolved is not None and time.monotonic() < _resolved[1]:
        return _resolved[0]
    epoch = _cache_epoch
    try:
        owners = (await client.get_role_owners()).get(REDIS_ROLE) or []
    except aiohttp.ClientResponseError as exc:
        raise access_error(exc) or RedisConnectionError(f"SLM role lookup failed: HTTP {exc.status}") from exc
    except Exception as exc:
        raise RedisConnectionError(f"Cannot reach SLM API for the role lookup: {exc}") from exc
    if not owners:
        raise RedisNodeUnresolvedError(
            f"No node holds the '{REDIS_ROLE}' role and REDIS_NODE_ID is not set; assign the role to a node"
        )
    if len(owners) > 1:
        logger.warning("Several nodes hold the '%s' role (%s); using %s", REDIS_ROLE, owners, owners[0])
    if epoch == _cache_epoch:  # a clear during the await means this answer may already be stale
        _resolved = (owners[0], time.monotonic() + REDIS_NODE_CACHE_TTL_S)
    return owners[0]
