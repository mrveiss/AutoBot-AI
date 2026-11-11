# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A template import creates work items that meet the hierarchy rules (#20472), on a real (SQLite) database."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkItemType as T
from llc.models.sprint import LLCProject
from llc.models.work_item import LLCWorkItem
from llc.services.work_item_hierarchy import ALLOWED_PARENT_TYPES
from llc.services.work_item_import import import_template_work, import_work_items
from llc.tests import _e2e_harness as harness

pytestmark = pytest.mark.asyncio

_BUILT_IN = {
    p.stem: json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((Path(__file__).parent.parent / "built_in_templates").glob("*.json"))
}


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    await harness.create_loop_schema(eng)
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        eng, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s
    await eng.dispose()


async def _run(session, template) -> tuple[dict, dict, list]:
    created = {"projects": [], "work_items": []}
    skipped = {"work_items": []}
    skipped_items = await import_template_work(session, template, uuid.uuid4(), created, skipped, [])
    return created, skipped, skipped_items


async def _rows(session) -> dict:
    return {r.title: r for r in (await session.execute(select(LLCWorkItem))).scalars()}


def _item(source_id, title, type_, parent=None, project="p1") -> dict:
    return {"id": source_id, "title": title, "type": type_, "parent_id": parent, "project_id": project}


@pytest.mark.parametrize("template", _BUILT_IN.values(), ids=_BUILT_IN.keys())
async def test_a_built_in_template_imports_every_item_as_an_epic_in_a_project_named_after_it(session, template) -> None:
    created, skipped, skipped_items = await _run(session, template)
    assert (len(created["work_items"]), skipped["work_items"], skipped_items) == (3, [], [])
    assert len(created["projects"]) == 1
    project = await session.get(LLCProject, uuid.UUID(created["projects"][0]))
    assert project.name == template["metadata"]["name"]
    rows = list((await _rows(session)).values())
    assert len(rows) == 3
    for row in rows:
        assert row.type == T.EPIC and row.project_id == project.id
        assert not ALLOWED_PARENT_TYPES[T.EPIC] and row.parent_id is None


async def test_a_snapshot_chain_keeps_its_parents_whatever_order_it_lists_them(session) -> None:
    template = {
        "export_kind": "snapshot",
        "projects": [{"id": "p1", "name": "P"}],
        "work_items": [
            _item("pbi", "PBI", "pbi", parent="feat"),
            _item("feat", "Feature", "feature", parent="epic"),
            _item("epic", "Epic", "epic"),
        ],
    }
    created, _, skipped_items = await _run(session, template)
    rows = await _rows(session)
    assert skipped_items == [] and len(created["work_items"]) == 3
    assert rows["PBI"].parent_id == rows["Feature"].id
    assert rows["Feature"].parent_id == rows["Epic"].id
    assert rows["PBI"].project_id == rows["Epic"].project_id


async def test_an_item_whose_parent_is_missing_is_reported_and_not_created(session) -> None:
    template = {
        "projects": [{"id": "p1", "name": "P"}],
        "work_items": [_item("f", "Orphan", "feature", parent="gone"), _item("t", "Child", "pbi", parent="f")],
    }
    created, skipped, skipped_items = await _run(session, template)
    assert created["work_items"] == [] and await _rows(session) == {}
    assert [(s["title"], s["reason"]) for s in skipped_items] == [
        ("Orphan", "parent_missing"),
        ("Child", "parent_not_imported"),
    ]
    assert skipped["work_items"] == ["Orphan", "Child"]


async def test_a_hierarchy_violation_is_reported_not_raised(session) -> None:
    template = {
        "projects": [{"id": "p1", "name": "P"}],
        "work_items": [_item("e", "Epic", "epic"), _item("t", "Task", "task", parent="e")],
    }
    created, _, skipped_items = await _run(session, template)
    assert len(created["work_items"]) == 1
    assert [(s["title"], s["reason"]) for s in skipped_items] == [("Task", "hierarchy_violation")]


async def test_a_template_export_still_imports_only_its_seeds(session) -> None:
    template = {
        "export_kind": "template",
        "projects": [{"id": "p1", "name": "P"}],
        "seed_work_items": [{**_item("e", "Seed", "epic"), "is_seed": True}],
        "work_items": [_item("x", "Not a seed", "epic")],
    }
    created, _, _ = await _run(session, template)
    assert list(await _rows(session)) == ["Seed"] and len(created["work_items"]) == 1


async def test_a_two_item_loop_and_a_self_parent_are_reported_as_cycles(session) -> None:
    template = {
        "projects": [{"id": "p1", "name": "P"}],
        "work_items": [
            _item("a", "A", "feature", parent="b"),
            _item("b", "B", "feature", parent="a"),
            _item("s", "Self", "feature", parent="s"),
            _item("ok", "Fine", "epic"),
        ],
    }
    created, _, skipped_items = await _run(session, template)
    assert sorted((s["title"], s["reason"]) for s in skipped_items) == [
        ("A", "parent_cycle"),
        ("B", "parent_cycle"),
        ("Self", "parent_cycle"),
    ]
    assert list(await _rows(session)) == ["Fine"] and len(created["work_items"]) == 1


async def test_an_item_naming_a_project_that_was_not_imported_is_skipped_not_moved(session) -> None:
    template = {"projects": [{"id": "p1", "name": "P"}], "work_items": [_item("e", "Lost", "epic", project="nope")]}
    _, _, skipped_items = await _run(session, template)
    assert [(s["title"], s["reason"]) for s in skipped_items] == [("Lost", "project_not_imported")]
    assert await _rows(session) == {}


async def test_an_item_with_no_project_to_go_to_is_reported(session) -> None:
    created, skipped, skipped_items = await _run(session, {"work_items": []})
    assert (created["projects"], skipped_items) == ([], [])
    report = await import_work_items([_item("e", "Homeless", "epic", project=None)], uuid.uuid4(), {}, _never)
    assert [(s["title"], s["reason"]) for s in report["skipped_items"]] == [("Homeless", "no_project")]
    assert report["created"] == [] and report["warnings"]


async def _never(*_args):  # noqa: ANN002, ANN202
    raise AssertionError("an item with no project must not be created")
