# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Acceptance tests for FileServerConnector (Issue #8151).

Reference implementation of ConnectorAcceptanceTest.  Uses a tmp_path
populated with real text files so no external services are needed.
"""

from unittest.mock import AsyncMock, patch

import pytest

from knowledge.connectors.file_server import FileServerConnector
from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.testing.acceptance import ConnectorAcceptanceTest


def _file_server_config(tmp_path) -> ConnectorConfig:
    return ConnectorConfig(
        connector_id="test-file-server-001",
        connector_type="file_server",
        name="Test File Server",
        config={
            "base_path": str(tmp_path),
            # Use patterns without mandatory directory prefix so root-level
            # test files are discovered (fnmatch: "**/*.txt" requires a "/").
            "include_patterns": ["*.txt", "*.md", "docs/**/*.txt", "docs/**/*.md"],
            "exclude_patterns": [],
        },
    )


class TestFileServerConnectorAcceptance(ConnectorAcceptanceTest):
    """Acceptance test suite for FileServerConnector."""

    @pytest.fixture(autouse=True)
    def setup(self, tmp_path):
        (tmp_path / "hello.txt").write_text("Hello, world!", encoding="utf-8")
        (tmp_path / "readme.md").write_text("# README\nContent here.", encoding="utf-8")
        (tmp_path / "data.json").write_text('{"key": "value"}', encoding="utf-8")

        cfg = _file_server_config(tmp_path)
        self.connector = FileServerConnector(cfg)

        # Patch KB ingestion so sync() doesn't need a real KB
        patcher = patch(
            "knowledge.connectors.base.AbstractConnector._ingest_content",
            new=AsyncMock(),
        )
        patcher.start()
        yield
        patcher.stop()
