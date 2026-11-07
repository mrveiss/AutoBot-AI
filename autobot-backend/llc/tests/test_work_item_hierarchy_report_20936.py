# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The violation report returns a stable code per rule and is bounded in SQL (#20936)."""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkItemType as T
from llc.models.work_item import LLCWorkItem
from llc.services import work_item_hierarchy as wih
from llc.tests import _e2e_harness as harness
from llc.tests.test_work_item_hierarchy_18978 import COMPANY, PROJECT, _ensure_project, _legacy, _make

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    await harness.create_loop_schema(eng)
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        eng, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        await _ensure_project(s, COMPANY, PROJECT)
        yield s
    await eng.dispose()


async def _codes(session, **kw):
    rows, truncated = await wih.find_hierarchy_violations(session, COMPANY, **kw)
    return {r["identifier"]: r["code"] for r in rows}, truncated


async def test_each_rule_gets_its_stable_code(session):
    epic = await _make(session, T.EPIC, project=PROJECT)
    wrong_type = await _legacy(session, T.TASK, parent_id=epic.id, project_id=PROJECT)
    other_project = await _legacy(session, T.PBI, parent_id=epic.id, project_id=str(uuid.uuid4()))
    no_project = await _legacy(session, T.EPIC)
    orphan = await _legacy(session, T.TASK, parent_id=uuid.uuid4(), project_id=PROJECT)
    a = await _legacy(session, T.PBI, project_id=PROJECT)
    b = await _legacy(session, T.PBI, parent_id=a.id, project_id=PROJECT)
    a.parent_id = b.id
    await session.flush()

    codes, truncated = await _codes(session)
    assert truncated is False
    assert codes[wrong_type.identifier] == wih.PARENT_TYPE
    assert codes[other_project.identifier] == wih.PROJECT_MISMATCH
    assert codes[no_project.identifier] == wih.PROJECT_REQUIRED
    assert codes[orphan.identifier] == wih.PARENT_MISSING
    assert codes[a.identifier] == codes[b.identifier] == wih.CYCLE
    assert epic.identifier not in codes


async def test_a_valid_tree_and_another_companys_rows_are_not_reported(session):
    epic = await _make(session, T.EPIC, project=PROJECT)
    await _make(session, T.PBI, parent=epic)
    await _legacy(session, T.EPIC, company=str(uuid.uuid4()))
    assert await _codes(session) == ({}, False)


async def test_the_report_stops_at_the_limit_and_says_so(session):
    for _ in range(5):
        await _legacy(session, T.EPIC)
    codes, truncated = await _codes(session, limit=3)
    assert len(codes) == 3 and truncated is True
    codes, truncated = await _codes(session, limit=5)
    assert len(codes) == 5 and truncated is False


def test_the_limit_is_an_env_backed_constant():
    assert wih.HIERARCHY_VIOLATIONS_LIMIT == 500


# --- cycle shapes, PostgreSQL rendering, and the filter/label contract (#20936 review) ---------------


async def _reported(session):
    rows, _ = await wih.find_hierarchy_violations(session, COMPANY)
    ids = [r["identifier"] for r in rows]
    assert len(ids) == len(set(ids)), "an item is reported once"
    return {r["identifier"]: r["code"] for r in rows}


async def test_a_self_parent_is_a_cycle_reported_once(session):
    row = await _legacy(session, T.PBI, project_id=PROJECT)
    row.parent_id = row.id
    await session.flush()
    assert (await _reported(session)) == {row.identifier: wih.CYCLE}


async def test_a_tail_pointing_into_a_cycle_is_a_cycle_too(session):
    a = await _legacy(session, T.PBI, project_id=PROJECT)
    b = await _legacy(session, T.PBI, parent_id=a.id, project_id=PROJECT)
    a.parent_id = b.id
    tail = await _legacy(session, T.TASK, parent_id=a.id, project_id=PROJECT)
    await session.flush()
    codes = await _reported(session)
    assert codes[a.identifier] == codes[b.identifier] == wih.CYCLE
    assert codes[tail.identifier] == wih.CYCLE  # its chain never ends: same verdict as the in-memory walk


