# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for RAPTOR recursive clustering in HierarchicalSummarizer (#2027, #2051)."""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

sklearn = pytest.importorskip("sklearn")

from knowledge.pipeline.base import PipelineContext
from knowledge.pipeline.cognifiers.summarizer import HierarchicalSummarizer


class TestClusterEmbeddings:
    """Test k-means clustering on embeddings."""

    def test_clusters_similar_vectors(self):
        summarizer = HierarchicalSummarizer()
        embeddings = np.array(
            [
                [1.0, 0.0],
                [0.9, 0.1],
                [0.0, 1.0],
                [0.1, 0.9],
            ]
        )
        labels = summarizer._cluster_embeddings(embeddings, n_clusters=2)
        assert labels[0] == labels[1]
        assert labels[2] == labels[3]
        assert labels[0] != labels[2]

    def test_single_item_returns_zero_label(self):
        summarizer = HierarchicalSummarizer()
        embeddings = np.array([[1.0, 0.0]])
        labels = summarizer._cluster_embeddings(embeddings, n_clusters=1)
        assert labels[0] == 0


class TestComputeNClusters:
    """Test cluster count derivation."""

    def test_default_range(self):
        s = HierarchicalSummarizer(cluster_size_range=(3, 10))
        assert s._compute_n_clusters(20) == 3  # 20 // 6 = 3

    def test_small_input(self):
        s = HierarchicalSummarizer(cluster_size_range=(3, 10))
        assert s._compute_n_clusters(2) == 1

    def test_custom_range(self):
        s = HierarchicalSummarizer(cluster_size_range=(2, 4))
        assert s._compute_n_clusters(9) == 3  # 9 // 3 = 3


class TestGroupByCluster:
    """Test grouping items by label."""

    def test_groups_correctly(self):
        s = HierarchicalSummarizer()
        items = ["a", "b", "c", "d"]
        labels = np.array([0, 1, 0, 1])
        groups = s._group_by_cluster(items, labels)
        assert groups[0] == ["a", "c"]
        assert groups[1] == ["b", "d"]


class TestBuildRaptorTree:
    """Test full RAPTOR tree building."""

    @pytest.mark.asyncio
    async def test_single_chunk_no_clustering(self):
        s = HierarchicalSummarizer()
        chunk = MagicMock()
        chunk.content = "Single chunk content"
        embeddings = np.array([[1.0, 0.0]])
        tree = await s.build_raptor_tree([chunk], embeddings)
        assert "L0" in tree
        assert len(tree["L0"]) == 1
        assert "L1" not in tree


class TestProcessPopulatesRaptorTree:
    """Verify process() wires build_raptor_tree when embeddings are present (#2051)."""

    @pytest.mark.asyncio
    async def test_raptor_tree_set_when_embeddings_present(self):
        """process() must populate context.raptor_tree when context.embeddings is set."""
        s = HierarchicalSummarizer()

        # Stub every LLM call so no real network I/O occurs.
        stub_summary = MagicMock()
        stub_summary.id = "s1"
        stub_summary.content = "stub"
        stub_summary.parent_summary_id = None
        stub_summary.child_summary_ids = []

        context = PipelineContext()
        chunk = MagicMock()
        chunk.content = "chunk content"
        chunk.id = "c1"
        chunk.document_id = "doc1"
        context.chunks = [chunk]
        context.embeddings = np.array([[1.0, 0.0]])

        fake_tree = {"L0": [chunk]}

        with patch.object(s, "_summarize_text", new=AsyncMock(return_value=stub_summary)):
            with patch.object(s, "build_raptor_tree", new=AsyncMock(return_value=fake_tree)):
                result = await s.process(context)

        assert result.raptor_tree is not None
        assert "L0" in result.raptor_tree

    @pytest.mark.asyncio
    async def test_raptor_tree_skipped_when_no_embeddings(self):
        """process() must leave context.raptor_tree as None when no embeddings."""
        s = HierarchicalSummarizer()

        stub_summary = MagicMock()
        stub_summary.id = "s1"
        stub_summary.content = "stub"
        stub_summary.parent_summary_id = None
        stub_summary.child_summary_ids = []

        context = PipelineContext()
        chunk = MagicMock()
        chunk.content = "chunk content"
        chunk.id = "c1"
        chunk.document_id = "doc1"
        context.chunks = [chunk]
        # embeddings intentionally left as None

        with patch.object(s, "_summarize_text", new=AsyncMock(return_value=stub_summary)):
            with patch.object(s, "build_raptor_tree", new=AsyncMock()) as mock_brt:
                result = await s.process(context)

        mock_brt.assert_not_called()
        assert result.raptor_tree is None
