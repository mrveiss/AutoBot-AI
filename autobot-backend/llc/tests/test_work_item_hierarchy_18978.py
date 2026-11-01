# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Work item parent/child rules on create and update, on a real (SQLite) database (#18978).

Rows that already break the rules are seeded straight into the table, bypassing the service, the
way legacy data got there. They must be refused as a *new* parent target but never rewritten.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkItemType as T
from llc.models.work_item import LLCWorkItem
from llc.services.work_item_hierarchy import (
    ALLOWED_PARENT_TYPES,
    HierarchyViolation,
    find_hierarchy_violations,
)
from llc.services.work_item_service import WorkItemService
from llc.tests import _e2e_harness as harness

pytestmark = pytest.mark.asyncio

MEMORY_URL = "sqlite+aiosqlite:///:memory:"
COMPANY = str(uuid.uuid4())
PROJECT = str(uuid.uuid4())


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    eng = create_async_engine(MEMORY_URL)  # canonical: ignore py-adhoc-db-engine (test-local engine)
    await harness.create_loop_schema(eng)
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        eng, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s
    await eng.dispose()


async def _make(session, kind, *, parent=None, project=None, company=COMPANY):
    return await WorkItemService().create(
        session,
        company_id=company,
        type=kind,
        title=f"{kind.value}",
        parent_id=str(parent.id) if parent else None,
        project_id=project,
    )


async def _legacy(session, kind, *, parent_id=None, project_id=None, company=COMPANY):
    """A row written outside the service, as pre-rule data was."""
    row = LLCWorkItem(
        id=uuid.uuid4(),
        company_id=uuid.UUID(company),
        type=kind,
        title="legacy",
        labels=[],
        identifier=f"OLD-{uuid.uuid4().hex[:8]}",
        parent_id=parent_id,
        project_id=uuid.UUID(project_id) if project_id else None,
    )
    session.add(row)
    await session.flush()
    return row


_PARENT_FOR = {
    T.EPIC: [],
    T.FEATURE: [T.EPIC],
    T.PBI: [T.EPIC, T.FEATURE],
    T.TASK: [T.PBI],
    T.SPIKE: [T.PBI],
    T.RISK: [T.PBI],
    T.BUG: [T.PBI, T.EPIC],
    T.SUBTASK: [T.TASK, T.BUG],
}


def test_the_table_is_the_issue_table():
    assert {k: sorted(v, key=str) for k, v in ALLOWED_PARENT_TYPES.items()} == {
        k: sorted(v, key=str) for k, v in _PARENT_FOR.items()
    }


@pytest.mark.parametrize("child", list(T))
@pytest.mark.parametrize("parent_kind", list(T))
async def test_every_child_parent_pair(session, child, parent_kind):
    parent = (
        await _make(session, parent_kind, project=PROJECT)
        if parent_kind is T.EPIC
        else await _legacy(session, parent_kind, project_id=PROJECT)
    )
    if parent_kind in _PARENT_FOR[child]:
        item = await _make(session, child, parent=parent, project=PROJECT if child is T.EPIC else None)
        assert item.parent_id == parent.id
    else:
        with pytest.raises(HierarchyViolation):
            await _make(session, child, parent=parent)


async def test_epic_requires_a_project(session):
    with pytest.raises(HierarchyViolation, match="requires a project_id"):
        await _make(session, T.EPIC)


async def test_parent_from_another_company_is_refused(session):
    foreign = await _make(session, T.EPIC, project=PROJECT, company=str(uuid.uuid4()))
    with pytest.raises(HierarchyViolation, match="not found in this company"):
        await _make(session, T.FEATURE, parent=foreign)


async def test_self_parent_is_refused(session):
    pbi = await _make(session, T.PBI)
    with pytest.raises(HierarchyViolation, match="own parent"):
        await WorkItemService().update(session, str(pbi.id), parent_id=str(pbi.id))


async def test_cycle_is_refused_and_the_walk_terminates(session):
    task = await _legacy(session, T.TASK)
    pbi = await _legacy(session, T.PBI, parent_id=task.id)  # legacy: a PBI under its own Task
    with pytest.raises(HierarchyViolation, match="cycle"):
        await WorkItemService().update(session, str(task.id), parent_id=str(pbi.id))


async def test_a_parent_chain_that_already_loops_is_refused_not_walked_forever(session):
    a = await _legacy(session, T.PBI)
    b = await _legacy(session, T.PBI, parent_id=a.id)
    a.parent_id = b.id
    await session.flush()
    with pytest.raises(HierarchyViolation, match="cyclic or deeper"):
        await _make(session, T.TASK, parent=a)


async def test_child_inherits_the_parents_project(session):
    epic = await _make(session, T.EPIC, project=PROJECT)
    pbi = await _make(session, T.PBI, parent=epic)
    assert str(pbi.project_id) == PROJECT


async def test_child_cannot_name_a_different_project(session):
    epic = await _make(session, T.EPIC, project=PROJECT)
    with pytest.raises(HierarchyViolation, match="same project"):
        await _make(session, T.PBI, parent=epic, project=str(uuid.uuid4()))


async def test_reparenting_moves_the_whole_subtree(session):
    other = str(uuid.uuid4())
    epic_a = await _make(session, T.EPIC, project=PROJECT)
    epic_b = await _make(session, T.EPIC, project=other)
    pbi = await _make(session, T.PBI, parent=epic_a)
    task = await _make(session, T.TASK, parent=pbi)
    sub = await _make(session, T.SUBTASK, parent=task)
    await WorkItemService().update(session, str(pbi.id), parent_id=str(epic_b.id))
    for row in (pbi, task, sub):
        await session.refresh(row)
        assert str(row.project_id) == other
    assert pbi.parent_id == epic_b.id


async def test_update_that_leaves_parent_alone_works_on_an_invalid_row(session):
    epic_proj = str(uuid.uuid4())
    epic = await _make(session, T.EPIC, project=epic_proj)
    bad = await _legacy(session, T.TASK, parent_id=epic.id, project_id=PROJECT)  # wrong type, wrong project
    updated = await WorkItemService().update(session, str(bad.id), title="renamed")
    assert updated.title == "renamed"
    assert updated.parent_id == epic.id and str(updated.project_id) == PROJECT
    # passing the unchanged parent back (a form that resends every field) is also not a re-check
    await WorkItemService().update(session, str(bad.id), parent_id=str(epic.id), title="again")


async def test_the_read_only_report_names_invalid_rows_and_changes_nothing(session):
    epic = await _make(session, T.EPIC, project=PROJECT)
    bad = await _legacy(session, T.TASK, parent_id=epic.id, project_id=PROJECT)
    no_project = await _legacy(session, T.EPIC)
    found = {v["id"]: v["reason"] for v in await find_hierarchy_violations(session, COMPANY)}
    assert set(found) == {str(bad.id), str(no_project.id)}
    await session.refresh(bad)
    assert bad.parent_id == epic.id
