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

import json
import os
from typing import List, Optional

from autobot_shared.ai_lines import VERIFIED_ATTACHMENT_ACCESS_KEY, VERIFIED_COMPANY_KEY, VERIFIED_USER_KEY
from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin
from orchestration.agent_registry import get_default_agents

logger = get_logger(__name__)

# TTL for a session's role binding — env-tunable, never hard-coded.
SESSION_ROLE_TTL_SECONDS: int = env_int("AUTOBOT_SESSION_ROLE_TTL_SECONDS", 24 * 3600)

# GH#11202: master switch for the chat approval gate. OFF by default — the gate
# routes tool calls through the LangGraph approval interrupt, which the frontend
# must render/resolve, so it stays disabled until that path is verified end-to-end.
CHAT_APPROVAL_GATE_ENABLED: bool = os.environ.get("AUTOBOT_CHAT_APPROVAL_GATE", "").lower() in ("1", "true", "yes")

_KEY = "autobot:session:{session_id}:role"
_APPROVAL_KEY = "autobot:session:{session_id}:approval_categories"

_valid_roles: "frozenset[str] | None" = None


def valid_roles() -> "frozenset[str]":
    """Registered agent-profile ids a session may be pinned to (cached)."""
    global _valid_roles  # noqa: PLW0603
    if _valid_roles is None:
        _valid_roles = frozenset(a.agent_id for a in get_default_agents())
    return _valid_roles


#: Context key carrying the *authenticated caller's* RBAC role (#13821).
#:
#: Distinct from the ``agent_id`` role above, which pins a governed agent profile.
#: This one answers "who is signed in", and is what ``MCPDispatcher.dispatch()``
#: resolves permissions against.
AUTH_ROLE_CONTEXT_KEY = "auth_role"

#: Role assumed when no authenticated identity reached the workflow. Matches the
#: long-standing ``role: str = "user"`` default at every seam downstream, so an
#: unauthenticated path is no more privileged than it was before #13821.
DEFAULT_AUTH_ROLE = "user"


def apply_auth_role(context: "dict | None", role: Optional[str], scope: "dict | None" = None) -> "dict | None":
    """Overlay the trusted authenticated *role* onto *context* (#13821).

    Unlike ``apply_role``, a falsy *role* **strips** the key rather than leaving
    *context* untouched. That asymmetry is the security property: ``context`` is
    the client-supplied ``request_data["context"]`` bag, so a caller can put
    ``auth_role: "admin"`` in it. Returning early on a missing server-side role
    would let exactly that value survive into the tool seam and grant the
    privileges it names. Every path therefore writes or removes the key — the
    caller's value is never the one that reaches ``dispatch()``.

    #18430: *scope* (``{"org_id", "user_id"}`` of the AUTHENTICATED principal) is overlaid the same way as
    ``verified_company_id`` / ``verified_user_id``, the scope the AI lines are decided for. The request's own
    ``company_id`` and ``user_id`` are client claims and never scope a decision.
    """
    merged = {**(context or {})}
    for key, value in (
        (VERIFIED_COMPANY_KEY, (scope or {}).get("org_id")),
        (VERIFIED_USER_KEY, (scope or {}).get("user_id")),
    ):
        if value:
            merged[key] = str(value)
        else:
            merged.pop(key, None)
    if (scope or {}).get("attachment_access") is True:  # #20195: the route's STRICT check, never the client's word
        merged[VERIFIED_ATTACHMENT_ACCESS_KEY] = True
    else:
        merged.pop(VERIFIED_ATTACHMENT_ACCESS_KEY, None)
    if role:
        merged[AUTH_ROLE_CONTEXT_KEY] = role
    else:
        merged.pop(AUTH_ROLE_CONTEXT_KEY, None)
    return merged


def stamp_verified_identity(metadata: dict, context: "dict | None") -> None:
    """Record the AUTHENTICATED principal on session *metadata*, replacing whatever a prior turn left (#18825).

    ``metadata["user_id"]`` / ``["org_id"]`` bound the memory-graph owner scope (L2 context, trajectory reads), so
    they come from the verified keys ``apply_auth_role`` overlaid -- never the request's own ``user_id`` /
    ``org_id``. A turn with no verified principal (or no context) writes ``""``: the scope fails closed rather
    than inheriting the previous turn's identity.
    """
    metadata["user_id"] = (context or {}).get(VERIFIED_USER_KEY) or ""
    metadata["org_id"] = (context or {}).get(VERIFIED_COMPANY_KEY) or ""


def resolve_auth_role(context: "dict | None") -> str:
    """Read the authenticated role a trusted producer overlaid, else the default.

    Only ever called on a context already passed through ``apply_auth_role``.
    """
    value = (context or {}).get(AUTH_ROLE_CONTEXT_KEY)
    return value if isinstance(value, str) and value else DEFAULT_AUTH_ROLE


