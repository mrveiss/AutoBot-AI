# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-session work-item binding (#13704).

Binds a chat session to an LLC work item so L4 GoalAncestry can render that
item's goal chain into the prompt (GH#6469, #13687).

This is the *trusted* producer of ``work_item_id``, deliberately mirroring
:mod:`chat_workflow.session_role`: the binding is set server-side through an
authenticated endpoint that verifies the work item belongs to the caller's
company, stored in Redis, then overlaid onto the chat context — overriding any
client-supplied ``work_item_id``.

Why this exists rather than reading the request context directly: the only
carrier into the prompt path was ``api/chat.py`` ``request_data.get("context")``,
a raw client JSON bag, and neither ``WorkItemService.get`` nor
``GoalService.get`` filtered on ``company_id``. Sourcing a goal lookup from that
bag would let any authenticated caller render another company's goal titles into
their own prompt. Making the value server-written removes that at the root; the
tenant predicates added alongside are defence in depth, not the only defence.
"""

import json
import os
from typing import NamedTuple, Optional

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin

logger = get_logger(__name__)

# TTL for a session's work-item binding — env-tunable, never hard-coded.
SESSION_WORK_ITEM_TTL_SECONDS: int = int(os.environ.get("AUTOBOT_SESSION_WORK_ITEM_TTL_SECONDS", str(24 * 3600)))

_KEY = "autobot:session:{session_id}:work_item"


class SessionWorkItemBinding(NamedTuple):
    """What the bind endpoint authorised, as stored (#13729).

    ``user_id`` is carried so the resolve path can re-check membership rather
    than trusting ``company_id`` for the rest of the TTL. A named tuple, not a
    plain tuple: it grew a third field, and two-value unpacking at an unfixed
    call site should fail loudly instead of silently binding the wrong name.
    """

    work_item_id: Optional[str] = None
    company_id: Optional[str] = None
    user_id: Optional[str] = None


def apply_work_item(context: "dict | None", work_item_id: Optional[str]) -> "dict | None":
    """Overlay a trusted *work_item_id* onto *context* (#13704).

    A server-set binding overrides any client-supplied ``work_item_id``, so a
    caller cannot select which work item's goal chain is read on their behalf.
    ``None`` returns *context* unchanged — and unchanged means the client's own
    value is **removed**, not preserved, because an unbound session must not be
    able to name a work item at all.
    """
    if not work_item_id:
        if context and "work_item_id" in context:
            trimmed = {k: v for k, v in context.items() if k != "work_item_id"}
            logger.debug("session_work_item.reject client-supplied work_item_id on unbound session")
            return trimmed
        return context
    return {**(context or {}), "work_item_id": work_item_id}


class SessionWorkItemService(AsyncRedisClientMixin):
    """Redis-backed store for a chat session's bound work item."""

    _redis_database = "knowledge"

    async def set_work_item(
        self,
        session_id: str,
        work_item_id: str,
        company_id: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Bind *session_id* to *work_item_id*, recording its verified company.

        The company is stored **with** the binding rather than read later from
        the session or request context, because both of those are
        client-influenced: ``session.metadata["company_id"]`` is assigned from
        the request bag at ``chat_workflow/manager.py:3331``. Persisting the
        company the endpoint actually authorised is what makes the later goal
        lookup's tenant scope trustworthy.

        The caller is responsible for having verified ownership of both the
        session and the work item; this stores an already-authorised decision.

        ``user_id`` (#13729) is stored so the resolve path can confirm that
        authorisation still holds. Without it the binding vouched for the
        company for the full TTL, so a user removed from the company kept
        receiving its goal chain for up to 24 hours after losing access.
        """
        if not work_item_id or not str(work_item_id).strip():
            raise ValueError("work_item_id is required")
        if not company_id or not str(company_id).strip():
            raise ValueError("company_id is required — an unscoped binding is not a binding")
        payload = json.dumps(
            {
                "work_item_id": str(work_item_id).strip(),
                "company_id": str(company_id).strip(),
                "user_id": str(user_id).strip() if user_id else None,
            }
        )
        redis = await self._get_redis()
        await redis.set(_KEY.format(session_id=session_id), payload, ex=SESSION_WORK_ITEM_TTL_SECONDS)
        logger.info("session_work_item.set session=%s work_item=%s company=%s", session_id, work_item_id, company_id)

    async def get_binding(self, session_id: str) -> SessionWorkItemBinding:
        """Return the session's binding, or an all-``None`` one.

        Never raises into chat — a resolution failure leaves L4 silent.
        """
        try:
            redis = await self._get_redis()
            raw = await redis.get(_KEY.format(session_id=session_id))
            if not raw:
                return SessionWorkItemBinding()
            data = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            return SessionWorkItemBinding(
                work_item_id=data.get("work_item_id"),
                company_id=data.get("company_id"),
                user_id=data.get("user_id"),
            )
        except Exception as exc:  # defensive; resolution must never break chat
            logger.warning("session_work_item.get failed for session=%s: %s", session_id, exc)
            return SessionWorkItemBinding()

    async def get_work_item(self, session_id: str) -> Optional[str]:
        """Return just the bound work item id, or ``None``."""
        return (await self.get_binding(session_id)).work_item_id

    async def clear_work_item(self, session_id: str) -> None:
        """Remove the session's work-item binding."""
        redis = await self._get_redis()
        await redis.delete(_KEY.format(session_id=session_id))
        logger.info("session_work_item.clear session=%s", session_id)


__all__ = [
    "SESSION_WORK_ITEM_TTL_SECONDS",
    "SessionWorkItemBinding",
    "SessionWorkItemService",
    "apply_work_item",
]
