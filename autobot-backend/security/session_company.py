# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The company a caller is acting in, and the refusal of a chat that belongs to another one (#21997).

The active company is the one every Company OS route already uses (``docs/llc/tenant-context.md``): the
``X-Organization-Id`` header the top-bar switcher sends (``fetchWithAuth.ts``), else the JWT ``org_id`` claim. A
header naming a company the caller is not a member of is refused, exactly as ``get_tenant_context`` refuses it;
a platform admin may name any. A service principal, or a caller with no identity, acts in no company. Companies
are internal entities, not tenants: this scopes what a person sees and opens, it is not an isolation boundary.

With no active company nothing is refused: a chat tagged with a company is hidden from that caller's list (it is
in neither set, ``chat_history.company_scope``) but its owner can still open it by id, under the owner and share
rules alone. The owner-only rule applies and a company is not a tenant, so hiding is not denying.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, Request, WebSocket
from starlette.datastructures import State
from starlette.requests import HTTPConnection

from autobot_shared.http_refusal import fixed_refusal
from autobot_shared.logging_manager import get_logger
from chat_history.company_scope import ActiveCompany
from security.session_owner_errors import SessionOwnerUnreadable

logger = get_logger(__name__)

#: The header the company switcher sends on every request (the same one ``get_tenant_context`` reads).
ACTIVE_COMPANY_HEADER = "X-Organization-Id"
_STATE_KEY = "active_company_scope"
#: The key a live connection's user payload carries its active company under, resolved once at connect.
ACTIVE_COMPANY_KEY = "active_company"


