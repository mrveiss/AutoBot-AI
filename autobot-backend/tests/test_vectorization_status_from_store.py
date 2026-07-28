# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vectorization status must come from the vector store, not a Redis flag (#12733).

Status was read from a Redis key (`llama_index/vector_{id}`) written beside the
fact. Any Redis/ChromaDB drift made the indicator wrong — and when facts were
lost while their vectors survived, the Knowledge Browser reported everything
"unvectorized" on every reload.
"""

from unittest.mock import MagicMock, patch

import pytest

from api.knowledge_vectorization import (
    _check_vectorization_batch_internal,
    _vectorized_ids_from_vector_store,
)


def _kb():
    kb = MagicMock()
    kb.chromadb_path = "/tmp/chroma-test"
    kb.chromadb_collection = "autobot_memory"
    kb.embedding_dimensions = 768
    return kb


def _chroma_returning(ids):
    collection = MagicMock()
    collection.get.return_value = {"ids": list(ids)}
    client = MagicMock()
    client.get_collection.return_value = collection
    return client


@pytest.mark.asyncio
async def test_status_reflects_vector_store_membership():
    kb = _kb()
    with patch("knowledge.backends.get_default_client", return_value=_chroma_returning(["a", "c"])):
        result = await _check_vectorization_batch_internal(kb, ["a", "b", "c"])

    assert result["statuses"]["a"]["vectorized"] is True
    assert result["statuses"]["b"]["vectorized"] is False
    assert result["statuses"]["c"]["vectorized"] is True


@pytest.mark.asyncio
async def test_a_stale_redis_flag_does_not_win_over_the_store():
    """The drift case: Redis says vectorized, the store disagrees."""
    kb = _kb()
    # Redis would report every key as existing.
    kb.redis_client.pipeline.return_value.execute.return_value = [1, 1]

    with patch("knowledge.backends.get_default_client", return_value=_chroma_returning([])):
        result = await _check_vectorization_batch_internal(kb, ["a", "b"])

    assert result["statuses"]["a"]["vectorized"] is False
    assert result["statuses"]["b"]["vectorized"] is False


@pytest.mark.asyncio
async def test_vectors_without_facts_are_reported_vectorized():
    """The observed state: 0 facts, 22 vectors. Those ids ARE vectorized."""
    kb = _kb()
    with patch("knowledge.backends.get_default_client", return_value=_chroma_returning(["v1", "v2"])):
        result = await _check_vectorization_batch_internal(kb, ["v1", "v2"])

    assert result["summary"]["vectorized"] == 2


@pytest.mark.asyncio
async def test_unreachable_store_falls_back_to_redis_not_all_unvectorized():
    """A false 'nothing is vectorized' is worse than a stale flag."""
    kb = _kb()
    pipe = MagicMock()
    pipe.execute.return_value = [1, 0]
    kb.redis_client.pipeline.return_value = pipe

    with patch("knowledge.backends.get_default_client", side_effect=RuntimeError("chroma down")):
        result = await _check_vectorization_batch_internal(kb, ["a", "b"])

    assert result["statuses"]["a"]["vectorized"] is True, "fell back to Redis rather than reporting all false"
    assert result["statuses"]["b"]["vectorized"] is False


@pytest.mark.asyncio
async def test_unreachable_store_returns_none_not_empty_set():
    """None and empty-set mean different things: 'unknown' vs 'nothing vectorized'."""
    with patch("knowledge.backends.get_default_client", side_effect=RuntimeError("down")):
        assert await _vectorized_ids_from_vector_store(_kb(), ["a"]) is None


@pytest.mark.asyncio
async def test_empty_store_returns_an_empty_set():
    with patch("knowledge.backends.get_default_client", return_value=_chroma_returning([])):
        assert await _vectorized_ids_from_vector_store(_kb(), ["a"]) == set()


@pytest.mark.asyncio
async def test_status_request_never_raises_when_the_store_errors():
    """The browser must still render; a status check is not worth a 500."""
    kb = _kb()
    kb.redis_client.pipeline.return_value.execute.return_value = [0]

    with patch("knowledge.backends.get_default_client", side_effect=Exception("boom")):
        result = await _check_vectorization_batch_internal(kb, ["a"])

    assert "statuses" in result and "summary" in result
