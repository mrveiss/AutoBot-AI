# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every ``kb.search`` caller #19144 lists inherits the quarantine from the canonical ``KB.search``.

Each caller runs against the #19163 store harness, whose every retrieval leg returns a quarantined
fact beside a normal one and ignores any ``where``. The caller adds no quarantine filter of its own,
so only the canonical layer can withhold the quarantined fact. Where the caller then applies the
#16665 ownership post-filter, that filter is replaced by a recorder: what it receives is exactly
what ``KB.search`` handed the caller.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.ssot_config import config
from knowledge.search_quarantine_19163_test import _ENGINE, _engine, _Store

_NOT_HELD = {"collection": {"$ne": config.research_quarantine_collection}}


def _doc_ids(hits) -> list:
    return [h["metadata"]["fact_id"] for h in hits]


def _recorder():
    """A stand-in ownership post-filter that records what it was given and passes it through."""
    seen: list = []

    async def _record(results, *_args, **_kwargs):
        seen.extend(results)
        return results

    return seen, _record


@pytest.mark.asyncio
async def test_hardware_accelerator_semantic_search_withholds_quarantined():
    from ai_hardware_accelerator import AIHardwareAccelerator

    accel = AIHardwareAccelerator.__new__(AIHardwareAccelerator)
    with (
        patch(_ENGINE, AsyncMock(return_value=_engine())),
        patch("knowledge_base_factory.get_knowledge_base_or_none", AsyncMock(return_value=_Store())),
    ):
        out = await accel._gpu_semantic_search({"query": "autobot", "top_k": 5})

    assert [r["metadata"]["fact_id"] for r in out["search_results"]] == ["good"]


def _retrieval_agent():
    from agents.knowledge_retrieval_agent import KnowledgeRetrievalAgent

    agent = KnowledgeRetrievalAgent.__new__(KnowledgeRetrievalAgent)
    agent.knowledge_base, agent._kb_initialized, agent.model_name = _Store(), True, "test-model"
    return agent


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["process_query", "find_similar_documents"])
async def test_knowledge_retrieval_agent_withholds_quarantined(method):
    seen, record = _recorder()
    agent = _retrieval_agent()
    with (
        patch(_ENGINE, AsyncMock(return_value=_engine())),
        patch("agents.knowledge_retrieval_agent.filter_for_user_id", record),
        patch.object(agent, "_generate_quick_summary", AsyncMock(return_value="")),
    ):
        await getattr(agent, method)("autobot", user_id="alice")

    assert _doc_ids(seen) == ["good"]


@pytest.mark.asyncio
async def test_kb_search_task_handler_withholds_quarantined():
    from task_handlers.knowledge_base_handlers import KBSearchHandler

    seen, record = _recorder()
    values = {"query": "autobot", "n_results": 5}
    ctx = MagicMock(metadata={"user_id": "alice"})
    ctx.require_payload_value.side_effect = values.__getitem__
    ctx.get_payload_value.side_effect = lambda key, default=None: values.get(key, default)
    ctx.worker.resolve_knowledge_base = AsyncMock(return_value=_Store())
    with (
        patch(_ENGINE, AsyncMock(return_value=_engine())),
        patch("task_handlers.knowledge_base_handlers.filter_for_user_id", record),
    ):
        await KBSearchHandler().execute(ctx)

    assert _doc_ids(seen) == ["good"]


def _npu_over_store():
    from npu_semantic_search import NPUSemanticSearch

    obj = NPUSemanticSearch.__new__(NPUSemanticSearch)
    store = _Store()
    store.vector_index = None  # no LlamaIndex engine: the KB.search fallback runs
    obj.knowledge_base = store
    return obj


@pytest.mark.asyncio
async def test_npu_vector_search_fallback_withholds_quarantined():
    obj = _npu_over_store()
    with patch(_ENGINE, AsyncMock(return_value=_engine())):
        results, device = await obj._perform_vector_search("autobot", 5, None)

    assert device == "cpu_fallback" and [r.metadata["fact_id"] for r in results] == ["good"]


@pytest.mark.asyncio
async def test_npu_search_error_fallback_withholds_quarantined():
    obj = _npu_over_store()
    with patch(_ENGINE, AsyncMock(return_value=_engine())):
        results, _ = await obj._handle_search_error(RuntimeError("npu down"), "autobot", 5, None, 0.0)

    assert [r.metadata["fact_id"] for r in results] == ["good"]


@pytest.mark.asyncio
async def test_llamaindex_engine_is_built_with_the_quarantine_where_and_the_callers_filter():
    from npu_semantic_search import NPUSemanticSearch

    obj = NPUSemanticSearch.__new__(NPUSemanticSearch)
    engine = MagicMock()
    engine.query.return_value = SimpleNamespace(source_nodes=[])
    index = MagicMock(as_query_engine=MagicMock(return_value=engine))
    obj.knowledge_base = SimpleNamespace(vector_store=MagicMock(), vector_index=index)

    await obj._perform_vector_search("autobot", 5, {"category": "docs"})

    where = index.as_query_engine.call_args.kwargs["vector_store_kwargs"]["where"]
    assert _NOT_HELD in where["$and"] and {"category": "docs"} in where["$and"]


@pytest.mark.asyncio
@pytest.mark.parametrize("is_admin", [True, False], ids=["admin", "user"])
async def test_rest_scoped_search_withholds_quarantined_for_every_role(is_admin):
    from api.knowledge_search_scoped import _scoped_search_results

    store, seen = _Store(), _recorder()
    store.ownership_manager = MagicMock()
    request = SimpleNamespace(app=SimpleNamespace())
    search_request = SimpleNamespace(query="autobot", top_k=5, mode="semantic")
    engine = _engine()
    with (
        patch(_ENGINE, AsyncMock(return_value=engine)),
        patch("api.knowledge_search_scoped.get_or_create_knowledge_base", AsyncMock(return_value=store)),
        patch("api.knowledge_search_scoped.filter_search_results_by_permission", seen[1]),
    ):
        await _scoped_search_results(search_request, request, {"user_id": "alice"}, is_admin=is_admin)

    assert _doc_ids(seen[0]) == ["good"]
    sent = engine.search.call_args.kwargs["filters"]  # an admin's None permission filter still gets the clause
    assert _NOT_HELD in sent["$and"]
