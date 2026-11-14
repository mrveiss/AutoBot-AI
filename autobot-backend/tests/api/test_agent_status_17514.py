# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /agents/status reports what it measures and nothing else (#17514).

Every card read "0 Tasks / 0s Uptime / N/A" and the header "0 active", because the service
filled each activity field with a constant 0 and every unpaused node with "idle". Unmeasured
fields are now None, and each card names its company, so five agents called "CEO" are five
visibly different cards.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.agent_org import router
from api.agent_org_visibility import AgentVisibility, get_agent_visibility
from api.user_management.dependencies import get_current_user, get_db_session, get_optional_db_session

# Registers the SQLite shims for JSONB / UUID (see test_agent_org_tenant_scope.py).
from llc.tests import _e2e_harness as harness  # noqa: F401
from models.agent_org import AgentOrgNode
from user_management.models.base import Base
from user_management.models.organization import Organization

ACME = uuid.uuid4()
GLOBEX = uuid.uuid4()


@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [AgentOrgNode.__table__, Organization.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    made = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with made() as session:
        session.add_all(
            [Organization(id=ACME, name="Acme", slug="acme"), Organization(id=GLOBEX, name="Globex", slug="globex")]
        )
        await session.flush()
        for agent_id, company, paused in [
            ("ceo-acme", ACME, None),
            ("ceo-globex", GLOBEX, None),
            ("paused", ACME, "active"),
            ("platform", None, None),
        ]:
            session.add(
                AgentOrgNode(
                    id=uuid.uuid4(),
                    agent_id=agent_id,
                    name="CEO" if agent_id.startswith("ceo") else agent_id,
                    org_role="ceo",
                    company_id=company,
                    pre_pause_status=paused,
                )
            )
        await session.commit()
    yield made
    await engine.dispose()


@pytest.fixture(autouse=True)
def _no_redis_feeds(monkeypatch):  # noqa: ANN001, ANN202
    """Keep these tests off the analytics Redis (#21270): feeds are unreadable (None) unless a test says otherwise."""
    from services import agent_org_service

    async def unreadable(ids):  # noqa: ANN001, ANN202
        return {i: None for i in ids}

    monkeypatch.setattr(agent_org_service, "get_agent_feeds", unreadable)


ADMIN = AgentVisibility(is_platform_admin=True)
MEMBER_OF_ACME = AgentVisibility(is_platform_admin=False, company_ids=frozenset({ACME}))


async def _status(factory, visibility: AgentVisibility = ADMIN, *, postgres: bool = True) -> list[dict]:  # noqa: ANN001
    """GET /agents/status; ``postgres=False`` hands the route no session, so it takes the registry fallback."""
    app = FastAPI()
    app.include_router(router, prefix="/agents")

    async def _session():  # noqa: ANN202
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _session
    app.dependency_overrides[get_optional_db_session] = _session if postgres else (lambda: None)
    app.dependency_overrides[get_agent_visibility] = lambda: visibility
    app.dependency_overrides[get_current_user] = lambda: {"user_id": str(uuid.uuid4())}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return (await client.get("/agents/status")).json()["agents"]


@pytest.mark.asyncio
async def test_unmeasured_activity_is_not_reported_as_zero(factory):  # noqa: ANN001
    by_id = {a["id"]: a for a in await _status(factory)}
    for agent in by_id.values():
        assert agent["tasksCompleted"] is None
        assert agent["uptime"] is None
        assert agent["successRate"] is None
    assert by_id["ceo-acme"]["status"] is None  # not "idle": nobody measured it
    assert by_id["paused"]["status"] == "paused"  # the one state the registry does know
    for agent in by_id.values():  # the store is unreadable here, so the feeds are not reported either
        assert agent["recentTasks"] is None and agent["activityTimeline"] is None
        assert agent["activityWindowStart"] is None


@pytest.mark.asyncio
async def test_two_ceos_in_different_companies_both_appear_and_are_told_apart(factory):  # noqa: ANN001
    ceos = [a for a in await _status(factory) if a["name"] == "CEO"]
    # Contrast for any future de-duplication: same name and role, different companies, both stay.
    assert sorted(a["companyName"] for a in ceos) == ["Acme", "Globex"]
    assert {a["companyId"] for a in ceos} == {str(ACME), str(GLOBEX)}


@pytest.mark.asyncio
async def test_a_platform_agent_has_no_company(factory):  # noqa: ANN001
    platform = next(a for a in await _status(factory) if a["id"] == "platform")
    assert platform["companyId"] is None and platform["companyName"] is None


@pytest.mark.asyncio
async def test_a_member_sees_neither_another_companys_agent_nor_its_name(factory):  # noqa: ANN001
    agents = await _status(factory, MEMBER_OF_ACME)
    assert {a["id"] for a in agents} == {"ceo-acme", "paused", "platform"}
    assert "Globex" not in {a["companyName"] for a in agents}
    assert str(GLOBEX) not in {a["companyId"] for a in agents}


@pytest.mark.asyncio
async def test_a_soft_deleted_company_is_not_named(factory):  # noqa: ANN001
    async with factory() as session:
        (await session.get(Organization, GLOBEX)).soft_delete()
        await session.commit()
    by_id = {a["id"]: a for a in await _status(factory)}
    assert by_id["ceo-globex"]["companyName"] is None
    assert by_id["ceo-acme"]["companyName"] == "Acme"  # contrast: a live company is still named


@pytest.mark.asyncio
async def test_unreadable_feeds_are_none_on_the_wire_and_measured_empty_is_a_list(factory, monkeypatch):  # noqa: ANN001
    """#21270: the status response carries None for an unmeasured feed and [] only for a measured one."""
    from services import agent_org_service

    async def feeds(ids):  # noqa: ANN001, ANN202
        return {
            i: ({"recentTasks": [], "activityTimeline": [], "windowStart": 1} if i == "paused" else None) for i in ids
        }

    monkeypatch.setattr(agent_org_service, "get_agent_feeds", feeds)
    by_id = {a["id"]: a for a in await _status(factory)}
    assert by_id["ceo-acme"]["recentTasks"] is None and by_id["ceo-acme"]["activityTimeline"] is None
    assert by_id["paused"]["recentTasks"] == [] and by_id["paused"]["activityTimeline"] == []


def _patch_fallback_feeds(monkeypatch, feed_for):  # noqa: ANN001, ANN202
    """Patch the helper where the route looks it up; returns the list of id-lists the route asked for."""
    from api import agent_org

    asked: list[list[str]] = []

    async def feeds(ids):  # noqa: ANN001, ANN202
        asked.append(list(ids))
        return {i: feed_for(i) for i in ids}

    monkeypatch.setattr(agent_org, "get_agent_feeds", feeds)
    return asked


@pytest.mark.asyncio
async def test_fallback_route_reports_an_unreadable_store_as_none(factory, monkeypatch):  # noqa: ANN001
    asked = _patch_fallback_feeds(monkeypatch, lambda i: None)
    agents = await _status(factory, postgres=False)
    assert agents and asked == [[a["id"] for a in agents]]  # the route fed its own registry agents to the helper
    for agent in agents:
        assert agent["recentTasks"] is None and agent["activityTimeline"] is None
        assert agent["activityWindowStart"] is None


@pytest.mark.asyncio
async def test_fallback_route_reports_a_measured_empty_history_as_empty_lists(factory, monkeypatch):  # noqa: ANN001
    _patch_fallback_feeds(monkeypatch, lambda i: {"recentTasks": [], "activityTimeline": [], "windowStart": 1234})
    agents = await _status(factory, postgres=False)
    assert agents
    for agent in agents:
        assert agent["recentTasks"] == [] and agent["activityTimeline"] == []
        assert agent["activityWindowStart"] == 1234


@pytest.mark.asyncio
async def test_fallback_route_carries_the_helpers_items_per_agent(factory, monkeypatch):  # noqa: ANN001
    def feed(agent_id: str) -> dict:
        task = {"id": f"t-{agent_id}", "name": "Deploy", "status": "completed", "completedAt": 5}
        bar = {"task": "Deploy", "type": "working", "startPercent": 1.0, "widthPercent": 2.0, "duration": 3}
        return {"recentTasks": [task], "activityTimeline": [bar], "windowStart": 99}

    _patch_fallback_feeds(monkeypatch, feed)
    agents = await _status(factory, postgres=False)
    assert agents
    for agent in agents:
        assert [t["id"] for t in agent["recentTasks"]] == [f"t-{agent['id']}"]
        assert agent["activityTimeline"][0]["task"] == "Deploy" and agent["activityWindowStart"] == 99
