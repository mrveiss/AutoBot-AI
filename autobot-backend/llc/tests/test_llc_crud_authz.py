# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Auth + tenant-isolation tests for LLC CRUD/config routers (GH#12148).

costs.py / decisions.py / labels.py / templates.py previously depended only on
``get_async_session`` / ``get_session`` — no authentication and no tenant
authorization — allowing an unauthenticated caller to read/mutate ANY company's
data by supplying an arbitrary ``company_id`` (missing-authentication + IDOR).

Each router is exercised for: unauthenticated -> 401, cross-tenant -> 403/404,
same-tenant -> success. Labels use the real in-memory ORM harness so the
IDOR guards run against real rows; decisions/templates mock their KB/DB layer.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator, Optional
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkItemStatus, WorkItemType
from llc.models.label import LLCLabel
from llc.models.work_item import LLCWorkItem
from llc.tests import _e2e_harness as harness

_FIXED_USER_ID = uuid.UUID("77777777-7777-7777-7777-777777777777")
_OTHER_ORG = str(uuid.uuid4())


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    return async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )  # canonical: ignore py-adhoc-db-engine


def _make_app(
    session_factory,
    caller_org_id: str,
    *,
    is_platform_admin: bool = False,
    unauth: bool = False,
    template_svc: Optional[object] = None,
) -> FastAPI:  # noqa: ANN001
    """Build a FastAPI app wiring the 4 CRUD routers with a fixed tenant ctx."""
    from api.user_management.dependencies import get_current_user, require_org_context
    from llc.api import costs as costs_api
    from llc.api import decisions as decisions_api
    from llc.api import labels as labels_api
    from llc.api import templates as templates_api
    from llc.deps import get_session
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    app = FastAPI()
    app.include_router(costs_api.router, prefix="/api/llc")
    app.include_router(decisions_api.router, prefix="/api/llc")
    app.include_router(labels_api.router, prefix="/api/llc")
    app.include_router(templates_api.router, prefix="/api/llc")

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_async_session] = _override_session
    app.dependency_overrides[get_session] = _override_session

    def _override_current_user() -> dict:
        if unauth:
            raise HTTPException(status_code=401, detail="Authentication required")
        return {"id": str(_FIXED_USER_ID), "user_id": str(_FIXED_USER_ID)}

    def _override_tenant() -> TenantContext:
        return TenantContext(
            org_id=uuid.UUID(caller_org_id),
            user_id=_FIXED_USER_ID,
            is_platform_admin=is_platform_admin,
        )

    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_org_context] = _override_tenant

    if template_svc is not None:
        app.dependency_overrides[templates_api._get_service] = lambda: template_svc

    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _insert_label(session_factory, company_id: str, name: str = "bug") -> str:  # noqa: ANN001
    label_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(LLCLabel(id=label_id, company_id=uuid.UUID(company_id), name=name, color="#ef4444"))
        await session.commit()
    return str(label_id)


async def _insert_work_item(session_factory, company_id: str) -> str:  # noqa: ANN001
    wi_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCWorkItem(
                id=wi_id,
                company_id=uuid.UUID(company_id),
                identifier=f"WI-{uuid.uuid4().hex[:8]}",
                type=WorkItemType.TASK.value,
                title="Item",
                status=WorkItemStatus.BACKLOG.value,
                priority="medium",
                version=1,
                labels=[],
            )
        )
        await session.commit()
    return str(wi_id)


# ---------------------------------------------------------------------------
# labels.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_labels_unauth_returns_401(session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    async with _client(_make_app(session_factory, company_id, unauth=True)) as client:
        resp = await client.get(f"/api/llc/companies/{company_id}/labels")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_labels_same_tenant_update_and_list(session_factory) -> None:  # noqa: ANN001
    """Same-tenant caller can mutate and list a label owned by their company.

    Uses a pre-seeded label with an explicit id because the SQLite harness has
    no ``gen_random_uuid()`` server default (Postgres-only); label creation via
    the service is covered by the service unit tests in test_labels.py.
    """
    company_id = str(uuid.uuid4())
    label_id = await _insert_label(session_factory, company_id)
    async with _client(_make_app(session_factory, company_id)) as client:
        patched = await client.patch(f"/api/llc/companies/{company_id}/labels/{label_id}", json={"name": "renamed"})
        assert patched.status_code == 200, patched.text
        assert patched.json()["name"] == "renamed"
        listing = await client.get(f"/api/llc/companies/{company_id}/labels")
    assert listing.status_code == 200, listing.text
    assert len(listing.json()) == 1


