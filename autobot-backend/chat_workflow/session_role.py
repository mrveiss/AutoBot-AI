# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-session governed role binding (GH#11186).

Pins a chat session to a registered agent profile (e.g. ``research_agent``) so its
declarative ``forbidden_work`` manifest is enforced at the production tool seam
(``_dispatch_tool_call`` → ``_enforce_forbidden_work``, GH#11145/#11185).

This is the *trusted* producer of the governed identity: the role is set
server-side via an authenticated endpoint and stored in Redis, then injected into
the chat context — overriding any client-supplied ``agent_id`` — so a caller can
never lift a server-assigned restriction (they may only further restrict their own
run, since ``forbidden_work`` is deny-only).
"""

import os
from typing import Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from orchestration.agent_registry import get_default_agents

logger = get_logger(__name__)

# TTL for a session's role binding — env-tunable, never hard-coded.
SESSION_ROLE_TTL_SECONDS: int = int(os.environ.get("AUTOBOT_SESSION_ROLE_TTL_SECONDS", str(24 * 3600)))

_KEY = "autobot:session:{session_id}:role"

_valid_roles: "frozenset[str] | None" = None


def valid_roles() -> "frozenset[str]":
    """Registered agent-profile ids a session may be pinned to (cached)."""
    global _valid_roles  # noqa: PLW0603
    if _valid_roles is None:
        _valid_roles = frozenset(a.agent_id for a in get_default_agents())
    return _valid_roles


def apply_role(context: "dict | None", role: Optional[str]) -> "dict | None":
    """Overlay a trusted *role* onto *context* as ``agent_id`` (GH#11186).

    A set role overrides any client-supplied ``agent_id`` (trusted server value
    wins). ``None`` role returns *context* unchanged.
    """
    if not role:
        return context
    return {**(context or {}), "agent_id": role}


class SessionRoleService(AsyncRedisClientMixin):
    """Redis-backed store for a chat session's governed role."""

    _redis_database = "knowledge"

    async def set_role(self, session_id: str, role: str) -> None:
        """Pin *session_id* to *role*. Raises ``ValueError`` for an unknown role."""
        if role not in valid_roles():
            raise ValueError(f"unknown agent role: {role!r} (valid: {sorted(valid_roles())})")
        redis = await self._get_redis()
        await redis.set(_KEY.format(session_id=session_id), role, ex=SESSION_ROLE_TTL_SECONDS)
        logger.info("session_role.set session=%s role=%s", session_id, role)

    async def get_role(self, session_id: str) -> Optional[str]:
        """Return the session's pinned role, or ``None``. Never raises into the caller."""
        try:
            redis = await self._get_redis()
            raw = await redis.get(_KEY.format(session_id=session_id))
            if raw is None:
                return None
            return raw.decode() if isinstance(raw, bytes) else str(raw)
        except Exception as exc:  # pragma: no cover - defensive; resolution must not break chat
            logger.warning("session_role.get failed for session=%s: %s", session_id, exc)
            return None

    async def clear_role(self, session_id: str) -> None:
        """Remove the session's role binding."""
        redis = await self._get_redis()
        await redis.delete(_KEY.format(session_id=session_id))
        logger.info("session_role.clear session=%s", session_id)