#: The ``agent_id`` this overlay pinned, if any (#16950). ``build_governed_identity``
#: honours an executor (unbounded) ``agent_id`` only when it equals this key, so a
#: client's or a peer's dict naming an executor gets the default boundary instead.
#: Like ``AUTH_ROLE_CONTEXT_KEY``, it is written or removed on every overlay and
#: never left as the caller sent it.
PINNED_ROLE_CONTEXT_KEY = "pinned_agent_id"


def apply_role(context: "dict | None", role: Optional[str]) -> "dict | None":
    """Overlay a trusted *role* onto *context* as ``agent_id`` (GH#11186).

    A set role overrides any client-supplied ``agent_id`` (trusted server value
    wins), and is recorded under ``PINNED_ROLE_CONTEXT_KEY`` as the overlay's own.
    With no role, a client's ``agent_id`` is left alone. It can only name a
    profile to restrict its own run, and ``build_governed_identity`` refuses one
    that would widen it. But a client-supplied pin is always removed (#16950).
    """
    if not role:
        if context and PINNED_ROLE_CONTEXT_KEY in context:
            logger.debug("session_role.reject client-supplied %s", PINNED_ROLE_CONTEXT_KEY)
            return {k: v for k, v in context.items() if k != PINNED_ROLE_CONTEXT_KEY}
        return context
    return {**(context or {}), "agent_id": role, PINNED_ROLE_CONTEXT_KEY: role}


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
        except Exception as exc:  # defensive; resolution must never break chat
            logger.warning("session_role.get failed for session=%s: %s", session_id, exc)
            return None

    async def clear_role(self, session_id: str) -> None:
        """Remove the session's role binding."""
        redis = await self._get_redis()
        await redis.delete(_KEY.format(session_id=session_id))
        logger.info("session_role.clear session=%s", session_id)

    # --- approval categories (GH#11202) ------------------------------------

    async def set_approval_categories(self, session_id: str, categories: List[str]) -> None:
        """Declare which action categories require approval for *session_id*.

        Raises ``ValueError`` on an unknown category. These are the *server-side*
        permission decision — the frontend only renders the resulting interrupt.
        """
        from autobot_shared.tool_catalogue import valid_approval_categories

        valid = valid_approval_categories()
        unknown = [c for c in categories if c not in valid]
        if unknown:
            raise ValueError(f"unknown approval categories: {unknown} (valid: {sorted(valid)})")
        redis = await self._get_redis()
        await redis.set(
            _APPROVAL_KEY.format(session_id=session_id), json.dumps(list(categories)), ex=SESSION_ROLE_TTL_SECONDS
        )
        logger.info("session_role.set_approval session=%s categories=%s", session_id, categories)

    async def get_approval_categories(self, session_id: str) -> List[str]:
        """Return the session's declared approval categories (never raises into chat)."""
        try:
            redis = await self._get_redis()
            raw = await redis.get(_APPROVAL_KEY.format(session_id=session_id))
            if not raw:
                return []
            return list(json.loads(raw.decode() if isinstance(raw, bytes) else raw))
        except Exception as exc:  # defensive; must never break chat
            logger.warning("session_role.get_approval failed for session=%s: %s", session_id, exc)
            return []

    async def clear_approval_categories(self, session_id: str) -> None:
        """Remove the session's approval-category declaration."""
        redis = await self._get_redis()
        await redis.delete(_APPROVAL_KEY.format(session_id=session_id))


async def apply_session_governance(
    session_id: str, context: "dict | None", auth_role: Optional[str] = None, scope: "dict | None" = None
) -> "dict | None":
    """Overlay the trusted per-session governance onto the chat context (GH#11186/#11202/#20195).

    A server-set session role overrides any client-supplied ``agent_id`` so the pinned agent's ``forbidden_work``
    is enforced at the tool seam and cannot be lifted by the caller. When the approval gate flag is on, the
    baseline and the session's approval categories are overlaid as ``requires_approval_before``. #20195: the
    attachment floor (this chat used a file; an admin may waive it) is written from server state, never the client.
    """
    from chat_workflow.approval_baseline import with_baseline_categories
    from chat_workflow.attachment_floor import stamp_attachment_floor
    from chat_workflow.session_work_item import SessionWorkItemService, apply_work_item

    svc = SessionRoleService()
    # #13821: the authenticated caller's RBAC role, applied unconditionally (it strips a missing one).
    context = apply_auth_role(context, auth_role, scope)  # scope: #18430, the AI lines' verified principal
    context = apply_role(context, await svc.get_role(session_id))
    # #13704: a server-set work-item binding overrides any client-supplied work_item_id (#13687).
    context = apply_work_item(context, await SessionWorkItemService().get_work_item(session_id))
    context = await stamp_attachment_floor(context, session_id)
    if CHAT_APPROVAL_GATE_ENABLED:
        # #18294: all categories gated by default; only the SLM setting relaxes one.
        context = await with_baseline_categories(context, await svc.get_approval_categories(session_id))
    return context
