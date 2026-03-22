# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for RAPTOR recursive clustering in HierarchicalSummarizer (#2027)."""
import numpy as np
import pytest

sklearn = pytest.importorskip("sklearn")

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
        from unittest.mock import MagicMock

        chunk = MagicMock()
        chunk.content = "Single chunk content"
        embeddings = np.array([[1.0, 0.0]])
        tree = await s.build_raptor_tree([chunk], embeddings)
        assert "L0" in tree
        assert len(tree["L0"]) == 1
        assert "L1" not in tree
