# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A projectless item whose child already sits in another project is a conflict: listed, never filled (#20930)."""

import uuid

from llc.services.project_backfill import apply_project_backfill, preview_project_backfill
from testkit.fake_async_session import FakeAsyncSession, FakeResult

COMPANY = uuid.uuid4()
REAL, OTHER, DEFAULT = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _session(rows, *, default=None) -> FakeAsyncSession:
    """Answers the three reads: work-item rows, the company's projects, its default project."""
    projects = [REAL, OTHER] + ([default] if default else [])
    return FakeAsyncSession(results=[list(rows), FakeResult(projects), FakeResult([default] if default else [])])


def _hierarchy():
    epic, pbi, task = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    return epic, pbi, task


async def test_the_preview_lists_a_pbi_whose_task_sits_in_another_project() -> None:
    epic, pbi, task = _hierarchy()
    rows = [(epic, None, REAL), (pbi, epic, None), (task, pbi, OTHER)]
    result = await preview_project_backfill(_session(rows), COMPANY)
    assert result["conflicts"] == 1 and result["conflicting_item_ids"] == [str(pbi)]
    assert (result["missing"], result["from_ancestor"], result["to_default"]) == (1, 0, 0)


async def test_a_task_in_the_same_project_is_no_conflict() -> None:
    epic, pbi, task = _hierarchy()
    rows = [(epic, None, REAL), (pbi, epic, None), (task, pbi, REAL)]
    result = await preview_project_backfill(_session(rows), COMPANY)
    assert (result["conflicts"], result["from_ancestor"]) == (0, 1)


async def test_an_item_bound_for_the_default_conflicts_with_a_child_in_any_other_project() -> None:
    pbi, task = uuid.uuid4(), uuid.uuid4()
    rows = [(pbi, None, None), (task, pbi, REAL)]
    result = await preview_project_backfill(_session(rows), COMPANY)
    assert result["conflicting_item_ids"] == [str(pbi)] and result["to_default"] == 0
    assert (await preview_project_backfill(_session(rows, default=REAL), COMPANY))["conflicts"] == 0


async def test_apply_skips_the_conflict_fills_the_rest_and_reports_the_skipped_ids() -> None:
    epic, pbi, task = _hierarchy()
    free = uuid.uuid4()
    rows = [(epic, None, REAL), (pbi, epic, None), (task, pbi, OTHER), (free, epic, None)]
    session = _session(rows)
    result = await apply_project_backfill(session, COMPANY)
    assert result["conflicting_item_ids"] == [str(pbi)]
    assert result["from_ancestor"] == 1 and result["missing"] == 2
    assert len(session.statements) == 4  # three reads and one UPDATE, for the one item that is not a conflict
    written = str(session.statements[-1].compile().params)
    assert str(free) in written and str(pbi) not in written
