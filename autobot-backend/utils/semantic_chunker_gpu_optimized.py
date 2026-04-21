# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
GPU-optimized semantic chunker with explicit optimization metadata.

Wires in the module `utils.simple_optimization_test` expected to exist
(originally referenced at import-time; the module was missing, so the
test was blocked). Rather than redirecting the test to a different
module (which hides the original design intent), this wires in a thin
wrapper around the post-#5363 consolidated `GPUSemanticChunker`.

The wrapper exposes:

    * ``chunk_text_optimized(text, metadata=None)`` \u2014 explicit alias for
      ``chunk_text`` that also adds an ``optimization_version`` field to
      each chunk's metadata so smoke-tests can verify the optimized path
      was taken.

    * ``get_optimized_semantic_chunker()`` \u2014 singleton factory mirroring
      the pattern used by :mod:`utils.semantic_chunker` and
      :mod:`utils.semantic_chunker_gpu`.

The underlying compute path is unchanged from :class:`GPUSemanticChunker`:
FP16 mixed precision, TF32, cuDNN benchmark, GPU memory pool, kernel
warmup. All performance features inherited through composition, no
divergence from the canonical GPU chunker.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from utils.semantic_chunker_base import SemanticChunk
from utils.semantic_chunker_gpu import GPUSemanticChunker

__all__ = [
    "OptimizedSemanticChunker",
    "SemanticChunk",
    "get_optimized_semantic_chunker",
]

# Bumped whenever the optimization-metadata contract changes so consumers
# can gate behavior on a known baseline. Bump on material changes only.
OPTIMIZATION_VERSION = "gpu-consolidated-1"


class OptimizedSemanticChunker(GPUSemanticChunker):
    """GPU semantic chunker with explicit ``optimization_version`` metadata.

    Thin subclass that delegates the full pipeline to
    :class:`GPUSemanticChunker` and augments each resulting chunk's
    metadata with an ``optimization_version`` field so callers and
    smoke-tests can assert the optimized path was used.
    """

    async def chunk_text_optimized(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[SemanticChunk]:
        """Chunk ``text`` via the GPU-optimized pipeline.

        Equivalent to :meth:`chunk_text` but each returned
        :class:`SemanticChunk` carries ``metadata["optimization_version"]``
        set to :data:`OPTIMIZATION_VERSION`.
        """
        chunks = await self.chunk_text(text, metadata=metadata)
        for chunk in chunks:
            if chunk.metadata is None:
                chunk.metadata = {}
            chunk.metadata["optimization_version"] = OPTIMIZATION_VERSION
        return chunks


_optimized_instance: Optional[OptimizedSemanticChunker] = None
_optimized_lock = threading.Lock()


def get_optimized_semantic_chunker(
    *args: Any, **kwargs: Any
) -> OptimizedSemanticChunker:
    """Return the process-wide :class:`OptimizedSemanticChunker` singleton."""
    global _optimized_instance
    if _optimized_instance is None:
        with _optimized_lock:
            if _optimized_instance is None:
                _optimized_instance = OptimizedSemanticChunker(*args, **kwargs)
    return _optimized_instance
