# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The retrieval plan contract of ``RAGService.advanced_search`` (#21606).

Pins the toggle names to the benchmark gate's, ``DEFAULT_PLAN`` to today's behaviour, the cache key
under ``DEFAULT_PLAN`` to today's, a provenance record on every hit, the unsupported-toggle report,
and the mandatory principal.
"""

import importlib
from dataclasses import fields
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from advanced_rag_optimizer import RAGMetrics, RankedResult
from knowledge.search_filters import SYSTEM_SCOPE
from services.rag_service import RAGService
from services.retrieval_contract import (
    DEFAULT_PLAN,
    GATE_TECHNIQUES,
    PlannedMetrics,
    RetrievalPlan,
    get_provenance,
    unsupported_toggles,
)

SCOPE = "scope-x"
EXPECTED_DEFAULT_KEY = f"{SCOPE}:q:5:True:all"


def _hit(source: str = "", rerank: float | None = None) -> RankedResult:
    return RankedResult(
        content="c",
        metadata={"source": source} if source else {},
        semantic_score=0.4,
        keyword_score=0.2,
        hybrid_score=0.3,
        relevance_rank=1,
        source_path="p",
        rerank_score=rerank,
    )


def _service() -> RAGService:
    svc = RAGService.__new__(RAGService)
    svc._initialized = True
    svc._mesh_retriever = None
    svc.config = SimpleNamespace(
        enable_advanced_rag=True,
        mesh_retriever_enabled=False,
        enable_session_adaptive_reranking=False,
        timeout_seconds=1.0,
    )
    return svc


class _Run:
    """One ``advanced_search`` with every leg replaced by a mock; the mocks are the assertions' source."""

    def __init__(self, hits):
        self.hits = hits
        self.mocks = {}

    async def go(self, **kwargs):
        svc = _service()
        names = {
            "check": "_check_cache_tiers",
            "execute": "_execute_and_cache_search",
            "docs": "_merge_docs_leg",
            "sem": "_store_in_semantic_cache",
            "topic": "_store_in_topic_cache",
        }
        with (
            patch.multiple(
                RAGService,
                _check_cache_tiers=AsyncMock(return_value=None),
                _execute_and_cache_search=AsyncMock(return_value=(self.hits, RAGMetrics())),
                _merge_docs_leg=AsyncMock(side_effect=lambda q, r, *a: r),
                _store_in_semantic_cache=AsyncMock(),
                _store_in_topic_cache=AsyncMock(),
                _lookup_retrieval_pattern=AsyncMock(return_value=None),
                _record_retrieval_outcome=AsyncMock(),
                _emit_ranked_feedback=AsyncMock(),
                _filter_stale_chunks=AsyncMock(side_effect=lambda r: r),
                initialize=AsyncMock(return_value=True),
            ),
            patch("services.rag_service.cache_scope", AsyncMock(return_value=SCOPE)),
            patch("services.rag_service.get_query_classifier", MagicMock()),
        ):
            out = await svc.advanced_search("q", principal=SYSTEM_SCOPE, **kwargs)
            self.mocks = {k: getattr(RAGService, v) for k, v in names.items()}
            self.calls = {k: m.call_args for k, m in self.mocks.items()}
            self.called = {k: m.called for k, m in self.mocks.items()}
        return out


def test_plan_field_names_equal_the_gate_toggle_names_plus_docs():
    assert {f.name for f in fields(RetrievalPlan)} == set(GATE_TECHNIQUES) | {"docs"}


def test_plan_field_names_equal_the_merged_gate_when_it_is_on_main():
    """Reads the gate's own tuple once #20949 (PR #21064) lands; until then there is nothing to read."""
    try:
        gate = importlib.import_module("knowledge.retrieval_gate")
    except ModuleNotFoundError:
        pytest.skip("knowledge.retrieval_gate is not on main yet (#21064); GATE_TECHNIQUES mirrors it")
    assert {f.name for f in fields(RetrievalPlan)} == set(gate.TECHNIQUES) | {"docs"}


def test_default_plan_is_pinned_to_todays_behaviour():
    """A change here needs a benchmark-gate report (#20949)."""
    assert {f.name: getattr(DEFAULT_PLAN, f.name) for f in fields(DEFAULT_PLAN)} == {
        "dense": True,
        "bm25": True,
        "fusion": True,
        "rerank": True,
        "query_expansion": True,
        "graph": False,
        "memory": False,
        "docs": True,
        "cache": True,
    }
    assert unsupported_toggles(DEFAULT_PLAN) == ()


@pytest.mark.asyncio
async def test_advanced_search_without_a_principal_still_raises():
    with pytest.raises(ValueError):
        await _service().advanced_search("q", principal=None)


@pytest.mark.asyncio
async def test_every_hit_carries_provenance():
    run = _Run([_hit(), _hit("autobot_docs"), _hit("topic_cache", rerank=0.9)])
    results, _ = await run.go()
    marks = [get_provenance(r) for r in results]
    assert all(m is not None for m in marks)
    assert [(m.bucket, m.leg) for m in marks] == [("facts", "hybrid"), ("docs", "docs"), ("facts", "cache")]
    assert marks[0].scores == {"semantic": 0.4, "keyword": 0.2, "hybrid": 0.3} and marks[0].final_score == 0.3
    assert marks[2].scores["rerank"] == 0.9 and marks[2].final_score == 0.9


@pytest.mark.asyncio
async def test_default_plan_returns_the_plain_metrics_and_todays_cache_key():
    run = _Run([_hit()])
    _, metrics = await run.go()
    assert type(metrics) is RAGMetrics
    assert run.calls["execute"].args[5] == EXPECTED_DEFAULT_KEY
    assert run.calls["check"].args[5] == SCOPE and run.calls["check"].kwargs == {"shared_tiers": True}
    assert run.called["docs"] and run.called["sem"] and run.called["topic"]


@pytest.mark.asyncio
async def test_toggles_without_a_leg_are_reported_not_ignored():
    run = _Run([_hit()])
    _, metrics = await run.go(plan=RetrievalPlan(dense=False, graph=True, memory=True))
    assert isinstance(metrics, PlannedMetrics)
    assert metrics.unsupported == ["dense", "graph", "memory"]
    assert run.calls["execute"].args[5] == EXPECTED_DEFAULT_KEY  # results are unchanged, so is the key


@pytest.mark.asyncio
async def test_a_docs_less_plan_skips_the_docs_merge_and_the_post_docs_cache_tiers():
    run = _Run([_hit()])
    await run.go(plan=RetrievalPlan(docs=False))
    assert run.calls["check"].kwargs == {"shared_tiers": False}
    assert not run.called["docs"] and not run.called["sem"] and not run.called["topic"]
    assert run.calls["execute"].args[5] == EXPECTED_DEFAULT_KEY  # tier 1 is stored before the docs merge


@pytest.mark.asyncio
async def test_rerank_off_is_part_of_the_key_and_cache_off_has_no_scope():
    run = _Run([_hit()])
    await run.go(plan=RetrievalPlan(rerank=False))
    assert run.calls["execute"].args[2] is False and run.calls["execute"].args[5] == f"{SCOPE}:q:5:False:all"
    cold = _Run([_hit()])
    await cold.go(plan=RetrievalPlan(cache=False))
    assert cold.calls["check"].args[5] is None and cold.calls["execute"].args[5] == ""
    assert not cold.called["sem"] and not cold.called["topic"]


def test_a_plan_that_is_not_a_retrieval_plan_is_rejected():
    from services.retrieval_contract import require_plan

    with pytest.raises(TypeError):
        require_plan({"docs": False})
