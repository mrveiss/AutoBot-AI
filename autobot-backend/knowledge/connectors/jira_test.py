# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Jira Knowledge Connector (Issue #10538)

All HTTP calls are mocked — no network access, and the module never makes a
live request just from being imported or instantiated.
"""

from unittest.mock import AsyncMock, patch

import pytest

from knowledge.connectors.jira import JiraConnector
from knowledge.connectors.models import ConnectorConfig


@pytest.fixture
def jira_config():
    return ConnectorConfig(
        connector_id="test-jira-1",
        connector_type="jira",
        name="Test Jira",
        config={
            "base_url": "https://example.atlassian.net",
            "username": "bot@example.com",
            "password": "test-fake-api-credential",
            "project_keys": ["ABC"],
        },
        enabled=True,
        verification_mode="collaborative",
    )


class TestJiraConnectorInit:
    def test_init(self, jira_config):
        connector = JiraConnector(jira_config)
        assert connector.connector_type == "jira"
        assert connector.tier == 2
        assert connector._email == "bot@example.com"
        assert connector._project_keys == ["ABC"]
        assert connector.max_concurrency == 4

    def test_auth_schema(self):
        from autobot_shared.auth import BasicAuth

        assert JiraConnector.auth_schema() == BasicAuth

    def test_output_schema(self):
        schema = JiraConnector.output_schema()
        assert schema["type"] == "object"
        assert "jira_issue_key" in schema["required"]
        assert "jira_project_key" in schema["required"]

    def test_build_jql_default(self, jira_config):
        connector = JiraConnector(jira_config)
        assert connector._build_jql() == "project in (ABC)"

    def test_build_jql_override(self, jira_config):
        jira_config.config["jql"] = "assignee = currentUser()"
        connector = JiraConnector(jira_config)
        assert connector._build_jql() == "assignee = currentUser()"


class TestJiraConnectorConnection:
    @pytest.mark.asyncio
    async def test_test_connection_success(self, jira_config):
        connector = JiraConnector(jira_config)
        with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status_code": 200, "body": {"accountId": "u1"}}
            assert await connector.test_connection() is True

    @pytest.mark.asyncio
    async def test_test_connection_failure(self, jira_config):
        connector = JiraConnector(jira_config)
        with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status_code": 401, "body": {}}
            assert await connector.test_connection() is False


class TestJiraConnectorDiscovery:
    @pytest.mark.asyncio
    async def test_discover_sources(self, jira_config):
        connector = JiraConnector(jira_config)
        search_body = {
            "total": 1,
            "issues": [
                {
                    "key": "ABC-1",
                    "fields": {
                        "summary": "Fix the bug",
                        "project": {"key": "ABC"},
                        "updated": "2026-01-01T00:00:00.000+0000",
                    },
                }
            ],
        }
        with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"status_code": 200, "body": search_body}
            sources = await connector.discover_sources()

        assert len(sources) == 1
        assert sources[0].source_id == "jira:test-jira-1:issue:ABC-1"
        assert sources[0].name == "Fix the bug"

    @pytest.mark.asyncio
    async def test_discover_sources_paginates(self, jira_config):
        """_search() must follow startAt batches until total is reached (#10538)."""
        connector = JiraConnector(jira_config)
        connector._page_size = 1

        def _issue(key: str, updated: str) -> dict:
            return {
                "key": key,
                "fields": {"summary": key, "project": {"key": "ABC"}, "updated": updated},
            }

        page1 = {"total": 2, "issues": [_issue("ABC-1", "2026-01-01T00:00:00.000+0000")]}
        page2 = {"total": 2, "issues": [_issue("ABC-2", "2026-01-02T00:00:00.000+0000")]}
        with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = [
                {"status_code": 200, "body": page1},
                {"status_code": 200, "body": page2},
            ]
            sources = await connector.discover_sources()

        assert mock_post.call_count == 2
        assert {s.source_id for s in sources} == {
            "jira:test-jira-1:issue:ABC-1",
            "jira:test-jira-1:issue:ABC-2",
        }


class TestJiraConnectorFetchContent:
    @pytest.mark.asyncio
    async def test_fetch_content(self, jira_config):
        connector = JiraConnector(jira_config)
        source_id = "jira:test-jira-1:issue:ABC-1"
        issue_body = {
            "key": "ABC-1",
            "fields": {
                "summary": "Fix the bug",
                "status": {"name": "Open"},
                "project": {"key": "ABC"},
                "updated": "2026-01-01T00:00:00.000+0000",
                "description": {"type": "doc", "content": [{"type": "text", "text": "Steps to reproduce"}]},
                "comment": {
                    "comments": [
                        {
                            "author": {"displayName": "Alice"},
                            "body": {"type": "doc", "content": [{"type": "text", "text": "Looking into it"}]},
                        }
                    ]
                },
            },
        }
        with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status_code": 200, "body": issue_body}
            result = await connector.fetch_content(source_id)

        assert result is not None
        assert "Fix the bug" in result.content
        assert "Steps to reproduce" in result.content
        assert "Alice" in result.content
        assert result.metadata["jira_issue_key"] == "ABC-1"
        assert result.metadata["jira_project_key"] == "ABC"
        assert result.metadata["comment_count"] == 1

    @pytest.mark.asyncio
    async def test_fetch_content_malformed_source_id(self, jira_config):
        connector = JiraConnector(jira_config)
        assert await connector.fetch_content("not-a-jira-id") is None

    @pytest.mark.asyncio
    async def test_fetch_content_not_found(self, jira_config):
        connector = JiraConnector(jira_config)
        source_id = "jira:test-jira-1:issue:ABC-999"
        with patch.object(connector, "_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"status_code": 404, "body": {}}
            assert await connector.fetch_content(source_id) is None


class TestJiraConnectorChangeDetection:
    @pytest.mark.asyncio
    async def test_detect_changes_initial_sync(self, jira_config):
        connector = JiraConnector(jira_config)
        search_body = {
            "total": 1,
            "issues": [
                {"key": "ABC-1", "fields": {"updated": "2026-01-01T00:00:00.000+0000"}},
            ],
        }
        with patch.object(connector, "_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"status_code": 200, "body": search_body}
            changes = await connector.detect_changes(since=None)

        assert len(changes) == 1
        assert changes[0].change_type == "added"
        assert changes[0].source_id == "jira:test-jira-1:issue:ABC-1"


class TestJiraModuleHelpers:
    def test_adf_to_text_plain_paragraph(self):
        from knowledge.connectors.jira import _adf_to_text

        node = {"type": "doc", "content": [{"type": "text", "text": "hello"}]}
        assert _adf_to_text(node) == "hello"

    def test_adf_to_text_none(self):
        from knowledge.connectors.jira import _adf_to_text

        assert _adf_to_text(None) == ""

    def test_adf_to_text_legacy_string(self):
        from knowledge.connectors.jira import _adf_to_text

        assert _adf_to_text("plain text body") == "plain text body"

    def test_parse_issue_key_valid(self):
        from knowledge.connectors.jira import _parse_issue_key

        assert _parse_issue_key("jira:conn-1:issue:ABC-1") == "ABC-1"

    def test_parse_issue_key_malformed(self):
        from knowledge.connectors.jira import _parse_issue_key

        assert _parse_issue_key("bad:id") is None
