# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One functional, end-to-end test per #16985 connector (#16985 AC2).

connector_redaction_guard_test.py proves the SHAPE of the code is right --
every connector reaches ``kb.store_fact()`` (statically, via source
inspection). This file proves the BEHAVIOUR is right: a real credential-
shaped value returned by each connector's own ``fetch_content()`` (or its
audio/external_adapter bypass) does not survive into what
``knowledge.fact_store.persist_fact`` actually receives -- i.e. it is
redacted for real, by the real ``sanitize_fact_content`` call inside
``FactsMixin.store_fact``, not merely by a mock standing in for it.

Each connector's own external dependency (HTTP call, DB query, subprocess,
transcription) is mocked at the narrowest point that still exercises its
real ``fetch_content`` -> ``_ingest_content`` -> ``kb.store_fact`` path;
Redis/ChromaDB/the durable row are faked out the same way
``knowledge/bulk_restore_redaction_test.py`` does it for the restore path.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.connectors.audio_connector import AudioConnector
from knowledge.connectors.confluence import ConfluenceConnector
from knowledge.connectors.database import DatabaseConnector
from knowledge.connectors.external_adapter import ExternalConnectorAdapter
from knowledge.connectors.file_server import FileServerConnector
from knowledge.connectors.gitlab import GitLabConnector
from knowledge.connectors.jira import JiraConnector
from knowledge.connectors.models import ConnectorConfig, SyncResult
from knowledge.connectors.nextcloud import NextcloudConnector
from knowledge.connectors.notion import NotionConnector
from knowledge.connectors.slack import SlackConnector
from knowledge.connectors.web_crawler import WebCrawlerConnector, _url_to_source_id
from knowledge.facts import FactsMixin

_SECRET = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"  # pragma: allowlist secret


class _FakeKB(FactsMixin):
    """Real FactsMixin.store_fact (and therefore real sanitize_fact_content
    redaction), with Redis/ChromaDB/the durable store faked out -- same shape
    as bulk_restore_redaction_test.py's _RestoreFakeKB."""

    embedding_model_name = "test-embed"

    def __init__(self):
        self.redis_client = MagicMock()
        self.vector_store = MagicMock()
        self._aioredis_client = AsyncMock()

    def ensure_initialized(self):
        pass

    async def _increment_stat(self, *_a, **_kw):
        pass

    def _schedule_bm25_refresh(self):
        pass

    async def _check_for_duplicates(self, content, metadata, **_kwargs):
        return None


def _config(connector_type: str, config: dict) -> ConnectorConfig:
    return ConnectorConfig(
        connector_id="test-%s" % connector_type, connector_type=connector_type, name="t", config=config
    )


async def _drive_through_chokepoint(connector, source_id: str) -> dict:
    """Call connector.fetch_content(source_id), then feed the result through
    the real _ingest_content -> kb.store_fact chokepoint. Returns what
    fact_store.persist_fact actually received (the redacted content)."""
    kb = _FakeKB()
    captured: dict = {}

    def _capture_persist(fact_id, content, metadata, **_kw):
        captured["content"] = content
        captured["metadata"] = metadata

    with (
        patch("knowledge.get_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_capture_persist)),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        content = await connector.fetch_content(source_id)
        assert content is not None, "fetch_content returned None -- the test's own mocking is broken, not the connector"
        await connector._ingest_content(content)

    assert "content" in captured, "fact_store.persist_fact was never called -- content did not reach the chokepoint"
    return captured


@pytest.mark.asyncio
async def test_confluence_redacts_a_credential():
    connector = ConfluenceConnector(
        _config("confluence", {"base_url": "https://x.atlassian.net/wiki", "space_keys": ["S"]})
    )
    page = {
        "title": "Setup",
        "body": {"storage": {"value": "<p>your api key is %s</p>" % _SECRET}},
        "space": {"key": "S"},
        "version": {"when": "2026-01-01T00:00:00Z"},
    }
    with patch.object(connector, "_get", new=AsyncMock(return_value={"status_code": 200, "body": page})):
        captured = await _drive_through_chokepoint(connector, "confluence:test-confluence:page:123")
    assert _SECRET not in captured["content"]


@pytest.mark.asyncio
async def test_jira_redacts_a_credential():
    connector = JiraConnector(_config("jira", {"base_url": "https://x.atlassian.net", "project_keys": ["P"]}))
    issue = {
        "fields": {
            "summary": "Setup",
            "status": {"name": "Open"},
            "project": {"key": "P"},
            "updated": "2026-01-01T00:00:00Z",
            "description": "your password is %s" % _SECRET,
            "comment": {"comments": []},
        }
    }
    with patch.object(connector, "_get", new=AsyncMock(return_value={"status_code": 200, "body": issue})):
        captured = await _drive_through_chokepoint(connector, "jira:test-jira:issue:PROJ-1")
    assert _SECRET not in captured["content"]


@pytest.mark.asyncio
async def test_notion_redacts_a_credential():
    connector = NotionConnector(_config("notion", {"token": "t", "database_ids": ["d"]}))
    page = {"url": "https://notion.so/p", "last_edited_time": "2026-01-01T00:00:00Z"}
    blocks = {
        "results": [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "the token is %s" % _SECRET}]}}]
    }

    async def _fake_request(method, path, **_kw):
        if path.startswith("/pages/"):
            return {"status_code": 200, "body": page}
        return {"status_code": 200, "body": blocks}

    with patch.object(connector, "_notion_request", new=AsyncMock(side_effect=_fake_request)):
        captured = await _drive_through_chokepoint(connector, "notion-page-1")
    assert _SECRET not in captured["content"]