async def test_a_chain_deeper_than_the_limit_is_reported(session):
    nodes = [await _legacy(session, T.EPIC, project_id=PROJECT)]
    for _ in range(wih.MAX_HIERARCHY_DEPTH + 2):
        nodes.append(await _legacy(session, T.EPIC, parent_id=nodes[-1].id, project_id=PROJECT))
    codes = await _reported(session)
    assert codes[nodes[-1].identifier] == wih.CYCLE
    assert nodes[1].identifier not in {i for i, c in codes.items() if c == wih.CYCLE}  # shallow rows are not


async def test_a_parent_in_another_company_is_missing_and_never_walked(session):
    other = str(uuid.uuid4())
    foreign = await _legacy(session, T.EPIC, project_id=PROJECT, company=other)
    foreign.parent_id = foreign.id  # a cycle on the other side must not leak in
    child = await _legacy(session, T.TASK, parent_id=foreign.id, project_id=PROJECT)
    await session.flush()
    assert (await _reported(session)) == {child.identifier: wih.PARENT_MISSING}


def test_the_statement_renders_for_postgresql():
    from sqlalchemy.dialects import postgresql

    sql = str(wih.violations_statement(uuid.uuid4(), 10).compile(dialect=postgresql.dialect()))
    assert "WITH RECURSIVE hierarchy_walk" in sql
    assert "UNION ALL" in sql
    assert " AS depth" in sql and "%(param_1)s AS depth" in sql  # the typed literal(1) seed
    assert "llc_work_items.id IN (SELECT hierarchy_walk.start" in sql.replace("\n", " ")
    assert "IS DISTINCT FROM" in sql


def _row(kind, parent_id=None, project=None):
    return LLCWorkItem(id=uuid.uuid4(), type=kind, parent_id=parent_id, project_id=project)


_P1, _P2 = uuid.uuid4(), uuid.uuid4()
_PARENT = LLCWorkItem(id=uuid.uuid4(), type=T.EPIC, project_id=_P1)
_CASES = [
    (_row(T.EPIC, project=_P1), None, True, wih.CYCLE),
    (_row(T.TASK, _PARENT.id, _P1), None, False, wih.PARENT_MISSING),
    (_row(T.TASK, _PARENT.id, _P1), _PARENT, False, wih.PARENT_TYPE),
    (_row(T.PBI, _PARENT.id, _P2), _PARENT, False, wih.PROJECT_MISMATCH),
    (_row(T.EPIC, project=None), None, False, wih.PROJECT_REQUIRED),
    (_row(T.PBI, _PARENT.id, None), _PARENT, False, wih.PROJECT_MISMATCH),  # parent has a project, row has none
]


@pytest.mark.parametrize("row,parent,in_cycle,code", _CASES)
async def test_every_row_the_filter_matches_gets_the_right_code(session, row, parent, in_cycle, code):
    """Seed the case, ask SQL (``_violation_filter``) and Python (``_row_violation``): both must agree."""
    seeded = []
    if parent is not None or row.parent_id is not None:
        seeded.append(await _legacy(session, parent.type if parent else T.EPIC, project_id=str(_P1)))
    pid = seeded[0].id if parent is not None else (row.parent_id if code == wih.PARENT_MISSING else None)
    item = await _legacy(session, row.type, parent_id=pid, project_id=str(row.project_id) if row.project_id else None)
    if in_cycle:
        item.parent_id = item.id
        await session.flush()
    rows, _ = await wih.find_hierarchy_violations(session, COMPANY)
    assert {r["identifier"]: r["code"] for r in rows}[item.identifier] == code
    assert wih._row_violation(item, seeded[0] if parent is not None else None, in_cycle)[0] == code
