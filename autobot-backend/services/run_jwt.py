# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Run-scoped short-lived JWTs to limit blast radius of leaked credentials (#6473).

Mints a short-lived JWT at heartbeat start so MCP bridges use it instead of
the long-lived API key.  A leaked JWT auto-expires within ``RUN_JWT_TTL_SECONDS``
(default 300 s / 5 min).

Scope registry
--------------
``VALID_SCOPES`` defines the minimum-privilege scopes assignable to a run::

    mcp:knowledge   – read-only access to the knowledge MCP bridge
    mcp:web_fetch   – outbound web-fetch bridge
    mcp:filesystem  – local filesystem bridge (read-only subset)
    task:read       – read task metadata
    task:write      – update task status and comments
    agent:invoke    – call sub-agents

Flow
----
1. Scheduler calls ``mint_run_jwt(run_id, task_id, agent_id, tenant_id, scope)``
   before adapter invoke.
2. ``mint_run_jwt`` returns a signed JWT carrying ``jti``, ``run_id``,
   ``task_id``, ``agent_id``, ``tenant_id``, ``scope``, and ``exp``.
3. Adapter passes the JWT in the ``run_jwt`` field of every MCP RPC request;
   bridge workers call ``validate_run_jwt(token)`` on each ``call``.
4. On run end (or error), scheduler calls ``revoke_run_jwt(token)``; the
   ``jti`` is added to a Redis denylist with TTL = remaining token lifetime.
5. JWT auto-expires after ``RUN_JWT_TTL_SECONDS``; denylist entry also expires.

JTI denylist
-----------
Redis key: ``run_jwt:revoked:{jti}``  TTL = remaining token lifetime so the
denylist self-expires and never grows unbounded.

Configuration
-------------
``RUN_JWT_SECRET``       – HMAC signing secret (32+ char recommended).
                           Falls back to ``AUTOBOT_JWT_SECRET`` / ``SECRET_KEY``.
``RUN_JWT_TTL_SECONDS``  – Token lifetime in seconds (default 300).
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from datetime import timedelta
from typing import Dict, List, Optional

from autobot_shared.auth.jwt_core import (
    JWTDecodeError,
    JWTExpiredError,
    decode_jwt,
    encode_jwt,
)
from autobot_shared.fire_and_forget import run_redis_write
from autobot_shared.redis_client import get_async_redis_client
from services.audit.audit_log import AuditAction, audit_record

logger = logging.getLogger(__name__)

_ENV_SECRET = "RUN_JWT_SECRET"
_ENV_TTL = "RUN_JWT_TTL_SECONDS"
_DEFAULT_TTL = 300
_DENYLIST_PREFIX = "run_jwt:revoked:"

#: Allowed scopes for run JWTs (minimum-privilege model, documented in module docstring).
VALID_SCOPES: frozenset[str] = frozenset(
    {
        "mcp:knowledge",
        "mcp:web_fetch",
        "mcp:filesystem",
        "task:read",
        "task:write",
        "agent:invoke",
    }
)


def _secret() -> str:
    """Resolve the signing secret from environment variables, in priority order."""
    for var in (_ENV_SECRET, "AUTOBOT_JWT_SECRET", "SECRET_KEY"):
        val = os.environ.get(var, "")
        if val:
            return val
    raise RuntimeError(
        "No JWT signing secret configured.  Set RUN_JWT_SECRET (or AUTOBOT_JWT_SECRET)."
    )


def _ttl() -> int:
    """Resolve TTL from ``RUN_JWT_TTL_SECONDS`` env var, defaulting to 300 s."""
    raw = os.environ.get(_ENV_TTL, "")
    if not raw:
        return _DEFAULT_TTL
    try:
        return int(raw)
    except ValueError:
        logger.warning("RUN_JWT_TTL_SECONDS=%r is not an integer; using default %d s", raw, _DEFAULT_TTL)
        return _DEFAULT_TTL


