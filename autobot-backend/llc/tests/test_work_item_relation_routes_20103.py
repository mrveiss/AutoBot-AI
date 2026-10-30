# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The work-item relation routes, through the real routers on a real session (#20103).

``POST``/``DELETE /api/llc/work-items/{id}/relations`` called the relation service
without the ``session`` it requires, so every request was a ``TypeError`` -> 500. The
unit tests for the service pass a session by hand and so never saw the routes.

The app mounts the production ``llc.api.router``, so these assertions hold wherever
the relation routes live.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api import router as llc_router
from llc.deps import get_session
from llc.models.enums import WorkItemRelationType, WorkItemType
from llc.models.work_item import LLCWorkItemRelation
from llc.services.work_item_service import WorkItemService
from llc.tests import _e2e_harness as harness
from user_management.services import TenantContext

pytestmark = pytest.mark.asyncio

COMPANY_A, COMPANY_B = uuid.uuid4(), uuid.uuid4()
USER_A = uuid.uuid4()
FORGED_COMPANY, FORGED_USER, FORGED_AGENT = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


@pytest_asyncio.fixture
async def maker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    await harness.create_loop_schema(engine)
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


def _client(maker, company: uuid.UUID = COMPANY_A) -> httpx.AsyncClient:
    app = FastAPI()
    app.include_router(llc_router, prefix="/api")

    async def _session():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(USER_A)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=company, user_id=USER_A, is_platform_admin=False
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")


async def _item(maker, company: uuid.UUID, title: str) -> str:
    async with maker() as s:
        item = await WorkItemService().create(s, company_id=str(company), type=WorkItemType.TASK, title=title)
        await s.commit()
        return str(item.id)


async def _rows(maker) -> list[LLCWorkItemRelation]:
    async with maker() as s:
        return list((await s.execute(select(LLCWorkItemRelation))).scalars())


def _url(source: str) -> str:
    return f"/api/llc/work-items/{source}/relations"


def _body(target: str, rtype: str = "blocks", **extra) -> dict:
    return {"company_id": str(COMPANY_A), "target_id": target, "relation_type": rtype, **extra}


async def test_add_creates_the_relation_and_its_mirror(maker):
    a, b = await _item(maker, COMPANY_A, "a"), await _item(maker, COMPANY_A, "b")
    async with _client(maker) as c:
        resp = await c.post(_url(a), json=_body(b))
    assert resp.status_code == 201, resp.text
    assert resp.json()["relation_type"] == "blocks"
    assert {(str(r.source_id), str(r.target_id), r.relation_type) for r in await _rows(maker)} == {
        (a, b, WorkItemRelationType.BLOCKS.value),
        (b, a, WorkItemRelationType.BLOCKED_BY.value),
    }


async def test_remove_deletes_both_legs(maker):
    a, b = await _item(maker, COMPANY_A, "a"), await _item(maker, COMPANY_A, "b")
    async with _client(maker) as c:
        rel_id = (await c.post(_url(a), json=_body(b))).json()["id"]
        resp = await c.delete(f"{_url(a)}/{rel_id}", params={"company_id": str(COMPANY_A)})
    assert resp.status_code == 204, resp.text
    assert await _rows(maker) == []


async def test_forged_company_and_creator_fields_are_ignored(maker):
    a, b = await _item(maker, COMPANY_A, "a"), await _item(maker, COMPANY_A, "b")
    forged = {
        "company_id": str(FORGED_COMPANY),
        "created_by_user_id": str(FORGED_USER),
        "created_by_agent_id": str(FORGED_AGENT),
    }
    async with _client(maker) as c:
        resp = await c.post(_url(a), json={**_body(b), **forged})
    assert resp.status_code == 201, resp.text
    rows = await _rows(maker)
    assert len(rows) == 2
    assert {r.company_id for r in rows} == {COMPANY_A}
    assert {r.created_by_user_id for r in rows} == {USER_A}
    assert {r.created_by_agent_id for r in rows} == {None}


async def test_remove_ignores_a_forged_company_and_actor(maker):
    a, b = await _item(maker, COMPANY_A, "a"), await _item(maker, COMPANY_A, "b")
    async with _client(maker) as c:
        rel_id = (await c.post(_url(a), json=_body(b))).json()["id"]
        params = {"company_id": str(FORGED_COMPANY), "actor_user_id": str(FORGED_USER)}
        resp = await c.delete(f"{_url(a)}/{rel_id}", params=params)
    assert resp.status_code == 204, resp.text
    assert await _rows(maker) == []


async def test_a_target_in_another_company_is_refused(maker):
    a, foreign = await _item(maker, COMPANY_A, "a"), await _item(maker, COMPANY_B, "theirs")
    async with _client(maker) as c:
        resp = await c.post(_url(a), json=_body(foreign))
    assert resp.status_code == 404
    assert await _rows(maker) == []


async def test_a_source_in_another_company_is_404(maker):
    mine, foreign = await _item(maker, COMPANY_A, "mine"), await _item(maker, COMPANY_B, "theirs")
    async with _client(maker) as c:
        resp = await c.post(_url(foreign), json=_body(mine))
    assert resp.status_code == 404
    assert await _rows(maker) == []


async def test_a_duplicate_is_409(maker):
    a, b = await _item(maker, COMPANY_A, "a"), await _item(maker, COMPANY_A, "b")
    async with _client(maker) as c:
        first = await c.post(_url(a), json=_body(b))
        again = await c.post(_url(a), json=_body(b))
    assert (first.status_code, again.status_code) == (201, 409)
    async with maker() as s:
        assert (await s.execute(select(func.count()).select_from(LLCWorkItemRelation))).scalar_one() == 2


async def test_removing_an_unknown_relation_is_404(maker):
    a = await _item(maker, COMPANY_A, "a")
    async with _client(maker) as c:
        resp = await c.delete(f"{_url(a)}/{uuid.uuid4()}", params={"company_id": str(COMPANY_A)})
    assert resp.status_code == 404
