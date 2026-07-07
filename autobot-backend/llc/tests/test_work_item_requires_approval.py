# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Declarative requires_approval_before on LLC work items (GH#11140).

Proves the plan-time approval declaration round-trips through the service
(create + update) and the API serialization contract. Runtime enforcement of
the declared categories is a separate follow-up (needs work_item_id threaded
into the execution context).
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.models.enums import WorkItemType
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


class TestCreate:
    async def test_create_persists_requires_approval_before(self, service, mock_session):
        captured = {}
        mock_session.add.side_effect = lambda obj: captured.__setitem__("item", obj)
        with patch.object(service, "_next_identifier", new=AsyncMock(return_value="PRJ-1")):
            item = await service.create(
                mock_session,
                company_id=str(uuid.uuid4()),
                type=WorkItemType.TASK,
                title="Deploy task",
                requires_approval_before=["pushing commits", "destructive operations"],
            )
        assert item.requires_approval_before == ["pushing commits", "destructive operations"]

    async def test_create_defaults_to_empty_list(self, service, mock_session):
        with patch.object(service, "_next_identifier", new=AsyncMock(return_value="PRJ-2")):
            item = await service.create(
                mock_session,
                company_id=str(uuid.uuid4()),
                type=WorkItemType.TASK,
                title="Plain task",
            )
        assert item.requires_approval_before == []


class TestUpdate:
    async def test_update_allows_requires_approval_before(self, service, mock_session):
        item = MagicMock()
        with patch.object(service, "get", new=AsyncMock(return_value=item)):
            result = await service.update(
                mock_session,
                str(uuid.uuid4()),
                requires_approval_before=["publishing"],
            )
        assert result is item
        assert item.requires_approval_before == ["publishing"]


class TestSerialization:
    async def test_item_to_dict_includes_requires_approval_before(self):
        from llc.api import work_items

        item = MagicMock()
        item.requires_approval_before = ["pushing commits"]
        item.linked_pr_urls = []
        item.labels = []
        session = AsyncMock()
        with (
            patch.object(work_items, "_assignee_display", new=AsyncMock(return_value=None)),
            patch.object(work_items, "_relations_to_list", return_value=[]),
        ):
            result = await work_items._item_to_dict(item, session)
        assert result["requires_approval_before"] == ["pushing commits"]
