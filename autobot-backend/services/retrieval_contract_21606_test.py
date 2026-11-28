# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The retrieval plan contract of ``RAGService.advanced_search`` (#21606).

Pins the toggle names to the benchmark gate's, ``DEFAULT_PLAN`` to today's behaviour, the cache key
under ``DEFAULT_PLAN`` to today's, a provenance record on every hit, the unsupported-toggle report,
and the mandatory principal.
"""

import asyncio
import importlib
from dataclasses import fields, replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from advanced_rag_optimizer import RAGMetrics, RankedResult
from knowledge.search_filters import SYSTEM_SCOPE
from services.rag_service import RAGService
from services.retrieval_contract import (
    DEFAULT_PLAN,
    RETRIEVAL_TECHNIQUES,
    PlannedMetrics,
    RetrievalPlan,
    get_provenance,
    unsupported_toggles,
    uses_shared_cache,
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
        self.order: list = []

    def _step(self, name, passthrough=None):
        async def run(*args, **kwargs):
            self.order.append(name)
            return passthrough(*args) if passthrough else None

        return AsyncMock(side_effect=run)

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
                _merge_docs_leg=self._step("docs", lambda q, r, *a: r),
                _store_in_semantic_cache=self._step("sem"),
                _store_in_topic_cache=self._step("topic"),
                _lookup_retrieval_pattern=AsyncMock(return_value=None),
                _record_retrieval_outcome=AsyncMock(),
                _emit_ranked_feedback=AsyncMock(),
                _filter_stale_chunks=self._step("stale", lambda r: r),
                initialize=AsyncMock(return_value=True),
            ),
            patch("services.rag_cache_tiers.cache_scope", AsyncMock(return_value=SCOPE)),
            patch("services.rag_service.get_query_classifier", MagicMock()),
        ):
            out = await svc.advanced_search("q", principal=SYSTEM_SCOPE, **kwargs)
            self.mocks = {k: getattr(RAGService, v) for k, v in names.items()}
            self.calls = {k: m.call_args for k, m in self.mocks.items()}
            self.called = {k: m.called for k, m in self.mocks.items()}
        return out


def test_plan_field_names_equal_the_gate_toggle_names_plus_docs():
    assert {f.name for f in fields(RetrievalPlan)} == set(RETRIEVAL_TECHNIQUES) | {"docs"}


def test_plan_field_names_equal_the_merged_gate_when_it_is_on_main():
    """Compares with the gate's tuple once #20949 (PR #21064) lands; #21625 makes the gate import ours."""
    try:
        gate = importlib.import_module("knowledge.retrieval_gate")
    except ModuleNotFoundError:
        pytest.skip(
            "knowledge.retrieval_gate is not on main yet (#21064); RETRIEVAL_TECHNIQUES is the one definition (#21625)"
        )
    assert {f.name for f in fields(RetrievalPlan)} == set(gate.TECHNIQUES) | {"docs"}
    assert gate.TECHNIQUES is RETRIEVAL_TECHNIQUES
    assert gate.DEFAULT_TOGGLES == {t: getattr(DEFAULT_PLAN, t) for t in RETRIEVAL_TECHNIQUES}  # values, not only names


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
    assert run.calls["check"].args[5] == SCOPE and run.calls["check"].kwargs == {}
    assert run.called["docs"] and run.called["sem"] and run.called["topic"]


@pytest.mark.asyncio
async def test_toggles_without_a_leg_are_reported_not_ignored():
    run = _Run([_hit()])
    _, metrics = await run.go(plan=RetrievalPlan(dense=False, graph=True, memory=True))
    assert isinstance(metrics, PlannedMetrics)
    assert metrics.unsupported == ["dense", "graph", "memory"]
    assert run.calls["check"].args[5] is None and run.calls["execute"].args[5] == ""  # not the default: no tier


@pytest.mark.parametrize("name", [f.name for f in fields(RetrievalPlan)])
def test_flipping_any_single_toggle_from_its_default_disables_the_shared_cache(name):
    flipped = replace(DEFAULT_PLAN, **{name: not getattr(DEFAULT_PLAN, name)})
    assert not uses_shared_cache(flipped)


