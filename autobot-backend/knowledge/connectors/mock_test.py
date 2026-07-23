# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the Mock/Replay Knowledge Connector (Issue #10538)

Proves the enterprise connectors' sync() path is testable end-to-end OFFLINE:
  - registration under ConnectorRegistry
  - discover_sources()/fetch_content()/detect_changes() read local fixtures only
  - category resolution (CATEGORY_MAP -> "test") works for a live instance
  - a full sync() run (the real inherited AbstractConnector pipeline, not a
    stub) normalizes every fixture into a ContentResult and ingests it
  - zero network sockets are opened at any point
"""

import socket
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from knowledge.connectors.mock import MockConnector, _parse_source_id
from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.registry import CATEGORY_MAP, ConnectorRegistry

_FIXTURE_CATEGORIES = {"engineering", "product", "hr", "support"}


@pytest.fixture
def mock_config():
    return ConnectorConfig(
        connector_id="test-mock-1",
        connector_type="mock",
        name="Test Mock",
        config={},
        enabled=True,
        verification_mode="collaborative",
    )


class TestMockConnectorRegistration:
    def test_registered_under_mock_type(self):
        assert ConnectorRegistry.get_registered_class("mock") is MockConnector

    def test_init(self, mock_config):
        connector = MockConnector(mock_config)
        assert connector.connector_type == "mock"
        assert connector.tier == 0

    def test_output_schema(self):
        schema = MockConnector.output_schema()
        assert schema["type"] == "object"
        assert "category" in schema["required"]


class TestMockConnectorFixtures:
    @pytest.mark.asyncio
    async def test_discover_sources_reads_bundled_fixtures(self, mock_config):
        connector = MockConnector(mock_config)
        sources = await connector.discover_sources()
        assert len(sources) == 5
        assert all(s.source_id.startswith("mock:test-mock-1:doc:") for s in sources)

    @pytest.mark.asyncio
    async def test_discover_sources_exercises_varied_categories(self, mock_config):
        connector = MockConnector(mock_config)
        sources = await connector.discover_sources()
        categories = {s.metadata["category"] for s in sources}
        assert categories == _FIXTURE_CATEGORIES

    @pytest.mark.asyncio
    async def test_test_connection_true_when_fixtures_present(self, mock_config):
        connector = MockConnector(mock_config)
        assert await connector.test_connection() is True

    @pytest.mark.asyncio
    async def test_test_connection_false_when_dir_missing(self, mock_config):
        mock_config.config["fixtures_dir"] = "/nonexistent/mock/fixtures"
        connector = MockConnector(mock_config)
        assert await connector.test_connection() is False


class TestMockConnectorFetchContent:
    @pytest.mark.asyncio
    async def test_fetch_content_normalizes_fixture(self, mock_config):
        connector = MockConnector(mock_config)
        source_id = "mock:test-mock-1:doc:doc-001"
        result = await connector.fetch_content(source_id)
        assert result is not None
        assert result.metadata["category"] == "engineering"
        assert result.metadata["doc_id"] == "doc-001"
        assert "Redis" in result.content

    @pytest.mark.asyncio
    async def test_fetch_content_unknown_doc_returns_none(self, mock_config):
        connector = MockConnector(mock_config)
        result = await connector.fetch_content("mock:test-mock-1:doc:doc-999")
        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_content_malformed_source_id_returns_none(self, mock_config):
        connector = MockConnector(mock_config)
        assert await connector.fetch_content("not-a-mock-id") is None


class TestMockConnectorDetectChanges:
    @pytest.mark.asyncio
    async def test_initial_sync_all_added(self, mock_config):
        connector = MockConnector(mock_config)
        changes = await connector.detect_changes(since=None)
        assert len(changes) == 5
        assert all(c.change_type == "added" for c in changes)

    @pytest.mark.asyncio
    async def test_incremental_sync_only_newer_docs(self, mock_config):
        connector = MockConnector(mock_config)
        since = datetime(2026, 3, 1, tzinfo=timezone.utc)
        changes = await connector.detect_changes(since=since)
        # doc-003/004/005 updated_at are after 2026-03-01; doc-001/002 are not.
        assert len(changes) == 3
        assert all(c.change_type == "modified" for c in changes)


class TestMockConnectorModuleHelpers:
    def test_parse_source_id_valid(self):
        assert _parse_source_id("mock:conn-1:doc:doc-001") == "doc-001"

    def test_parse_source_id_malformed(self):
        assert _parse_source_id("bad:id") is None


class TestMockConnectorCategoryResolution:
    @pytest.fixture(autouse=True)
    def _clean_instances(self):
        original = dict(ConnectorRegistry._instances)
        ConnectorRegistry._instances.clear()
        yield
        ConnectorRegistry._instances.clear()
        ConnectorRegistry._instances.update(original)

    def test_mock_listed_under_test_category(self):
        assert CATEGORY_MAP["test"] == ["mock"]

    def test_resolve_by_category_returns_live_mock_instance(self, mock_config):
        connector = MockConnector(mock_config)
        ConnectorRegistry.add_instance(connector)

        result = ConnectorRegistry.resolve_by_category("test")

        assert connector in result


class TestMockConnectorFullSyncOffline:
    """Exercises the real (non-overridden) AbstractConnector.sync() pipeline."""

    @pytest.mark.asyncio
    async def test_full_sync_ingests_all_fixtures_with_zero_network(self, mock_config):
        connector = MockConnector(mock_config)
        fake_kb = AsyncMock()

        with (
            patch("knowledge.get_knowledge_base", AsyncMock(return_value=fake_kb)),
            patch(
                "autobot_shared.redis_client.get_async_redis_client",
                AsyncMock(return_value=None),
            ),
            patch.object(socket.socket, "connect") as mock_connect,
        ):
            mock_connect.side_effect = AssertionError("MockConnector sync() must not open sockets")
            result = await connector.sync(incremental=False)

        assert mock_connect.call_count == 0
        assert result.status == "success"
        assert result.added == 5
        assert result.errors == []
        assert fake_kb.store_fact.call_count == 5

        # store_fact(text, metadata, fact_id=...) — metadata is positional arg 1.
        ingested_categories = {call.args[1]["category"] for call in fake_kb.store_fact.call_args_list}
        assert ingested_categories == _FIXTURE_CATEGORIES

    @pytest.mark.asyncio
    async def test_discover_fetch_detect_never_touch_a_socket(self, mock_config):
        """Direct proof the connector's own methods make zero network calls."""
        connector = MockConnector(mock_config)

        with patch.object(socket.socket, "connect") as mock_connect:
            mock_connect.side_effect = AssertionError("must not open sockets")
            await connector.discover_sources()
            await connector.fetch_content("mock:test-mock-1:doc:doc-001")
            await connector.detect_changes(since=None)
            await connector.test_connection()

        assert mock_connect.call_count == 0


class TestMockConnectorInMemoryDocs:
    """Unit tests that don't want real fixture files can pass docs= directly."""

    @pytest.mark.asyncio
    async def test_docs_override_bypasses_filesystem(self, mock_config):
        docs = [
            {
                "id": "custom-1",
                "title": "Custom Doc",
                "category": "custom",
                "author": "tester",
                "updated_at": "2026-06-01T00:00:00+00:00",
                "content": "custom content",
            }
        ]
        connector = MockConnector(mock_config, docs=docs)
        sources = await connector.discover_sources()
        assert len(sources) == 1
        assert sources[0].metadata["category"] == "custom"