@pytest.mark.asyncio
async def test_labels_cross_tenant_create_returns_404(session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    async with _client(_make_app(session_factory, _OTHER_ORG)) as client:
        resp = await client.post(f"/api/llc/companies/{company_id}/labels", json={"name": "bug"})
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_labels_cross_company_label_idor_returns_404(session_factory) -> None:  # noqa: ANN001
    """Caller owns company A but references a label that belongs to company B."""
    company_a = str(uuid.uuid4())
    company_b = str(uuid.uuid4())
    label_b = await _insert_label(session_factory, company_b)
    async with _client(_make_app(session_factory, company_a)) as client:
        resp = await client.patch(f"/api/llc/companies/{company_a}/labels/{label_b}", json={"name": "hijack"})
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_labels_cross_company_work_item_idor_returns_404(session_factory) -> None:  # noqa: ANN001
    company_a = str(uuid.uuid4())
    company_b = str(uuid.uuid4())
    wi_b = await _insert_work_item(session_factory, company_b)
    label_a = await _insert_label(session_factory, company_a)
    async with _client(_make_app(session_factory, company_a)) as client:
        resp = await client.post(
            f"/api/llc/companies/{company_a}/labels/work-items/{wi_b}/labels",
            json={"label_ids": [label_a]},
        )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# costs.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_costs_unauth_returns_401(session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    async with _client(_make_app(session_factory, company_id, unauth=True)) as client:
        resp = await client.get("/api/llc/costs/by-agent-model", params={"company_id": company_id})
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_costs_cross_tenant_returns_404(session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    async with _client(_make_app(session_factory, _OTHER_ORG)) as client:
        resp = await client.get("/api/llc/costs/by-agent-model", params={"company_id": company_id})
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_costs_same_tenant_returns_200(session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    async with _client(_make_app(session_factory, company_id)) as client:
        resp = await client.get("/api/llc/costs/by-agent-model", params={"company_id": company_id})
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# decisions.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_decisions_unauth_returns_401(session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    async with _client(_make_app(session_factory, company_id, unauth=True)) as client:
        resp = await client.get(f"/api/llc/companies/{company_id}/decisions")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_decisions_cross_tenant_returns_404(session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    async with _client(_make_app(session_factory, _OTHER_ORG)) as client:
        resp = await client.get(f"/api/llc/companies/{company_id}/decisions")
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_decisions_same_tenant_returns_200(session_factory, monkeypatch) -> None:  # noqa: ANN001
    from llc.api import decisions as decisions_api

    monkeypatch.setattr(decisions_api._reader, "list_decisions", AsyncMock(return_value=[]))
    company_id = str(uuid.uuid4())
    async with _client(_make_app(session_factory, company_id)) as client:
        resp = await client.get(f"/api/llc/companies/{company_id}/decisions")
    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# templates.py
# ---------------------------------------------------------------------------


def _fake_template_service() -> MagicMock:
    svc = MagicMock()
    svc.session = AsyncMock()
    svc.list_templates = AsyncMock(return_value=[])
    svc.import_template = AsyncMock()
    svc.delete = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_templates_unauth_returns_401(session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    app = _make_app(session_factory, company_id, unauth=True, template_svc=_fake_template_service())
    async with _client(app) as client:
        resp = await client.get("/api/llc/templates/built-in")
    assert resp.status_code == 401, resp.text


@pytest.mark.asyncio
async def test_templates_cross_tenant_list_returns_404(session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    app = _make_app(session_factory, _OTHER_ORG, template_svc=_fake_template_service())
    async with _client(app) as client:
        resp = await client.get("/api/llc/templates/", params={"company_id": company_id})
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_templates_import_cross_tenant_returns_404(session_factory) -> None:  # noqa: ANN001
    target = str(uuid.uuid4())
    template_id = str(uuid.uuid4())
    app = _make_app(session_factory, _OTHER_ORG, template_svc=_fake_template_service())
    async with _client(app) as client:
        resp = await client.post(
            f"/api/llc/templates/{template_id}/import",
            json={"target_company_id": target, "secrets": {}},
        )
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_templates_delete_non_owner_returns_404(session_factory) -> None:  # noqa: ANN001
    caller_org = str(uuid.uuid4())
    template_id = str(uuid.uuid4())
    svc = _fake_template_service()
    detail = MagicMock()
    detail.created_by_company_id = uuid.uuid4()  # owned by a different company
    svc.get = AsyncMock(return_value=detail)
    app = _make_app(session_factory, caller_org, template_svc=svc)
    async with _client(app) as client:
        resp = await client.delete(f"/api/llc/templates/{template_id}")
    assert resp.status_code == 404, resp.text
    svc.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_templates_same_tenant_list_returns_200(session_factory) -> None:  # noqa: ANN001
    company_id = str(uuid.uuid4())
    app = _make_app(session_factory, company_id, template_svc=_fake_template_service())
    async with _client(app) as client:
        resp = await client.get("/api/llc/templates/", params={"company_id": company_id})
    assert resp.status_code == 200, resp.text
    assert resp.json() == []
