# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared FastAPI dependency helpers for LLC API routers (GH#9843).

Eliminates per-router copy-paste of:
  - ``get_session`` / ``SESSION_DEP`` — the request session, committed before the response is
    sent (#21332)
  - ``_service()`` / ``lazy_singleton`` boilerplate — replaced by
    ``service_dep(SvcClass)`` which returns a cacheable Depends-compatible
    factory per service class.

Placed at ``llc.deps`` (not ``llc.api.deps``) so individual router modules can
import it without triggering ``llc.api.__init__`` — which would cause a
circular import when a router is loaded in isolation via importlib (e.g. tests).

Usage::

    from llc.deps import service_dep, SESSION_DEP
    from llc.services.my_service import MyService

    router = APIRouter(...)
    _my_svc_dep = service_dep(MyService)

    @router.get("/")
    async def handler(
        session: AsyncSession = SESSION_DEP,
        svc: MyService = Depends(_my_svc_dep),
    ) -> ...:
        ...
"""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from typing import Any, AsyncGenerator, Callable, Set, Type, TypeVar

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.db_session import PostCommitCallbackError, async_session_scope
from autobot_shared.logging_manager import get_logger
from autobot_shared.security.redaction import safe_log_text, sanitize_log_value
from autobot_shared.singleton_factory import lazy_singleton
from llc.models.sprint import LLCProject
from user_management.database import get_async_session_factory
from user_management.services import TenantContext

logger = get_logger(__name__)

_T = TypeVar("_T")

# Fixed caller-facing text for a failed membership lookup; the cause is logged, never returned.
MEMBERSHIP_LOOKUP_FAILED_DETAIL = "Membership lookup failed"


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Company OS request session: commits on success, rolls back on error (#21332).

    Built on the canonical ``async_session_scope``. Resolved through ``SESSION_DEP`` (function scope) it
    exits after the route body and BEFORE the response is sent, so a 2xx means the write is committed,
    a failing commit never reaches the client as a 2xx, and a raising route rolls back.

    A post-commit callback that fails AFTER the commit (``PostCommitCallbackError``) never turns the answer
    into a failure: the change is saved, so the route answers 2xx and every callback error is logged as a
    warning (owner decision 2026-11-22). A handler that itself raised keeps its own exception.

    Because every LLC router shares this single function object, a test's
    ``app.dependency_overrides[get_session]`` overrides the session for ALL
    migrated llc routers mounted on that app, not just one module.
    """
    handler_raised = False
    try:
        async with async_session_scope(get_async_session_factory()) as session:
            try:
                yield session
            except BaseException:
                handler_raised = True
                raise
    except PostCommitCallbackError as exc:
        if handler_raised:
            raise
        _log_post_commit_failure(exc)


def _log_post_commit_failure(exc: PostCommitCallbackError) -> None:
    """One WARNING naming every failed callback of a write that is already committed (never re-raised)."""
    logger.warning(
        "post-commit callback(s) failed after the write committed; answering success: %s",
        "; ".join(f"{type(e).__name__}: {safe_log_text(e)}" for e in exc.errors),
    )


#: THE session dependency of every LLC route (parameter default, sub-dependencies included). FastAPI's
#: ``scope="function"`` ends the yield dependency after the path operation function and before the response is
#: sent. A plain ``Depends(get_session)`` is request-scoped and would commit after the response: the llc guard
#: (``llc/tests/test_commit_before_answer_guard_21332.py``) fails on it.
SESSION_DEP = Depends(get_session, scope="function")


# ``functools.lru_cache`` does not lock a miss: two threads can both build the
# value and hand out different ones. A lock around a dict makes "one per class"
# true. Re-entrant because ``service_dep`` calls ``service_singleton`` under it.
_REGISTRY_LOCK = threading.RLock()
_SINGLETON_FACTORIES: dict[type, Callable[[], Any]] = {}
_SERVICE_DEPS: dict[type, Callable[[], Any]] = {}


def service_singleton(service_cls: Type[_T]) -> Callable[[], _T]:
    """The ONE singleton factory for *service_cls*, shared by every user (#20889).

    ``service_dep`` and ``services.accessors`` both resolve through here, so a
    dependency-injected handler and a direct caller get the same instance.
    """
    with _REGISTRY_LOCK:
        factory = _SINGLETON_FACTORIES.get(service_cls)
        if factory is None:
            factory = _SINGLETON_FACTORIES[service_cls] = lazy_singleton(service_cls)
        return factory


def service_dep(service_cls: Type[_T]) -> Callable[[], _T]:
    """Return a zero-argument FastAPI dependency that yields the singleton
    instance of *service_cls*.

    The returned callable is cached per class in a locked registry, so repeated
    calls with the same class return the same dependency function — avoiding
    redundant closure creation per request.

    Example::

        _svc_dep = service_dep(ApprovalService)

        @router.post("/")
        async def handler(svc: ApprovalService = Depends(_svc_dep)):
            ...
    """
    with _REGISTRY_LOCK:
        dep = _SERVICE_DEPS.get(service_cls)
        if dep is None:
            dep = _SERVICE_DEPS[service_cls] = _build_dep(service_cls)
        return dep


def _build_dep(service_cls: Type[_T]) -> Callable[[], _T]:
    _get = service_singleton(service_cls)

    def _dep() -> _T:
        return _get()

    # Give the function a readable name for FastAPI dependency introspection.
    _dep.__name__ = f"_dep_{service_cls.__name__}"
    return _dep


_LOGGED_FRAMES = 3


def _frames_label(exc: BaseException) -> str:
    """Innermost stack frames of *exc* as ``file:line in function``, no source lines, no message."""
    frames = traceback.extract_tb(exc.__traceback__)[-_LOGGED_FRAMES:]
    return " <- ".join(sanitize_log_value(f"{f.filename}:{f.lineno} in {f.name}") for f in reversed(frames))


def log_unexpected(
    log: logging.Logger,
    scope: str,
    exc: BaseException,
    *,
    headline: str = "Unexpected error",
    level: int = logging.WARNING,
) -> None:
    """One redacted log line for an exception nobody planned for: class, text, innermost frames (#21579).

    The traceback is never attached (no ``exc_info``): its text would carry the raw message past the redactor.
    *scope* is neutralised like any other untrusted log value.
    """
    log.log(
        level,
        "%s for %s: %s: %s [at %s]",
        headline,
        sanitize_log_value(scope),
        type(exc).__name__,
        safe_log_text(exc),
        _frames_label(exc),
    )


def logged_server_error(log: logging.Logger, detail: str, scope: str, exc: Exception) -> HTTPException:
    """500 carrying only the fixed *detail*; the cause goes to *log*, redacted (#21396).

    Exception text can hold driver messages and connection targets, so it never
    reaches the response body. The log line carries the exception class, its
    text through ``safe_log_text``, and the innermost frames (location only),
    all on one line; *scope* is neutralised like any other untrusted log value.
    """
    log_unexpected(log, scope, exc, headline=detail, level=logging.ERROR)
    return HTTPException(status_code=500, detail=detail)


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
        raise logged_server_error(logger, MEMBERSHIP_LOOKUP_FAILED_DETAIL, f"company {company_id}", exc) from exc

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
    "SESSION_DEP",
]
