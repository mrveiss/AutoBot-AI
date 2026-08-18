# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GPUSemanticChunker already carries the optimization metadata (#14215).

`OptimizedSemanticChunker` (removed) was a `GPUSemanticChunker` subclass whose
only capability was stamping `metadata["optimization_version"]` onto each
returned chunk. Nothing ever constructed it — `rg -n
"OptimizedSemanticChunker"` found only its own definition and its own test.

`GPUSemanticChunker` already does this, via `_extra_chunk_metadata()`, which
`SemanticChunkerBase._build_chunk_metadata()` merges into every chunk's
metadata on every call to the public `chunk_text()` entry point — the same
method `knowledge_sync_incremental.py` and `advanced_rag_optimizer.py` call
through `get_gpu_semantic_chunker()`. The subclass duplicated behaviour the
base already shipped; it added no new capability.

These tests drive the real `get_gpu_semantic_chunker()` singleton and its real
`chunk_text()` method — not `_extra_chunk_metadata()` or `_build_chunk_metadata()`
directly — so the assertion is about what a production caller actually
receives. Only the two hardware-bound hooks (`_initialize_model`,
`_compute_embeddings`) and the sklearn-backed distance step are stubbed, so
the test runs without a GPU, a real embedding model, or scikit-learn
installed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from utils.semantic_chunker_gpu import GPUSemanticChunker, get_gpu_semantic_chunker

_TEXT = "First sentence here. Second sentence follows now. Third one too right now."

# Issue #14467: input shapes that exercise `chunk_text()`'s zero/one-sentence
# fallback (`_create_single_sentence_chunk`) instead of the boundary-detection
# path. "Hi." is filtered to zero sentences by the >=3-word rule in
# `_split_into_sentences` (#380); the other has exactly one qualifying sentence.
_EMPTY_SENTENCE_TEXT = "Hi."
_ONE_SENTENCE_TEXT = "This single sentence is deliberately long enough to survive filtering."

# Keys `_build_chunk_metadata()`/`_extra_chunk_metadata()` add on every chunk,
# regardless of which internal path produced it.
_SUBCLASS_METADATA_KEYS = frozenset(
    {
        "chunk_index",
        "total_chunks",
        "source_metadata",
        "embedding_model",
        "chunking_method",
        "gpu_batch_size",
        "optimization_version",
    }
)


@pytest.mark.asyncio
class TestOptimizationMetadataReachesTheProductionSingleton:
    async def test_the_production_singleton_is_a_gpu_semantic_chunker(self):
        """The factory production callers actually use."""
        chunker = get_gpu_semantic_chunker()
        assert isinstance(chunker, GPUSemanticChunker)

    async def test_chunk_text_stamps_optimization_version_on_every_chunk(self):
        """The one behaviour the removed subclass existed for, reached through
        the real entry point production callers use."""
        chunker = get_gpu_semantic_chunker()

        with (
            patch.object(chunker, "_initialize_model", AsyncMock(return_value=None)),
            patch.object(chunker, "_compute_embeddings", AsyncMock(return_value=np.zeros((3, 4)))),
            patch.object(chunker, "_compute_semantic_distances", return_value=[0.1, 0.1]),
        ):
            chunks = await chunker.chunk_text(_TEXT)

        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.metadata.get("optimization_version") == "rtx4070_gpu"
            assert chunk.metadata.get("chunking_method") == "gpu_optimized_semantic"

    async def test_a_fresh_instance_behaves_the_same_as_the_singleton(self):
        """Pins the behaviour to the class, not to singleton-caching side effects."""
        chunker = GPUSemanticChunker(gpu_batch_size=10, enable_gpu_memory_pool=False)

        with (
            patch.object(chunker, "_initialize_model", AsyncMock(return_value=None)),
            patch.object(chunker, "_compute_embeddings", AsyncMock(return_value=np.zeros((3, 4)))),
            patch.object(chunker, "_compute_semantic_distances", return_value=[0.1, 0.1]),
        ):
            chunks = await chunker.chunk_text(_TEXT)

        assert chunks
        assert all(c.metadata.get("optimization_version") == "rtx4070_gpu" for c in chunks)


@pytest.mark.asyncio
class TestShortInputChunksCarryTheSameMetadataAsLongInput:
    """Issue #14467: `_create_single_sentence_chunk` used to return before
    `_enrich_chunks_with_metadata()` ran, so `chunk_text()` on zero- or
    one-sentence input silently dropped `optimization_version` and the rest
    of `_build_chunk_metadata()`'s keys, while identical multi-sentence input
    kept them. All three assertions below enter through the real, public
    `chunk_text()` — never `_create_single_sentence_chunk` directly — so a fix
    that only special-cases the private method without wiring it into the
    public path would still fail here.

    Pre-fix: the single- and empty-input cases fail (missing every key in
    `_SUBCLASS_METADATA_KEYS`). Post-fix: all three pass.
    """

    async def _chunk_text(self, chunker: GPUSemanticChunker, text: str):
        with (
            patch.object(chunker, "_initialize_model", AsyncMock(return_value=None)),
            patch.object(chunker, "_compute_embeddings", AsyncMock(return_value=np.zeros((3, 4)))),
            patch.object(chunker, "_compute_semantic_distances", return_value=[0.1, 0.1]),
        ):
            return await chunker.chunk_text(text)

    async def test_single_sentence_input_matches_multi_sentence_metadata_keys(self):
        chunker = GPUSemanticChunker(gpu_batch_size=10, enable_gpu_memory_pool=False)

        multi_chunks = await self._chunk_text(chunker, _TEXT)
        single_chunks = await self._chunk_text(chunker, _ONE_SENTENCE_TEXT)

        assert multi_chunks and single_chunks
        for chunk in multi_chunks + single_chunks:
            missing = _SUBCLASS_METADATA_KEYS - chunk.metadata.keys()
            assert not missing, f"chunk missing keys {missing}: {sorted(chunk.metadata.keys())}"

    async def test_empty_input_matches_multi_sentence_metadata_keys(self):
        chunker = GPUSemanticChunker(gpu_batch_size=10, enable_gpu_memory_pool=False)

        empty_chunks = await self._chunk_text(chunker, _EMPTY_SENTENCE_TEXT)

        assert empty_chunks
        for chunk in empty_chunks:
            missing = _SUBCLASS_METADATA_KEYS - chunk.metadata.keys()
            assert not missing, f"chunk missing keys {missing}: {sorted(chunk.metadata.keys())}"
            assert chunk.metadata.get("empty_input") is True
