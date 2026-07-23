# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Slack Knowledge Connector (Issue #10538)

All HTTP calls are mocked — no network access, and the module never makes a
live request just from being imported or instantiated.
"""

from unittest.mock import AsyncMock, patch

import pytest

from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.slack import SlackConnector


@pytest.fixture
def slack_config():
    return ConnectorConfig(
        connector_id="test-slack-1",
        connector_type="slack",
        name="Test Slack",
        config={
            "bot_token": "test-fake-bot-credential",
            "channel_ids": ["C123"],
            "sync_threads": True,
        },
        enabled=True,
        verification_mode="collaborative",
    )


class TestSlackConnectorInit:
    def test_init(self, slack_config):
        connector = SlackConnector(slack_config)
        assert connector.connector_type == "slack"
        assert connector.tier == 1
        assert connector._token == "test-fake-bot-credential"
        assert connector._channel_ids == ["C123"]
        assert connector._sync_threads is True
        assert connector.max_concurrency == 4

    def test_auth_schema(self):
        from autobot_shared.auth import BearerAuth

        assert SlackConnector.auth_schema() == BearerAuth

    def test_output_schema(self):
        schema = SlackConnector.output_schema()
        assert schema["type"] == "object"
        assert "slack_channel_id" in schema["required"]
        assert "slack_message_ts" in schema["required"]


class TestSlackConnectorConnection:
    @pytest.mark.asyncio
    async def test_test_connection_success(self, slack_config):
        connector = SlackConnector(slack_config)
        with patch.object(connector, "_slack_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"status_code": 200, "body": {"ok": True}}
            assert await connector.test_connection() is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, slack_config):
        connector = SlackConnector(slack_config)
        with patch.object(connector, "_slack_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"status_code": 200, "body": {"ok": False, "error": "invalid_auth"}}
            assert await connector.test_connection() is False


class TestSlackConnectorDiscovery:
    @pytest.mark.asyncio
    async def test_discover_sources(self, slack_config):
        connector = SlackConnector(slack_config)
        history_body = {
            "ok": True,
            "messages": [{"ts": "1000.001", "user": "U1", "text": "hello"}],
        }
        with patch.object(connector, "_slack_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"status_code": 200, "body": history_body}
            sources = await connector.discover_sources()

        assert len(sources) == 1
        assert sources[0].source_id == "slack:test-slack-1:channel:C123:ts:1000.001"
        assert "hello" in sources[0].name


class TestSlackConnectorFetchContent:
    @pytest.mark.asyncio
    async def test_fetch_content_no_thread(self, slack_config):
        connector = SlackConnector(slack_config)
        source_id = "slack:test-slack-1:channel:C123:ts:1000.001"
        history_body = {
            "ok": True,
            "messages": [{"ts": "1000.001", "user": "U1", "text": "hello world", "reply_count": 0}],
        }
        with patch.object(connector, "_slack_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"status_code": 200, "body": history_body}
            result = await connector.fetch_content(source_id)

        assert result is not None
        assert "hello world" in result.content
        assert result.metadata["slack_channel_id"] == "C123"
        assert result.metadata["slack_message_ts"] == "1000.001"
        assert result.metadata["thread_reply_count"] == 0

    @pytest.mark.asyncio
    async def test_fetch_content_malformed_source_id(self, slack_config):
        connector = SlackConnector(slack_config)
        assert await connector.fetch_content("not-a-slack-id") is None

    @pytest.mark.asyncio
    async def test_fetch_content_not_found(self, slack_config):
        connector = SlackConnector(slack_config)
        source_id = "slack:test-slack-1:channel:C123:ts:9999.001"
        with patch.object(connector, "_slack_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"status_code": 200, "body": {"ok": True, "messages": []}}
            assert await connector.fetch_content(source_id) is None


class TestSlackConnectorChangeDetection:
    @pytest.mark.asyncio
    async def test_detect_changes_initial_sync(self, slack_config):
        connector = SlackConnector(slack_config)
        history_body = {"ok": True, "messages": [{"ts": "1000.001", "user": "U1", "text": "hi"}]}
        with (
            patch.object(connector, "_slack_post", new_callable=AsyncMock) as mock_post,
            patch("knowledge.connectors.slack._load_ts", new=AsyncMock(return_value=None)),
            patch("knowledge.connectors.slack._store_ts", new=AsyncMock()),
        ):
            mock_post.return_value = {"status_code": 200, "body": history_body}
            changes = await connector.detect_changes(since=None)

        assert len(changes) == 1
        assert changes[0].change_type == "added"
        assert changes[0].source_id == "slack:test-slack-1:channel:C123:ts:1000.001"


class TestSlackModuleHelpers:
    def test_message_to_text(self):
        from knowledge.connectors.slack import _message_to_text

        assert _message_to_text({"user": "U1", "text": "hi there"}) == "[U1] hi there"

    def test_parse_source_id_valid(self):
        from knowledge.connectors.slack import _parse_source_id

        channel, ts = _parse_source_id("slack:conn-1:channel:C1:ts:100.5")
        assert channel == "C1"
        assert ts == "100.5"

    def test_parse_source_id_malformed(self):
        from knowledge.connectors.slack import _parse_source_id

        channel, ts = _parse_source_id("bad:id")
        assert channel is None
        assert ts is None
