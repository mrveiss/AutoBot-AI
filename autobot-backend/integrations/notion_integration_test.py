# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit Tests — NotionIntegration (Issue #4099)

Tests are isolated: all HTTP calls are patched so no real network traffic occurs.
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


def _mock_client(status: int, body: dict):
    """Build a mock ``HTTPClientManager`` whose ``tracked_request()`` yields a
    response mimicking the given status/body.

    Issue #12979: ``_notion_request`` routes through the shared pool's
    ``get_http_client().tracked_request(method, url, **kwargs)`` rather than
    constructing its own ``aiohttp.ClientSession``.
    """
    resp = AsyncMock()
    resp.status = status
    resp.json = AsyncMock(return_value=body)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.tracked_request = MagicMock(return_value=cm)
    return mock_client


@pytest.mark.asyncio
class TestNotionIntegration:
    """Tests for NotionIntegration."""

    # ------------------------------------------------------------------
    # test_connection
    # ------------------------------------------------------------------

    @patch("integrations.notion_integration.get_http_client")
    async def test_test_connection_success(self, mock_get_client):
        """Returns CONNECTED status on HTTP 200 from /users/me."""
        mock_get_client.return_value = _mock_client(
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

    @patch("integrations.notion_integration.get_http_client")
    async def test_test_connection_unauthorized(self, mock_get_client):
        """Returns UNAUTHORIZED status on HTTP 401."""
        mock_get_client.return_value = _mock_client(401, {"object": "error"})
        integration = NotionIntegration(_make_config())
        health = await integration.test_connection()

        assert health.status == IntegrationStatus.UNAUTHORIZED
        assert integration.status == IntegrationStatus.UNAUTHORIZED

    @patch("integrations.notion_integration.get_http_client")
    async def test_test_connection_error(self, mock_get_client):
        """Returns ERROR status on unexpected HTTP codes."""
        mock_get_client.return_value = _mock_client(500, {})
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

    @patch("integrations.notion_integration.get_http_client")
    async def test_list_databases_success(self, mock_get_client):
        """Parses database objects from /search response."""
        mock_get_client.return_value = _mock_client(
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

    @patch("integrations.notion_integration.get_http_client")
    async def test_list_databases_http_error(self, mock_get_client):
        """Returns error dict on non-200 response."""
        mock_get_client.return_value = _mock_client(403, {})
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

    @patch("integrations.notion_integration.get_http_client")
    async def test_query_database_success(self, mock_get_client):
        """Parses rows and has_more from database query response."""
        mock_get_client.return_value = _mock_client(
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

    @patch("integrations.notion_integration.get_http_client")
    async def test_get_page_success(self, mock_get_client):
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

        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=resp)
        cm.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.tracked_request = MagicMock(return_value=cm)
        mock_get_client.return_value = mock_client

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

    @patch("integrations.notion_integration.get_http_client")
    async def test_create_page_success(self, mock_get_client):
        """Returns page id, url and created_time on 200."""
        mock_get_client.return_value = _mock_client(
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

    @patch("integrations.notion_integration.get_http_client")
    async def test_update_page_archive(self, mock_get_client):
        """Sends archived=True and returns page id on 200."""
        mock_get_client.return_value = _mock_client(
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
