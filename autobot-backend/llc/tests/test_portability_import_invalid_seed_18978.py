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
