# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared stale filter on every retrieval path (#19280).

* ``drop_stale`` judges only the doc indexer's own chunks by its hash cache; a KB fact or a
  graph entity is never dropped for being absent from a cache it was never written to.
* KAG graph-expanded entities are stale when the entity or the relation that reached them has a
  closed validity window, and ``GraphRAGService`` drops them before they become results.
* ``POST /knowledge/search`` passes its results through the same ``drop_stale``.
* The mesh reranker and the vector optimizer look staleness up under the same key.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import knowledge.stale_filter as stale_mod
from advanced_rag_optimizer import RankedResult
from knowledge.chunk_identity import resolve_chunk_id
from knowledge.stale_filter import drop_stale, fresh_graph_items

PAST = "2020-01-01T00:00:00+00:00"
FUTURE = "2999-01-01T00:00:00+00:00"


@pytest.fixture
def hash_cache(tmp_path):
    """A hash cache that indexes ``docs/present.md`` only."""
    cache_file = tmp_path / ".doc_index_hashes.json"
    cache_file.write_text(json.dumps({"docs/present.md": "abc"}), encoding="utf-8")
    stale_mod.reset_hash_cache()
    with patch("services.knowledge.doc_indexer.HASH_CACHE_FILE", cache_file):
        yield
    stale_mod.reset_hash_cache()


def _doc_chunk(path: str) -> dict:
    return {"content": path, "metadata": {"source": "autobot_docs", "file_path": path}}


def _ranked(source_path: str, metadata: dict) -> RankedResult:
    return RankedResult(
        content=source_path,
        metadata=metadata,
        semantic_score=0.5,
        keyword_score=0.0,
        hybrid_score=0.5,
        relevance_rank=1,
        source_path=source_path,
    )


def _hit(name: str, entity_meta: dict | None = None, relation: dict | None = None) -> dict:
    entity = {"id": name, "name": name, "observations": [f"{name} fact"], "metadata": entity_meta or {}}
    relation = relation or {"type": "relates_to", "valid_to": None, "metadata": {"strength": 1.0}}
    return {"entity": entity, "relation": relation, "direction": "outgoing"}


class TestDropStale:
    @pytest.mark.asyncio
    async def test_a_doc_chunk_whose_file_left_the_index_is_dropped(self, hash_cache):
        kept = await drop_stale([_doc_chunk("docs/present.md"), _doc_chunk("docs/removed.md")])
        assert [c["metadata"]["file_path"] for c in kept] == ["docs/present.md"]

    @pytest.mark.asyncio
    async def test_a_kb_fact_and_a_graph_entity_are_not_judged_by_the_doc_cache(self, hash_cache):
        fact = _ranked("unknown", {"source": "manual", "relative_path": "notes/x.md"})
        entity = _ranked("graph:Redis", {"source": "graph_expansion"})
        stale_doc = _ranked("docs/removed.md", {"source": "autobot_docs", "file_path": "docs/removed.md"})
        assert await drop_stale([fact, entity, stale_doc]) == [fact, entity]


class TestKagStaleness:
    def test_an_expired_entity_or_relation_is_dropped_and_a_fresh_one_kept(self):
        fresh = _hit("fresh", {"valid_to": FUTURE})
        expired_entity = _hit("old", {"valid_to": PAST})
        expired_relation = _hit("cut", relation={"type": "relates_to", "valid_to": PAST})
        assert fresh_graph_items([fresh, expired_entity, expired_relation]) == [fresh]

    def test_graph_expansion_drops_the_stale_entity_before_it_becomes_a_result(self):
        from services.graph_rag_service import GraphRAGService

        svc = GraphRAGService(AsyncMock(), MagicMock(initialized=True))
        related = [_hit("fresh"), _hit("superseded", {"valid_to": PAST})]
        results = svc._process_graph_traversal_results([("start", 1.0)], [related], 2)
        assert [r.metadata["entity_name"] for r in results] == ["fresh"]


class TestKnowledgeSearchRoute:
    @pytest.mark.asyncio
    async def test_knowledge_search_drops_a_stale_doc_chunk_like_the_rag_branches(self, hash_cache):
        from api.knowledge_search import _aistack_search

        kb = MagicMock()
        kb.search = AsyncMock(return_value={"results": [_doc_chunk("docs/present.md"), _doc_chunk("docs/gone.md")]})
        request = MagicMock(uses_advanced_features=MagicMock(return_value=False))
        request.to_legacy_params.return_value = {"query": "q"}

        async def readable(results, **_kwargs):
            return results

        with patch("api.knowledge_search.filter_search_results_by_permission", side_effect=readable):
            response = await _aistack_search(request, kb, "u", None, [], True)

        assert [r["metadata"]["file_path"] for r in response["results"]] == ["docs/present.md"]
        assert response["total_results"] == 1


class TestOneStalenessKey:
    @pytest.mark.asyncio
    async def test_the_mesh_reranker_looks_staleness_up_under_resolve_chunk_id(self):
        from knowledge.search_components.reranking import RerankWeights, ResultReranker

        result = {"id": "row-1", "content": "c", "score": 0.5, "metadata": {"relative_path": "docs/a.md"}}
        reranker = ResultReranker()
        reranker._apply_rerank_scores(
            [result], [0.0], weights=RerankWeights(staleness=1.0), staleness_map={resolve_chunk_id(result): 1.0}
        )
        fresh = {"id": "row-1", "content": "c", "score": 0.5, "metadata": {"relative_path": "docs/a.md"}}
        reranker._apply_rerank_scores([fresh], [0.0], weights=RerankWeights(staleness=1.0), staleness_map={})
        assert result["rerank_score"] < fresh["rerank_score"]
