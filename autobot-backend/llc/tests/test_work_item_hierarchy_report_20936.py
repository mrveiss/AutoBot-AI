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
