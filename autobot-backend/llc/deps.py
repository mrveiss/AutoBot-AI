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

    from llc.deps import get_session, postgres_required, service_dep
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
from typing import AsyncGenerator, Callable, Set, Type, TypeVar

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session_factory

_T = TypeVar("_T")


def postgres_required() -> None:
    """FastAPI dependency hook for LLC endpoints requiring a Postgres session.

    AutoBot always runs full, Postgres-backed user management (#10636), so this
    gate always passes.  Retained as a router-level dependency hook so existing
    router wiring (``APIRouter(dependencies=[Depends(postgres_required)])``)
    stays in place.
    """
    return None


async def get_session(
    _gate: None = Depends(postgres_required),
) -> AsyncGenerator[AsyncSession, None]:
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


__all__ = ["get_session", "postgres_required", "require_board_role", "service_dep"]
