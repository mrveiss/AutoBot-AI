# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RAGService.advanced_search returns only what its principal may read, on every leg (#16664).

User A's view is own + shared-with-A + system facts and never B's private fact; B's view is the
mirror. Each leg (optimizer, both fallbacks, mesh, docs merge, cache tiers 0/1/2) gets that
contrast pair. The caches are partitioned by scope and carry the ACL epoch, so A's cached result
is a miss for B and an unshare orphans A's own hit. A missing principal raises before any read.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from advanced_rag_optimizer import RAGMetrics, RankedResult
from knowledge.acl_epoch import ACL_EPOCH_KEY
from knowledge.ownership import KnowledgeOwnership
from knowledge.search_filters import SYSTEM_SCOPE, kb_principal
from services.context_sufficiency import SufficiencyResult, SufficiencyVerdict
from services.rag_config import RAGConfig
from services.rag_service import RAGService
from services.rag_visibility import RESULT_METADATA_KEY, cache_scope
from testkit.fake_redis_pipeline import DualReply
from tests.fixtures.rag_cache_fakes import make_semantic_cache, make_topic_cache

PRINCIPAL_A = kb_principal({"user_id": "A"})
PRINCIPAL_B = kb_principal({"user_id": "B"})
QUERY = "how do I rotate the deploy key"
VECTOR = [0.1, 0.2, 0.3]


def _fact(content: str, **metadata) -> RankedResult:
    return RankedResult(
        content=content,
        metadata={"fact_id": content, **metadata},
        semantic_score=0.9,
        keyword_score=0.5,
        hybrid_score=0.8,
        relevance_rank=1,
        source_path=content,
    )


A_OWN = _fact("a-own", owner_id="A", visibility="private")
B_PRIVATE = _fact("b-private", owner_id="B", visibility="private")
B_PRIVATE_TOO = _fact("b-private-too", owner_id="B", visibility="private")
SHARED_WITH_A = _fact("shared-with-a", owner_id="B", visibility="shared", shared_with=["A"])
SYSTEM = _fact("system-fact", owner_id="B", visibility="system")
EVERYTHING = [B_PRIVATE, A_OWN, B_PRIVATE_TOO, SHARED_WITH_A, SYSTEM]

#: what each principal may read out of EVERYTHING
A_SEES = {"a-own", "shared-with-a", "system-fact"}
B_SEES = {"b-private", "b-private-too", "shared-with-a", "system-fact"}
WHO = [(PRINCIPAL_A, A_SEES), (PRINCIPAL_B, B_SEES)]


class _EpochStore:
    """A Redis stand-in for the ACL epoch: the sync SET ownership bumps with, the async GET/SET NX the readers use."""

    def __init__(self) -> None:
        self.value: str | None = None
        self.bumps = 0
        self.reachable = True

    def set(self, key, value, nx=False):
        assert key == ACL_EPOCH_KEY
        if nx and self.value is not None:
            return DualReply()
        self.value = value
        if not nx:
            self.bumps += 1
        return DualReply()

    async def get(self, key):
        assert key == ACL_EPOCH_KEY
        return self.value.encode("utf-8") if self.value is not None else None

    def evict(self) -> None:
        """allkeys-lru dropped the epoch key."""
        self.value = None

    def sadd(self, key, *members):
        return 1

    def srem(self, key, *members):
        return 1


