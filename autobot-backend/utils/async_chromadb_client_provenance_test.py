# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""#6514: integration test for the AsyncChromaCollection.add() provenance guard.

The guard reads ``collection.metadata`` for the autobot.embedding_provenance
namespace; if a (model_name, dim) tag is present, writes whose embedding
dim doesn't match get rejected with ``EmbeddingMismatchError`` BEFORE the
underlying Chroma `add()` call runs.

Untagged (legacy) collections fall through unchanged — the guard is
opt-in via the metadata tag, so existing collections aren't disturbed.
"""

from unittest.mock import MagicMock

import pytest

from autobot_shared.embedding_provenance import (
    EmbeddingMismatchError,
    EmbeddingProvenance,
    provenance_to_metadata,
)
from utils.async_chromadb_client import AsyncChromaCollection


def _stub_chroma_collection(metadata=None):
    """Build a MagicMock that walks like a Chroma Collection."""
    mock = MagicMock()
    mock.name = "test_collection"
    mock.metadata = metadata
    mock.add = MagicMock(return_value=None)
    return mock


@pytest.mark.asyncio
async def test_add_passes_through_when_collection_is_untagged():
    """Legacy collections (no provenance metadata) get no extra validation."""
    raw = _stub_chroma_collection(metadata={"hnsw:space": "cosine"})  # no tags
    coll = AsyncChromaCollection(raw)
    await coll.add(ids=["a"], embeddings=[[0.0] * 384])
    raw.add.assert_called_once()


@pytest.mark.asyncio
async def test_add_passes_when_dim_matches_provenance():
    p = EmbeddingProvenance("microsoft/codebert-base", 768)
    raw = _stub_chroma_collection(metadata=provenance_to_metadata(p))
    coll = AsyncChromaCollection(raw)
    await coll.add(ids=["a"], embeddings=[[0.0] * 768])
    raw.add.assert_called_once()


@pytest.mark.asyncio
async def test_add_rejects_cross_model_dim_mismatch():
    """The original #6514 reproducer at the chokepoint: collection tagged
    for codebert (768-dim), nomic writer (384-dim) tries to add — guard
    raises before the underlying Chroma add() runs."""
    p = EmbeddingProvenance("microsoft/codebert-base", 768)
    raw = _stub_chroma_collection(metadata=provenance_to_metadata(p))
    coll = AsyncChromaCollection(raw)
    with pytest.raises(EmbeddingMismatchError, match="dim 384.*expects dim 768"):
        await coll.add(ids=["a"], embeddings=[[0.0] * 384])
    # Crucial: the underlying Chroma write must NOT have been called —
    # the guard fires BEFORE the index is touched.
    raw.add.assert_not_called()


@pytest.mark.asyncio
async def test_add_without_embeddings_skips_validation():
    """When embeddings=None (caller relies on Chroma's embedding_function
    for documents=...), the dim guard has nothing to check. The underlying
    Chroma call is what enforces dim consistency in that path; this guard
    is opt-in for caller-supplied vectors."""
    p = EmbeddingProvenance("codebert", 768)
    raw = _stub_chroma_collection(metadata=provenance_to_metadata(p))
    coll = AsyncChromaCollection(raw)
    await coll.add(ids=["a"], documents=["hello"])
    raw.add.assert_called_once()


@pytest.mark.asyncio
async def test_add_rejects_partial_batch_mismatch():
    """Batch with one bad vector: fail-fast on the first mismatched index."""
    p = EmbeddingProvenance("codebert", 768)
    raw = _stub_chroma_collection(metadata=provenance_to_metadata(p))
    coll = AsyncChromaCollection(raw)
    with pytest.raises(EmbeddingMismatchError, match="vector at index 1"):
        await coll.add(
            ids=["a", "b", "c"],
            embeddings=[[0.0] * 768, [0.0] * 384, [0.0] * 768],
        )
    raw.add.assert_not_called()
