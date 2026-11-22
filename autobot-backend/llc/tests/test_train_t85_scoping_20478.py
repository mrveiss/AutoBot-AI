# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Board moves, subtree moves and handoffs stay inside the company; backfill and import keep data (#20478, #18978)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.api import _handoff_identity as identity
from llc.models.enums import WorkItemStatus
from llc.models.enums import WorkItemType as T
from llc.models.sprint import LLCProject
from llc.models.work_item import LLCWorkItem
from llc.services import project_backfill
from llc.services.board import BoardService
from llc.services.portability import PortabilityService
from llc.services.work_item_hierarchy import move_subtree_to_project
from llc.services.work_item_service import WorkItemService
from llc.tests import _e2e_harness as harness

COMPANY, OTHER = uuid.uuid4(), uuid.uuid4()


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    await harness.create_loop_schema(eng)
    maker = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        eng, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as s:
        yield s
    await eng.dispose()


async def _row(session, company, *, parent=None, project=None, status="backlog") -> LLCWorkItem:
    row = LLCWorkItem(
        id=uuid.uuid4(), company_id=company, type=T.TASK, title="t", labels=[], parent_id=parent,
        identifier=f"X-{uuid.uuid4().hex[:8]}", project_id=project, status=status,
    )  # fmt: skip
    session.add(row)
    await session.flush()
    return row


async def _project(session, company) -> uuid.UUID:
    pid = uuid.uuid4()
    session.add(LLCProject(id=pid, company_id=company, name="P"))
    await session.flush()
    return pid


# 1. board move ------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_board_move_scopes_the_transition_to_the_boards_company() -> None:
    column = SimpleNamespace(id=uuid.uuid4(), name="Done", wip_limit=None, status_filter=["done"])
    board = SimpleNamespace(id=uuid.uuid4(), company_id=COMPANY, project_id=None, sprint_id=None)
    session = AsyncMock()
    session.execute.side_effect = [
        MagicMock(scalar_one_or_none=MagicMock(return_value=board)),
        MagicMock(scalar_one_or_none=MagicMock(return_value=column)),
    ]
    transition = AsyncMock()
    svc = BoardService(activity_log=MagicMock())
    with patch.object(WorkItemService, "transition_status", transition), patch.object(svc, "_publish_board_event"):
        await svc.move_item(session, str(board.id), str(uuid.uuid4()), str(column.id))
    assert transition.await_args.kwargs["company_id"] == str(COMPANY)


@pytest.mark.asyncio
async def test_another_companys_item_is_not_found_and_its_status_is_not_named(session) -> None:
    foreign = await _row(session, OTHER, status="done")
    with pytest.raises(ValueError, match="not found") as refused:
        await WorkItemService().transition_status(
            session, str(foreign.id), WorkItemStatus.BACKLOG, company_id=str(COMPANY)
        )
    assert "done" not in str(refused.value)


# 2. handoff authority -----------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(("role", "allowed"), [("member", False), ("owner", True), ("lead", True), ("admin", True)])
async def test_only_an_owner_lead_or_admin_hands_off_an_agents_item(role: str, allowed: bool) -> None:
    agent = uuid.uuid4()
    item = SimpleNamespace(assignee_agent_id=agent, company_id=COMPANY)
    user = {"id": str(uuid.uuid4())}
    with (
        patch.object(identity, "is_interactive_human", return_value=True),
        patch.object(identity, "resolve_actor_role", AsyncMock(return_value=role)),
    ):
        if allowed:
            assert await identity.handing_off_agent(AsyncMock(), item, user) == str(agent)
        else:
            with pytest.raises(HTTPException) as refused:
                await identity.handing_off_agent(AsyncMock(), item, user)
            assert refused.value.status_code == 403


# 3. subtree move ----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_subtree_move_never_touches_another_companys_child(session) -> None:
    root = await _row(session, COMPANY)
    mine = await _row(session, COMPANY, parent=root.id)
    theirs = await _row(session, OTHER, parent=root.id)
    target = await _project(session, COMPANY)
    assert await move_subtree_to_project(session, root.id, target, COMPANY) == 1
    await session.refresh(mine)
    await session.refresh(theirs)
    assert (mine.project_id, theirs.project_id) == (target, None)


# 4. backfill --------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_backfill_keeps_a_project_an_item_got_after_planning(session) -> None:
    default = await _project(session, COMPANY)
    planned = await _row(session, COMPANY)
    raced = await _row(session, COMPANY)
    kept = await _project(session, COMPANY)
    plan = {planned.id: (default, False), raced.id: (default, False)}
    raced.project_id = kept
    await session.flush()
    with patch.object(project_backfill, "_plan_for", AsyncMock(return_value=(plan, set(), None))):
        result = await project_backfill.apply_project_backfill(session, COMPANY)
    await session.refresh(planned)
    await session.refresh(raced)
    assert (planned.project_id, raced.project_id) == (default, kept)
    assert (result["updated"], result["skipped_already_in_project"]) == (1, 1)


# 5. import ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_exported_seed_items_survive_an_import() -> None:
    item = SimpleNamespace(
        id=uuid.uuid4(), parent_id=None, project_id=None, sprint_id=None, goal_id=None, type="epic",
        title="Seed", description=None, status="backlog", priority="medium", assignee_agent_id=None,
        assignee_user_id=None, created_at=None,
    )  # fmt: skip
    session = AsyncMock()
    session.execute = AsyncMock(return_value=[(item,)])
    svc = PortabilityService(session=session)
    payload = {"seed_work_items": await svc._export_seed_items(str(COMPANY))}
    created = {"work_items": []}
    skipped = {"work_items": []}
    with patch.object(svc, "_import_work_item", AsyncMock(return_value=uuid.uuid4())) as imported:
        await svc._import_seed_items(payload, COMPANY, {"p": "proj"}, created, skipped, [])
    assert imported.await_count == 1 and len(created["work_items"]) == 1 and not skipped["work_items"]
