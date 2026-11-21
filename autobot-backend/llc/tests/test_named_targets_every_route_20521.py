# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every body-supplied person or agent target is checked as a member of the record's company (#20521).

Request-changes ``return_to_agent_id``, routine ``assignee_agent_id``, goal ``owner_agent_id``, project
``lead_agent_id`` / ``lead_user_id`` and co-worker ids. A forged target (an agent of another company, a person who
is not a member, a malformed id) is refused with 422 before anything is written.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from llc.api import _named_agent
from llc.api import goals as goals_api
from llc.api import routines as routines_api
from llc.api import sprints as sprints_api
from llc.api import work_items as work_items_api
from llc.models.goal import GoalLevel

_ORG = uuid.uuid4()
_ME = uuid.uuid4()
_FOREIGN = uuid.uuid4()  # an agent / user of some other company


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(org_id=_ORG, user_id=_ME, is_platform_admin=False)


def _result(row=None, agent_found: bool = False) -> MagicMock:
    """One query result: ``scalar_one_or_none`` is *row*; the agent-in-company lookup finds a row iff *agent_found*."""
    found = object() if agent_found else None
    return MagicMock(
        scalar_one_or_none=MagicMock(return_value=row),
        all=MagicMock(return_value=[found] if found else []),
    )


def _session(*results: MagicMock) -> AsyncMock:
    session = AsyncMock()
    session.execute.side_effect = list(results)
    return session


def _not_members():
    return patch.object(_named_agent, "is_company_member", AsyncMock(return_value=False))


async def _refused(call) -> HTTPException:
    with pytest.raises(HTTPException) as refused:
        await call
    assert refused.value.status_code == 422
    return refused.value


# -- review/request-changes ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("target", [str(_FOREIGN), "not-a-uuid"], ids=["foreign-agent", "malformed"])
async def test_request_changes_refuses_a_return_to_agent_outside_the_company(target) -> None:
    item = SimpleNamespace(company_id=_ORG)
    svc = MagicMock(get=AsyncMock(return_value=item))
    handoff = MagicMock(request_changes=AsyncMock())
    body = work_items_api.ReviewChangesRequest(change_request="redo", return_to_agent_id=target)
    user = {"id": str(_ME), "user_id": str(_ME), "auth_method": "session"}
    with (
        patch.object(work_items_api, "_service", return_value=svc),
        patch.object(work_items_api, "_handoff_service", return_value=handoff),
    ):
        await _refused(work_items_api.review_request_changes("w", body, _session(_result()), user, _ctx()))

    handoff.request_changes.assert_not_awaited()


# -- routines ---------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_routine_refuses_an_assignee_agent_of_another_company_on_create_and_update() -> None:
    svc = MagicMock(
        create=AsyncMock(), update=AsyncMock(), get=AsyncMock(return_value=SimpleNamespace(company_id=_ORG))
    )
    create = routines_api.RoutineCreate(name="r", cron_schedule="* * * * *", assignee_agent_id=_FOREIGN)
    update = routines_api.RoutineUpdate(assignee_agent_id=_FOREIGN)
    with patch.object(routines_api, "_service", return_value=svc):
        await _refused(routines_api.create_routine(_ORG, create, _session(_result()), {"id": str(_ME)}, _ctx()))
        await _refused(routines_api.update_routine(uuid.uuid4(), update, _session(_result()), {"id": str(_ME)}, _ctx()))

    svc.create.assert_not_awaited()
    svc.update.assert_not_awaited()


# -- goals ----------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_goal_refuses_an_owner_agent_of_another_company_on_create_and_update() -> None:
    svc = MagicMock(
        create=AsyncMock(), update=AsyncMock(), get=AsyncMock(return_value=SimpleNamespace(company_id=_ORG))
    )
    create = goals_api.GoalCreate(company_id=str(_ORG), title="g", level=GoalLevel.VISION, owner_agent_id="forged-slug")
    update = goals_api.GoalUpdate(owner_agent_id=str(_FOREIGN))
    with patch.object(goals_api, "_svc", return_value=svc):
        await _refused(goals_api.create_goal(create, _session(_result()), {"id": str(_ME)}, _ctx()))
        await _refused(goals_api.update_goal(uuid.uuid4(), update, _session(_result()), {"id": str(_ME)}, _ctx()))

    svc.create.assert_not_awaited()
    svc.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_goal_owner_may_be_a_company_agent_by_slug_or_id() -> None:
    session = _session(_result(agent_found=True), _result(agent_found=True))
    await _named_agent.require_member_targets(session, _ORG, None, "agent-slug", slug_ok=True)
    await _named_agent.require_member_targets(session, _ORG, None, str(uuid.uuid4()), slug_ok=True)


# -- projects (lead_agent_id, lead_user_id) --------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["lead_agent_id", "lead_user_id"])
async def test_a_project_refuses_a_lead_outside_the_company_on_create_and_update(field) -> None:
    program = SimpleNamespace(company_id=_ORG)
    project = SimpleNamespace(company_id=_ORG)
    create = sprints_api.ProjectCreate(company_id=_ORG, name="p", **{field: _FOREIGN})
    update = sprints_api.ProjectUpdate(**{field: _FOREIGN})
    with _not_members():
        await _refused(
            sprints_api.create_project(
                uuid.uuid4(), create, _session(_result(program), _result()), {"id": str(_ME)}, _ctx()
            )
        )
        await _refused(
            sprints_api.update_project(
                uuid.uuid4(), update, _session(_result(project), _result()), {"id": str(_ME)}, _ctx()
            )
        )


# -- co-worker -----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_coworker_outside_the_company_is_refused_before_the_service() -> None:
    svc = MagicMock(get=AsyncMock(return_value=SimpleNamespace(company_id=_ORG)), enable_coworking=AsyncMock())
    body = work_items_api.CoworkerRequest(co_worker_type="agent", co_worker_agent_id=str(_FOREIGN))
    user = {"id": str(_ME), "user_id": str(_ME)}
    with patch.object(work_items_api, "_service", return_value=svc):
        await _refused(work_items_api.set_coworker("w", body, _session(_result()), user, _ctx()))

    svc.enable_coworking.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_slug_is_refused_unless_the_column_takes_one_and_an_ambiguous_reference_names_nobody() -> None:
    session = _session(_result(agent_found=True))
    assert await _named_agent.agent_in_company(session, _ORG, "agent-slug") is False  # strict: UUID columns
    session.execute.assert_not_awaited()  # refused before any query, so never a 500 on the write
    two_rows = MagicMock(all=MagicMock(return_value=[("a", "x"), ("b", "x")]))
    assert await _named_agent.agent_in_company(_session(two_rows), _ORG, str(uuid.uuid4())) is False
