# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for staleness propagation wired into DocumentationWatcherService (#2547).

Covers:
- _propagate_staleness_for_doc() triggers propagation, store, and enqueue
- _propagate_staleness_for_doc() swallows errors to avoid breaking indexing
- _handle_update() calls _propagate_staleness_for_doc() after a successful
  enqueue_reindex (#4453 moved indexing onto DocumentSyncQueue, so there is
  no per-file index result anymore — propagation follows the enqueue)
- _handle_update() does NOT propagate when the indexer is unavailable or the
  enqueue fails

#11687: realigned with the current module — the Redis seam is the async
``get_async_redis_client`` and ``get_doc_indexer_service`` is imported
function-locally from ``services.knowledge.doc_indexer``.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import the seam module BEFORE any patch() call so mock.patch targets the
# canonical sys.modules entry — when patch() itself triggers the first import,
# the watcher's function-local import can resolve a different module object
# and the patches silently miss (#11687).
import services.knowledge.doc_indexer  # noqa: F401
import services.mesh_brain.staleness_propagator  # noqa: F401
from services.documentation_watcher import PROJECT_ROOT, DocumentationWatcherService

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
            patch(
                "autobot_shared.redis_client.get_async_redis_client",
                new=AsyncMock(return_value=mock_redis),
            ),
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
            "autobot_shared.redis_client.get_async_redis_client",
            side_effect=RuntimeError("Redis is down"),
        ):
            # Must not raise
            await watcher._propagate_staleness_for_doc("docs/guide.md")


# =============================================================================
# _handle_update integration
# =============================================================================


class TestHandleUpdateCallsStaleness:
    """_handle_update triggers staleness propagation only after a good enqueue."""

    @pytest.mark.asyncio
    async def test_staleness_called_on_success(self) -> None:
        """Staleness propagation is triggered after enqueue_reindex succeeds."""
        watcher = DocumentationWatcherService()
        file_path = PROJECT_ROOT / "docs" / "guide.md"

        mock_indexer = AsyncMock()
        mock_indexer.initialize = AsyncMock(return_value=True)
        mock_indexer.enqueue_reindex = AsyncMock()

        with (
            patch(
                "services.knowledge.doc_indexer.get_doc_indexer_service",
                return_value=mock_indexer,
            ),
            patch.object(
                watcher,
                "_propagate_staleness_for_doc",
                new=AsyncMock(),
            ) as mock_propagate,
        ):
            await watcher._handle_update(file_path)

        mock_indexer.enqueue_reindex.assert_awaited_once()
        mock_propagate.assert_awaited_once_with("docs/guide.md")

    @pytest.mark.asyncio
    async def test_staleness_not_called_when_indexer_unavailable(self) -> None:
        """Staleness propagation is NOT triggered when the indexer can't initialize."""
        watcher = DocumentationWatcherService()
        file_path = PROJECT_ROOT / "docs" / "guide.md"

        mock_indexer = AsyncMock()
        mock_indexer.initialize = AsyncMock(return_value=False)

        with (
            patch(
                "services.knowledge.doc_indexer.get_doc_indexer_service",
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
        """Staleness propagation is NOT triggered when enqueue_reindex fails."""
        watcher = DocumentationWatcherService()
        file_path = PROJECT_ROOT / "docs" / "guide.md"

        mock_indexer = AsyncMock()
        mock_indexer.initialize = AsyncMock(return_value=True)
        mock_indexer.enqueue_reindex = AsyncMock(side_effect=RuntimeError("queue write failed"))

        with (
            patch(
                "services.knowledge.doc_indexer.get_doc_indexer_service",
                return_value=mock_indexer,
            ),
            patch.object(
                watcher,
                "_propagate_staleness_for_doc",
                new=AsyncMock(),
            ) as mock_propagate,
        ):
            with pytest.raises(RuntimeError):
                await watcher._handle_update(file_path)

        mock_propagate.assert_not_awaited()
