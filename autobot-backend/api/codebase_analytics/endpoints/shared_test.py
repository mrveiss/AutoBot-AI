# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for trigger_auto_index_if_unindexed (Issue #12364).

Converged analytics panels fall back to a live filesystem walk only when the
indexed store has no data for a source yet; that fallback must also kick off
a background index job so subsequent requests are served from the index
without a manual "Run indexing first" step.
"""

from unittest.mock import AsyncMock, patch

from api.codebase_analytics.endpoints import shared
from api.codebase_analytics.endpoints import sources as sources_ep


class TestTriggerAutoIndexIfUnindexed:
    def setup_method(self):
        shared._auto_index_inflight.clear()

    async def test_noop_when_source_id_falsy(self):
        with patch("api.codebase_analytics.source_storage.get_source", AsyncMock()) as get_source:
            await shared.trigger_auto_index_if_unindexed(None)
        get_source.assert_not_called()

    async def test_noop_when_source_unresolvable(self):
        with patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=None)):
            await shared.trigger_auto_index_if_unindexed("missing-source")
        # Still marked in-flight so a burst of requests for the same
        # unresolvable source doesn't repeatedly hit get_source.
        assert "missing-source" in shared._auto_index_inflight

    async def test_triggers_indexing_for_resolvable_source(self):
        fake_source = AsyncMock()
        fake_source.clone_path = "/tmp/some/clone"

        trigger_mock = AsyncMock()
        with (
            patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=fake_source)),
            patch.object(sources_ep, "_trigger_indexing", trigger_mock),
        ):
            await shared.trigger_auto_index_if_unindexed("src-A")

        trigger_mock.assert_awaited_once_with(fake_source)

    async def test_second_call_for_same_source_is_a_noop(self):
        """Concurrent panel requests against an unindexed source must fire
        exactly one background job, not one per request."""
        fake_source = AsyncMock()
        fake_source.clone_path = "/tmp/some/clone"

        trigger_mock = AsyncMock()
        with (
            patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=fake_source)),
            patch.object(sources_ep, "_trigger_indexing", trigger_mock),
        ):
            await shared.trigger_auto_index_if_unindexed("src-B")
            await shared.trigger_auto_index_if_unindexed("src-B")

        trigger_mock.assert_awaited_once()

    async def test_two_sources_each_trigger_independently(self):
        fake_source = AsyncMock()
        fake_source.clone_path = "/tmp/some/clone"

        trigger_mock = AsyncMock()
        with (
            patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=fake_source)),
            patch.object(sources_ep, "_trigger_indexing", trigger_mock),
        ):
            await shared.trigger_auto_index_if_unindexed("src-C")
            await shared.trigger_auto_index_if_unindexed("src-D")

        assert trigger_mock.await_count == 2