def test_the_default_plan_uses_the_shared_cache():
    assert uses_shared_cache(DEFAULT_PLAN) and uses_shared_cache(RetrievalPlan())


@pytest.mark.asyncio
@pytest.mark.parametrize("plan", [RetrievalPlan(docs=False), RetrievalPlan(rerank=False), RetrievalPlan(cache=False)])
async def test_a_plan_that_changes_results_bypasses_every_shared_cache_tier(plan):
    run = _Run([_hit()])
    await run.go(plan=plan)
    assert run.calls["check"].args[5] is None  # scope None: tiers 0, 1 and 2 are neither read nor written
    assert run.calls["execute"].args[5] == ""
    assert not run.called["sem"] and not run.called["topic"]


def test_a_plan_that_is_not_a_retrieval_plan_is_rejected():
    from services.retrieval_contract import require_plan

    with pytest.raises(TypeError):
        require_plan({"docs": False})


@pytest.mark.asyncio
async def test_the_order_is_docs_merge_then_stale_cut_then_the_cache_stores():
    run = _Run([_hit()])
    await run.go()
    assert run.order == ["docs", "stale", "sem", "topic"]
    docs_less = _Run([_hit()])
    await docs_less.go(plan=RetrievalPlan(docs=False))
    assert docs_less.order == ["stale"]  # neither merged nor stored: tiers 0/2 hold post-docs results
    cold = _Run([_hit()])
    await cold.go(plan=RetrievalPlan(cache=False))
    assert cold.order == ["docs", "stale"]


@pytest.mark.asyncio
async def test_a_docs_chunk_served_from_a_cache_tier_keeps_the_docs_bucket_and_names_the_tier():
    from services.retrieval_contract import build_provenance, stamp_cached_from

    for tier in ("topic_cache", "semantic_cache"):
        hit = _hit(tier)
        stamp_cached_from(hit, "autobot_docs")
        mark = build_provenance(hit)
        assert (mark.bucket, mark.leg, mark.origin) == ("docs", "docs", tier)
    fact = _hit("topic_cache")
    stamp_cached_from(fact, "unknown_leg")
    assert (build_provenance(fact).bucket, build_provenance(fact).leg) == ("facts", "hybrid")


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", [SCOPE, None])
async def test_the_real_cache_tier_check_reads_tiers_0_and_2_only_inside_a_scope(scope):
    from services.context_sufficiency import SufficiencyVerdict

    evaluator = MagicMock()
    evaluator.evaluate = AsyncMock(return_value=SimpleNamespace(verdict=SufficiencyVerdict.SUFFICIENT, reason=""))
    sem = AsyncMock(return_value=([_hit()], RAGMetrics()))
    with (
        patch.multiple(RAGService, _check_semantic_cache=sem, _get_from_cache=AsyncMock(return_value=None)),
        patch("services.rag_cache_tiers.get_context_sufficiency_evaluator", return_value=evaluator),
    ):
        got = await _service()._check_cache_tiers("q", 5, True, None, SYSTEM_SCOPE, scope)
    assert sem.await_count == (0 if scope is None else 1)
    assert (got is None) == (scope is None)


