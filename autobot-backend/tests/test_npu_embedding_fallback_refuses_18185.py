# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18185: a query is embedded in its index's own space, or the search refuses; never another space."""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from autobot_shared.embedding_model import EmbeddingUnavailableError
from knowledge import index_embedding_space as spaces
from knowledge.index_embedding_space import CODE_INDEX, HYBRID_FAISS_INDEX, IndexSpace

ACC = "npu_semantic_search.accelerated_embedding_generation"
ACCESSOR = "services.npu_client.generate_embedding_with_fallback"
TEXT = "autobot_text_embeddings"


def _instance():
    from npu_semantic_search import NPUSemanticSearch

    obj = NPUSemanticSearch.__new__(NPUSemanticSearch)
    obj._l1_hits = obj._l2_hits = obj._cache_misses = 0
    obj.embedding_cache = MagicMock(get=AsyncMock(return_value=None), put=AsyncMock())
    obj._l2_cache_get = AsyncMock(return_value=None)
    obj._l2_cache_set = AsyncMock()
    obj.search_results_cache, obj.cache_max_size, obj.cache_ttl_seconds = {}, 10, 60
    obj.ai_accelerator, obj.hybrid_search = None, None
    obj.collection_names = {"text": TEXT, "image": "autobot_image_embeddings", "code": CODE_INDEX}
    return obj


def _recorded(dim=3):
    """A recorded text-accessor row, as #18217 would add after a reindex."""
    table = dict(spaces.index_spaces())
    table["idx"] = IndexSpace("index-model", dim)
    return patch.object(spaces, "index_spaces", return_value=table)


@pytest.mark.parametrize("index", [HYBRID_FAISS_INDEX, *spaces.ACCELERATOR_COLLECTIONS, "unknown_index"])
def test_unrecorded_or_unreproducible_spaces_refuse_with_a_reason(index):
    with pytest.raises(EmbeddingUnavailableError, match=f"'{index}'.*refused"):
        spaces.index_embedding_space(index)


def test_code_index_space_is_the_generator_model():
    from code_embedding_generator import CODEBERT_EMBEDDING_DIM, CODEBERT_MODEL_NAME

    space = spaces.index_embedding_space(CODE_INDEX)
    assert (space.model_id, space.dim) == (CODEBERT_MODEL_NAME, CODEBERT_EMBEDDING_DIM)


def test_dimension_mismatch_refuses_and_match_passes():
    spaces.require_query_dim(CODE_INDEX, np.zeros(768))
    with pytest.raises(EmbeddingUnavailableError, match="384-d but index"):
        spaces.require_query_dim(CODE_INDEX, np.zeros(384))


@pytest.mark.asyncio
@pytest.mark.parametrize("index", [HYBRID_FAISS_INDEX, TEXT])
async def test_refused_index_embeds_nothing_and_caches_nothing(index):
    obj, acc, accessor = _instance(), AsyncMock(), AsyncMock()
    with patch(ACC, acc), patch(ACCESSOR, accessor), pytest.raises(EmbeddingUnavailableError, match="#18217"):
        await obj._generate_optimized_embedding("q", index)
    acc.assert_not_awaited()
    accessor.assert_not_awaited()
    obj.embedding_cache.get.assert_not_awaited()
    obj.embedding_cache.put.assert_not_awaited()
    obj._l2_cache_set.assert_not_awaited()


@pytest.mark.asyncio
async def test_recorded_space_embeds_with_its_own_model_without_an_accelerator():
    obj, acc = _instance(), AsyncMock(side_effect=AssertionError("accelerator used"))
    accessor = AsyncMock(return_value=[0.1, 0.2, 0.3])
    with _recorded(), patch(ACC, acc), patch(ACCESSOR, accessor):
        vector, label = await obj._generate_optimized_embedding("q", "idx")
    accessor.assert_awaited_once_with("q", model_name="index-model")
    assert label == "index_space" and vector.shape == (3,)
    assert obj.embedding_cache.put.await_args.kwargs["model"] == "index-model/3"


@pytest.mark.asyncio
@pytest.mark.parametrize("produced", [None, [0.1, 0.2]])
async def test_recorded_space_refuses_when_its_model_gives_no_or_wrong_size_vector(produced):
    obj = _instance()
    with _recorded(), patch(ACCESSOR, AsyncMock(return_value=produced)), pytest.raises(EmbeddingUnavailableError):
        await obj._generate_optimized_embedding("q", "idx")
    obj.embedding_cache.put.assert_not_awaited()
    obj._l2_cache_set.assert_not_awaited()


