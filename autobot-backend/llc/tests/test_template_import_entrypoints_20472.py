# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The public import entry points keep their parents and report what they skip (#20472).

``PortabilityService.execute_import`` (a company export) and ``TemplateService.import_template`` (a library
template) run on the LLC SQLite harness; the library row is the only thing faked, as it is a Postgres-only table.
Also: an import wakes no agent, while a normal create with the same text does.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy as sa
from sqlalchemy import select

from llc.models.company import CompanyCreate
from llc.models.enums import WorkItemType
from llc.models.heartbeat_run import LLCHeartbeatRun
from llc.models.template import TemplateImportRequest
from llc.models.work_item import LLCWorkItem
from llc.services.company import CompanyService
from llc.services.portability import PortabilityService, TemplateImportError
from llc.services.template import TemplateService
from llc.services.work_item_service import WorkItemService
from llc.tests import _e2e_harness as harness
from llc.tests import test_event_wakes_19582 as _wakes
from llc.tests import test_llc_org_chart as _org_chart_harness
from llc.tests.test_event_wakes_19582 import _COMPANY, _agent

factory = _wakes.factory
dispatched = _wakes.dispatched
engine = _org_chart_harness.engine
session_factory = _org_chart_harness.session_factory

pytestmark = pytest.mark.asyncio


def _snapshot() -> dict:
    """A company export, shaped as ``export_snapshot`` writes it: ids, parent_id, project_id, type."""
    ids = {n: str(uuid.uuid4()) for n in ("epic", "feat", "pbi", "orphan")}
    ghost = str(uuid.uuid4())
    row = lambda k, title, type_, parent: {  # noqa: E731
        "id": ids[k],
        "parent_id": parent,
        "project_id": "src-p",
        "type": type_,
        "title": title,
        "priority": "medium",
    }
    return {
        "schema_version": "1.0",
        "export_kind": "snapshot",
        "company": {"name": "Exported", "slug": f"exp-{uuid.uuid4().hex[:8]}"},
        "projects": [{"id": "src-p", "name": "Source project", "status": "in_progress"}],
        "work_items": [
            row("pbi", "PBI", "pbi", ids["feat"]),
            row("feat", "Feature", "feature", ids["epic"]),
            row("epic", "Epic", "epic", None),
            row("orphan", "Orphan", "feature", ghost),
        ],
    }


async def _items(session_factory, company_id) -> dict:  # noqa: ANN001
    async with session_factory() as session:
        stmt = select(LLCWorkItem).where(LLCWorkItem.company_id == uuid.UUID(str(company_id)))
        return {r.title: r for r in (await session.execute(stmt)).scalars()}


async def test_execute_import_of_an_exported_company_round_trips_parents(session_factory) -> None:  # noqa: ANN001
    async with session_factory() as session:
        with patch.object(PortabilityService, "_agent_names_exist", AsyncMock(return_value=[])):
            result = await PortabilityService(session).execute_import(_snapshot())
        await session.commit()
    rows = await _items(session_factory, result["company_id"])
    assert sorted(rows) == ["Epic", "Feature", "PBI"]
    assert rows["PBI"].parent_id == rows["Feature"].id and rows["Feature"].parent_id == rows["Epic"].id
    assert [(s["title"], s["reason"]) for s in result["skipped_work_items"]] == [("Orphan", "parent_missing")]
    assert result["skipped"]["work_items"] == ["Orphan"] and len(result["created_entities"]["work_items"]) == 3


async def test_execute_import_with_a_bad_item_type_rolls_back(session_factory) -> None:  # noqa: ANN001
    template = _snapshot()
    template["work_items"][0]["type"] = "not-a-type"
    async with session_factory() as session:
        with (
            patch.object(PortabilityService, "_agent_names_exist", AsyncMock(return_value=[])),
            pytest.raises(TemplateImportError, match="Import rolled back"),
        ):
            await PortabilityService(session).execute_import(template)


async def _library_session(session_factory, template_json) -> tuple:  # noqa: ANN001
    """A session on the harness DB, a target company, and the library row the service reads."""
    async with session_factory() as session:
        org = await CompanyService(session).create(CompanyCreate(name="Target", slug=f"t-{uuid.uuid4().hex[:6]}"))
        await session.execute(sa.text("CREATE TABLE IF NOT EXISTS llc_template_library (id TEXT, usage_count INT)"))
        await session.commit()
    tid = uuid.uuid4()
    row = {"id": tid, "template_json": template_json, "created_by_company_id": org.id, "is_public": True}
    return org, tid, row


async def test_import_template_creates_built_in_style_items_and_reports_counts(session_factory) -> None:  # noqa: ANN001
    body = {"metadata": {"name": "Ops Team"}, "work_items": [{"title": f"Item {i}"} for i in range(3)]}
    org, tid, row = await _library_session(session_factory, body)
    async with session_factory() as session:
        with patch("llc.services.template._fetch_row", new=AsyncMock(return_value=row)):
            result = await TemplateService(session).import_template(
                tid, TemplateImportRequest(target_company_id=org.id)
            )
        await session.commit()
    rows = await _items(session_factory, org.id)
    assert sorted(rows) == ["Item 0", "Item 1", "Item 2"] and all(r.type == WorkItemType.EPIC for r in rows.values())
    assert (result.entities_created["projects"], result.entities_created["work_items"]) == (1, 3)
    assert result.skipped_work_items == []


async def test_import_template_reports_a_missing_parent_and_rejects_a_bad_enum(session_factory) -> None:  # noqa: ANN001
    items = [{"id": "f", "title": "Lonely", "type": "feature", "parent_id": "gone"}]
    org, tid, row = await _library_session(session_factory, {"metadata": {"name": "T"}, "work_items": items})
    async with session_factory() as session:
        with patch("llc.services.template._fetch_row", new=AsyncMock(return_value=row)):
            result = await TemplateService(session).import_template(
                tid, TemplateImportRequest(target_company_id=org.id)
            )
    assert [(s["title"], s["reason"]) for s in result.skipped_work_items] == [("Lonely", "parent_missing")]
    assert result.entities_created["work_items"] == 0

    bad = {"metadata": {"name": "T"}, "work_items": [{"title": "X", "priority": "urgent-ish"}]}
    row["template_json"] = bad
    async with session_factory() as session:
        with (
            patch("llc.services.template._fetch_row", new=AsyncMock(return_value=row)),
            pytest.raises(TemplateImportError, match="Import rolled back"),
        ):
            await TemplateService(session).import_template(tid, TemplateImportRequest(target_company_id=org.id))


async def _create_mentioning(factory, slug: str, *, wake: bool) -> None:  # noqa: ANN001
    async with factory() as session:
        await WorkItemService().create(
            session,
            str(_COMPANY),
            WorkItemType.TASK,
            f"Ping @{slug}",
            project_id=await harness.seed_project(session, _COMPANY),
            wake_agents=wake,
        )
        await session.commit()


async def _run_count(factory, slug: str) -> int:  # noqa: ANN001
    async with factory() as session:
        stmt = select(LLCHeartbeatRun).where(LLCHeartbeatRun.agent_id == slug)
        return len((await session.execute(stmt)).scalars().all())


async def test_wake_agents_false_wakes_nobody_but_a_normal_create_does(factory, dispatched) -> None:  # noqa: ANN001
    node = await _agent(factory)
    await _create_mentioning(factory, node.agent_id, wake=False)
    assert await _run_count(factory, node.agent_id) == 0
    await _create_mentioning(factory, node.agent_id, wake=True)
    assert await _run_count(factory, node.agent_id) == 1
