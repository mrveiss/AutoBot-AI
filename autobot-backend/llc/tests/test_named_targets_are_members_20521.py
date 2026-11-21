# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A named assignee or handoff target stays allowed in the body, and must belong to the item's company (#20521)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from llc.api import _named_agent
from llc.api import work_items as work_items_api
from llc.models.enums import WorkItemType

_ORG = uuid.uuid4()
_ME = uuid.uuid4()
_OUTSIDER = str(uuid.uuid4())  # a real user id that is not a member of the company
_FOREIGN_AGENT = str(uuid.uuid4())


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(org_id=_ORG, user_id=_ME, is_platform_admin=False)


def _session(agent_company: uuid.UUID | None = None) -> AsyncMock:
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=agent_company))
    return session


def _members(*, member: bool):
    return patch.object(_named_agent, "is_company_member", AsyncMock(return_value=member))


def _service() -> MagicMock:
    item = SimpleNamespace(id=uuid.uuid4(), company_id=_ORG)
    return MagicMock(
        get=AsyncMock(return_value=item), create=AsyncMock(return_value=item), update=AsyncMock(return_value=item)
    )


@pytest.mark.asyncio
async def test_a_non_member_assignee_is_refused_on_create_and_never_reaches_the_service() -> None:
    body = work_items_api.WorkItemCreate(
        company_id=str(_ORG), type=WorkItemType.TASK, title="t", assignee_user_id=_OUTSIDER
    )
    svc = _service()
    with _members(member=False), patch.object(work_items_api, "_service", return_value=svc):
        with pytest.raises(HTTPException) as refused:
            await work_items_api.create_work_item(body, _session(), {"id": str(_ME)}, _ctx())

    assert refused.value.status_code == 422 and "not a member" in refused.value.detail
    svc.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_non_member_assignee_is_refused_on_update() -> None:
    body = work_items_api.WorkItemUpdate(assignee_user_id=_OUTSIDER)
    svc = _service()
    with _members(member=False), patch.object(work_items_api, "_service", return_value=svc):
        with pytest.raises(HTTPException) as refused:
            await work_items_api.update_work_item("w", body, _session(), {"id": str(_ME)}, _ctx())

    assert refused.value.status_code == 422
    svc.update.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_company", [uuid.uuid4(), None], ids=["other-company", "unknown-agent"])
async def test_an_agent_assignee_of_another_company_is_refused_on_create_and_update(agent_company) -> None:
    svc = _service()
    create = work_items_api.WorkItemCreate(
        company_id=str(_ORG), type=WorkItemType.TASK, title="t", assignee_agent_id=_FOREIGN_AGENT
    )
    update = work_items_api.WorkItemUpdate(assignee_agent_id=_FOREIGN_AGENT)
    with patch.object(work_items_api, "_service", return_value=svc):
        for call in (
            work_items_api.create_work_item(create, _session(agent_company), {"id": str(_ME)}, _ctx()),
            work_items_api.update_work_item("w", update, _session(agent_company), {"id": str(_ME)}, _ctx()),
        ):
            with pytest.raises(HTTPException) as refused:
                await call
            assert refused.value.status_code == 422
    svc.create.assert_not_awaited()
    svc.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_handoff_to_an_agent_of_another_company_is_refused() -> None:
    body = work_items_api.HandoffToAgentRequest(target_agent_id=_FOREIGN_AGENT, human_notes="n")
    handoff = MagicMock(human_to_agent=AsyncMock())
    with (
        patch.object(work_items_api, "_service", return_value=_service()),
        patch.object(work_items_api, "_handoff_service", return_value=handoff),
    ):
        with pytest.raises(HTTPException) as refused:
            await work_items_api.handoff_to_agent("w", body, _session(uuid.uuid4()), {"id": str(_ME)}, _ctx())

    assert refused.value.status_code == 422
    handoff.human_to_agent.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_member_assignee_and_a_company_agent_stay_allowed() -> None:
    session = _session(_ORG)  # the named agent's company is this one
    with _members(member=True):
        await _named_agent.require_member_targets(session, _ORG, str(_ME), str(uuid.uuid4()))
        await _named_agent.require_member_targets(session, _ORG)  # nothing named, nothing to check
