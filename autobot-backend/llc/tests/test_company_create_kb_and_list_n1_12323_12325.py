# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""create_company commit-ordering (#12323) + list_companies N+1 (#12325).

#12323 — ``create_company`` used to ``commit()`` the new company *before*
serializing the response and creating its KB collections, so a failure in either
left a committed-but-500 company (the DB and the caller disagreed). The handler
now serializes + ensures KB collections BEFORE the single commit, mirroring the
#12309/#12321 "serialize before commit" invariant: any failure rolls the INSERT
back and no company is persisted.

#12325 — ``list_companies`` used to run one ``is_member`` query per root company
across *every* tenant (an N+1 scaling with system-wide tenant count). It now
issues a single ``list_member_company_ids`` query and filters in memory.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from api.user_management.dependencies import get_current_user
from autobot_shared.datetime_utils import datetime_now
from llc.api import companies

_ORG_ID = uuid.uuid4()
_USER_ID = uuid.uuid4()


def _org(org_id: uuid.UUID = _ORG_ID) -> SimpleNamespace:
    now = datetime_now()
    return SimpleNamespace(
        id=org_id,
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


def _client(app: FastAPI) -> httpx.AsyncClient:
    # raise_app_exceptions=False so a re-raised endpoint error surfaces as a 500
    # HTTP response (the rollback-on-failure tests assert on that status).
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


def _app(svc, membership, *, is_platform_admin: bool = False, subject: str = None) -> FastAPI:
    app = FastAPI()
    app.include_router(companies.router, prefix="/api/llc")
    app.dependency_overrides[companies._get_service] = lambda: svc
    app.dependency_overrides[companies._get_membership_service] = lambda: membership

    def _cur() -> dict:
        user = {"id": subject or str(_USER_ID), "user_id": subject or str(_USER_ID)}
        if is_platform_admin:
            user["role"] = "admin"
        return user

    app.dependency_overrides[get_current_user] = _cur
    return app


# ===========================================================================
# #12323 — create commit ordering / rollback on failure
# ===========================================================================


def _create_svc() -> MagicMock:
    svc = MagicMock()
    svc.session = AsyncMock()
    svc.create = AsyncMock(return_value=_org())
    return svc


def _membership() -> MagicMock:
    m = MagicMock()
    m.add_member = AsyncMock()
    m.is_member = AsyncMock(return_value=True)
    return m


@pytest.mark.asyncio
async def test_create_commits_after_kb_and_serialize(monkeypatch):
    """Happy path: KB ensured + response serialized, then exactly one commit."""
    ensure = AsyncMock()
    monkeypatch.setattr(companies.KbCollectionManager, "ensure_collection", ensure)
    svc = _create_svc()
    membership = _membership()
    async with _client(_app(svc, membership)) as client:
        resp = await client.post("/api/llc/companies/", json={"name": "NewCo"})
    assert resp.status_code == 201, resp.text
    # KB collections created for the 3 canonical suffixes.
    assert ensure.await_count == 3
    svc.session.commit.assert_awaited_once()
    svc.session.rollback.assert_not_called()


@pytest.mark.asyncio
async def test_create_kb_failure_rolls_back_no_commit(monkeypatch):
    """A KB failure must roll the INSERT back and never commit (#12323)."""
    monkeypatch.setattr(
        companies.KbCollectionManager,
        "ensure_collection",
        AsyncMock(side_effect=RuntimeError("chroma down")),
    )
    svc = _create_svc()
    membership = _membership()
    async with _client(_app(svc, membership)) as client:
        resp = await client.post("/api/llc/companies/", json={"name": "NewCo"})
    assert resp.status_code == 500
    # The company INSERT is rolled back and never committed → no committed-but-500 row.
    svc.session.commit.assert_not_called()
    svc.session.rollback.assert_awaited()


@pytest.mark.asyncio
async def test_create_serialize_failure_rolls_back_no_commit(monkeypatch):
    """A serialization failure before commit also rolls back (#12323)."""
    monkeypatch.setattr(companies.KbCollectionManager, "ensure_collection", AsyncMock())
    monkeypatch.setattr(
        companies,
        "_to_read",
        MagicMock(side_effect=RuntimeError("serialize boom")),
    )
    svc = _create_svc()
    membership = _membership()
    async with _client(_app(svc, membership)) as client:
        resp = await client.post("/api/llc/companies/", json={"name": "NewCo"})
    assert resp.status_code == 500
    svc.session.commit.assert_not_called()
    svc.session.rollback.assert_awaited()


# ===========================================================================
# #12325 — list_companies single membership query (no N+1)
# ===========================================================================


def _list_svc(roots) -> MagicMock:
    svc = MagicMock()
    svc.session = AsyncMock()
    svc.list_root_companies = AsyncMock(return_value=roots)
    return svc


def _list_membership(member_ids: set) -> MagicMock:
    m = MagicMock()
    m.list_member_company_ids = AsyncMock(return_value=member_ids)
    m.is_member = AsyncMock(return_value=False)  # must NOT be used by list
    return m


@pytest.mark.asyncio
async def test_list_uses_single_membership_query_not_per_root():
    """Membership is resolved with ONE query, not one is_member per root (#12325)."""
    roots = [_org(uuid.uuid4()) for _ in range(5)]
    visible_id = roots[2].id
    svc = _list_svc(roots)
    membership = _list_membership({visible_id})
    async with _client(_app(svc, membership)) as client:
        resp = await client.get("/api/llc/companies/")
    assert resp.status_code == 200
    body = resp.json()
    assert [c["id"] for c in body] == [str(visible_id)]
    # Exactly one membership round-trip regardless of root count; no per-root N+1.
    membership.list_member_company_ids.assert_awaited_once()
    membership.is_member.assert_not_called()


@pytest.mark.asyncio
async def test_list_non_member_sees_nothing():
    roots = [_org(uuid.uuid4()) for _ in range(3)]
    svc = _list_svc(roots)
    membership = _list_membership(set())
    async with _client(_app(svc, membership)) as client:
        resp = await client.get("/api/llc/companies/")
    assert resp.status_code == 200
    assert resp.json() == []
    membership.list_member_company_ids.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_admin_sees_all_without_membership_query():
    roots = [_org(uuid.uuid4()) for _ in range(4)]
    svc = _list_svc(roots)
    membership = _list_membership(set())
    async with _client(_app(svc, membership, is_platform_admin=True)) as client:
        resp = await client.get("/api/llc/companies/")
    assert resp.status_code == 200
    assert len(resp.json()) == 4
    membership.list_member_company_ids.assert_not_called()


@pytest.mark.asyncio
async def test_list_non_uuid_subject_is_401(monkeypatch):
    """A non-UUID JWT subject yields a clean 401, not a 500 (#12325 nit)."""
    roots = [_org(uuid.uuid4())]
    svc = _list_svc(roots)
    membership = _list_membership(set())
    async with _client(_app(svc, membership, subject="not-a-uuid")) as client:
        resp = await client.get("/api/llc/companies/")
    assert resp.status_code == 401
    membership.list_member_company_ids.assert_not_called()
