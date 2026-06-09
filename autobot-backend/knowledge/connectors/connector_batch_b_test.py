# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for connector batch B features (Issues #8147, #8148, #8149).

Covers:
  - output_schema() classmethod defaults and concrete implementations (#8147)
  - _validate_metadata() pass / fail / no-schema cases (#8147)
  - max_concurrency property default and config override (#8148)
  - sync() parallel path via asyncio.gather + Semaphore (#8148)
  - SyncResult source counters populated correctly (#8148/#8149)
"""

import os
import sys
import types
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WORKTREE_ROOT = os.path.dirname(_BACKEND_DIR)
for _p in (_WORKTREE_ROOT, _BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Stub web_fetch before any connector import triggers its load.
# web_fetch.cache calls config.web_fetch_cache_ttl (a MiscConfig field) directly
# on AutoBotConfig, which fails in test env.  Tests here don't exercise web_fetch
# at runtime; stubs satisfy the import chain only.
if "web_fetch" not in sys.modules:

    def _make_wf_stub(name: str) -> types.ModuleType:
        m = types.ModuleType(name)
        m.__path__ = []  # type: ignore[attr-defined]
        m.__package__ = name
        m.__getattr__ = lambda attr: MagicMock()  # type: ignore[attr-defined]
        sys.modules[name] = m
        return m

    _wf = _make_wf_stub("web_fetch")
    _wf.ERR_CONNECTION = "err_connection"  # type: ignore[attr-defined]
    _wf.FetchResult = MagicMock  # type: ignore[attr-defined]
    _wf.Frontier = MagicMock  # type: ignore[attr-defined]
    _wf.RenderMode = MagicMock  # type: ignore[attr-defined]
    _wf.RobotsCache = MagicMock  # type: ignore[attr-defined]
    _wf.WebFetcher = MagicMock  # type: ignore[attr-defined]
    _make_wf_stub("web_fetch.extractors").extract_markdown = MagicMock()  # type: ignore[attr-defined]
    _make_wf_stub("web_fetch.frontier").extract_links = MagicMock()  # type: ignore[attr-defined]
    _make_wf_stub("web_fetch.cache")
    _make_wf_stub("web_fetch.fetcher")

from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.file_server import FileServerConnector
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SyncResult,
)
from knowledge.connectors.web_crawler import WebCrawlerConnector

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(extra: dict | None = None) -> ConnectorConfig:
    base = {
        "connector_id": "test-id",
        "connector_type": "file_server",
        "name": "test",
        "config": {"base_path": "/tmp/test"},  # nosec B108 - test/controlled code uses tmpdir intentionally
    }
    if extra:
        base.update(extra)
    return ConnectorConfig(**base)


def _web_config() -> ConnectorConfig:
    return ConnectorConfig(
        connector_id="web-id",
        connector_type="web_crawler",
        name="web test",
        config={"urls": ["http://example.com"]},
    )


class _MinimalConnector(AbstractConnector):
    """Concrete subclass that satisfies ABC with empty stubs."""

    connector_type = "test"

    async def test_connection(self) -> bool:
        return True

    async def discover_sources(self):
        return []

    async def fetch_content(self, source_id: str):
        return None

    async def detect_changes(self, since=None):
        return []


# ---------------------------------------------------------------------------
# Issue #8147 — output_schema()
# ---------------------------------------------------------------------------


class TestOutputSchema:
    def test_base_default_empty(self):
        assert AbstractConnector.output_schema() == {}

    def test_minimal_connector_inherits_empty(self):
        conn = _MinimalConnector(_config())
        assert conn.output_schema() == {}

    def test_file_server_schema_has_required(self):
        schema = FileServerConnector.output_schema()
        assert "required" in schema
        assert "path" in schema["required"]
        assert "name" in schema["required"]
        assert "extension" in schema["required"]

    def test_file_server_schema_properties(self):
        schema = FileServerConnector.output_schema()
        props = schema.get("properties", {})
        assert "path" in props
        assert "relative_path" in props
        assert props["path"]["type"] == "string"

    def test_web_crawler_schema_has_required(self):
        schema = WebCrawlerConnector.output_schema()
        assert "url" in schema.get("required", [])
        assert "domain" in schema.get("required", [])

    def test_web_crawler_schema_properties(self):
        schema = WebCrawlerConnector.output_schema()
        props = schema.get("properties", {})
        assert "url" in props
        assert "title" in props


# ---------------------------------------------------------------------------
# Issue #8147 — _validate_metadata()
# ---------------------------------------------------------------------------


class TestValidateMetadata:
    def setup_method(self):
        self.conn = FileServerConnector(_config())
        self.result = SyncResult(
            connector_id="test-id",
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            status="running",
        )

    def _content(self, metadata: dict) -> ContentResult:
        return ContentResult(
            source_id="s1",
            content="hello",
            content_type="text/plain",
            metadata=metadata,
        )

    def test_valid_metadata_no_errors(self):
        content = self._content({"path": "/x", "name": "f.txt", "extension": ".txt"})
        self.conn._validate_metadata(content, self.result)
        assert len(self.result.errors) == 0

    def test_missing_required_field(self):
        content = self._content({"path": "/x", "name": "f.txt"})  # missing extension
        self.conn._validate_metadata(content, self.result)
        assert any("extension" in e for e in self.result.errors)

    def test_wrong_type_logs_error(self):
        content = self._content({"path": "/x", "name": "f.txt", "extension": 123})  # int not str
        self.conn._validate_metadata(content, self.result)
        assert any("extension" in e for e in self.result.errors)

    def test_no_schema_no_errors(self):
        conn = _MinimalConnector(_config())
        result = SyncResult(
            connector_id="test-id",
            started_at=datetime.now(timezone.utc),
            completed_at=None,
            status="running",
        )
        conn._validate_metadata(self._content({}), result)
        assert len(result.errors) == 0


# ---------------------------------------------------------------------------
# Issue #8148 — max_concurrency
# ---------------------------------------------------------------------------


class TestMaxConcurrency:
    def test_base_default_is_1(self):
        conn = _MinimalConnector(_config())
        assert conn.max_concurrency == 1

    def test_config_override(self):
        conn = _MinimalConnector(_config({"max_concurrency": 4}))
        assert conn.max_concurrency == 4

    def test_config_none_falls_back_to_default(self):
        conn = _MinimalConnector(_config({"max_concurrency": None}))
        assert conn.max_concurrency == 1

    def test_web_crawler_default_is_5(self):
        conn = WebCrawlerConnector(_web_config())
        assert conn.max_concurrency == 5

    def test_web_crawler_config_override(self):
        cfg = _web_config()
        cfg.max_concurrency = 2
        conn = WebCrawlerConnector(cfg)
        assert conn.max_concurrency == 2


# ---------------------------------------------------------------------------
# Issue #8148 — sync() parallel path
# ---------------------------------------------------------------------------


class TestSyncParallelPath:
    """Verify that sync() uses asyncio.gather when max_concurrency > 1."""

    def _make_connector(self, max_c: int, num_changes: int):
        class _Spy(AbstractConnector):
            connector_type = "spy"
            _calls: list = []

            @property
            def max_concurrency(self):
                return max_c

            async def test_connection(self):
                return True

            async def discover_sources(self):
                return []

            async def fetch_content(self, source_id):
                return ContentResult(
                    source_id=source_id,
                    content="x",
                    content_type="text/plain",
                    metadata={"path": "/p", "name": "n", "extension": ".txt"},
                )

            async def detect_changes(self, since=None):
                return [
                    ChangeInfo(
                        source_id="s%d" % i,
                        change_type="added",
                        timestamp=datetime.now(timezone.utc),
                    )
                    for i in range(num_changes)
                ]

        return _Spy(_config({"max_concurrency": max_c}))

    @pytest.mark.asyncio
    async def test_sequential_path_all_added(self):
        conn = self._make_connector(max_c=1, num_changes=3)
        with (
            patch.object(conn, "_ingest_content", new_callable=AsyncMock) as ingest,
            patch.object(conn, "_write_job_state", new_callable=AsyncMock),
        ):
            result = await conn.sync(incremental=False)
        assert result.added == 3
        assert ingest.call_count == 3

    @pytest.mark.asyncio
    async def test_parallel_path_all_added(self):
        conn = self._make_connector(max_c=3, num_changes=6)
        with (
            patch.object(conn, "_ingest_content", new_callable=AsyncMock) as ingest,
            patch.object(conn, "_write_job_state", new_callable=AsyncMock),
        ):
            result = await conn.sync(incremental=False)
        assert result.added == 6
        assert ingest.call_count == 6

    @pytest.mark.asyncio
    async def test_parallel_error_isolation(self):
        """A single source failure must not abort remaining sources."""

        class _ErrConnector(AbstractConnector):
            connector_type = "err"

            @property
            def max_concurrency(self):
                return 3

            async def test_connection(self):
                return True

            async def discover_sources(self):
                return []

            async def fetch_content(self, source_id):
                if source_id == "s1":
                    raise RuntimeError("boom")
                return ContentResult(
                    source_id=source_id,
                    content="x",
                    content_type="text/plain",
                    metadata={},
                )

            async def detect_changes(self, since=None):
                return [
                    ChangeInfo(source_id="s%d" % i, change_type="added", timestamp=datetime.now(timezone.utc))
                    for i in range(4)
                ]

        conn = _ErrConnector(_config({"max_concurrency": 3}))
        with (
            patch.object(conn, "_ingest_content", new_callable=AsyncMock),
            patch.object(conn, "_write_job_state", new_callable=AsyncMock),
        ):
            result = await conn.sync(incremental=False)

        assert result.status == "partial"
        assert result.added == 3  # s0, s2, s3 succeed
        assert any("s1" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_sources_total_and_done_counted(self):
        conn = self._make_connector(max_c=1, num_changes=5)
        with (
            patch.object(conn, "_ingest_content", new_callable=AsyncMock),
            patch.object(conn, "_write_job_state", new_callable=AsyncMock),
        ):
            result = await conn.sync(incremental=False)
        assert result.sources_total == 5
        assert result.sources_done == 5
        assert result.sources_failed == 0
