# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who requested an approval gate: the verified caller, never a field of the request (#20521).

The requester drives who may resubmit (``approval_gates._requester_matches``), so it is stamped server-side in the
``user:<id>`` form that ``_requester_matches`` and ``autobot_shared.approval_four_eyes.requester_id`` parse. A
requester the body names (the SLM console sends a ``data_hygiene_console`` label) is kept only as
``requested_label`` in the approval's context, for display; nothing reads it for an authorisation decision.
"""

from __future__ import annotations

import uuid
from typing import Any, Mapping, Sequence

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.principal import resolve_audit_actor_id
from llc.services.member_standing import member_people
from services.approval_execution import REQUESTED_LABEL_KEY

logger = get_logger(__name__)

_SERVICE_PREFIX = "service:"


def stamped_requester(current_user: Mapping[str, Any]) -> str:
    """``user:<id>`` for the authenticated caller; a caller with no identity is refused (401), never anonymous."""
    ident = current_user.get("id") or current_user.get("user_id") or current_user.get("username")
    if not ident:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return f"user:{ident}"


def with_requested_label(context: dict | None, label: str | None) -> dict | None:
    """*context* with the body's requester kept as a display label; unchanged when the body named none."""
    if not label:
        return context
    return {**(context or {}), REQUESTED_LABEL_KEY: label}


def caller_identities(current_user: Mapping[str, Any]) -> set[str]:
    """Every value a stored requester may name for this caller: the canonical ids, the service name, the username."""
    claims = (
        *(current_user.get(c) for c in ("id", "user_id", "sub", "username")),
        resolve_audit_actor_id(dict(current_user)),
    )
    return {str(v) for v in claims if v}


def _requester_user_id(requester: str) -> uuid.UUID | None:
    """The user id a stored requester names: the whole value, else the part after the last colon."""
    for candidate in (requester, requester.rsplit(":", 1)[-1]):
        try:
            return uuid.UUID(candidate)
        except ValueError:
            continue
    return None


async def requester_names(session: AsyncSession, approvals: Sequence[Any]) -> dict[str, str]:
    """Approval id -> the requester's human-readable name, resolved at read time (#22222).

    A ``service:<caller>`` requester is shown as stored. An id with no user row is left out, so the response
    falls back to the raw value; the display lookup never fails a response.
    """
    wanted = {str(a.id): _requester_user_id(str(getattr(a, "requested_by_agent", None) or "")) for a in approvals}
    ids = [uid for uid in wanted.values() if uid]
    try:
        names, _active = await member_people(session, ids)
    except Exception:
        logger.debug("requester names could not be resolved; showing the raw ids", exc_info=True)
        return {}
    return {aid: names[uid] for aid, uid in wanted.items() if uid in names}


def display_requester(approval: Any, names: Mapping[str, str]) -> str | None:
    """The requester's resolved name, else the stored value (a ``service:<caller>`` name or an unknown id)."""
    return names.get(str(approval.id)) or approval.requested_by_agent