def mint_run_jwt(
    run_id: str,
    task_id: str,
    agent_id: str,
    tenant_id: str,
    scope: List[str],
) -> str:
    """Mint a short-lived run-scoped JWT.

    Args:
        run_id: Unique identifier for the current heartbeat run.
        task_id: Task/issue being executed.
        agent_id: Agent performing the run.
        tenant_id: Tenant/company identifier for multi-tenancy.
        scope: List of ``VALID_SCOPES`` strings the run requires.

    Returns:
        Signed JWT string.

    Raises:
        ValueError: If any scope value is not in ``VALID_SCOPES``.
        RuntimeError: If no signing secret is configured.
    """
    invalid = [s for s in scope if s not in VALID_SCOPES]
    if invalid:
        raise ValueError(f"Unknown scopes: {invalid!r}.  Valid: {sorted(VALID_SCOPES)}")

    ttl = _ttl()
    jti = str(uuid.uuid4())
    payload: Dict[str, object] = {
        "jti": jti,
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "scope": scope,
    }
    token = encode_jwt(payload, secret=_secret(), expires_delta=timedelta(seconds=ttl))

    audit_record(
        user_id=agent_id,
        action=AuditAction.RUN_JWT_MINT,
        resource_type="run_jwt",
        resource_id=jti,
        metadata={
            "run_id": run_id,
            "task_id": task_id,
            "tenant_id": tenant_id,
            "scope": scope,
            "ttl_seconds": ttl,
        },
    )
    logger.info(
        "run_jwt: minted jti=%s run_id=%s agent=%s ttl=%ds",
        jti,
        run_id,
        agent_id,
        ttl,
    )
    return token


async def _add_to_denylist(jti: str, remaining_ttl: int) -> None:
    """Write JTI to Redis denylist with TTL = remaining token lifetime."""
    redis = await get_async_redis_client(database="main")
    if redis is None:
        logger.warning("run_jwt: Redis unavailable — jti=%s NOT added to denylist", jti)
        return
    key = _DENYLIST_PREFIX + jti
    await redis.set(key, "1", ex=max(1, remaining_ttl))
    logger.debug("run_jwt: denylist key=%s ttl=%ds", key, remaining_ttl)


async def _is_denied(jti: str) -> bool:
    """Return True if the JTI is present in the Redis denylist."""
    redis = await get_async_redis_client(database="main")
    if redis is None:
        return False
    return bool(await redis.exists(_DENYLIST_PREFIX + jti))


async def validate_run_jwt(token: str) -> Dict[str, object]:
    """Validate a run-scoped JWT.

    Checks:
    1. Signature validity and expiry via ``decode_jwt``.
    2. JTI not present in the Redis denylist.

    Args:
        token: JWT string received from the RPC params or ``MCP_RUN_JWT`` env var.

    Returns:
        Decoded claims dict on success.

    Raises:
        JWTExpiredError: Token has passed its ``exp`` timestamp.
        JWTDecodeError: Token has an invalid signature, is malformed, or its
            JTI has been explicitly revoked.
    """
    claims = decode_jwt(token, _secret())

    jti = claims.get("jti")
    if not jti:
        raise JWTDecodeError("run_jwt: missing jti claim")

    if await _is_denied(str(jti)):
        raise JWTDecodeError(f"run_jwt: jti {jti} has been revoked")

    return claims


def revoke_run_jwt(token: str, agent_id: Optional[str] = None) -> None:
    """Revoke a run-scoped JWT by adding its JTI to the Redis denylist.

    The denylist entry TTL equals the remaining token lifetime so it
    self-expires and never accumulates indefinitely.  Silently skips
    tokens that have already expired (nothing to revoke).

    Args:
        token: JWT string to revoke (returned by ``mint_run_jwt``).
        agent_id: Optional caller identity for the audit record (defaults to
            the ``agent_id`` claim embedded in the token).
    """
    try:
        claims = decode_jwt(token, _secret())
    except JWTExpiredError:
        logger.debug("run_jwt: revoke called on already-expired token — noop")
        return
    except JWTDecodeError as exc:
        logger.warning("run_jwt: revoke called on invalid token: %s", exc)
        return

    jti = str(claims.get("jti", ""))
    exp = claims.get("exp")
    remaining = max(0, int(exp) - int(time.time())) if exp else _ttl()

    run_redis_write(_add_to_denylist(jti, remaining), label="run_jwt_revoke")

    effective_agent = agent_id or str(claims.get("agent_id", "unknown"))
    audit_record(
        user_id=effective_agent,
        action=AuditAction.RUN_JWT_REVOKE,
        resource_type="run_jwt",
        resource_id=jti,
        metadata={
            "run_id": claims.get("run_id"),
            "task_id": claims.get("task_id"),
            "tenant_id": claims.get("tenant_id"),
            "remaining_ttl_seconds": remaining,
        },
    )
    logger.info(
        "run_jwt: revoked jti=%s run_id=%s remaining_ttl=%ds",
        jti,
        claims.get("run_id"),
        remaining,
    )