@pytest.mark.asyncio
async def test_code_index_is_never_embedded_by_the_text_accessor():
    with patch(ACCESSOR, AsyncMock()) as accessor, pytest.raises(ValueError, match="code_embedding_generator"):
        await spaces.embed_in_index_space("q", CODE_INDEX)
    accessor.assert_not_awaited()


@pytest.mark.asyncio
async def test_populated_hybrid_index_is_a_failed_search_with_its_reason():
    obj = _instance()
    obj.hybrid_search = MagicMock(search=AsyncMock(side_effect=AssertionError("searched")))
    obj.hybrid_search.gpu_index.index.ntotal = 5
    obj.knowledge_base = MagicMock(search=AsyncMock(side_effect=AssertionError("text fallback used")))
    results, metrics = await obj.search("q")
    assert results == [] and "hybrid_faiss" in metrics.error and metrics.device_used == "embedding_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("enable_npu", [True, False])
async def test_kb_search_works_without_an_accelerator_and_with_the_query_text(enable_npu):
    """enable_npu_acceleration=False used to refuse on every host; the KB embeds in its own space."""
    obj = _instance()
    node = MagicMock(score=0.9, node=MagicMock(text="t", metadata={}, id_="d"))
    engine = MagicMock(query=MagicMock(return_value=MagicMock(source_nodes=[node])))
    obj.knowledge_base = MagicMock(vector_store=True, vector_index=MagicMock(as_query_engine=lambda **_: engine))
    with patch(ACC, AsyncMock(side_effect=AssertionError("accelerator used"))):
        results, metrics = await obj.search("real query", enable_npu_acceleration=enable_npu)
    engine.query.assert_called_once_with("real query")
    assert [r.doc_id for r in results] == ["d"] and metrics.error is None
    assert metrics.device_used == "knowledge_base"


@pytest.mark.asyncio
async def test_batch_embedding_refusal_keeps_its_reason_per_query():
    obj = _instance()
    obj.collections = {}
    ((results, metrics),) = await obj.batch_search(["q"])
    assert results == [] and "autobot_text_embeddings" in metrics.error and metrics.device_used == "error"


@pytest.mark.asyncio
async def test_cross_modal_search_refuses_instead_of_returning_no_matches():
    obj = _instance()
    obj.chroma_client, obj.collections = MagicMock(), {"text": MagicMock(), "image": MagicMock()}
    with patch(ACC, AsyncMock(side_effect=AssertionError("embedded"))), pytest.raises(EmbeddingUnavailableError):
        await obj.cross_modal_search("q", "text", target_modalities=["image"])


@pytest.mark.asyncio
async def test_code_collection_refuses_a_query_from_another_space():
    obj = _instance()
    collection = MagicMock()
    obj.chroma_client, obj.collections = MagicMock(), {"code": collection}
    with pytest.raises(EmbeddingUnavailableError, match="384-d"):
        await obj.search_code_embeddings(np.zeros(384))
    collection.query.assert_not_called()


def test_contrast_no_other_space_fallback_remains_in_the_engine():
    import inspect

    import npu_semantic_search as mod

    src = inspect.getsource(mod)
    assert "semantic_chunker" not in src and "embed_sentences" not in src
    assert "generate_embedding_with_fallback" not in src and "active_embedding_model" not in src
    assert not hasattr(mod.NPUSemanticSearch, "_generate_fallback_embedding")
    assert not hasattr(mod.NPUSemanticSearch, "_generate_embedding_with_device")


@pytest.mark.asyncio
async def test_two_different_queries_reach_the_query_engine_as_two_different_strings_18218():
    """#18218: the engine sees each caller's query, never a fixed literal such as "search query"."""
    obj = _instance()
    engine = MagicMock(query=MagicMock(return_value=MagicMock(source_nodes=[])))
    obj.knowledge_base = MagicMock(vector_index=MagicMock(as_query_engine=lambda **_: engine))
    await obj._search_with_llamaindex("how do I rotate keys", 3)
    await obj._search_with_llamaindex("what is the backup schedule", 3)
    sent = [call.args[0] for call in engine.query.call_args_list]
    assert sent == ["how do I rotate keys", "what is the backup schedule"]
    assert "search query" not in sent