@pytest.mark.asyncio
async def test_slack_redacts_a_credential():
    connector = SlackConnector(_config("slack", {"token": "t", "channel_ids": ["C1"]}))
    messages = [{"user": "u1", "ts": "1.0", "text": "our api key is %s" % _SECRET}]
    with (
        patch.object(connector, "_history", new=AsyncMock(return_value=messages)),
        patch.object(connector, "_store_ts", new=AsyncMock()),
    ):
        captured = await _drive_through_chokepoint(connector, "slack:test-slack:channel:C1:ts:1.0")
    assert _SECRET not in captured["content"]


@pytest.mark.asyncio
async def test_gitlab_redacts_a_credential():
    connector = GitLabConnector(_config("gitlab", {"gitlab_url": "https://gitlab.example.com", "project_ids": [1]}))
    issue = {
        "iid": 5,
        "title": "Setup",
        "state": "opened",
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
        "description": "the token is %s" % _SECRET,
    }
    with (
        patch.object(connector, "_gl_get", new=AsyncMock(return_value={"status_code": 200, "body": issue})),
        patch.object(connector, "_store_ts", new=AsyncMock()),
    ):
        content = await connector.fetch_content("gitlab:test-gitlab:project:1:issue:5")
        assert content is not None
        kb = _FakeKB()
        captured: dict = {}

        def _capture(fact_id, content_arg, metadata, **_kw):
            captured["content"] = content_arg

        with (
            patch("knowledge.get_knowledge_base", new=AsyncMock(return_value=kb)),
            patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_capture)),
            patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
            patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
        ):
            await connector._ingest_content(content)
    assert _SECRET not in captured["content"]


