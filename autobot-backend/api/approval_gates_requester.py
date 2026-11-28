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
from typing import Any, Iterable, Mapping, Sequence

from fastapi import HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
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
    """The ids a stored requester may name for this caller: the canonical ids and an admitted service's name."""
    claims = (*(current_user.get(c) for c in ("id", "user_id", "sub")), resolve_audit_actor_id(dict(current_user)))
    return {str(v) for v in claims if v}


def requester_is_caller(requester: str, current_user: Mapping[str, Any]) -> bool:
    """Whether a stored requester value names this caller.

    An id-form value (a user id) matches only the caller's ids: the mutable username never satisfies it, or a user
    could take the username of another's id (#22338). A value that is not an id was stored as a name (a row from
    before ids were recorded) and may match the caller's username.
    """
    ids = caller_identities(current_user)
    username = current_user.get("username")
    for value in (requester, requester.rsplit(":", 1)[-1]):
        if value in ids or (value == username and _requester_user_id(value) is None):
            return True
    return False


def _requester_user_id(requester: str) -> uuid.UUID | None:
    """The user id a stored requester names: the whole value, else the part after the last colon."""
    for candidate in (requester, requester.rsplit(":", 1)[-1]):
        try:
            return uuid.UUID(candidate)
        except ValueError:
            continue
    return None


def is_actor_id(value: str) -> bool:
    """Whether *value* is id-form (a user id, bare or after a ``user:`` prefix), not a username or a service name."""
    return _requester_user_id(value) is not None


async def actor_names(session: AsyncSession, actors: Iterable[str]) -> dict[str, str]:
    """Stored actor value -> that user's human-readable name, resolved at read time (#22222, #22338).

    The one batch name lookup behind both the approval requester and the audit actor. A ``service:<caller>``,
    ``system`` or unknown id is left out, so the caller falls back to the raw value; the display lookup never
    fails a response.
    """
    wanted = {actor: _requester_user_id(actor) for actor in {a for a in actors if a}}
    ids = [uid for uid in wanted.values() if uid]
    if not ids:
        return {}
    try:
        async with session.begin_nested():  # a failed lookup rolls back only itself, never the request's transaction
            names, _active = await member_people(session, ids)
    except SQLAlchemyError:
        logger.debug("actor names could not be resolved; showing the raw ids", exc_info=True)
        return {}
    return {actor: names[uid] for actor, uid in wanted.items() if uid in names}


async def requester_names(session: AsyncSession, approvals: Sequence[Any]) -> dict[str, str]:
    """Approval id -> the requester's human-readable name, resolved at read time (#22222).

    A ``service:<caller>`` requester is shown as stored. An id with no user row is left out, so the response
    falls back to the raw value.
    """
    by_actor = await actor_names(session, (str(getattr(a, "requested_by_agent", None) or "") for a in approvals))
    return {
        str(a.id): by_actor[actor]
        for a in approvals
        if (actor := str(getattr(a, "requested_by_agent", None) or "")) in by_actor
    }


def display_requester(approval: Any, names: Mapping[str, str]) -> str | None:
    """The requester's resolved name, else the stored value (a ``service:<caller>`` name or an unknown id)."""
    return names.get(str(approval.id)) or approval.requested_by_agent
