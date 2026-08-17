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
