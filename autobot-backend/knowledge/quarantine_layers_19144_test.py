# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The quarantine holds at the layers below and beside ``KB.search`` (#19144).

* ``servable_response``'s default refuses a quarantined hit (the second line of defence, #19164), so
  the REST ``/knowledge/search`` engine leg, which calls it bare, never serves one.
* The permission ``where`` builders combine through ``and_where``, never a hand-built ``$and``.
* The GPU hybrid search drops a hit it cannot check against a filter, instead of passing it through.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ssot_config import config
from knowledge.serving import servable_response
from knowledge.vector_search_engine import VectorSearchResult

_HELD = {"fact_id": "held", "collection": config.research_quarantine_collection, "visibility": "public"}
_GOOD = {"fact_id": "good", "visibility": "public"}


def test_servable_response_default_refuses_a_quarantined_hit():
    hits = [{"metadata": dict(_GOOD)}, {"metadata": dict(_HELD)}]
    assert [h["metadata"]["fact_id"] for h in servable_response(hits)] == ["good"]
    response = servable_response({"results": hits, "total_count": 2})
    assert [h["metadata"]["fact_id"] for h in response["results"]] == ["good"] and response["total_count"] == 1


@pytest.mark.asyncio
async def test_rest_knowledge_search_engine_leg_withholds_quarantined():
    from api.knowledge_search import _execute_kb_search
    from knowledge.ownership import KnowledgeOwnership

    engine = MagicMock()
    engine.search = AsyncMock(
        return_value=[
            VectorSearchResult(text=m["fact_id"], score=0.9, metadata=dict(m), source=m["fact_id"])
            for m in (_GOOD, _HELD)
        ]
    )
    kb = SimpleNamespace(ownership_manager=KnowledgeOwnership(MagicMock()))
    with patch("api.knowledge_search.get_vector_search_engine", AsyncMock(return_value=engine)):
        results = await _execute_kb_search(kb, "autobot", 5, "semantic", "alice", None, [], False)

    assert [r["metadata"]["fact_id"] for r in results] == ["good"]


@pytest.mark.asyncio
async def test_permission_where_combines_through_and_where():
    from knowledge.search_filters import augment_search_request_with_permissions

    caller = {"$and": [{"category": "docs"}, {"source": "manual"}]}
    where = await augment_search_request_with_permissions("q", "alice", "org-1", original_where=caller)

    # and_where flattens the caller's own $and; a hand-built {"$and": [caller, permission]} would nest it
    assert where["$and"][:2] == caller["$and"] and "$or" in where["$and"][2]
    org_clause = {"$and": [{"visibility": "organization"}, {"organization_id": "org-1"}]}
    assert org_clause in where["$and"][2]["$or"]


def _hybrid(lookup: dict | Exception):
    from utils.gpu_vector_search import GpuSearchResult, HybridVectorSearch

    search = HybridVectorSearch.__new__(HybridVectorSearch)
    collection = MagicMock()
    if isinstance(lookup, Exception):
        collection.get.side_effect = lookup
    else:
        ids = list(lookup)
        collection.get.return_value = {"ids": ids, "documents": ids, "metadatas": [lookup[i] for i in ids]}
    search.chromadb = MagicMock(get_collection=MagicMock(return_value=collection))
    hits = [GpuSearchResult(doc_id=d, score=0.9, distance=0.1) for d in ("good", "unlooked")]
    return search, hits


@pytest.mark.asyncio
async def test_gpu_enrich_drops_a_hit_it_cannot_check_under_a_filter():
    search, hits = _hybrid({"good": dict(_GOOD)})
    where = {"collection": {"$ne": config.research_quarantine_collection}}

    assert [r.doc_id for r in await search._enrich_from_chromadb(hits, "default", where)] == ["good"]
    search, hits = _hybrid({"good": dict(_GOOD)})
    assert [r.doc_id for r in await search._enrich_from_chromadb(hits, "default", None)] == ["good", "unlooked"]


@pytest.mark.asyncio
async def test_gpu_enrich_failure_serves_nothing_under_a_filter():
    search, hits = _hybrid(RuntimeError("chroma down"))
    assert await search._enrich_from_chromadb(hits, "default", {"collection": {"$ne": "research"}}) == []


@pytest.mark.asyncio
async def test_gpu_search_with_no_store_to_check_a_filter_serves_nothing():
    search, hits = _hybrid({})
    search.chromadb = None
    search.gpu_index = SimpleNamespace(index=SimpleNamespace(ntotal=2), search=AsyncMock(return_value=(hits, "m")))

    assert await search.search([0.0], top_k=2, metadata_filter={"category": "docs"}) == ([], "m")
    assert (await search.search([0.0], top_k=2))[0] == hits
