# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Endpoint wiring tests for the company status-transition routes (#12211).

Companies were stuck in ONBOARDING because the CompanyService transitions
(suspend/archive) were never exposed and no activate() existed. These tests
assert the new POST /activate|/suspend|/archive routes are wired, delegate to
the service, map an invalid-transition ValueError to 409, and commit/rollback.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.datetime_utils import datetime_now
from llc.api import companies
from user_management.services import TenantContext

_ORG_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _org(llc_status: str = "active", pause_reason=None) -> SimpleNamespace:
    now = datetime_now()
    return SimpleNamespace(
        id=uuid.uuid4(),
        name="Acme",
        slug="acme",
        description=None,
        issue_prefix="ACME",
        issue_counter=0,
        budget_monthly_cents=0,
        spent_monthly_cents=0,
        brand_color=None,
        require_approval_for_hires=False,
        parent_org_id=None,
        llc_status=llc_status,
        pause_reason=pause_reason,
        paused_at=None,
        created_at=now,
        updated_at=now,
    )


def _app(svc, *, org_id: uuid.UUID = _ORG_ID, is_platform_admin: bool = False, unauth: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(companies.router, prefix="/api/llc")
    app.dependency_overrides[companies._get_service] = lambda: svc

    def _override_current_user() -> dict:
        if unauth:
            raise HTTPException(status_code=401, detail="Authentication required")
        return {"id": str(_USER_ID), "user_id": str(_USER_ID)}

    def _override_tenant() -> TenantContext:
        return TenantContext(org_id=org_id, user_id=_USER_ID, is_platform_admin=is_platform_admin)

    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[require_org_context] = _override_tenant
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _svc() -> MagicMock:
    svc = MagicMock()
    svc.session = AsyncMock()
    return svc


@pytest.mark.asyncio
async def test_activate_endpoint_returns_active_and_commits():
    svc = _svc()
    svc.activate = AsyncMock(return_value=_org(llc_status="active"))
    async with _client(_app(svc)) as client:
        resp = await client.post(f"/api/llc/companies/{_ORG_ID}/activate")
    assert resp.status_code == 200
    assert resp.json()["llc_status"] == "active"
    svc.activate.assert_awaited_once()
    svc.session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_endpoint_invalid_transition_maps_to_409():
    svc = _svc()
    svc.activate = AsyncMock(side_effect=ValueError("Cannot activate company in 'archived' state"))
    async with _client(_app(svc)) as client:
        resp = await client.post(f"/api/llc/companies/{_ORG_ID}/activate")
    assert resp.status_code == 409
    assert "Cannot activate" in resp.json()["detail"]
    svc.session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_suspend_endpoint_forwards_reason():
    svc = _svc()
    svc.suspend = AsyncMock(return_value=_org(llc_status="paused", pause_reason="audit"))
    async with _client(_app(svc)) as client:
        resp = await client.post(f"/api/llc/companies/{_ORG_ID}/suspend", json={"reason": "audit"})
    assert resp.status_code == 200
    assert resp.json()["llc_status"] == "paused"
    assert svc.suspend.await_args.kwargs["reason"] == "audit"


@pytest.mark.asyncio
async def test_archive_endpoint_returns_archived():
    svc = _svc()
    svc.archive = AsyncMock(return_value=_org(llc_status="archived"))
    async with _client(_app(svc)) as client:
        resp = await client.post(f"/api/llc/companies/{_ORG_ID}/archive")
    assert resp.status_code == 200
    assert resp.json()["llc_status"] == "archived"
    svc.archive.assert_awaited_once()


# ---------------------------------------------------------------------------
# Authn / tenant authz on the mutating transition routes (#12211)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_activate_requires_authentication():
    svc = _svc()
    svc.activate = AsyncMock(return_value=_org())
    async with _client(_app(svc, unauth=True)) as client:
        resp = await client.post(f"/api/llc/companies/{_ORG_ID}/activate")
    assert resp.status_code == 401
    svc.activate.assert_not_called()


@pytest.mark.asyncio
async def test_activate_cross_tenant_is_404_and_does_not_touch_service():
    svc = _svc()
    svc.activate = AsyncMock(return_value=_org())
    other_company = uuid.uuid4()  # caller's org is _ORG_ID, target is a different company
    async with _client(_app(svc)) as client:
        resp = await client.post(f"/api/llc/companies/{other_company}/activate")
    assert resp.status_code == 404
    svc.activate.assert_not_called()


@pytest.mark.asyncio
async def test_platform_admin_may_transition_any_company():
    svc = _svc()
    svc.archive = AsyncMock(return_value=_org(llc_status="archived"))
    other_company = uuid.uuid4()
    async with _client(_app(svc, is_platform_admin=True)) as client:
        resp = await client.post(f"/api/llc/companies/{other_company}/archive")
    assert resp.status_code == 200
    svc.archive.assert_awaited_once()


@pytest.mark.asyncio
async def test_suspend_not_found_maps_to_404():
    from llc.services.company import CompanyNotFoundError

    svc = _svc()
    svc.suspend = AsyncMock(side_effect=CompanyNotFoundError("not found"))
    async with _client(_app(svc)) as client:
        resp = await client.post(f"/api/llc/companies/{_ORG_ID}/suspend")
    assert resp.status_code == 404
    svc.session.rollback.assert_awaited_once()
