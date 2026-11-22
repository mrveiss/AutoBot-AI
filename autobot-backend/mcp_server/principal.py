# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The authenticated MCP principal, as a memory-graph OwnerScope (#18825).

Every memory tool reads under the scope of whoever authenticated the request:

* a run JWT -> the run's ``agent_id`` in the run's ``tenant_id`` (the org);
* a bearer token (static or Redis-issued) -> a stable id derived from the token secret,
  so each client sees only what it owns plus the shared entities;
* the stdio transport's self-composed bearer -> no identity at all. That case FAILS
  CLOSED: memory tools refuse (``OwnerScopeRequired``) rather than reading across owners.
  (#16727 tracks giving stdio a real identity; until then there is no unscoped read.)
"""

from __future__ import annotations

import hashlib
from contextvars import ContextVar
from typing import Any, Mapping

from autobot_memory_graph.owner_scope import OwnerScope, OwnerScopeRequired

#: Client address the stdio transport reports; an HTTP peer address can never equal it.
STDIO_CLIENT = "stdio"

_MCP_OWNER: ContextVar[OwnerScope | None] = ContextVar("mcp_owner_scope", default=None)


def mcp_owner_scope(claims: Mapping[str, Any] | None, auth_token: str, client_ip: str) -> OwnerScope | None:
    """OwnerScope for an authenticated request, or None when the caller has no identity."""
    try:
        if claims is not None:
            agent_id, tenant_id = claims.get("agent_id"), claims.get("tenant_id")
            return OwnerScope.for_user(agent_id, tenant_id) if agent_id else None
        secret = (auth_token or "").split(":", 1)[0]
        if client_ip == STDIO_CLIENT or not secret:
            return None
        return OwnerScope.for_user("mcp-token:" + hashlib.sha256(secret.encode("utf-8")).hexdigest()[:16])
    except OwnerScopeRequired:
        return None


def bind_owner(scope: OwnerScope | None):
    """Bind ``scope`` for the current request; returns the token for :func:`unbind_owner`."""
    return _MCP_OWNER.set(scope)


def unbind_owner(token) -> None:
    _MCP_OWNER.reset(token)


def current_owner() -> OwnerScope:
    """The request's OwnerScope; raises ``OwnerScopeRequired`` when the caller has no identity."""
    scope = _MCP_OWNER.get()
    if scope is None:
        raise OwnerScopeRequired("memory tools need an authenticated principal (the stdio transport has none)")
    return scope
