# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tenant-authz tests for the company get/update/delete endpoints (#12233).

These endpoints previously depended only on ``_get_service`` — no authn and no
tenant check — an unauthenticated cross-tenant IDOR (read/modify/delete any
company by UUID). They now enforce the same guard as the status transitions:
authenticated, and the caller's org must match ``company_id`` unless platform
admin.
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


def _org() -> SimpleNamespace:
    now = datetime_now()
    return SimpleNamespace(
        id=_ORG_ID,
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
        llc_status="active",
        pause_reason=None,
        paused_at=None,
        created_at=now,
        updated_at=now,
    )


def _app(svc, *, org_id: uuid.UUID = _ORG_ID, is_platform_admin: bool = False, unauth: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(companies.router, prefix="/api/llc")
    app.dependency_overrides[companies._get_service] = lambda: svc

    def _cur() -> dict:
        if unauth:
            raise HTTPException(status_code=401, detail="Authentication required")
        return {"id": str(_USER_ID), "user_id": str(_USER_ID)}

    def _ctx() -> TenantContext:
        return TenantContext(org_id=org_id, user_id=_USER_ID, is_platform_admin=is_platform_admin)

    app.dependency_overrides[get_current_user] = _cur
    app.dependency_overrides[require_org_context] = _ctx
    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _svc() -> MagicMock:
    svc = MagicMock()
    svc.session = AsyncMock()
    svc.get = AsyncMock(return_value=_org())
    svc.update = AsyncMock(return_value=_org())
    svc.delete = AsyncMock(return_value=None)
    return svc


# --- happy path (own org) ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_own_company_ok():
    svc = _svc()
    async with _client(_app(svc)) as client:
        resp = await client.get(f"/api/llc/companies/{_ORG_ID}")
    assert resp.status_code == 200
    svc.get.assert_awaited_once()


@pytest.mark.asyncio
async def test_platform_admin_may_delete_any_company():
    svc = _svc()
    other = uuid.uuid4()
    async with _client(_app(svc, is_platform_admin=True)) as client:
        resp = await client.delete(f"/api/llc/companies/{other}")
    assert resp.status_code == 204
    svc.delete.assert_awaited_once()


# --- authz enforcement ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_requires_authentication():
    svc = _svc()
    async with _client(_app(svc, unauth=True)) as client:
        resp = await client.get(f"/api/llc/companies/{_ORG_ID}")
    assert resp.status_code == 401
    svc.get.assert_not_called()


@pytest.mark.asyncio
async def test_update_cross_tenant_is_404_and_untouched():
    svc = _svc()
    other = uuid.uuid4()
    async with _client(_app(svc)) as client:
        resp = await client.patch(f"/api/llc/companies/{other}", json={"name": "Hacked"})
    assert resp.status_code == 404
    svc.update.assert_not_called()


@pytest.mark.asyncio
async def test_delete_cross_tenant_is_404_and_untouched():
    svc = _svc()
    other = uuid.uuid4()
    async with _client(_app(svc)) as client:
        resp = await client.delete(f"/api/llc/companies/{other}")
    assert resp.status_code == 404
    svc.delete.assert_not_called()
