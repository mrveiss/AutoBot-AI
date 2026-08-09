#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""GPU semantic chunker + knowledge base integration (#13563).

Both tests here used to be unfailable. Each wrapped its body in a bare
``except Exception`` and returned ``True``/``False``; pytest ignores a test's
return value, so every run reported success no matter what happened. That hid
two real defects for as long as the file has existed:

* ``test_chunker_optimization`` imported ``get_semantic_chunker`` from
  ``knowledge_base``, which **never exported it** — the module re-exports only
  ``KnowledgeBase``, ``get_knowledge_base``, ``EmbeddingCache``,
  ``get_embedding_cache`` and ``_sanitize_metadata_for_chromadb``. The import
  raised ``ImportError`` on every run and the ``except`` swallowed it. The real
  accessor lives in ``utils.semantic_chunker_gpu``.
* ``test_kb_stats`` called the coroutine ``get_knowledge_base()`` without
  ``await`` (#13563), so it used a coroutine object as if it were the knowledge
  base. Same defect class as the two fixed under #13551.

They now assert instead of returning, so a regression fails the run.
"""

import pytest

from utils.semantic_chunker_gpu import get_gpu_semantic_chunker

# Long enough that chunking has something to divide, short enough to stay fast.
SAMPLE_TEXT = (
    "AutoBot is an advanced Linux administration platform designed for intelligent automation. "
    "The system utilizes AI technologies to manage Linux environments efficiently. "
    "Through machine learning and natural language processing it interprets system requirements. "
    "The platform provides autonomous decision-making for routine administrative tasks. "
    "Security and reliability are paramount in its architectural design. "
) * 3


async def test_chunker_optimization():
    """The GPU chunker is reachable and actually chunks text.

    Hermetic: ``get_gpu_semantic_chunker()`` needs no Redis and no ChromaDB, so
    this belongs on the PR unit gate. Verified by running it against a clean
    environment where ``get_knowledge_base()`` fails.
    """
    chunker = get_gpu_semantic_chunker()

    # The GPU implementation is what this file exists to cover — assert the
    # identity rather than accepting whatever the factory happens to return.
    assert type(chunker).__name__ == "GPUSemanticChunker"
    assert hasattr(chunker, "gpu_batch_size")
    assert hasattr(chunker, "get_performance_stats")

    chunks = await chunker.chunk_text(SAMPLE_TEXT)

    assert chunks, "chunker returned no chunks for a multi-sentence document"
    assert all(chunk.content for chunk in chunks), "a chunk was produced with empty content"


@pytest.mark.integration
async def test_kb_stats():
    """Knowledge base statistics are reachable and well-formed.

    Requires a fully initialised KnowledgeBase (Redis ``knowledge`` database plus
    ChromaDB): without one ``get_knowledge_base()`` raises
    ``RuntimeError: Failed to initialize knowledge base``. It cannot run on the
    PR unit gate, so it is marked ``integration`` — the same treatment
    ``kb_optimization_test.py`` received under #13551.
    """
    from knowledge_base import get_knowledge_base

    kb = await get_knowledge_base()
    stats = await kb.get_stats()

    assert isinstance(stats, dict)
    for key in ("total_vectors", "total_chunks", "total_documents"):
        assert key in stats, f"stats missing '{key}'"
        assert isinstance(stats[key], int), f"stats['{key}'] is not an int"
