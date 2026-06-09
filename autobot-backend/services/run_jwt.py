# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
``RUN_JWT_SECRET``          – HMAC signing secret (32+ char recommended).
                              Falls back to ``AUTOBOT_JWT_SECRET``.
                              ``SECRET_KEY`` is intentionally excluded — a
                              general app secret would allow any service that
                              knows it to forge run JWTs.
``RUN_JWT_TTL_SECONDS``     – Token lifetime in seconds (default 300).
``RUN_JWT_REDIS_FAIL_OPEN`` – Set to ``"1"`` to allow validation when Redis is
                              unreachable (fail-open).  Default is fail-closed:
                              if Redis cannot be reached the JTI denylist check
                              raises ``JWTDecodeError`` so revoked tokens are
                              never silently accepted during an outage.
"""

from __future__ import annotations

import os
import time
import uuid
from datetime import timedelta
from typing import Dict, List

from autobot_shared.auth.jwt_core import (
    JWTDecodeError,
    JWTExpiredError,
    decode_jwt,
    encode_jwt,
)
from autobot_shared.fire_and_forget import run_redis_write
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from services.audit.unified_audit import AuditAction, audit_record  # GH#8290 Phase 2


class JWTRefreshConflictError(Exception):
    """Raised when a concurrent refresh loses the SET NX race.

    Treat as HTTP 409: the caller should use the token returned by the
    winning concurrent request rather than retrying with the same old token.
    """


logger = get_logger(__name__)

_ENV_SECRET = "RUN_JWT_SECRET"
_ENV_TTL = "RUN_JWT_TTL_SECONDS"
_ENV_AUDIENCE = "RUN_JWT_AUDIENCE"
_ENV_FAIL_OPEN = "RUN_JWT_REDIS_FAIL_OPEN"
_DEFAULT_TTL = 300
_DEFAULT_AUDIENCE = "autobot:run-validator"
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

# Minimum scopes per agent_type — keys match agent_registry_service._tier_map values
# ("coordinator", "specialist", "worker").  Unknown types fall to ["task:read"].
_AGENT_TYPE_SCOPES: dict[str, list[str]] = {
    "coordinator": ["task:read", "task:write", "agent:invoke", "mcp:knowledge"],
    "specialist": ["task:read", "task:write", "mcp:knowledge", "mcp:web_fetch"],
    "worker": ["task:read", "task:write"],
}
_FALLBACK_SCOPES: list[str] = ["task:read"]


def get_run_jwt_scopes(agent_type: str, task_type: str | None = None) -> list[str]:
    """Resolve the minimum required JWT scopes for an agent type.

    Args:
        agent_type: Value of ``Agent.agent_type`` (e.g. ``"worker"``, ``"chat_agent"``).
        task_type: Optional hint from the task payload. Pass ``"read_only"`` to
            strip write and invoke scopes even for higher-privilege agent types.

    Returns:
        List of scope strings, each guaranteed to be in ``VALID_SCOPES``.
        Unknown agent types receive the safest minimum: ``["task:read"]``.
    """
    scopes = list(_AGENT_TYPE_SCOPES.get(agent_type, _FALLBACK_SCOPES))
    if task_type == "read_only":
        scopes = [s for s in scopes if s not in ("task:write", "agent:invoke")]
    return scopes


def _secret() -> str:
    """Resolve the signing secret from environment variables, in priority order.

    ``SECRET_KEY`` is deliberately excluded from the fallback chain.  A
    general-purpose app secret that is known to multiple services would allow
    any of those services to forge run JWTs, undermining the isolation goal.
    """
    for var in (_ENV_SECRET, "AUTOBOT_JWT_SECRET"):
        val = os.environ.get(var, "")
        if val:
            return val
    raise RuntimeError("No run-JWT signing secret configured.  Set RUN_JWT_SECRET (or AUTOBOT_JWT_SECRET).")


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


def _audience() -> str:
    """Resolve the expected ``aud`` claim from ``RUN_JWT_AUDIENCE``, defaulting to ``_DEFAULT_AUDIENCE``."""
    return os.environ.get(_ENV_AUDIENCE, "") or _DEFAULT_AUDIENCE


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
        "aud": _audience(),
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
    """Return True if the JTI is present in the Redis denylist.

    When Redis is unavailable the default policy is **fail-closed**: raises
    ``JWTDecodeError`` so that a revoked token cannot be used during an outage.
    Set ``RUN_JWT_REDIS_FAIL_OPEN=1`` to allow validation when Redis is down
    (only appropriate for environments where Redis availability is more critical
    than the revocation guarantee).

    Raises:
        JWTDecodeError: Redis is unavailable and fail-closed mode is active.
    """
    redis = await get_async_redis_client(database="main")
    if redis is None:
        if os.environ.get(_ENV_FAIL_OPEN) == "1":  # ssot-config-exempt: dynamic env var name
            logger.warning("run_jwt: Redis unavailable — denylist check skipped (RUN_JWT_REDIS_FAIL_OPEN=1)")
            return False
        raise JWTDecodeError(
            "run_jwt: Redis unavailable — cannot verify JTI revocation status "
            "(set RUN_JWT_REDIS_FAIL_OPEN=1 to allow fail-open)"
        )
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
    claims = decode_jwt(token, _secret(), audience=_audience())

    jti = claims.get("jti")
    if not jti:
        raise JWTDecodeError("run_jwt: missing jti claim")

    if await _is_denied(str(jti)):
        raise JWTDecodeError(f"run_jwt: jti {jti} has been revoked")

    return claims


def _extract_revoke_claims(token: str) -> Dict[str, object] | None:
    """Decode token for revocation; returns None when already expired/invalid."""
    try:
        return decode_jwt(token, _secret())
    except JWTExpiredError:
        logger.debug("run_jwt: revoke called on already-expired token — noop")
        return None
    except JWTDecodeError as exc:
        logger.warning("run_jwt: revoke called on invalid token: %s", exc)
        return None


def _emit_revoke_audit(claims: Dict[str, object], agent_id: str | None, remaining: int) -> None:
    """Fire audit record for a revocation event."""
    effective_agent = agent_id or str(claims.get("agent_id", "unknown"))
    jti = str(claims.get("jti", ""))
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


async def revoke_run_jwt_async(token: str, agent_id: str | None = None) -> None:
    """Revoke a run-scoped JWT — async variant with guaranteed Redis write.

    Prefer this over ``revoke_run_jwt`` in async contexts (e.g. breach-response
    handlers) where you need confirmation that the JTI has been written to the
    denylist before proceeding.  The sync variant uses fire-and-forget which
    has a small race window between the call returning and the actual Redis write.

    Args:
        token: JWT string to revoke.
        agent_id: Optional caller identity for the audit record.
    """
    claims = _extract_revoke_claims(token)
    if claims is None:
        return

    jti = str(claims.get("jti", ""))
    exp = claims.get("exp")
    remaining = max(0, int(exp) - int(time.time())) if exp else _ttl()

    await _add_to_denylist(jti, remaining)
    _emit_revoke_audit(claims, agent_id, remaining)


def revoke_run_jwt(token: str, agent_id: str | None = None) -> None:
    """Revoke a run-scoped JWT by adding its JTI to the Redis denylist.

    Uses fire-and-forget for the Redis write — safe for end-of-run cleanup
    where a small async race is acceptable.  For breach-response or any
    context where you need the revocation confirmed before continuing, use
    ``revoke_run_jwt_async`` instead.

    The denylist entry TTL equals the remaining token lifetime so it
    self-expires and never accumulates indefinitely.  Silently skips
    tokens that have already expired (nothing to revoke).

    Args:
        token: JWT string to revoke (returned by ``mint_run_jwt``).
        agent_id: Optional caller identity for the audit record (defaults to
            the ``agent_id`` claim embedded in the token).
    """
    claims = _extract_revoke_claims(token)
    if claims is None:
        return

    jti = str(claims.get("jti", ""))
    exp = claims.get("exp")
    remaining = max(0, int(exp) - int(time.time())) if exp else _ttl()

    run_redis_write(_add_to_denylist(jti, remaining), label="run_jwt_revoke")
    _emit_revoke_audit(claims, agent_id, remaining)


async def refresh_run_jwt(token: str, run_id: str) -> str:
    """Refresh a run-scoped JWT, returning a new token with the same scope.

    Validates that the presented JWT is not expired and not revoked, checks
    that its ``run_id`` claim matches the *run_id* path parameter, then
    uses a Redis SET NX on the old JTI to atomically claim the revocation
    right before minting a fresh token.  A concurrent refresh on the same
    token will lose the SET NX and receive ``JWTRefreshConflictError``
    (→ HTTP 409) instead of yielding a second live token.

    Args:
        token: Current valid run JWT (must not be expired or revoked).
        run_id: Expected ``run_id`` from the URL path — must match the
            claim in *token* to prevent cross-run token swaps.

    Returns:
        New signed JWT string with a fresh TTL and a new ``jti``.

    Raises:
        JWTExpiredError: The presented token has already expired.
        JWTDecodeError: The token is invalid, revoked, or its ``run_id``
            claim does not match *run_id*, or Redis is unavailable.
        JWTRefreshConflictError: A concurrent refresh already claimed this
            token; caller should use the token from the winning request.
    """
    claims = await validate_run_jwt(token)

    if str(claims.get("run_id", "")) != run_id:
        raise JWTDecodeError(f"run_jwt: run_id mismatch — token has {claims.get('run_id')!r}, expected {run_id!r}")

    scope = list(claims.get("scope", []))
    task_id = str(claims.get("task_id", ""))
    agent_id = str(claims.get("agent_id", ""))
    tenant_id = str(claims.get("tenant_id", ""))
    old_jti = str(claims.get("jti", ""))
    exp = claims.get("exp")
    remaining = max(1, int(exp) - int(time.time())) if exp else _ttl()

    # Mint first so the agent retains a valid token even if the denylist
    # write fails (MVA-170 regression prevention).
    new_token = mint_run_jwt(run_id, task_id, agent_id, tenant_id, scope)

    # Atomic SET NX: only the first concurrent caller claims the revocation.
    # The loser receives JWTRefreshConflictError and must reuse the winner's
    # token.  Honours RUN_JWT_REDIS_FAIL_OPEN for environments where Redis
    # availability is more critical than the revocation guarantee.
    redis = await get_async_redis_client(database="main")
    if redis is None:
        if os.environ.get(_ENV_FAIL_OPEN) == "1":  # ssot-config-exempt: dynamic env var name
            logger.warning("run_jwt: Redis unavailable — refresh denylist skipped (RUN_JWT_REDIS_FAIL_OPEN=1)")
        else:
            raise JWTDecodeError(
                "run_jwt: Redis unavailable — cannot perform atomic refresh "
                "(set RUN_JWT_REDIS_FAIL_OPEN=1 to allow fail-open)"
            )
    else:
        acquired = await redis.set(_DENYLIST_PREFIX + old_jti, "1", ex=remaining, nx=True)
        if not acquired:
            raise JWTRefreshConflictError(
                f"run_jwt: concurrent refresh detected for jti={old_jti} — " "use the token from the winning request"
            )

    _emit_revoke_audit(claims, agent_id, remaining)

    audit_record(
        user_id=agent_id,
        action=AuditAction.RUN_JWT_REFRESH,
        resource_type="run_jwt",
        resource_id=old_jti,
        metadata={
            "run_id": run_id,
            "task_id": task_id,
            "tenant_id": tenant_id,
            "scope": scope,
        },
    )
    logger.info("run_jwt: refreshed jti=%s run_id=%s agent=%s", old_jti, run_id, agent_id)
    return new_token