def _parse(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None


async def may_act_in_company(company_id: uuid.UUID, user: dict) -> bool:
    """Whether *user* may act in *company_id*: a platform admin, or a member of it (``llc.services.authz``)."""
    from api.user_management.dependencies import _is_platform_admin_claim
    from llc.services.authz import is_company_member
    from user_management.database import get_async_session_factory

    if _is_platform_admin_claim(user):
        return True
    user_id = user.get("user_id") or user.get("id") or user.get("sub")
    if not user_id:
        return False
    async with get_async_session_factory()() as session:
        return await is_company_member(session, company_id, str(user_id))


def _caller(request: Request) -> dict | None:
    from auth_middleware import get_auth_middleware

    return get_auth_middleware().get_user_from_request(request)


async def resolve_company_scope(request: Request, user: dict | None = None) -> ActiveCompany:
    """The caller's ``ActiveCompany``, resolved once per request; a company they may not act in is the canonical 403.

    The answer (membership check included) is kept on ``request.state``, so the several checks one request makes
    cost one lookup. It is the request's own state, not a process-wide cache.
    """
    state = getattr(request, "state", None)
    if isinstance(state, State) and hasattr(state, _STATE_KEY):
        return getattr(state, _STATE_KEY)
    scope = await _resolve_company_scope(request, user)
    if isinstance(state, State):
        setattr(state, _STATE_KEY, scope)
    return scope


async def _resolve_company_scope(request: Request, user: dict | None) -> ActiveCompany:
    user = user if user is not None else _caller(request)
    if not user or user.get("service") or user.get("auth_disabled"):
        return ActiveCompany(None)
    named = _parse(request.headers.get(ACTIVE_COMPANY_HEADER))
    if named is None:
        return ActiveCompany(_parse(user.get("org_id")))
    if not await may_act_in_company(named, user):
        logger.warning("Active company refused: caller is not a member of the company the header names")
        raise fixed_refusal(403)
    return ActiveCompany(named)


async def company_of_session(request: Request, session_id: str) -> str | None:
    """The company stored on the session (a metadata read), ``None`` when it is Unassigned or absent.

    A file that cannot be read is the canonical 503, never "Unassigned": it is not evidence of no company.
    """
    from utils.chat_utils import get_chat_history_manager

    try:
        return await get_chat_history_manager(request).get_session_company(session_id)
    except SessionOwnerUnreadable:
        raise fixed_refusal(503) from None


class OtherCompanyRefusal(HTTPException):
    """The canonical 403 for a chat of another company.

    A subclass so a route that must not reveal a chat exists (``validate_strict_hidden``) can answer it as not found.
    """

    def __init__(self) -> None:
        refusal = fixed_refusal(403)
        super().__init__(status_code=refusal.status_code, detail=refusal.detail)


def refuse_other_company(scope: ActiveCompany, stored_company: str | None) -> None:
    """The one company rule behind HTTP, WebSocket and import: the canonical 403 for a chat of another company.

    No active company, or an Unassigned chat, or the same company, passes.
    """
    if scope.active is not None and not scope.allows(stored_company):
        raise OtherCompanyRefusal()


async def enforce_session_company(session_id: str, request: Request, user: dict | None = None) -> None:
    """Refuse (canonical 403) a session tagged with a company other than the active one; no active company, no check."""
    scope = await resolve_company_scope(request, user)
    if scope.active is not None:
        refuse_other_company(scope, await company_of_session(request, session_id))


async def require_session_company(conn: HTTPConnection) -> None:
    """Route dependency for a router whose paths name a chat session: another company's chat is the canonical 403.

    The session is the path's ``session_id`` / ``chat_id``; a path with neither, or with an id that is not a chat
    session id (read as such nowhere else), is left to its route. HTTP and WebSocket routes both take it.
    """
    from utils.chat_utils import validate_chat_session_id

    session_id = next((conn.path_params[k] for k in ("session_id", "chat_id") if k in conn.path_params), None)
    if session_id and validate_chat_session_id(str(session_id)):
        await enforce_session_company(str(session_id), conn)  # type: ignore[arg-type]


async def connection_company(websocket: WebSocket, user: dict | None) -> ActiveCompany | None:
    """The socket's ``ActiveCompany``, resolved once at connect; None after the socket is closed 4403.

    A header naming a company the caller may not act in refuses the connection (accept, then close, so the client
    sees a close frame). No identity, or no header, is no active company.
    """
    from autobot_shared.websocket_subprotocol import accept_websocket

    try:
        return await resolve_company_scope(websocket, user)  # type: ignore[arg-type]
    except HTTPException:
        await accept_websocket(websocket)
        await websocket.close(code=4403, reason="Forbidden")
        return None


async def session_in_company(manager, session_id: str, scope: ActiveCompany) -> bool:
    """Whether *scope* may reach *session_id*: the canonical rule as a yes/no for socket and event filters."""
    try:
        refuse_other_company(scope, await manager.get_session_company(session_id) if scope.active else None)
    except HTTPException:
        return False
    return True


async def creation_company_metadata(request: Request, client_metadata: dict | None, user: dict | None) -> dict:
    """``{"company_id": ...}`` a new session is stamped with, or ``{}`` for an Unassigned one.

    A new chat belongs to the active company. A client that names one itself (the Company OS CEO chat) must name the
    active company, or a company it may act in when it names none; any other is the canonical 403. With no active
    company the chat is created Unassigned, not refused: a fresh install, the CLI and an API caller have no company
    to name, and the owner decision is that an untagged chat waits in Unassigned for a person to assign it.
    """
    scope = await resolve_company_scope(request, user)
    named = _parse((client_metadata or {}).get("company_id"))
    if named is None:
        return {"company_id": scope.active} if scope.active else {}
    if scope.active is not None and str(named) != scope.active:
        raise fixed_refusal(403)
    if scope.active is None and not (user and await may_act_in_company(named, user)):
        raise fixed_refusal(403)
    return {"company_id": str(named)}


async def company_exists(company_id: uuid.UUID) -> bool:
    """Whether *company_id* is a company (the organization a Company OS company is)."""
    from user_management.database import get_async_session_factory
    from user_management.models.organization import Organization

    async with get_async_session_factory()() as session:
        return await session.get(Organization, company_id) is not None
