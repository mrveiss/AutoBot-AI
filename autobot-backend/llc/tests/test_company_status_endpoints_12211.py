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
from fastapi import FastAPI

from autobot_shared.datetime_utils import datetime_now
from llc.api import companies


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


def _app(svc) -> FastAPI:
    app = FastAPI()
    app.include_router(companies.router, prefix="/api/llc")
    app.dependency_overrides[companies._get_service] = lambda: svc
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
        resp = await client.post(f"/api/llc/companies/{uuid.uuid4()}/activate")
    assert resp.status_code == 200
    assert resp.json()["llc_status"] == "active"
    svc.activate.assert_awaited_once()
    svc.session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_activate_endpoint_invalid_transition_maps_to_409():
    svc = _svc()
    svc.activate = AsyncMock(side_effect=ValueError("Cannot activate company in 'archived' state"))
    async with _client(_app(svc)) as client:
        resp = await client.post(f"/api/llc/companies/{uuid.uuid4()}/activate")
    assert resp.status_code == 409
    assert "Cannot activate" in resp.json()["detail"]
    svc.session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_suspend_endpoint_forwards_reason():
    svc = _svc()
    svc.suspend = AsyncMock(return_value=_org(llc_status="paused", pause_reason="audit"))
    async with _client(_app(svc)) as client:
        resp = await client.post(f"/api/llc/companies/{uuid.uuid4()}/suspend", json={"reason": "audit"})
    assert resp.status_code == 200
    assert resp.json()["llc_status"] == "paused"
    assert svc.suspend.await_args.kwargs["reason"] == "audit"


@pytest.mark.asyncio
async def test_archive_endpoint_returns_archived():
    svc = _svc()
    svc.archive = AsyncMock(return_value=_org(llc_status="archived"))
    async with _client(_app(svc)) as client:
        resp = await client.post(f"/api/llc/companies/{uuid.uuid4()}/archive")
    assert resp.status_code == 200
    assert resp.json()["llc_status"] == "archived"
    svc.archive.assert_awaited_once()
