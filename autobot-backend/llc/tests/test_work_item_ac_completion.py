# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Per-criterion acceptance-criteria completion on LLC work items (GH#10852).

The WorkItemDetail checkboxes were local-only display state (``saveAC()`` was a
no-op), so toggles never persisted and were lost on reload. This proves the new
``acceptance_criteria_done`` boolean list round-trips through the service update
path and the API serialization contract.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.services.work_item_service import WorkItemService


@pytest.fixture
def service():
    return WorkItemService()


@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


class TestUpdate:
    async def test_update_persists_acceptance_criteria_done(self, service, mock_session):
        item = MagicMock()
        with patch.object(service, "get", new=AsyncMock(return_value=item)):
            result = await service.update(
                mock_session,
                str(uuid.uuid4()),
                acceptance_criteria_done=[True, False, True],
            )
        assert result is item
        assert item.acceptance_criteria_done == [True, False, True]

    async def test_update_accepts_empty_completion_list(self, service, mock_session):
        """All-unchecked (or no criteria) sends an empty list, not None."""
        item = MagicMock()
        with patch.object(service, "get", new=AsyncMock(return_value=item)):
            await service.update(mock_session, str(uuid.uuid4()), acceptance_criteria_done=[])
        assert item.acceptance_criteria_done == []


class TestSerialization:
    async def test_item_to_dict_includes_acceptance_criteria_done(self):
        from llc.api import work_items

        item = MagicMock()
        item.acceptance_criteria_done = [True, False]
        item.requires_approval_before = []
        item.linked_pr_urls = []
        item.labels = []
        session = AsyncMock()
        with (
            patch.object(work_items, "_assignee_display", new=AsyncMock(return_value=None)),
            patch.object(work_items, "_relations_to_list", return_value=[]),
        ):
            result = await work_items._item_to_dict(item, session)
        assert result["acceptance_criteria_done"] == [True, False]

    async def test_item_to_dict_defaults_none_to_empty_list(self):
        from llc.api import work_items

        item = MagicMock()
        item.acceptance_criteria_done = None  # never tracked
        item.requires_approval_before = []
        item.linked_pr_urls = []
        item.labels = []
        session = AsyncMock()
        with (
            patch.object(work_items, "_assignee_display", new=AsyncMock(return_value=None)),
            patch.object(work_items, "_relations_to_list", return_value=[]),
        ):
            result = await work_items._item_to_dict(item, session)
        assert result["acceptance_criteria_done"] == []
