# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A CEO's heartbeat is the owner's setting, and a CEO follows its org's position (#15907).

The model under test: the heartbeat is the optional, per-agent periodic schedule;
event wakes are separate (#19582) and not exercised here.

Every assertion about "is this agent on the heartbeat" reads ``heartbeat_enabled``
through the scheduler's own query (``_load_enabled_agents``), never ``status`` --
the two disagreed in #15907, and the scheduler only ever reads the former.

SQLite harness (``test_llc_org_chart``), like ``test_company_ceo_15770``: the
service writes here are dialect-neutral, so these run locally and in CI alike.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa

from llc.models.company import CompanyCreate, CompanyUpdate
from llc.models.enums import ActivityEventType, LLCAgentStatus
from llc.services.company import CompanyService
from llc.services.company_ceo import DORMANT_CEO_STATUS, CompanyCEOService, default_ceo_slug
from llc.services.controls_service import AgentNotFoundError, AgentNotSchedulableError, ControlsService
from llc.tests import test_llc_org_chart as _org_chart_harness
from models.agent_org import AgentOrgNode

_CRON = "*/5 * * * *"

# The SQLite harness fixtures, re-exported so pytest finds them in this module.
engine = _org_chart_harness.engine
session_factory = _org_chart_harness.session_factory


async def _create(session_factory, name: str, parent: uuid.UUID | None = None) -> uuid.UUID:  # noqa: ANN001
    async with session_factory() as session:
        org = await CompanyService(session).create(CompanyCreate(name=name, slug=name.lower(), parent_org_id=parent))
        await session.commit()
        return org.id


async def _ceo_nodes(session_factory, company_id: uuid.UUID) -> list[AgentOrgNode]:  # noqa: ANN001
    async with session_factory() as session:
        stmt = sa.select(AgentOrgNode).where(AgentOrgNode.agent_id == default_ceo_slug(company_id))
        return list((await session.execute(stmt)).scalars().all())


async def _designation(session_factory, company_id: uuid.UUID):  # noqa: ANN001, ANN202
    async with session_factory() as session:
        return await CompanyCEOService().designation(session, company_id)


async def _scheduler_enabled_slugs(session_factory) -> set[str]:  # noqa: ANN001
    """What ``heartbeat_scheduler.py``'s ``WHERE aon.heartbeat_enabled = true`` query returns."""
    from llc.scheduler import heartbeat_scheduler as hs

    with patch.object(hs, "get_async_session_factory", return_value=session_factory):
        rows = await hs.LLCHeartbeatScheduler()._load_enabled_agents()
    return {r["agent_id"] for r in rows}


async def _toggle(session_factory, company_id: uuid.UUID, slug: str, enabled: bool) -> dict:  # noqa: ANN001
    async with session_factory() as session:
        result = await ControlsService(activity_log=AsyncMock()).set_agent_heartbeat(
            session, str(company_id), slug, enabled, str(uuid.uuid4()), _CRON
        )
        await session.commit()
    return result


# ---------------------------------------------------------------------------
# Provisioning
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_new_company_ceo_has_its_heartbeat_off_by_default(session_factory):  # noqa: ANN001
    company_id = await _create(session_factory, "Acme")

    [ceo] = await _ceo_nodes(session_factory, company_id)
    assert ceo.heartbeat_enabled is False
    assert (await _designation(session_factory, company_id)).holder_agent_id == ceo.id
    assert ceo.agent_id not in await _scheduler_enabled_slugs(session_factory)


@pytest.mark.asyncio
async def test_a_new_sub_org_gets_no_ceo_at_all(session_factory):  # noqa: ANN001
    """Migration 090's end state for a non-company: no designation and no CEO node."""
    parent = await _create(session_factory, "Parent")
    sub = await _create(session_factory, "Sub", parent=parent)

    assert await _designation(session_factory, sub) is None
    assert await _ceo_nodes(session_factory, sub) == []
    # The control: the parent, a company, still has one.
    assert await _designation(session_factory, parent) is not None


# ---------------------------------------------------------------------------
# Moves
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_demoting_a_company_retires_its_ceo_and_keeps_the_node(session_factory):  # noqa: ANN001
    parent = await _create(session_factory, "Parent")
    company_id = await _create(session_factory, "Acme")
    [ceo] = await _ceo_nodes(session_factory, company_id)
    await _toggle(session_factory, company_id, ceo.agent_id, True)

    async with session_factory() as session:
        await CompanyService(session).update(company_id, CompanyUpdate(parent_org_id=parent))
        await session.commit()

    assert await _designation(session_factory, company_id) is None
    [node] = await _ceo_nodes(session_factory, company_id)
    assert node.id == ceo.id
    assert node.status == DORMANT_CEO_STATUS
    assert node.heartbeat_enabled is False
    assert node.agent_id not in await _scheduler_enabled_slugs(session_factory)


@pytest.mark.asyncio
async def test_promoting_back_reuses_the_retired_node(session_factory):  # noqa: ANN001
    parent = await _create(session_factory, "Parent")
    company_id = await _create(session_factory, "Acme")
    [original] = await _ceo_nodes(session_factory, company_id)
    async with session_factory() as session:
        await CompanyService(session).update(company_id, CompanyUpdate(parent_org_id=parent))
        await session.commit()

    async with session_factory() as session:
        await CompanyCEOService().sync_with_parent(session, company_id, None)
        await session.commit()

    nodes = await _ceo_nodes(session_factory, company_id)
    assert [n.id for n in nodes] == [original.id]
    assert nodes[0].status == LLCAgentStatus.AVAILABLE.value
    assert nodes[0].heartbeat_enabled is False
    assert (await _designation(session_factory, company_id)).holder_agent_id == original.id


async def _demote(session_factory, company_id: uuid.UUID, parent: uuid.UUID) -> None:  # noqa: ANN001
    async with session_factory() as session:
        await CompanyService(session).update(company_id, CompanyUpdate(parent_org_id=parent))
        await session.commit()


async def _set_status(session_factory, company_id: uuid.UUID, status: str) -> None:  # noqa: ANN001
    async with session_factory() as session:
        node = (
            await session.execute(sa.select(AgentOrgNode).where(AgentOrgNode.agent_id == default_ceo_slug(company_id)))
        ).scalar_one()
        node.status = status
        await session.commit()


@pytest.mark.asyncio
async def test_a_promotion_does_not_lift_a_stop_it_did_not_make(session_factory):  # noqa: ANN001
    """A node the budget watchdog set inactive is re-designated but stays stopped."""
    parent = await _create(session_factory, "Parent")
    company_id = await _create(session_factory, "Acme")
    await _demote(session_factory, company_id, parent)
    await _set_status(session_factory, company_id, DORMANT_CEO_STATUS)
    async with session_factory() as session:
        node = (
            await session.execute(sa.select(AgentOrgNode).where(AgentOrgNode.agent_id == default_ceo_slug(company_id)))
        ).scalar_one()
        node.pause_reason = None  # as the watchdog / 090 leave it: inactive, no demotion reason
        await session.commit()

    async with session_factory() as session:
        await CompanyCEOService().sync_with_parent(session, company_id, None)
        await session.commit()

    [node] = await _ceo_nodes(session_factory, company_id)
    assert node.status == DORMANT_CEO_STATUS
    assert (await _designation(session_factory, company_id)).holder_agent_id == node.id


@pytest.mark.asyncio
async def test_demoting_never_softens_a_termination(session_factory):  # noqa: ANN001
    parent = await _create(session_factory, "Parent")
    company_id = await _create(session_factory, "Acme")
    await _set_status(session_factory, company_id, LLCAgentStatus.TERMINATED.value)
    await _demote(session_factory, company_id, parent)
    async with session_factory() as session:
        await CompanyCEOService().sync_with_parent(session, company_id, None)
        await session.commit()

    [node] = await _ceo_nodes(session_factory, company_id)
    assert node.status == LLCAgentStatus.TERMINATED.value


@pytest.mark.asyncio
async def test_an_update_that_does_not_move_the_org_leaves_the_ceo_alone(session_factory):  # noqa: ANN001
    company_id = await _create(session_factory, "Acme")
    before = await _designation(session_factory, company_id)

    with patch.object(CompanyCEOService, "sync_with_parent", new=AsyncMock()) as sync:
        async with session_factory() as session:
            await CompanyService(session).update(company_id, CompanyUpdate(name="Acme Renamed"))
            await session.commit()

    sync.assert_not_awaited()
    after = await _designation(session_factory, company_id)
    assert (after.id, after.holder_agent_id) == (before.id, before.holder_agent_id)


# ---------------------------------------------------------------------------
# The heartbeat control
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enabling_puts_the_ceo_on_the_column_the_scheduler_reads(session_factory):  # noqa: ANN001
    company_id = await _create(session_factory, "Acme")
    slug = default_ceo_slug(company_id)

    result = await _toggle(session_factory, company_id, slug, True)
    assert result == {"agent_id": slug, "heartbeat_enabled": True, "heartbeat_cron": _CRON}
    assert slug in await _scheduler_enabled_slugs(session_factory)

    await _toggle(session_factory, company_id, slug, False)
    assert slug not in await _scheduler_enabled_slugs(session_factory)
    # Disabling keeps the cron, so re-enabling restores the same cadence.
    [ceo] = await _ceo_nodes(session_factory, company_id)
    assert ceo.heartbeat_cron == _CRON


@pytest.mark.asyncio
async def test_the_toggle_is_audited(session_factory):  # noqa: ANN001
    company_id = await _create(session_factory, "Acme")
    log = AsyncMock()
    async with session_factory() as session:
        await ControlsService(activity_log=log).set_agent_heartbeat(
            session, str(company_id), default_ceo_slug(company_id), True, "actor-1", _CRON
        )
    kwargs = log.record.await_args.kwargs
    assert kwargs["event_type"] == ActivityEventType.CONTROL_AGENT_HEARTBEAT_SET
    assert kwargs["actor_id"] == "actor-1"
    assert kwargs["before"]["heartbeat_enabled"] is False
    assert kwargs["after"]["heartbeat_enabled"] is True


@pytest.mark.asyncio
async def test_another_companys_agent_is_not_found(session_factory):  # noqa: ANN001
    """The UPDATE is scoped to the path's company: a foreign slug reads as missing."""
    acme = await _create(session_factory, "Acme")
    other = await _create(session_factory, "Other")
    with pytest.raises(AgentNotFoundError):
        await _toggle(session_factory, other, default_ceo_slug(acme), True)
    assert default_ceo_slug(acme) not in await _scheduler_enabled_slugs(session_factory)


@pytest.mark.asyncio
async def test_a_dormant_ceo_cannot_be_put_on_the_heartbeat(session_factory):  # noqa: ANN001
    parent = await _create(session_factory, "Parent")
    company_id = await _create(session_factory, "Acme")
    async with session_factory() as session:
        await CompanyService(session).update(company_id, CompanyUpdate(parent_org_id=parent))
        await session.commit()
    with pytest.raises(AgentNotSchedulableError):
        await _toggle(session_factory, company_id, default_ceo_slug(company_id), True)


# ---------------------------------------------------------------------------
# The route
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncIterator[httpx.AsyncClient]:  # noqa: ANN001
    from fastapi import FastAPI

    from api.user_management.dependencies import get_current_user
    from llc.api import controls
    from llc.deps import get_session

    app = FastAPI()
    app.include_router(controls.router, prefix="/api/llc")

    async def _session() -> AsyncIterator:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4())}
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_the_route_takes_a_ceo_slug_and_schedules_it(session_factory, client):  # noqa: ANN001
    """``ceo-<uuid>`` is not a UUID; a ``uuid.UUID`` path type answered 422."""
    from llc.api import controls

    company_id = await _create(session_factory, "Acme")
    slug = default_ceo_slug(company_id)
    url = f"/api/llc/companies/{company_id}/controls/agents/{slug}/heartbeat"
    with (
        patch.object(controls, "require_board_role", new=AsyncMock(return_value=str(uuid.uuid4()))),
        patch.object(controls, "schedule_heartbeat", new=AsyncMock(return_value=True)) as schedule,
        patch("llc.services.activity_log.LLCActivityLogService.record", new=AsyncMock()),
    ):
        resp = await client.put(url, json={"heartbeat_enabled": True})

    assert resp.status_code == 200, resp.text
    assert resp.json()["scheduled"] is True
    schedule.assert_awaited_once_with(slug, controls.DEFAULT_HEARTBEAT_CRON)
    assert slug in await _scheduler_enabled_slugs(session_factory)


@pytest.mark.asyncio
async def test_the_route_refuses_a_non_board_member(session_factory, client):  # noqa: ANN001
    from fastapi import HTTPException

    from llc.api import controls

    company_id = await _create(session_factory, "Acme")
    slug = default_ceo_slug(company_id)
    url = f"/api/llc/companies/{company_id}/controls/agents/{slug}/heartbeat"
    denied = AsyncMock(side_effect=HTTPException(status_code=403, detail="no"))
    with patch.object(controls, "require_board_role", new=denied):
        resp = await client.put(url, json={"heartbeat_enabled": True})

    assert resp.status_code == 403
    assert slug not in await _scheduler_enabled_slugs(session_factory)
