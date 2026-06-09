# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit Tests — NotionIntegration (Issue #4099)

Tests are isolated: all aiohttp calls are patched so no real network traffic occurs.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations.base import IntegrationConfig, IntegrationStatus
from integrations.notion_integration import NotionIntegration, _extract_title


def _make_config(**kwargs) -> IntegrationConfig:
    defaults = dict(
        name="Test Notion",
        provider="notion",
        token="secret_test_token",
        base_url="https://api.notion.com/v1",
    )
    defaults.update(kwargs)
    return IntegrationConfig(**defaults)


def _mock_session(status: int, body: dict):
    """Build a nested mock that mimics aiohttp.ClientSession context manager."""
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=body)

    cm_inner = AsyncMock()
    cm_inner.__aenter__ = AsyncMock(return_value=resp)
    cm_inner.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.request = MagicMock(return_value=cm_inner)

    cm_outer = MagicMock()
    cm_outer.__aenter__ = AsyncMock(return_value=mock_session)
    cm_outer.__aexit__ = AsyncMock(return_value=False)
    return cm_outer


@pytest.mark.asyncio
class TestNotionIntegration:
    """Tests for NotionIntegration."""

    # ------------------------------------------------------------------
    # test_connection
    # ------------------------------------------------------------------

    @patch("aiohttp.ClientSession")
    async def test_test_connection_success(self, mock_session_cls):
        """Returns CONNECTED status on HTTP 200 from /users/me."""
        mock_session_cls.return_value = _mock_session(
            200,
            {
                "id": "bot-uuid",
                "name": "AutoBot",
                "bot": {"workspace_name": "My Workspace"},
            },
        )
        integration = NotionIntegration(_make_config())
        health = await integration.test_connection()

        assert health.status == IntegrationStatus.CONNECTED
        assert integration.status == IntegrationStatus.CONNECTED
        assert health.details["bot_id"] == "bot-uuid"
        assert health.details["workspace_name"] == "My Workspace"

    @patch("aiohttp.ClientSession")
    async def test_test_connection_unauthorized(self, mock_session_cls):
        """Returns UNAUTHORIZED status on HTTP 401."""
        mock_session_cls.return_value = _mock_session(401, {"object": "error"})
        integration = NotionIntegration(_make_config())
        health = await integration.test_connection()

        assert health.status == IntegrationStatus.UNAUTHORIZED
        assert integration.status == IntegrationStatus.UNAUTHORIZED

    @patch("aiohttp.ClientSession")
    async def test_test_connection_error(self, mock_session_cls):
        """Returns ERROR status on unexpected HTTP codes."""
        mock_session_cls.return_value = _mock_session(500, {})
        integration = NotionIntegration(_make_config())
        health = await integration.test_connection()

        assert health.status == IntegrationStatus.ERROR

    # ------------------------------------------------------------------
    # execute_action — unknown action
    # ------------------------------------------------------------------

    async def test_execute_action_unknown(self):
        """Returns error dict for unknown action names."""
        integration = NotionIntegration(_make_config())
        result = await integration.execute_action("does_not_exist", {})
        assert "error" in result

    # ------------------------------------------------------------------
    # list_databases
    # ------------------------------------------------------------------

    @patch("aiohttp.ClientSession")
    async def test_list_databases_success(self, mock_session_cls):
        """Parses database objects from /search response."""
        mock_session_cls.return_value = _mock_session(
            200,
            {
                "results": [
                    {
                        "id": "db-1",
                        "title": [{"plain_text": "Tasks"}],
                        "url": "https://notion.so/db-1",
                        "created_time": "2024-01-01T00:00:00.000Z",
                        "last_edited_time": "2024-06-01T00:00:00.000Z",
                    }
                ],
                "has_more": False,
            },
        )
        integration = NotionIntegration(_make_config())
        result = await integration.execute_action("list_databases", {})

        assert "databases" in result
        assert len(result["databases"]) == 1
        assert result["databases"][0]["id"] == "db-1"
        assert result["databases"][0]["title"] == "Tasks"

    @patch("aiohttp.ClientSession")
    async def test_list_databases_http_error(self, mock_session_cls):
        """Returns error dict on non-200 response."""
        mock_session_cls.return_value = _mock_session(403, {})
        integration = NotionIntegration(_make_config())
        result = await integration.execute_action("list_databases", {})
        assert "error" in result

    # ------------------------------------------------------------------
    # query_database
    # ------------------------------------------------------------------

    async def test_query_database_missing_id(self):
        """Returns error when database_id is absent."""
        integration = NotionIntegration(_make_config())
        result = await integration.execute_action("query_database", {})
        assert "error" in result

    @patch("aiohttp.ClientSession")
    async def test_query_database_success(self, mock_session_cls):
        """Parses rows and has_more from database query response."""
        mock_session_cls.return_value = _mock_session(
            200,
            {
                "results": [
                    {
                        "id": "page-1",
                        "url": "https://notion.so/page-1",
                        "created_time": "2024-01-01T00:00:00.000Z",
                        "last_edited_time": "2024-06-01T00:00:00.000Z",
                        "properties": {"Status": {"select": {"name": "Done"}}},
                    }
                ],
                "has_more": False,
            },
        )
        integration = NotionIntegration(_make_config())
        result = await integration.execute_action("query_database", {"database_id": "db-abc"})

        assert "rows" in result
        assert len(result["rows"]) == 1
        assert result["rows"][0]["id"] == "page-1"
        assert result["has_more"] is False

    # ------------------------------------------------------------------
    # get_page
    # ------------------------------------------------------------------

    async def test_get_page_missing_id(self):
        """Returns error when page_id is absent."""
        integration = NotionIntegration(_make_config())
        result = await integration.execute_action("get_page", {})
        assert "error" in result

    @patch("aiohttp.ClientSession")
    async def test_get_page_success(self, mock_session_cls):
        """Returns page metadata and block list on success."""
        page_body = {
            "id": "page-xyz",
            "url": "https://notion.so/page-xyz",
            "created_time": "2024-01-01T00:00:00.000Z",
            "last_edited_time": "2024-06-01T00:00:00.000Z",
            "properties": {"Name": {"title": [{"plain_text": "My Doc"}]}},
        }
        blocks_body = {
            "results": [
                {
                    "type": "paragraph",
                    "paragraph": {"rich_text": [{"plain_text": "Hello world"}]},
                }
            ]
        }

        call_count = 0

        async def fake_json(content_type=None):
            nonlocal call_count
            call_count += 1
            return page_body if call_count == 1 else blocks_body

        resp = AsyncMock()
        resp.status = 200
        resp.json = fake_json

        cm_inner = AsyncMock()
        cm_inner.__aenter__ = AsyncMock(return_value=resp)
        cm_inner.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.request = MagicMock(return_value=cm_inner)

        cm_outer = MagicMock()
        cm_outer.__aenter__ = AsyncMock(return_value=mock_session)
        cm_outer.__aexit__ = AsyncMock(return_value=False)

        mock_session_cls.return_value = cm_outer

        integration = NotionIntegration(_make_config())
        result = await integration.execute_action("get_page", {"page_id": "page-xyz"})

        assert result["id"] == "page-xyz"
        assert result["title"] == "My Doc"
        assert len(result["blocks"]) == 1

    # ------------------------------------------------------------------
    # create_page
    # ------------------------------------------------------------------

    async def test_create_page_missing_fields(self):
        """Returns error when required fields are absent."""
        integration = NotionIntegration(_make_config())
        result = await integration.execute_action("create_page", {"database_id": "db-1"})
        assert "error" in result

    @patch("aiohttp.ClientSession")
    async def test_create_page_success(self, mock_session_cls):
        """Returns page id, url and created_time on 200."""
        mock_session_cls.return_value = _mock_session(
            200,
            {
                "id": "new-page-id",
                "url": "https://notion.so/new-page-id",
                "created_time": "2024-06-01T00:00:00.000Z",
            },
        )
        integration = NotionIntegration(_make_config())
        result = await integration.execute_action(
            "create_page",
            {
                "database_id": "db-1",
                "properties": {"Name": {"title": [{"text": {"content": "New Task"}}]}},
            },
        )

        assert result["id"] == "new-page-id"
        assert "url" in result

    # ------------------------------------------------------------------
    # update_page
    # ------------------------------------------------------------------

    async def test_update_page_missing_id(self):
        """Returns error when page_id is absent."""
        integration = NotionIntegration(_make_config())
        result = await integration.execute_action("update_page", {})
        assert "error" in result

    async def test_update_page_no_fields(self):
        """Returns error when no update fields are provided."""
        integration = NotionIntegration(_make_config())
        result = await integration.execute_action("update_page", {"page_id": "page-1"})
        assert "error" in result

    @patch("aiohttp.ClientSession")
    async def test_update_page_archive(self, mock_session_cls):
        """Sends archived=True and returns page id on 200."""
        mock_session_cls.return_value = _mock_session(
            200,
            {
                "id": "page-1",
                "url": "https://notion.so/page-1",
                "last_edited_time": "2024-06-02T00:00:00.000Z",
            },
        )
        integration = NotionIntegration(_make_config())
        result = await integration.execute_action("update_page", {"page_id": "page-1", "archived": True})
        assert result["id"] == "page-1"


def test_get_available_actions_returns_five():
    """All five actions are exposed."""
    integration = NotionIntegration(_make_config())
    actions = integration.get_available_actions()
    names = {a.name for a in actions}
    assert names == {
        "list_databases",
        "query_database",
        "get_page",
        "create_page",
        "update_page",
    }


# ------------------------------------------------------------------
# _extract_title helper
# ------------------------------------------------------------------


class TestExtractTitle:
    def test_database_title_field(self):
        obj = {"title": [{"plain_text": "My DB"}]}
        assert _extract_title(obj) == "My DB"

    def test_page_name_property(self):
        obj = {"properties": {"Name": {"title": [{"plain_text": "Page Title"}]}}}
        assert _extract_title(obj) == "Page Title"

    def test_empty_object(self):
        assert _extract_title({}) == ""

    def test_multiple_rich_text_segments(self):
        obj = {"title": [{"plain_text": "Part A"}, {"plain_text": " Part B"}]}
        assert _extract_title(obj) == "Part A Part B"
