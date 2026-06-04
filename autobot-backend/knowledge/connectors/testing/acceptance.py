# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Acceptance Test Harness for AbstractConnector

Issue #8151: Shared pytest base class that exercises every AbstractConnector
implementation against the interface contract. Subclass and set ``connector``
to a configured instance to inherit the full suite.

Usage::

    class TestMyConnector(ConnectorAcceptanceTest):
        @pytest.fixture(autouse=True)
        def setup(self, ...):
            self.connector = MyConnector(config)
"""

import pytest

from knowledge.connectors.models import (
    ChangeInfo,
    ContentResult,
    SourceInfo,
    SyncResult,
)


class ConnectorAcceptanceTest:
    """Base class for connector acceptance tests.

    Subclass and set ``self.connector`` in an ``autouse`` fixture before each
    test.  All async tests are decorated with ``@pytest.mark.asyncio`` and run
    against the real connector interface — mocking is the subclass's concern.
    """

    connector = None  # set by subclass fixture

    # ------------------------------------------------------------------
    # test_connection
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_connection_returns_bool(self):
        result = await self.connector.test_connection()
        assert isinstance(result, bool), "test_connection() must return bool, got %s" % type(result).__name__

    # ------------------------------------------------------------------
    # discover_sources
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_discover_sources_returns_list(self):
        sources = await self.connector.discover_sources()
        assert isinstance(sources, list), "discover_sources() must return list, got %s" % type(sources).__name__

    @pytest.mark.asyncio
    async def test_discover_sources_items_are_source_info(self):
        sources = await self.connector.discover_sources()
        for s in sources:
            assert isinstance(s, SourceInfo), "discover_sources() items must be SourceInfo, got %s" % type(s).__name__
            assert s.source_id, "SourceInfo.source_id must not be empty"
            assert s.name, "SourceInfo.name must not be empty"

    # ------------------------------------------------------------------
    # fetch_content
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fetch_content_returns_content_result_or_none(self):
        sources = await self.connector.discover_sources()
        if not sources:
            pytest.skip("No sources discovered — skipping fetch_content test")
        result = await self.connector.fetch_content(sources[0].source_id)
        assert result is None or isinstance(result, ContentResult), (
            "fetch_content() must return ContentResult or None, got %s" % type(result).__name__
        )

    @pytest.mark.asyncio
    async def test_fetch_content_result_has_required_fields(self):
        sources = await self.connector.discover_sources()
        if not sources:
            pytest.skip("No sources discovered — skipping fetch_content field test")
        result = await self.connector.fetch_content(sources[0].source_id)
        if result is None:
            return
        assert result.source_id, "ContentResult.source_id must not be empty"
        assert isinstance(result.content, str), "ContentResult.content must be str"
        assert isinstance(result.metadata, dict), "ContentResult.metadata must be dict"

    # ------------------------------------------------------------------
    # detect_changes
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_detect_changes_returns_list(self):
        changes = await self.connector.detect_changes(since=None)
        assert isinstance(changes, list), "detect_changes() must return list, got %s" % type(changes).__name__

    @pytest.mark.asyncio
    async def test_detect_changes_items_are_change_info(self):
        changes = await self.connector.detect_changes(since=None)
        for c in changes:
            assert isinstance(c, ChangeInfo), "detect_changes() items must be ChangeInfo, got %s" % type(c).__name__
            assert c.source_id, "ChangeInfo.source_id must not be empty"
            assert c.change_type in (
                "added",
                "modified",
                "deleted",
            ), "ChangeInfo.change_type must be 'added', 'modified', or 'deleted'"

    # ------------------------------------------------------------------
    # sync
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_sync_full_returns_valid_sync_result(self):
        result = await self.connector.sync(incremental=False)
        assert isinstance(result, SyncResult), "sync() must return SyncResult, got %s" % type(result).__name__
        assert result.connector_id, "SyncResult.connector_id must not be empty"
        assert result.started_at is not None, "SyncResult.started_at must not be None"
        assert isinstance(result.added, int), "SyncResult.added must be int"
        assert isinstance(result.errors, list), "SyncResult.errors must be list"
        assert result.status in (
            "success",
            "partial",
            "failed",
        ), "SyncResult.status must be 'success', 'partial', or 'failed'"

    @pytest.mark.asyncio
    async def test_sync_incremental_returns_valid_sync_result(self):
        result = await self.connector.sync(incremental=True)
        assert isinstance(result, SyncResult)
        assert result.connector_id
        assert result.started_at is not None

    @pytest.mark.asyncio
    async def test_incremental_sync_does_not_exceed_full_sync_count(self):
        full = await self.connector.sync(incremental=False)
        incremental = await self.connector.sync(incremental=True)
        assert incremental.added <= full.added, "Incremental sync added=%d should not exceed full sync added=%d" % (
            incremental.added,
            full.added,
        )
