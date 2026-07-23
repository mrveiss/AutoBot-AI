# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared FastAPI dependency helpers for LLC API routers (GH#9843).

Eliminates per-router copy-paste of:
  - ``get_session`` — bare async session (no auto-commit; callers manage
    transactions explicitly via ``session.begin()`` / ``session.commit()``)
  - ``_service()`` / ``lazy_singleton`` boilerplate — replaced by
    ``service_dep(SvcClass)`` which returns a cacheable Depends-compatible
    factory per service class.

Placed at ``llc.deps`` (not ``llc.api.deps``) so individual router modules can
import it without triggering ``llc.api.__init__`` — which would cause a
circular import when a router is loaded in isolation via importlib (e.g. tests).

Usage::

    from llc.deps import get_session, service_dep
    from llc.services.my_service import MyService

    router = APIRouter(...)
    _my_svc_dep = service_dep(MyService)

    @router.get("/")
    async def handler(
        session: AsyncSession = Depends(get_session),
        svc: MyService = Depends(_my_svc_dep),
    ) -> ...:
        ...
"""

from __future__ import annotations

import functools
import uuid
from typing import Any, AsyncGenerator, Callable, Set, Type, TypeVar

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.singleton_factory import lazy_singleton
from llc.models.sprint import LLCProject
from user_management.database import get_async_session_factory
from user_management.services import TenantContext

_T = TypeVar("_T")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Bare async DB session — no auto-commit or auto-rollback.

    Callers are responsible for explicit transaction management
    (``session.begin()`` / ``session.commit()``).  This mirrors the
    pre-refactor per-router ``get_session`` implementations exactly so that
    endpoint behaviour is unchanged.

    Because every LLC router shares this single function object, a test's
    ``app.dependency_overrides[get_session]`` overrides the session for ALL
    migrated llc routers mounted on that app, not just one module.
    """
    factory = get_async_session_factory()
    async with factory() as session:
        yield session


@functools.lru_cache(maxsize=None)
def service_dep(service_cls: Type[_T]) -> Callable[[], _T]:
    """Return a zero-argument FastAPI dependency that yields the singleton
    instance of *service_cls*.

    The returned callable is cached per class (``lru_cache``), so repeated
    calls with the same class return the same dependency function — avoiding
    redundant closure creation per request.

    Example::

        _svc_dep = service_dep(ApprovalService)

        @router.post("/")
        async def handler(svc: ApprovalService = Depends(_svc_dep)):
            ...
    """
    _get = lazy_singleton(service_cls)

    def _dep() -> _T:
        return _get()

    # Give the function a readable name for FastAPI dependency introspection.
    _dep.__name__ = f"_dep_{service_cls.__name__}"
    return _dep


async def require_board_role(
    company_id: uuid.UUID,
    current_user: dict,
    session: AsyncSession,
    allowed_roles: Set[str],
    membership_svc: object,
    detail: str = "Insufficient board role for this operation",
) -> str:
    """Raise 403 unless caller holds one of *allowed_roles* in *company_id*.

    Canonical implementation shared by controls.py and replay.py (M7).
    Returns the actor user_id string for activity log use.
    """
    user_id = current_user.get("id") or current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        members = await membership_svc.list_members(session, str(company_id))  # type: ignore[attr-defined]
        role = next(
            (m.role for m in members if str(m.user_id) == str(user_id)),
            None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Membership lookup failed: {exc}") from exc

    if role not in allowed_roles:
        raise HTTPException(status_code=403, detail=detail)
    return str(user_id)


async def load_owned_project(project_id: uuid.UUID, session: AsyncSession, ctx: TenantContext) -> LLCProject:
    """Load a project by id; 404 when missing or owned by a different org.

    IDOR guard (#10148): canonical implementation shared by sprints.py and
    findings.py, which previously each defined an identical
    ``_load_owned_project`` (#11359). 404 (not 403) is used for both "missing"
    and "wrong org" to avoid disclosing project existence to non-owners.
    """
    result = await session.execute(select(LLCProject).where(LLCProject.id == project_id))
    project = result.scalar_one_or_none()
    if project is None or str(project.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def assert_company_access(ctx: TenantContext, company_id: Any) -> None:
    """Reject cross-tenant access to a company-scoped resource (#12184).

    Canonical tenant-check idiom, consolidated from the near-identical
    per-router ``_assert_company_match`` copies previously defined in
    approvals.py, decisions.py, costs.py, goals.py, backlog.py, budget.py,
    review_gate_policies.py, agent_hires.py, and labels.py. 404 (not 403) so a
    cross-tenant caller can't distinguish "not my company" from "doesn't
    exist". Platform admins are exempt. Both sides are ``str()``-coerced so
    callers may pass either a ``str`` or a ``uuid.UUID``.
    """
    if str(company_id) != str(ctx.org_id) and not ctx.is_platform_admin:
        raise HTTPException(status_code=404, detail="Company not found")


async def load_authorized(
    session: AsyncSession,
    model: Type[_T],
    obj_id: Any,
    ctx: TenantContext,
    *,
    id_attr: str = "id",
    company_attr: str = "company_id",
    not_found_detail: str = "Not found",
) -> _T:
    """Load a *model* row by *obj_id*; 404 if missing or owned by another org (#12184).

    Generic IDOR-guard loader consolidating the per-router
    ``_get_authorized_<obj>`` / ``_load_authorized_<obj>`` copies, each of
    which re-implemented "select by id, then compare the row's owning company
    to ``ctx.org_id``". 404 (not 403) is used for both "missing" and "wrong
    org" to avoid disclosing row existence to non-owners. Platform admins are
    exempt.
    """
    result = await session.execute(select(model).where(getattr(model, id_attr) == obj_id))
    row = result.scalar_one_or_none()
    if row is None or (str(getattr(row, company_attr)) != str(ctx.org_id) and not ctx.is_platform_admin):
        raise HTTPException(status_code=404, detail=not_found_detail)
    return row


__all__ = [
    "assert_company_access",
    "get_session",
    "load_authorized",
    "load_owned_project",
    "require_board_role",
    "service_dep",
]
