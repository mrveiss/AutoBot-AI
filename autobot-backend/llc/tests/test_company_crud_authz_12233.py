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


# ===========================================================================
# Collection routes: list / create (#12233).
#
# These carry no ``company_id`` path param, so they authenticate with
# ``get_current_user`` and scope by membership (not ``require_org_context``):
#   - list   → non-admins see only companies they are a member of.
#   - create → a sub-company may only be grafted under an owned parent; the
#              creator is recorded as OWNER. Root creation is open to any
#              authenticated user (the creation-wizard flow).
# ===========================================================================


def _collection_app(
    svc,
    membership_svc,
    *,
    is_platform_admin: bool = False,
    unauth: bool = False,
) -> FastAPI:
    app = FastAPI()
    app.include_router(companies.router, prefix="/api/llc")
    app.dependency_overrides[companies._get_service] = lambda: svc
    app.dependency_overrides[companies._get_membership_service] = lambda: membership_svc

    def _cur() -> dict:
        if unauth:
            raise HTTPException(status_code=401, detail="Authentication required")
        user = {"id": str(_USER_ID), "user_id": str(_USER_ID)}
        if is_platform_admin:
            user["role"] = "admin"
        return user

    app.dependency_overrides[get_current_user] = _cur
    return app


def _list_svc() -> MagicMock:
    svc = MagicMock()
    svc.session = AsyncMock()
    svc.list_root_companies = AsyncMock(return_value=[_org()])
    return svc


def _create_svc() -> MagicMock:
    svc = MagicMock()
    svc.session = AsyncMock()
    svc.create = AsyncMock(return_value=_org())
    return svc


def _membership(is_member: bool = True) -> MagicMock:
    m = MagicMock()
    m.is_member = AsyncMock(return_value=is_member)
    m.add_member = AsyncMock()
    # #12325: list_companies now filters against a single membership-id query
    # instead of one is_member call per root.
    m.list_member_company_ids = AsyncMock(return_value=({_ORG_ID} if is_member else set()))
    return m


# --- list_companies ---------------------------------------------------------


@pytest.mark.asyncio
async def test_list_requires_authentication():
    svc = _list_svc()
    app = _collection_app(svc, _membership(), unauth=True)
    async with _client(app) as client:
        resp = await client.get("/api/llc/companies/")
    assert resp.status_code == 401
    svc.list_root_companies.assert_not_called()


@pytest.mark.asyncio
async def test_list_member_sees_own_company():
    svc = _list_svc()
    app = _collection_app(svc, _membership(is_member=True))
    async with _client(app) as client:
        resp = await client.get("/api/llc/companies/")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


@pytest.mark.asyncio
async def test_list_non_member_sees_nothing():
    """Cross-tenant enumeration is closed: a non-member gets an empty list."""
    svc = _list_svc()
    app = _collection_app(svc, _membership(is_member=False))
    async with _client(app) as client:
        resp = await client.get("/api/llc/companies/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_platform_admin_sees_all():
    svc = _list_svc()
    membership = _membership(is_member=False)  # admin bypasses membership entirely
    app = _collection_app(svc, membership, is_platform_admin=True)
    async with _client(app) as client:
        resp = await client.get("/api/llc/companies/")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    membership.is_member.assert_not_called()


# --- create_company ---------------------------------------------------------


@pytest.mark.asyncio
async def test_create_requires_authentication():
    svc = _create_svc()
    app = _collection_app(svc, _membership(), unauth=True)
    async with _client(app) as client:
        resp = await client.post("/api/llc/companies/", json={"name": "NewCo"})
    assert resp.status_code == 401
    svc.create.assert_not_called()


@pytest.mark.asyncio
async def test_create_root_records_creator_as_owner(monkeypatch):
    from llc.models.enums import MembershipRole

    monkeypatch.setattr(companies._kb_manager, "ensure_collection", AsyncMock())
    svc = _create_svc()
    membership = _membership()
    app = _collection_app(svc, membership)
    async with _client(app) as client:
        resp = await client.post("/api/llc/companies/", json={"name": "NewCo"})
    assert resp.status_code == 201, resp.text
    svc.create.assert_awaited_once()
    membership.add_member.assert_awaited_once()
    # creator is added to the just-created company as OWNER
    args = membership.add_member.await_args.args
    assert args[1] == str(_ORG_ID)
    assert args[2] == str(_USER_ID)
    assert args[3] == MembershipRole.OWNER


@pytest.mark.asyncio
async def test_create_sub_company_cross_tenant_parent_is_404():
    """A non-member cannot graft a sub-company under another tenant's company."""
    svc = _create_svc()
    membership = _membership(is_member=False)
    app = _collection_app(svc, membership)
    async with _client(app) as client:
        resp = await client.post(
            "/api/llc/companies/",
            json={"name": "Sub", "parent_org_id": str(uuid.uuid4())},
        )
    assert resp.status_code == 404
    svc.create.assert_not_called()
    membership.add_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_sub_company_owned_parent_ok(monkeypatch):
    monkeypatch.setattr(companies._kb_manager, "ensure_collection", AsyncMock())
    svc = _create_svc()
    membership = _membership(is_member=True)
    app = _collection_app(svc, membership)
    async with _client(app) as client:
        resp = await client.post(
            "/api/llc/companies/",
            json={"name": "Sub", "parent_org_id": str(uuid.uuid4())},
        )
    assert resp.status_code == 201, resp.text
    svc.create.assert_awaited_once()


# ===========================================================================
# Path-scoped route guard — export_snapshot as a representative (#12233).
# Every {company_id} route now enforces get_current_user + require_org_context
# + assert_company_access; the export routes leak a full tenant snapshot.
# ===========================================================================


def _export_svc() -> MagicMock:
    svc = MagicMock()
    svc.export_snapshot = AsyncMock(return_value={"company_id": str(_ORG_ID)})
    return svc


def _export_app(svc, *, org_id: uuid.UUID = _ORG_ID, unauth: bool = False) -> FastAPI:
    app = FastAPI()
    app.include_router(companies.router, prefix="/api/llc")
    app.dependency_overrides[companies._get_portability_service] = lambda: svc

    def _cur() -> dict:
        if unauth:
            raise HTTPException(status_code=401, detail="Authentication required")
        return {"id": str(_USER_ID), "user_id": str(_USER_ID)}

    def _ctx() -> TenantContext:
        return TenantContext(org_id=org_id, user_id=_USER_ID, is_platform_admin=False)

    app.dependency_overrides[get_current_user] = _cur
    app.dependency_overrides[require_org_context] = _ctx
    return app


@pytest.mark.asyncio
async def test_export_snapshot_requires_authentication():
    svc = _export_svc()
    async with _client(_export_app(svc, unauth=True)) as client:
        resp = await client.post(f"/api/llc/companies/{_ORG_ID}/export/snapshot")
    assert resp.status_code == 401
    svc.export_snapshot.assert_not_called()


@pytest.mark.asyncio
async def test_export_snapshot_cross_tenant_is_404_and_untouched():
    svc = _export_svc()
    other = uuid.uuid4()
    async with _client(_export_app(svc)) as client:
        resp = await client.post(f"/api/llc/companies/{other}/export/snapshot")
    assert resp.status_code == 404
    svc.export_snapshot.assert_not_called()


@pytest.mark.asyncio
async def test_export_snapshot_same_tenant_ok():
    svc = _export_svc()
    async with _client(_export_app(svc)) as client:
        resp = await client.post(f"/api/llc/companies/{_ORG_ID}/export/snapshot")
    assert resp.status_code == 200
    svc.export_snapshot.assert_awaited_once()