@pytest.mark.asyncio
@pytest.mark.parametrize("first", [RetrievalPlan(docs=False), RetrievalPlan(rerank=False)])
async def test_a_non_default_plan_never_leaves_an_entry_a_default_plan_reads(first):
    """Sequential: the odd plan runs, then the default plan on the same query must run the full search."""
    from services.context_sufficiency import SufficiencyVerdict

    svc = _service()
    svc.config.cache_ttl_seconds = 60
    svc._cache, svc._cache_lock = {}, asyncio.Lock()
    evaluator = MagicMock()
    evaluator.evaluate = AsyncMock(return_value=SimpleNamespace(verdict=SufficiencyVerdict.SUFFICIENT, reason=""))
    search = AsyncMock(side_effect=lambda *a: ([_hit()], RAGMetrics()))
    sem, topic = AsyncMock(), AsyncMock()
    docs = AsyncMock(side_effect=lambda q, r, *a: r + [_hit("autobot_docs")])
    with (
        patch.multiple(
            RAGService,
            _execute_search_with_timeout=search,
            _merge_docs_leg=docs,
            _store_in_semantic_cache=sem,
            _store_in_topic_cache=topic,
            _check_semantic_cache=AsyncMock(return_value=None),
            _check_topic_cache=AsyncMock(return_value=None),
            _lookup_retrieval_pattern=AsyncMock(return_value=None),
            _record_retrieval_outcome=AsyncMock(),
            _emit_ranked_feedback=AsyncMock(),
            _filter_stale_chunks=AsyncMock(side_effect=lambda r: r),
            initialize=AsyncMock(return_value=True),
        ),
        patch("services.rag_cache_tiers.cache_scope", AsyncMock(return_value=SCOPE)),
        patch("services.rag_service.get_query_classifier", MagicMock()),
        patch("services.rag_cache_tiers.get_context_sufficiency_evaluator", return_value=evaluator),
    ):
        await svc.advanced_search("q", principal=SYSTEM_SCOPE, plan=first)
        assert svc._cache == {} and not sem.await_count and not topic.await_count  # nothing written, any tier
        got, _ = await svc.advanced_search("q", principal=SYSTEM_SCOPE)
    assert search.await_count == 2  # the default plan did not read an entry of the odd plan
    assert any((get_provenance(h).bucket == "docs") for h in got)  # and it got the docs merge
    assert sem.await_count == 1 and topic.await_count == 1  # the default plan still writes


@pytest.mark.asyncio
async def test_a_cache_served_hit_has_the_same_metadata_as_a_cold_hit():
    from knowledge.search_filters import SYSTEM_SCOPE as scope_
    from services.retrieval_contract import CACHED_FROM_ATTR
    from services.topic_retrieval_cache import CachedChunk

    cold_meta = {"source": "autobot_docs", "file_path": "a.md"}
    chunk = CachedChunk(content="c", metadata=dict(cold_meta), score=0.7)
    topic_cache = MagicMock()
    topic_cache.lookup = AsyncMock(return_value=[chunk])
    facts = MagicMock(_generate_embedding_with_npu_fallback=AsyncMock(return_value=[0.1]))
    with (
        patch.multiple(RAGService, _visible=AsyncMock(side_effect=lambda r, p: r)),
        patch("services.rag_cache_tiers.get_topic_retrieval_cache", AsyncMock(return_value=topic_cache)),
        patch.dict("sys.modules", {"knowledge.facts": facts}),
    ):
        hits, _ = await _service()._check_topic_cache("q", scope_, SCOPE)
    assert hits[0].metadata == {**cold_meta, "source": "topic_cache"}  # exactly main's tier-2 metadata
    assert "cached_from" not in hits[0].metadata and getattr(hits[0], CACHED_FROM_ATTR) == "autobot_docs"
    assert chunk.metadata == cold_meta  # what the cache holds is untouched


@pytest.mark.asyncio
async def test_a_semantic_cache_hit_has_the_same_metadata_as_main_builds():
    from services.rag_visibility import RESULT_METADATA_KEY
    from services.retrieval_contract import CACHED_FROM_ATTR

    cold_meta = {"source": "autobot_docs", "file_path": "a.md"}
    entry = SimpleNamespace(
        response_text="c",
        metadata={RESULT_METADATA_KEY: dict(cold_meta)},
        model="rag",
        original_query="q0",
        similarity_score=0.9,
    )
    sem_cache = MagicMock()
    sem_cache.lookup = AsyncMock(return_value=entry)
    with (
        patch.multiple(RAGService, _visible=AsyncMock(side_effect=lambda r, p: r)),
        patch("services.rag_cache_tiers.get_semantic_query_cache", AsyncMock(return_value=sem_cache)),
    ):
        hits, _ = await _service()._check_semantic_cache("q", SYSTEM_SCOPE, SCOPE)
    expected = {
        **cold_meta,
        "source": "semantic_cache",
        "model": "rag",
        "original_query": "q0",
        "similarity_score": 0.9,
    }
    assert hits[0].metadata == expected  # exactly main's tier-0 metadata
    assert "cached_from" not in hits[0].metadata and getattr(hits[0], CACHED_FROM_ATTR) == "autobot_docs"
    assert entry.metadata[RESULT_METADATA_KEY] == cold_meta  # what the cache holds is untouched