class _Harness:
    """A RAGService over fakes, with the caches and the ACL epoch under test control."""

    def __init__(self, config: RAGConfig, semantic, topic, epoch: _EpochStore) -> None:
        svc = RAGService.__new__(RAGService)
        svc.config, svc._initialized, svc._cache, svc._cache_lock = config, True, {}, asyncio.Lock()
        svc._mesh_retriever = None
        svc.optimizer = MagicMock()
        svc.optimizer.advanced_search = AsyncMock(return_value=(list(EVERYTHING), RAGMetrics()))
        svc.kb_adapter = SimpleNamespace(
            kb=SimpleNamespace(ownership_manager=KnowledgeOwnership(redis_client=epoch)),
            implementation_type="fake",
            search=AsyncMock(side_effect=lambda **_: [_as_kb_row(r) for r in EVERYTHING]),
        )
        for name in ("_emit_ranked_feedback", "_record_retrieval_outcome"):
            setattr(svc, name, AsyncMock())
        svc._lookup_retrieval_pattern = AsyncMock(return_value=None)
        svc._filter_stale_chunks = AsyncMock(side_effect=lambda r: r)
        self.svc, self.semantic, self.topic, self.epoch = svc, semantic, topic, epoch

    async def search(self, principal, **kwargs):
        results, _ = await self.svc.advanced_search(QUERY, principal=principal, **kwargs)
        return results


def _as_kb_row(result: RankedResult) -> dict:
    return {"content": result.content, "metadata": result.metadata, "score": result.hybrid_score}


def _contents(results) -> set:
    return {r.content for r in results}


@pytest.fixture
def harness():
    epoch, semantic, topic = _EpochStore(), make_semantic_cache(), make_topic_cache()
    sufficient = SimpleNamespace(
        evaluate=AsyncMock(return_value=SufficiencyResult(SufficiencyVerdict.SUFFICIENT, 1.0, "test"))
    )
    with (
        patch("knowledge.acl_epoch.get_async_redis_client", new=AsyncMock(return_value=epoch)),
        patch("services.rag_cache_tiers.get_semantic_query_cache", new=AsyncMock(return_value=semantic)),
        patch("services.rag_cache_tiers.get_topic_retrieval_cache", new=AsyncMock(return_value=topic)),
        patch("services.rag_cache_tiers.get_context_sufficiency_evaluator", return_value=sufficient),
        patch("knowledge.facts._generate_embedding_with_npu_fallback", new=AsyncMock(return_value=VECTOR)),
        patch(
            "services.knowledge.doc_indexer.get_doc_indexer_service", return_value=SimpleNamespace(_initialized=False)
        ),
    ):
        yield _Harness(RAGConfig(enable_advanced_rag=True), semantic, topic, epoch)


# --- the contract: a principal is required -------------------------------------------------------


@pytest.mark.asyncio
async def test_a_missing_principal_raises_type_error_and_reads_nothing(harness):
    with pytest.raises(TypeError):
        await harness.svc.advanced_search(QUERY)
    harness.svc.optimizer.advanced_search.assert_not_called()
    harness.svc.kb_adapter.search.assert_not_called()


@pytest.mark.asyncio
async def test_a_none_principal_raises_value_error_and_reads_nothing(harness):
    with pytest.raises(ValueError):
        await harness.svc.advanced_search(QUERY, principal=None)
    harness.svc.optimizer.advanced_search.assert_not_called()
    harness.svc.kb_adapter.search.assert_not_called()


@pytest.mark.asyncio
async def test_a_string_that_spells_system_scope_is_not_system_scope(harness):
    """The sentinel is not a str, so no user id or caller string can ever equal it."""
    with pytest.raises(TypeError):
        await harness.svc.advanced_search(QUERY, principal="SYSTEM_SCOPE")
    harness.svc.optimizer.advanced_search.assert_not_called()


# --- every leg returns the principal's view ------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("principal, expected", WHO)
async def test_the_optimizer_leg_keeps_the_principals_view_and_the_topk_survives(harness, principal, expected):
    results = await harness.search(principal, max_results=3)

    assert _contents(results) <= expected
    assert len(results) == 3, "the 2x over-fetch must leave a full top-k after the private facts are removed"
    assert harness.svc.optimizer.advanced_search.await_args.kwargs["max_results"] == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("principal, expected", WHO)
