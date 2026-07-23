# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Confluence Knowledge Connector (Issue #10538)

All HTTP calls are mocked — no network access, and the module never makes a
live request just from being imported or instantiated.
"""

from unittest.mock import AsyncMock, patch

import pytest

from knowledge.connectors.confluence import ConfluenceConnector
from knowledge.connectors.models import ConnectorConfig


@pytest.fixture
def confluence_config():
    return ConnectorConfig(
        connector_id="test-confluence-1",
        connector_type="confluence",
        name="Test Confluence",
        config={
            "base_url": "https://example.atlassian.net/wiki",
            "email": "bot@example.com",
            "api_token": "test-fake-api-credential",
            "space_keys": ["ENG"],
        },
        enabled=True,
        verification_mode="collaborative",
    )


class TestConfluenceConnectorInit:
    def test_init(self, confluence_config):
        connector = ConfluenceConnector(confluence_config)
        assert connector.connector_type == "confluence"
        assert connector.tier == 2
        assert connector._email == "bot@example.com"
        assert connector._base_url == "https://example.atlassian.net/wiki"
        assert connector._space_keys == ["ENG"]
        assert connector.max_concurrency == 4

    def test_auth_schema(self):
        from autobot_shared.auth import BasicAuth

        assert ConfluenceConnector.auth_schema() == BasicAuth

    def test_output_schema(self):
        schema = ConfluenceConnector.output_schema()
        assert schema["type"] == "object"
        assert "confluence_page_id" in schema["required"]
        assert "confluence_space_key" in schema["required"]


class TestConfluenceConnectorConnection:
    @pytest.mark.asyncio
    async def test_test_connection_success(self, confluence_config):
        connector = ConfluenceConnector(confluence_config)
        with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status_code": 200, "body": {"results": []}}
            assert await connector.test_connection() is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, confluence_config):
        connector = ConfluenceConnector(confluence_config)
        with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status_code": 401, "body": {}}
            assert await connector.test_connection() is False


class TestConfluenceConnectorDiscovery:
    @pytest.mark.asyncio
    async def test_discover_sources(self, confluence_config):
        connector = ConfluenceConnector(confluence_config)
        list_body = {
            "results": [
                {"id": "111", "title": "Runbook", "version": {"when": "2026-01-01T00:00:00.000Z"}},
            ]
        }
        with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status_code": 200, "body": list_body}
            sources = await connector.discover_sources()

        assert len(sources) == 1
        assert sources[0].source_id == "confluence:test-confluence-1:page:111"
        assert sources[0].name == "Runbook"


class TestConfluenceConnectorFetchContent:
    @pytest.mark.asyncio
    async def test_fetch_content(self, confluence_config):
        connector = ConfluenceConnector(confluence_config)
        source_id = "confluence:test-confluence-1:page:111"
        page_body = {
            "title": "Runbook",
            "body": {"storage": {"value": "<p>Restart the <b>service</b>.</p>"}},
            "space": {"key": "ENG"},
            "version": {"when": "2026-01-01T00:00:00.000Z"},
            "_links": {"webui": "/spaces/ENG/pages/111"},
        }
        with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status_code": 200, "body": page_body}
            result = await connector.fetch_content(source_id)

        assert result is not None
        assert "Runbook" in result.content
        assert "Restart the service" in result.content
        assert result.metadata["confluence_page_id"] == "111"
        assert result.metadata["confluence_space_key"] == "ENG"
        assert result.metadata["confluence_url"] == "https://example.atlassian.net/wiki/spaces/ENG/pages/111"

    @pytest.mark.asyncio
    async def test_fetch_content_malformed_source_id(self, confluence_config):
        connector = ConfluenceConnector(confluence_config)
        assert await connector.fetch_content("not-a-confluence-id") is None

    @pytest.mark.asyncio
    async def test_fetch_content_not_found(self, confluence_config):
        connector = ConfluenceConnector(confluence_config)
        source_id = "confluence:test-confluence-1:page:999"
        with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status_code": 404, "body": {}}
            assert await connector.fetch_content(source_id) is None


class TestConfluenceConnectorChangeDetection:
    @pytest.mark.asyncio
    async def test_detect_changes_initial_sync(self, confluence_config):
        connector = ConfluenceConnector(confluence_config)
        list_body = {"results": [{"id": "111", "title": "Runbook", "version": {"when": "2026-01-01T00:00:00.000Z"}}]}
        with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status_code": 200, "body": list_body}
            changes = await connector.detect_changes(since=None)

        assert len(changes) == 1
        assert changes[0].change_type == "added"
        assert changes[0].source_id == "confluence:test-confluence-1:page:111"


class TestConfluenceModuleHelpers:
    def test_html_to_text_strips_markup(self):
        from knowledge.connectors.confluence import _html_to_text

        assert _html_to_text("<p>Hello <b>World</b></p>") == "Hello World"

    def test_html_to_text_empty(self):
        from knowledge.connectors.confluence import _html_to_text

        assert _html_to_text("") == ""

    def test_parse_page_id_valid(self):
        from knowledge.connectors.confluence import _parse_page_id

        assert _parse_page_id("confluence:conn-1:page:111") == "111"

    def test_parse_page_id_malformed(self):
        from knowledge.connectors.confluence import _parse_page_id

        assert _parse_page_id("bad:id") is None
