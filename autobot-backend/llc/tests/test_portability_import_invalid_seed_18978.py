# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A seed item with an invalid type or priority is the import's validation error, not a 500 (#18978).

``_import_work_item`` raises ``ValueError`` for an unknown enum value; ``execute_import`` runs it in its
savepoint, rolls back, and raises ``TemplateImportError`` -- which the route returns as 422.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.services import portability
from llc.services.portability import PortabilityService, TemplateImportError


def _template(**seed) -> dict:
    item = {"is_seed": True, "title": "Seed", "project_id": "p1", **seed}
    return {
        "schema_version": "1.0",
        "company": {"name": "Imported"},
        "projects": [{"id": "p1", "name": "P"}],
        "work_items": [item],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [{"type": "not-a-type"}, {"priority": "urgent-ish"}])
async def test_an_invalid_seed_type_or_priority_is_a_validation_error_and_rolls_back(bad) -> None:
    savepoint = MagicMock(commit=AsyncMock(), rollback=AsyncMock())
    session = MagicMock(begin_nested=AsyncMock(return_value=savepoint), flush=AsyncMock(), add=MagicMock())
    svc = PortabilityService(session=session)
    with (
        patch.object(PortabilityService, "_refuse_agents_into_gated_company", new=AsyncMock()),
        patch.object(PortabilityService, "_resolve_or_create_company", new=AsyncMock(return_value=uuid.uuid4())),
        patch.object(portability, "mint_agent_ids", new=AsyncMock(return_value={})),
        patch.object(portability, "settle_imported_ceo", new=AsyncMock()),
        patch.object(PortabilityService, "_link_reporting_lines", new=AsyncMock()),
        pytest.raises(TemplateImportError, match="Import rolled back"),
    ):
        await svc.execute_import(_template(**bad))
    savepoint.rollback.assert_awaited_once()
    savepoint.commit.assert_not_awaited()


async def _seed_placement(*names: object) -> tuple[list, dict, list]:
    items = [{"is_seed": True, "title": f"s{i}", "project_id": name} for i, name in enumerate(names)]
    place = AsyncMock(return_value=uuid.uuid4())
    created, skipped, warnings = {"work_items": []}, {"work_items": []}, []
    with patch.object(PortabilityService, "_import_work_item", new=place):
        await PortabilityService(session=MagicMock())._import_seed_items(
            {"work_items": items}, uuid.uuid4(), {"p1": "dest-1", "p2": "dest-2"}, created, skipped, warnings
        )
    return [call.args[2] for call in place.await_args_list], skipped, warnings


@pytest.mark.asyncio
async def test_a_seed_goes_to_the_project_it_names_and_one_naming_none_to_the_first() -> None:
    placed, skipped, warnings = await _seed_placement("p2", None)
    assert placed == ["dest-2", "dest-1"]
    assert (skipped["work_items"], warnings) == ([], [])


@pytest.mark.asyncio
async def test_a_seed_naming_a_project_that_was_not_imported_is_skipped_not_moved() -> None:
    placed, skipped, warnings = await _seed_placement("gone")
    assert placed == []
    assert skipped["work_items"] == ["s0"]
    assert warnings == ["Work item 's0' skipped: the project it names was not imported"]