async def test_the_basic_fallback_keeps_the_principals_view(harness, principal, expected):
    harness.svc.config.enable_advanced_rag = False

    assert _contents(await harness.search(principal, max_results=5)) == expected
    harness.svc.optimizer.advanced_search.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [asyncio.TimeoutError(), RuntimeError("optimizer down")])
@pytest.mark.parametrize("principal, expected", WHO)
async def test_the_timeout_and_exception_fallbacks_keep_the_principals_view(harness, principal, expected, failure):
    harness.svc.optimizer.advanced_search = AsyncMock(side_effect=failure)

    assert _contents(await harness.search(principal, max_results=5)) == expected
    harness.svc.kb_adapter.search.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("principal, expected", WHO)
async def test_the_mesh_leg_keeps_the_principals_view(harness, principal, expected):
    harness.svc.config.mesh_retriever_enabled = True
    mesh = MagicMock()
    mesh.retrieve = AsyncMock(return_value=SimpleNamespace(ranked_chunks=lambda: list(EVERYTHING)))
    harness.svc._mesh_retriever = mesh
    harness.svc._emit_retrieval_feedback = AsyncMock()
    harness.svc._store_feedback_in_stream = AsyncMock()

    assert _contents(await harness.search(principal, max_results=5)) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("principal, expected", WHO)
async def test_the_docs_merge_keeps_the_principals_view(harness, principal, expected):
    platform_doc = _fact("platform-doc", visibility="system", access_level="autobot")
    docs = SimpleNamespace(_initialized=True, search=AsyncMock(return_value=[B_PRIVATE, A_OWN, platform_doc]))
    harness.svc.optimizer.advanced_search = AsyncMock(return_value=([], RAGMetrics()))

    with patch("services.knowledge.doc_indexer.get_doc_indexer_service", return_value=docs):
        results = await harness.search(principal, max_results=5)

    own = {"a-own"} if principal is PRINCIPAL_A else {"b-private"}
    assert _contents(results) == {"platform-doc"} | own


@pytest.mark.asyncio
async def test_system_scope_reads_non_private_facts_only(harness):
    results = await harness.search(SYSTEM_SCOPE, max_results=5)

    assert _contents(results) == {"system-fact"}


# --- cache hits are post-filtered, whatever scope they sit in ------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("principal, expected", WHO)
async def test_a_tier1_hit_is_post_filtered(harness, principal, expected):
    """Seed the exact-match cache in the reader's own scope with facts it may not all read."""
    scope = await cache_scope(principal)
    key = harness.svc._build_cache_key(QUERY, 5, True, None, scope)
    harness.svc._cache[key] = (list(EVERYTHING), 9e12)

    results = await harness.search(principal, max_results=5)

    assert _contents(results) == expected
    harness.svc.optimizer.advanced_search.assert_not_called()


@pytest.mark.asyncio
async def test_a_tier0_hit_is_post_filtered_through_the_stored_top_result_metadata(harness):
    """A semantic hit holds only the top result; its stored ownership metadata decides if B may have it."""
    for principal, served in ((PRINCIPAL_A, True), (PRINCIPAL_B, False)):
        scope = await cache_scope(principal)
        await harness.semantic.store(
            QUERY, "a-own", "rag", embedding=VECTOR, scope=scope, metadata={RESULT_METADATA_KEY: A_OWN.metadata}
        )
        harness.svc.optimizer.advanced_search.reset_mock()

        results = await harness.search(principal, max_results=5)

        assert (results[0].metadata.get("source") == "semantic_cache") is served
        assert harness.svc.optimizer.advanced_search.await_count == (0 if served else 1)
        assert "a-own" not in _contents(results) or served


@pytest.mark.asyncio
async def test_a_tier2_hit_is_post_filtered(harness):
    from services.topic_retrieval_cache import CachedChunk

    chunks = [CachedChunk(r.content, r.metadata, 0.9) for r in EVERYTHING]
    await harness.topic.store([VECTOR] * len(chunks), chunks, scope=await cache_scope(PRINCIPAL_A))

    results = await harness.search(PRINCIPAL_A, max_results=5)

    assert _contents(results) == A_SEES
    harness.svc.optimizer.advanced_search.assert_not_called()


