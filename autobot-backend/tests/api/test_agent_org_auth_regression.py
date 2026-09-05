# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for GH #15794 — agent org routes accepted anyone.

Linked issue: https://github.com/mrveiss/AutoBot-AI/issues/15794

Bug: ``api/agent_org.py`` declared ``router = APIRouter()`` with no dependencies,
and every route took only ``session: AsyncSession = Depends(get_db_session)``.
No caller identity was involved anywhere. Two of those routes write
``reports_to``:

* ``PATCH /agents/{agent_id}/org`` — ``new_manager_id=body.reports_to``
* ``PUT   /agents/{agent_id}/org`` — ``reports_to=body.reports_to``

That was a data-integrity gap while the hierarchy only described reporting. It
becomes privilege escalation once the hierarchy gates card edits (#15765),
because setting someone's manager *grants* that manager edit rights over them.
``PUT /llc/reporting-lines/...`` was gated on ``admin.reporting_line.write``
while this wrote the same fact with no gate at all — so the permission protected
one of two paths and this was the easier to reach.

Fix applied: ``APIRouter(dependencies=[Depends(get_current_user)])`` on the
router, plus ``Depends(require_reporting_line_write)`` on the two writes.

Regression guarantee: these assert the **negative** — an unauthenticated caller
is refused, and an authenticated caller without the permission is refused on the
writes. A structural check that the dependency is declared cannot show that it
refuses anybody, and a test that only exercises the happy path passes against a
router with no gate at all.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient


def _app_with(overrides: dict) -> FastAPI:
    """Mount the real router with the given dependency overrides."""
    from api.agent_org import router
    from api.user_management.dependencies import get_db_session

    app = FastAPI()
    app.include_router(router, prefix="/agents")

    async def _no_session():  # noqa: ANN202
        # The gate must refuse before any handler touches the database, so the
        # session override is deliberately something that would fail loudly if
        # a handler ever ran. A test that supplied a working session could not
        # tell "refused at the gate" from "ran and happened to return an error".
        raise AssertionError("handler body ran — the gate did not refuse")

    app.dependency_overrides[get_db_session] = _no_session
    for dep, impl in overrides.items():
        app.dependency_overrides[dep] = impl
    return app


def _unauthenticated():  # noqa: ANN202
    async def _raise():  # noqa: ANN202
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    return _raise


@pytest.mark.parametrize("method", ["patch", "put"])
def test_reporting_line_writes_reject_an_unauthenticated_caller(method: str) -> None:
    """No caller identity → refused, before the handler runs."""
    from api.user_management.dependencies import get_current_user

    app = _app_with({get_current_user: _unauthenticated()})
    client = TestClient(app, raise_server_exceptions=False)

    resp = getattr(client, method)(f"/agents/{uuid.uuid4()}/org", json={"reports_to": str(uuid.uuid4())})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.text


@pytest.mark.parametrize("method", ["patch", "put"])
def test_reporting_line_writes_reject_a_caller_without_the_permission(
    method: str,
) -> None:
    """Authenticated but unprivileged → refused.

    This is the case the router-level auth dependency alone would let through,
    and it is the one that matters: an ordinary logged-in user must not be able
    to re-parent an agent and thereby grant authority.
    """
    from api.user_management.dependencies import (
        get_current_user,
        require_reporting_line_write,
    )

    async def _forbidden():  # noqa: ANN202
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin.reporting_line.write permission required",
        )

    app = _app_with(
        {
            get_current_user: lambda: {"id": str(uuid.uuid4()), "role": "user"},
            require_reporting_line_write: _forbidden,
        }
    )
    client = TestClient(app, raise_server_exceptions=False)

    resp = getattr(client, method)(f"/agents/{uuid.uuid4()}/org", json={"reports_to": str(uuid.uuid4())})
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.text


def test_reads_also_require_authentication() -> None:
    """The gate is on the router, not only on the writes.

    The whole org chart — who reports to whom, roles, titles, capabilities — was
    readable by anyone who could reach the port. Gating only the two writes
    would have left that disclosure in place while making the router *look*
    protected to a per-router check.
    """
    from api.user_management.dependencies import get_current_user

    app = _app_with({get_current_user: _unauthenticated()})
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get(f"/agents/{uuid.uuid4()}/reports")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED, resp.text


@pytest.mark.parametrize(
    ("method", "service_method"),
    [("patch", "update_reporting_line"), ("put", "upsert_node")],
)
def test_the_route_passes_the_callers_company_to_the_service(
    method: str, service_method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An authorised write carries the caller's company through to the service.

    The refusal tests above prove the gate refuses. They cannot prove the
    *authorised* path is tenant-scoped: with ``company_id=context.org_id``
    deleted from the route, every one of them still passes while the service
    receives ``None`` and its scoping becomes unreachable from HTTP. Mutation
    showed exactly that — a surviving mutant with a fully green suite.

    So this asserts the wiring rather than the outcome: the value reaching the
    service is the one from the authenticated context.
    """
    import api.agent_org as agent_org
    from api.user_management.dependencies import (
        get_current_user,
        require_reporting_line_write,
    )

    company = uuid.uuid4()
    seen: dict = {}

    class _Svc:
        def __init__(self, session):  # noqa: ANN001
            pass

        async def _record(self, **kwargs):  # noqa: ANN003
            seen.update(kwargs)

            class _Node:
                agent_id = "a"
                name = "n"
                org_role = "worker"
                title = None
                reports_to = None
                capabilities = None
                company_id = company

            return _Node()

    setattr(_Svc, service_method, _Svc._record)
    monkeypatch.setattr(agent_org, "AgentOrgService", _Svc)

    class _Ctx:
        org_id = company

    app = FastAPI()
    app.include_router(agent_org.router, prefix="/agents")
    app.dependency_overrides[get_current_user] = lambda: {
        "id": str(uuid.uuid4()),
        "role": "admin",
    }
    app.dependency_overrides[require_reporting_line_write] = lambda: _Ctx()

    async def _session():  # noqa: ANN202
        return object()

    app.dependency_overrides[agent_org.get_db_session] = _session
    client = TestClient(app, raise_server_exceptions=False)

    getattr(client, method)(
        "/agents/some-agent/org", json={"reports_to": "a-manager", "name": "n"}
    )

    assert seen.get("company_id") == company, (
        f"the service received company_id={seen.get('company_id')!r}; the route must pass the "
        "caller's context, or tenant scoping is unreachable from HTTP"
    )