class _FakeAiohttpResponse:
    def __init__(self, status: int, body: bytes, headers: dict | None = None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def read(self) -> bytes:
        return self._body


class _FakeTrackedRequest:
    def __init__(self, response: _FakeAiohttpResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *_exc):
        return False


class _FakeHttpClient:
    def __init__(self, response: _FakeAiohttpResponse):
        self._response = response

    def tracked_request(self, *_a, **_kw):
        return _FakeTrackedRequest(self._response)


@pytest.mark.asyncio
async def test_nextcloud_redacts_a_credential():
    connector = NextcloudConnector(
        _config("nextcloud", {"nextcloud_url": "https://cloud.example.com", "username": "u", "password": "p"})
    )
    body = ("your password is %s" % _SECRET).encode("utf-8")
    fake_client = _FakeHttpClient(_FakeAiohttpResponse(200, body, {"Content-Type": "text/plain", "Last-Modified": ""}))
    with patch("knowledge.connectors.nextcloud.get_http_client", return_value=fake_client):
        captured = await _drive_through_chokepoint(connector, "nextcloud:test-nextcloud:file:secret.txt")
    assert _SECRET not in captured["content"]


@pytest.mark.asyncio
async def test_database_redacts_a_credential():
    from knowledge.connectors.database import _row_to_source_id

    connector = DatabaseConnector(
        _config(
            "database",
            {"connection_string": "sqlite://", "query": "SELECT 1", "id_column": "id", "content_columns": ["notes"]},
        )
    )
    row = {"id": "1", "notes": "the api key is %s" % _SECRET}
    source_id = _row_to_source_id("test-database", "1")
    with patch.object(connector, "_execute_query", new=AsyncMock(return_value=[row])):
        captured = await _drive_through_chokepoint(connector, source_id)
    assert _SECRET not in captured["content"]


@pytest.mark.asyncio
async def test_external_adapter_redacts_a_credential():
    """external_adapter has no fetch_content path (raises NotImplementedError
    by design -- it streams via sync()); its real chokepoint is
    _handle_record -> _convert_record -> _ingest_content."""
    connector = ExternalConnectorAdapter(_config("external_adapter", {"entrypoint": "x.py"}))
    kb = _FakeKB()
    captured: dict = {}

    def _capture(fact_id, content, metadata, **_kw):
        captured["content"] = content

    msg = {"stream": "notes", "record": {"data": {"note": "the secret is %s" % _SECRET}}}
    result = SyncResult(connector_id="test-external_adapter", started_at=None, completed_at=None, status="failed")
    with (
        patch("knowledge.get_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_capture)),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        await connector._handle_record(msg, result)
    assert result.added == 1, "record was not ingested -- the test's own setup is broken, not the connector"
    assert _SECRET not in captured["content"]


@pytest.mark.asyncio
async def test_web_crawler_redacts_a_credential():
    from web_fetch import FetchResult, WebFetcher

    url = "https://example.com/page"
    connector = WebCrawlerConnector(_config("web_crawler", {"urls": [url]}))
    fetch_result = FetchResult(url=url, success=True, markdown="the token is %s" % _SECRET, title="t", source="test")
    with patch.object(WebFetcher, "fetch", new=AsyncMock(return_value=fetch_result)):
        kb = _FakeKB()
        captured: dict = {}

        def _capture(fact_id, content, metadata, **_kw):
            captured["content"] = content

        with (
            patch("knowledge.get_knowledge_base", new=AsyncMock(return_value=kb)),
            patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_capture)),
            patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
            patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
        ):
            content = await connector.fetch_content(_url_to_source_id(url))
            assert content is not None
            await connector._ingest_content(content)
    assert _SECRET not in captured["content"]


@pytest.mark.asyncio
async def test_audio_connector_redacts_a_credential():
    from knowledge.connectors.audio_connector import _source_id_for
    from knowledge.connectors.models import ContentResult

    source_path = "/tmp/fake.wav"
    source_id = _source_id_for(source_path)
    connector = AudioConnector(_config("audio_connector", {"sources": [source_path]}))
    fake_result = ContentResult(
        source_id=source_id, content="the password is %s" % _SECRET, content_type="text/plain", metadata={}
    )
    kb = _FakeKB()
    captured: dict = {}

    def _capture(fact_id, content, metadata, **_kw):
        captured["content"] = content

    with (
        patch.object(connector, "_transcribe_source", new=AsyncMock(return_value=fake_result)),
        patch("knowledge.get_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_capture)),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        content = await connector.fetch_content(source_id)
        assert content is not None
        await connector._ingest_content(content)
    assert _SECRET not in captured["content"]


@pytest.mark.asyncio
async def test_file_server_redacts_a_credential(tmp_path):
    (tmp_path / "notes.txt").write_text("the secret is %s" % _SECRET, encoding="utf-8")
    connector = FileServerConnector(_config("file_server", {"base_path": str(tmp_path), "include_patterns": ["*.txt"]}))
    sources = await connector.discover_sources()
    assert len(sources) == 1
    kb = _FakeKB()
    captured: dict = {}

    def _capture(fact_id, content, metadata, **_kw):
        captured["content"] = content

    with (
        patch("knowledge.get_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_capture)),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        content = await connector.fetch_content(sources[0].source_id)
        assert content is not None
        await connector._ingest_content(content)
    assert _SECRET not in captured["content"]


@pytest.mark.asyncio
async def test_negative_control_ordinary_content_is_unchanged(tmp_path):
    """Proves the chokepoint doesn't mangle content that has nothing to redact."""
    (tmp_path / "notes.txt").write_text("Redis listens on port 6379.", encoding="utf-8")
    connector = FileServerConnector(_config("file_server", {"base_path": str(tmp_path), "include_patterns": ["*.txt"]}))
    sources = await connector.discover_sources()
    assert len(sources) == 1
    kb = _FakeKB()
    captured: dict = {}

    def _capture(fact_id, content, metadata, **_kw):
        captured["content"] = content

    with (
        patch("knowledge.get_knowledge_base", new=AsyncMock(return_value=kb)),
        patch("knowledge.fact_store.persist_fact", new=AsyncMock(side_effect=_capture)),
        patch.object(type(kb), "_project_fact_to_redis", new=AsyncMock()),
        patch.object(type(kb), "_vectorize_fact_in_chromadb", new=AsyncMock()),
    ):
        content = await connector.fetch_content(sources[0].source_id)
        await connector._ingest_content(content)
    assert captured["content"] == "Redis listens on port 6379."
