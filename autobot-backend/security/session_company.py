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
"""

from __future__ import annotations

import uuid

from fastapi import Request

from autobot_shared.http_refusal import fixed_refusal
from autobot_shared.logging_manager import get_logger
from chat_history.company_scope import CompanyScope

logger = get_logger(__name__)

#: The header the company switcher sends on every request (the same one ``get_tenant_context`` reads).
ACTIVE_COMPANY_HEADER = "X-Organization-Id"


def _parse(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, TypeError):
        return None


async def is_company_member(company_id: uuid.UUID, user: dict) -> bool:
    """Whether *user* may act in *company_id*: a platform admin, or a member of it."""
    from api.user_management.dependencies import (
        _check_org_membership,
        _is_platform_admin_claim,
    )
    from user_management.database import get_async_session_factory

    if _is_platform_admin_claim(user):
        return True
    user_id = _parse(user.get("user_id") or user.get("id") or user.get("sub"))
    if user_id is None:
        return False
    async with get_async_session_factory()() as session:
        return await _check_org_membership(session, company_id, user_id)


def _caller(request: Request) -> dict | None:
    from auth_middleware import get_auth_middleware

    return get_auth_middleware().get_user_from_request(request)


async def resolve_company_scope(request: Request, user: dict | None = None) -> CompanyScope:
    """The caller's ``CompanyScope``; a header naming a company they may not act in is the canonical 403."""
    user = user if user is not None else _caller(request)
    if not user or user.get("service") or user.get("auth_disabled"):
        return CompanyScope(None)
    named = _parse(request.headers.get(ACTIVE_COMPANY_HEADER))
    if named is None:
        return CompanyScope(_parse(user.get("org_id")))
    if not await is_company_member(named, user):
        logger.warning("Active company refused: caller is not a member of the company the header names")
        raise fixed_refusal(403)
    return CompanyScope(named)


async def company_of_session(request: Request, session_id: str) -> str | None:
    """The company stored on the session, ``None`` when it is Unassigned or absent."""
    from utils.chat_utils import get_chat_history_manager

    doc = await get_chat_history_manager(request).get_session(session_id)
    return ((doc or {}).get("metadata") or {}).get("company_id") or None


async def enforce_session_company(session_id: str, request: Request, user: dict | None = None) -> None:
    """Refuse (canonical 403) a session tagged with a company other than the active one; no active company, no check."""
    scope = await resolve_company_scope(request, user)
    if scope.active is None:
        return
    if not scope.allows(await company_of_session(request, session_id)):
        raise fixed_refusal(403)


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
    if scope.active is None and not (user and await is_company_member(named, user)):
        raise fixed_refusal(403)
    return {"company_id": str(named)}


async def company_exists(company_id: uuid.UUID) -> bool:
    """Whether *company_id* is a company (the organization a Company OS company is)."""
    from user_management.database import get_async_session_factory
    from user_management.models.organization import Organization

    async with get_async_session_factory()() as session:
        return await session.get(Organization, company_id) is not None
