# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Acceptance tests for WebCrawlerConnector (Issue #8151).

Uses a mocked WebFetcher so no live HTTP requests are made.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.testing.acceptance import ConnectorAcceptanceTest
from knowledge.connectors.web_crawler import WebCrawlerConnector
from web_fetch import FetchResult


def _web_crawler_config() -> ConnectorConfig:
    return ConnectorConfig(
        connector_id="test-web-crawler-001",
        connector_type="web_crawler",
        name="Test Web Crawler",
        config={
            "urls": ["https://example.com"],
            "max_depth": 1,
            "max_pages": 10,
            "respect_robots": False,
            "same_origin": True,
        },
    )


def _mock_fetch_result(url: str = "https://example.com") -> FetchResult:
    return FetchResult(
        url=url,
        success=True,
        markdown="# Example\n\nTest content for acceptance test.",
        title="Example Domain",
        status_code=200,
    )


class TestWebCrawlerConnectorAcceptance(ConnectorAcceptanceTest):
    """Acceptance test suite for WebCrawlerConnector."""

    @pytest.fixture(autouse=True)
    def setup(self):
        cfg = _web_crawler_config()
        self.connector = WebCrawlerConnector(cfg)

        mock_result = _mock_fetch_result()

        # Patch WebFetcher.fetch so no real HTTP calls are made
        patcher_fetch = patch(
            "web_fetch.WebFetcher.fetch",
            new=AsyncMock(return_value=mock_result),
        )
        # Patch fetch_raw_html for the crawl path
        patcher_raw = patch(
            "web_fetch.WebFetcher.fetch_raw_html",
            new=AsyncMock(return_value=("<html><body>Test</body></html>", 200)),
        )
        # Patch KB ingestion
        patcher_kb = patch(
            "knowledge.connectors.base.AbstractConnector._ingest_content",
            new=AsyncMock(),
        )
        # Patch robots cache
        patcher_robots = patch(
            "knowledge.connectors.web_crawler.WebCrawlerConnector._build_robots_cache",
            new=AsyncMock(return_value=None),
        )
        # Patch checkpoint methods to avoid Redis
        patcher_cp_read = patch(
            "knowledge.connectors.base.AbstractConnector._read_checkpoint",
            new=AsyncMock(return_value=set()),
        )
        patcher_cp_write = patch(
            "knowledge.connectors.base.AbstractConnector._write_checkpoint",
            new=AsyncMock(),
        )
        patcher_cp_clear = patch(
            "knowledge.connectors.base.AbstractConnector._clear_checkpoint",
            new=AsyncMock(),
        )
        patcher_job = patch(
            "knowledge.connectors.base.AbstractConnector._write_job_state",
            new=AsyncMock(),
        )

        self.patchers = [
            patcher_fetch,
            patcher_raw,
            patcher_kb,
            patcher_robots,
            patcher_cp_read,
            patcher_cp_write,
            patcher_cp_clear,
            patcher_job,
        ]
        for p in self.patchers:
            p.start()
        yield
        for p in self.patchers:
            p.stop()