# --- the caches are partitioned by scope, and the epoch orphans them -----------------------------


@pytest.mark.asyncio
async def test_a_result_cached_for_a_is_a_miss_for_b_in_every_tier(harness):
    first = await harness.search(PRINCIPAL_A, max_results=5)
    again = await harness.search(PRINCIPAL_A, max_results=5)
    assert _contents(first) == A_SEES
    assert again[0].metadata["source"] == "semantic_cache" and again[0].content == "a-own"
    assert harness.svc.optimizer.advanced_search.await_count == 1, "A's second search must be a cache hit"

    for_b = await harness.search(PRINCIPAL_B, max_results=5)

    assert harness.svc.optimizer.advanced_search.await_count == 2, "B must miss every cache A filled"
    assert _contents(for_b) == B_SEES
    assert "a-own" not in _contents(for_b)


@pytest.mark.asyncio
async def test_an_unshare_bumps_the_epoch_and_orphans_as_cached_hit(harness):
    await harness.search(PRINCIPAL_A, max_results=5)
    await harness.search(PRINCIPAL_A, max_results=5)
    assert harness.svc.optimizer.advanced_search.await_count == 1

    manager = harness.svc.kb_adapter.kb.ownership_manager
    await manager.unshare_fact("shared-with-a", user_ids=["A"], fact_metadata=dict(SHARED_WITH_A.metadata))
    assert harness.epoch.bumps == 1

    await harness.search(PRINCIPAL_A, max_results=5)
    assert harness.svc.optimizer.advanced_search.await_count == 2, "the unshare must invalidate A's cached hit"


@pytest.mark.asyncio
async def test_an_evicted_epoch_does_not_revalidate_a_cached_hit(harness):
    await harness.search(PRINCIPAL_A, max_results=5)
    first = harness.epoch.value
    await harness.search(PRINCIPAL_A, max_results=5)
    assert harness.svc.optimizer.advanced_search.await_count == 1

    harness.epoch.evict()
    await harness.search(PRINCIPAL_A, max_results=5)

    assert harness.svc.optimizer.advanced_search.await_count == 2, "an eviction must not serve the old entry"
    assert harness.epoch.value not in (None, "0", first)


@pytest.mark.asyncio
async def test_cleanup_of_visibility_indexes_bumps_the_epoch(harness):
    manager = harness.svc.kb_adapter.kb.ownership_manager
    await manager.cleanup_ownership_indexes("f1", {"owner_id": "B", "visibility": "shared", "shared_with": ["A"]})

    assert harness.epoch.bumps == 1


@pytest.mark.asyncio
async def test_an_unreadable_epoch_skips_the_caches_instead_of_serving_them(harness):
    await harness.search(PRINCIPAL_A, max_results=5)  # fills the caches while the epoch is readable
    with patch("knowledge.acl_epoch.get_async_redis_client", new=AsyncMock(return_value=None)):
        results = await harness.search(PRINCIPAL_A, max_results=5)

    assert _contents(results) == A_SEES
    assert harness.svc.optimizer.advanced_search.await_count == 2, "no tier may answer without a readable epoch"


@pytest.mark.asyncio
async def test_results_are_filtered_before_they_are_stored(harness):
    """What the semantic and topic caches hold for A's scope is already A's view."""
    await harness.search(PRINCIPAL_A, max_results=5)

    stored = {row[1].get("scope") for row in harness.semantic._collection.rows}
    assert len(stored) == 1
    payloads = [chunk for call in harness.topic._store_chunks.await_args_list for chunk in call.args[1]]
    assert payloads and {chunk["content"] for chunk in payloads} <= A_SEES
