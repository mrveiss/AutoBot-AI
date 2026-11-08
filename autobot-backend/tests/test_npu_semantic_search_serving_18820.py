# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18820/#18829: the NPU engine's retrieval paths that bypass KB.search apply the one serving predicate."""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import knowledge.serving as serving
from knowledge.index_embedding_space import CODE_INDEX
from npu_semantic_search import NPUSemanticSearch

PAST = "2000-01-01T00:00:00+00:00"
FUTURE = "2999-01-01T00:00:00+00:00"
VALID = {"verification_status": "verified", "valid_to": FUTURE}
REJECTED = {"verification_status": "rejected"}
EXPIRED = {"valid_to": PAST}
CASES = {"valid": VALID, "rejected": REJECTED, "expired": EXPIRED}


def _engine() -> NPUSemanticSearch:
    obj = NPUSemanticSearch.__new__(NPUSemanticSearch)
    obj.collections, obj.collection_names = {}, {"text": "autobot_text_embeddings", "code": CODE_INDEX}
    return obj


def test_llamaindex_path_drops_rejected_and_expired_keeps_valid():
    obj = _engine()
    nodes = [
        SimpleNamespace(node=SimpleNamespace(text=name, metadata=meta, id_=name), score=0.5)
        for name, meta in CASES.items()
    ]
    engine = MagicMock()
    engine.query.return_value = SimpleNamespace(source_nodes=nodes)
    obj.knowledge_base = SimpleNamespace(vector_index=MagicMock(as_query_engine=MagicMock(return_value=engine)))
    out = asyncio.run(obj._search_with_llamaindex("q", 5))
    assert [r.doc_id for r in out] == ["valid"]


def test_hybrid_path_drops_rejected_and_expired_keeps_valid(monkeypatch):
    import npu_semantic_search as mod

    obj = _engine()
    obj._generate_optimized_embedding = AsyncMock(return_value=([0.0], "cpu"))
    monkeypatch.setattr(mod, "require_query_dim", lambda *_: None)
    hits = [SimpleNamespace(content=n, metadata=m, score=0.5, doc_id=n) for n, m in CASES.items()]
    metrics = SimpleNamespace(gpu_utilized=False, query_time_ms=1.0, backend_used=SimpleNamespace(value="faiss"))
    obj.hybrid_search = SimpleNamespace(search=AsyncMock(return_value=(hits, metrics)))
    out, _ = asyncio.run(obj._search_hybrid_index("q", 5, None))
    assert [r.doc_id for r in out] == ["valid"]


def test_batch_chromadb_path_drops_rejected_and_expired_keeps_valid():
    obj = _engine()
    ids = list(CASES)
    batch = {
        "ids": [ids],
        "documents": [ids],
        "metadatas": [[CASES[i] for i in ids]],
        "distances": [[0.1, 0.2, 0.3]],
    }
    obj.collections["text"] = SimpleNamespace(query_batch=AsyncMock(return_value=batch))
    out = asyncio.run(obj._batch_chromadb_search([0], [[0.0]], 5, None, "cpu"))
    results, _ = out[0]
    assert [r.doc_id for r in results] == ["valid"]


def test_a_result_with_no_status_is_a_legacy_fact_and_is_served():
    obj = _engine()
    batch = {"ids": [["old"]], "documents": [["x"]], "metadatas": [[{}]], "distances": [[0.1]]}
    obj.collections["text"] = SimpleNamespace(query_batch=AsyncMock(return_value=batch))
    results, _ = asyncio.run(obj._batch_chromadb_search([0], [[0.0]], 5, None, "cpu"))[0]
    assert [r.doc_id for r in results] == ["old"]


def test_batch_path_reads_the_text_collection_not_the_code_collection():
    """Pins which collection the batch path serves from: KB text, so the predicate applies."""
    obj = _engine()
    assert obj.collection_names["text"] != obj.collection_names["code"]
    obj.collections["code"] = SimpleNamespace(query_batch=AsyncMock(side_effect=AssertionError("code read")))
    obj.collections["text"] = SimpleNamespace(
        query_batch=AsyncMock(return_value={"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]})
    )
    assert asyncio.run(obj._batch_chromadb_search([0], [[0.0]], 5, None, "cpu"))[0][0] == []


def test_cross_modal_text_leg_drops_rejected_and_expired_keeps_valid(monkeypatch):
    """cross_modal_search's text modality reads autobot_text_embeddings, which may hold KB facts (#18820)."""
    import npu_semantic_search as mod

    monkeypatch.setattr(mod, "require_query_dim", lambda *_a, **_k: None)
    obj = _engine()
    ids = list(CASES)
    found = {
        "ids": [ids],
        "documents": [ids],
        "metadatas": [[CASES[i] for i in ids]],
        "distances": [[0.1, 0.2, 0.3]],
    }
    obj.collections["text"] = SimpleNamespace(query=MagicMock(return_value=found))
    results = obj._search_single_modality("text", mod.np.zeros(3), 5, 0.0)
    assert [r.doc_id for r in results] == ["valid"]


def _cached_engine(results: list) -> NPUSemanticSearch:
    obj = _engine()
    obj.search_results_cache, obj.cache_ttl_seconds, obj.cache_max_size = {}, 300, 10
    obj._cache_result("k", (results, SimpleNamespace(cache_hit=False)))
    return obj


def test_a_cached_fact_that_expires_within_the_cache_ttl_is_not_served_on_the_next_hit(monkeypatch):
    """Store-time filtering is not enough: validity depends on when the cache is READ (#18820)."""
    soon = datetime.now(tz=timezone.utc) + timedelta(seconds=60)
    meta = {"verification_status": "verified", "valid_to": soon.isoformat()}
    fact = SimpleNamespace(content="f", metadata=meta, score=0.5, doc_id="f")
    obj = _cached_engine([fact])
    assert [r.doc_id for r in obj._get_cached_result("k")[0]] == ["f"]  # control: valid when cached
    monkeypatch.setattr(serving, "_as_of_instant", lambda _as_of: soon + timedelta(seconds=1))
    assert time.time() - obj.search_results_cache["k"][1] < obj.cache_ttl_seconds  # still a cache hit
    assert obj._get_cached_result("k")[0] == []
    obj._generate_cache_key = lambda *_a: "k"
    assert asyncio.run(obj.search("q"))[0] == []
    assert asyncio.run(obj.batch_search(["q"]))[0][0] == []
