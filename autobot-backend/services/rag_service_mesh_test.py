#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for Neural Mesh RAG feature flags and RAGService mesh path (#2059, #4686).

NOTE: mesh_retriever_enabled and _mesh_retriever were removed from RAGService in
#4686 — those injection-gate tests are gone. The remaining mesh flags (mesh_seed_edges,
mesh_edge_learner, etc.) live in RAGConfig and are tested here.
"""

import pytest


# =============================================================================
# Test: RAGConfig mesh flag defaults
# =============================================================================


class TestMeshFeatureFlagsDefaultValues:
    """All remaining mesh feature flags must have the correct defaults."""

    def test_mesh_feature_flags_default_values(self):
        """Verify mesh flags have correct defaults from RAGConfig()."""
        from services.rag_config import RAGConfig

        cfg = RAGConfig()
        assert cfg.mesh_seed_edges is True
        assert cfg.mesh_edge_learner is False
        assert cfg.mesh_edge_discoverer is False
        assert cfg.mesh_pruner is False
        assert cfg.mesh_node_promoter is False


# =============================================================================
# Test: to_dict() includes mesh flags
# =============================================================================


class TestRAGConfigSerializationIncludesMeshFlags:
    """RAGConfig.to_dict() must expose the mesh flags for YAML round-trips."""

    def test_rag_config_serialization_includes_mesh_flags(self):
        """to_dict() contains mesh flag keys with correct default values."""
        from services.rag_config import RAGConfig

        d = RAGConfig().to_dict()
        assert d["mesh_seed_edges"] is True
        assert d["mesh_edge_learner"] is False
        assert d["mesh_edge_discoverer"] is False
        assert d["mesh_pruner"] is False
        assert d["mesh_node_promoter"] is False
        # mesh_retriever_enabled was removed in #4686
        assert "mesh_retriever_enabled" not in d

    def test_from_dict_round_trips_mesh_flags(self):
        """from_dict(to_dict()) preserves non-default mesh flag values."""
        from services.rag_config import RAGConfig

        original = RAGConfig()
        original.mesh_edge_learner = True
        d = original.to_dict()

        restored = RAGConfig.from_dict(d)
        assert restored.mesh_edge_learner is True
        # Unmodified flags stay at defaults
        assert restored.mesh_seed_edges is True
        assert restored.mesh_edge_discoverer is False
