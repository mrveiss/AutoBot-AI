# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Structural pytest tests for OptimizedSemanticChunker.

Issue #5439: add pytest coverage for OptimizedSemanticChunker (currently
only manual-script-tested via utils/simple_optimization_test.py).

All tests here avoid loading a real embedding model so they run in the
dev/CI venv without GPU or sentence-transformers installed. The heavy
construction path is mocked at the class level.
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from utils.semantic_chunker_base import SemanticChunk
from utils.semantic_chunker_gpu import GPUSemanticChunker
from utils.semantic_chunker_gpu_optimized import (
    OPTIMIZATION_VERSION,
    OptimizedSemanticChunker,
    get_optimized_semantic_chunker,
)

# ---------------------------------------------------------------------------
# Structural / class-level tests (no model construction required)
# ---------------------------------------------------------------------------


class TestOptimizedSemanticChunkerStructure:
    def test_subclass_relationship(self):
        """OptimizedSemanticChunker must be a GPUSemanticChunker subclass."""
        assert issubclass(OptimizedSemanticChunker, GPUSemanticChunker)

    def test_chunk_text_optimized_exists(self):
        """chunk_text_optimized must exist as a callable member."""
        assert hasattr(OptimizedSemanticChunker, "chunk_text_optimized")
        assert callable(OptimizedSemanticChunker.chunk_text_optimized)

    def test_chunk_text_optimized_is_coroutine_function(self):
        """chunk_text_optimized must be declared async (returns a coroutine)."""
        assert inspect.iscoroutinefunction(OptimizedSemanticChunker.chunk_text_optimized)

    def test_optimization_version_is_set(self):
        """OPTIMIZATION_VERSION must be a non-empty string."""
        assert isinstance(OPTIMIZATION_VERSION, str)
        assert len(OPTIMIZATION_VERSION) > 0


# ---------------------------------------------------------------------------
# Singleton factory test
# ---------------------------------------------------------------------------


class TestSingletonFactory:
    def test_singleton_factory_caches(self):
        """Two calls to get_optimized_semantic_chunker() must return the same object.

        The factory (lazy_singleton) caches by closure; we patch the
        OptimizedSemanticChunker constructor so no real model loading occurs.
        Because lazy_singleton caches in its *own* closure we cannot easily
        reset it between test runs — instead we verify idempotency by calling
        the factory twice and asserting identity.

        If the singleton was already created (e.g. by a previous test session
        import), the patch below is never reached and the test still passes
        because both calls return the already-cached instance.
        """
        # Call twice and assert the returned objects are identical.
        with patch.object(OptimizedSemanticChunker, "__init__", return_value=None):
            instance_a = get_optimized_semantic_chunker()
            instance_b = get_optimized_semantic_chunker()

        assert instance_a is instance_b


# ---------------------------------------------------------------------------
# Behavioural test: chunk_text_optimized stamps optimization_version metadata
# ---------------------------------------------------------------------------


class TestChunkTextOptimizedMetadata:
    @pytest.mark.asyncio
    async def test_optimization_version_stamped_on_chunks(self):
        """chunk_text_optimized must set metadata['optimization_version'] on every chunk."""
        # Build a minimal OptimizedSemanticChunker without touching the real __init__.
        instance = object.__new__(OptimizedSemanticChunker)

        # Fabricate two SemanticChunk objects with no metadata.
        fake_chunks = [
            SemanticChunk(
                content="chunk one",
                start_index=0,
                end_index=9,
                sentences=["chunk one"],
                semantic_score=0.9,
                metadata={},
            ),
            SemanticChunk(
                content="chunk two",
                start_index=10,
                end_index=19,
                sentences=["chunk two"],
                semantic_score=0.8,
                metadata=None,  # also exercise the None-metadata branch
            ),
        ]

        # Patch chunk_text on the instance to return our fake chunks.
        async def _fake_chunk_text(text, metadata=None):
            return fake_chunks

        with patch.object(instance, "chunk_text", side_effect=_fake_chunk_text):
            result = await instance.chunk_text_optimized("some text")

        assert len(result) == 2
        for chunk in result:
            assert chunk.metadata is not None
            assert chunk.metadata.get("optimization_version") == OPTIMIZATION_VERSION

    @pytest.mark.asyncio
    async def test_optimization_version_preserves_existing_metadata(self):
        """chunk_text_optimized must preserve pre-existing metadata keys."""
        instance = object.__new__(OptimizedSemanticChunker)

        existing_meta = {"source": "unit-test", "page": 1}
        fake_chunks = [
            SemanticChunk(
                content="chunk",
                start_index=0,
                end_index=5,
                sentences=["chunk"],
                semantic_score=0.95,
                metadata=dict(existing_meta),
            ),
        ]

        async def _fake_chunk_text(text, metadata=None):
            return fake_chunks

        with patch.object(instance, "chunk_text", side_effect=_fake_chunk_text):
            result = await instance.chunk_text_optimized("text")

        assert result[0].metadata["source"] == "unit-test"
        assert result[0].metadata["page"] == 1
        assert result[0].metadata["optimization_version"] == OPTIMIZATION_VERSION
