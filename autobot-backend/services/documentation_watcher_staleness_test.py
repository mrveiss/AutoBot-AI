# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for staleness propagation wired into DocumentationWatcherService (#2547).

Covers:
- _propagate_staleness_for_doc() triggers propagation, store, and enqueue
- _propagate_staleness_for_doc() swallows errors to avoid breaking indexing
- _handle_update() calls _propagate_staleness_for_doc() on successful indexing
- _handle_update() does NOT call _propagate_staleness_for_doc() on skip/failure
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.documentation_watcher import DocumentationWatcherService

# =============================================================================
# _propagate_staleness_for_doc
# =============================================================================


class TestPropagateStalnessForDoc:
    """Unit tests for _propagate_staleness_for_doc."""

    @pytest.mark.asyncio
    async def test_propagation_calls_all_three_steps(self) -> None:
        """On success: propagate, store, and enqueue are all called."""
        watcher = DocumentationWatcherService()

        mock_redis = AsyncMock()
        mock_graph = MagicMock()
        mock_staleness_result = MagicMock()
        mock_staleness_result.scores = {"source": 1.0, "neighbor": 0.6}
        mock_staleness_result.flagged_for_reembedding = MagicMock(return_value=["neighbor"])

        with (
            patch("autobot_shared.redis_client.get_redis_client", return_value=mock_redis),
            patch(
                "services.mesh_brain.staleness_propagator.RedisGraphAdapter",
                return_value=mock_graph,
            ),
            patch(
                "services.mesh_brain.staleness_propagator.propagate_staleness",
                new=AsyncMock(return_value=mock_staleness_result),
            ),
            patch(
                "services.mesh_brain.staleness_propagator.store_staleness_scores",
                new=AsyncMock(return_value=2),
            ) as mock_store,
            patch(
                "services.mesh_brain.staleness_propagator.enqueue_for_reembedding",
                new=AsyncMock(return_value=1),
            ) as mock_enqueue,
        ):
            await watcher._propagate_staleness_for_doc("docs/guide.md")

        mock_store.assert_awaited_once()
        mock_enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_propagation_swallows_exceptions(self) -> None:
        """Errors in staleness propagation do not propagate to the caller."""
        watcher = DocumentationWatcherService()

        with patch(
            "autobot_shared.redis_client.get_redis_client",
            side_effect=RuntimeError("Redis is down"),
        ):
            # Must not raise
            await watcher._propagate_staleness_for_doc("docs/guide.md")


# =============================================================================
# _handle_update integration
# =============================================================================


class TestHandleUpdateCallsStaleness:
    """_handle_update triggers staleness propagation only on success."""

    def _make_index_result(self, success=0, skipped=0, failed=0, errors=None):
        result = MagicMock()
        result.success = success
        result.skipped = skipped
        result.failed = failed
        result.errors = errors or []
        return result

    @pytest.mark.asyncio
    async def test_staleness_called_on_success(self) -> None:
        """Staleness propagation is triggered when index_file returns success > 0."""
        watcher = DocumentationWatcherService()
        file_path = Path("/fake/docs/guide.md")

        mock_indexer = AsyncMock()
        mock_indexer.initialize = AsyncMock(return_value=True)
        mock_indexer.index_file = AsyncMock(return_value=self._make_index_result(success=1))

        with (
            patch(
                "services.documentation_watcher.get_doc_indexer_service",
                return_value=mock_indexer,
            ),
            patch.object(
                watcher,
                "_propagate_staleness_for_doc",
                new=AsyncMock(),
            ) as mock_propagate,
        ):
            await watcher._handle_update(file_path)

        mock_propagate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_staleness_not_called_on_skip(self) -> None:
        """Staleness propagation is NOT triggered when file is skipped."""
        watcher = DocumentationWatcherService()
        file_path = Path("/fake/docs/guide.md")

        mock_indexer = AsyncMock()
        mock_indexer.initialize = AsyncMock(return_value=True)
        mock_indexer.index_file = AsyncMock(return_value=self._make_index_result(skipped=1))

        with (
            patch(
                "services.documentation_watcher.get_doc_indexer_service",
                return_value=mock_indexer,
            ),
            patch.object(
                watcher,
                "_propagate_staleness_for_doc",
                new=AsyncMock(),
            ) as mock_propagate,
        ):
            await watcher._handle_update(file_path)

        mock_propagate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_staleness_not_called_on_failure(self) -> None:
        """Staleness propagation is NOT triggered when indexing fails."""
        watcher = DocumentationWatcherService()
        file_path = Path("/fake/docs/guide.md")

        mock_indexer = AsyncMock()
        mock_indexer.initialize = AsyncMock(return_value=True)
        mock_indexer.index_file = AsyncMock(return_value=self._make_index_result(failed=1, errors=["some error"]))

        with (
            patch(
                "services.documentation_watcher.get_doc_indexer_service",
                return_value=mock_indexer,
            ),
            patch.object(
                watcher,
                "_propagate_staleness_for_doc",
                new=AsyncMock(),
            ) as mock_propagate,
        ):
            await watcher._handle_update(file_path)

        mock_propagate.assert_not_awaited()
