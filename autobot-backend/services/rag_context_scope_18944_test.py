# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The assembled RAG context holds only what its caller may read (#18944, slice 2 of #16664).

User B's private fact must not reach user A's ``context`` from ``/advanced_search`` with
``return_context=true``, from ``/retrieval_context`` (``rag`` strategy and the CAG fallback), from the
synthesis and lessons legs, or from the chat doc-chunk leg. Every test runs the real
``KnowledgeOwnership`` through the real ``RAGService`` and ``AdvancedRAGOptimizer`` -- only the retrieval
sources and the content firewall are faked -- and each deny has a positive control for A's own fact.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from advanced_rag_optimizer import AdvancedRAGOptimizer, RAGMetrics, RankedResult
from api.knowledge_rag import advanced_search, retrieval_context
from knowledge.ownership import KnowledgeOwnership
from knowledge.platform_docs import PLATFORM_DOCS_GRANT
from knowledge.schemas.rag import AdvancedSearchRequest, RetrievalContextRequest
from knowledge.search_filters import SYSTEM_SCOPE, kb_principal
from services.knowledge.service import ChatKnowledgeService
from services.rag_config import RAGConfig
from services.rag_service import RAGService

QUERY = "how do I restart the service"
A_FACT = "A-OWN-FACT-TEXT"
B_FACT = "B-PRIVATE-FACT-TEXT"
USER_A = {"user_id": "A", "role": "user"}


def _ranked(content: str, **metadata) -> RankedResult:
    return RankedResult(
        content=content,
        metadata={"fact_id": content, **metadata},
        semantic_score=0.9,
        keyword_score=0.5,
        hybrid_score=0.8,
        relevance_rank=1,
        source_path=f"kb/{content}",
    )


A_OWN = _ranked(A_FACT, owner_id="A", visibility="private")
B_PRIVATE = _ranked(B_FACT, owner_id="B", visibility="private")


def _service(*, lessons: bool = False) -> RAGService:
    """A RAGService over the real optimizer and a real ownership manager; only retrieval is faked."""
    ownership = KnowledgeOwnership(redis_client=object())
    optimizer = AdvancedRAGOptimizer()
    optimizer.kb = SimpleNamespace(ownership_manager=ownership)
    optimizer.advanced_search = AsyncMock(return_value=([B_PRIVATE, A_OWN], RAGMetrics()))
    svc = RAGService.__new__(RAGService)
    svc.config = RAGConfig(enable_analyzer_lessons=lessons, enable_cag=True)
    svc._initialized = True
    svc.optimizer = optimizer
    svc.kb_adapter = SimpleNamespace(kb=SimpleNamespace(ownership_manager=ownership))
    svc.advanced_search = AsyncMock(return_value=([], RAGMetrics()))  # the CAG candidate ranking: empty -> fallback
    return svc


def _kb_fact(content: str, **metadata) -> dict:
    """A fact as ``kb.search`` returns it -- the layer BELOW the optimizer's query cache."""
    return {"content": content, "score": 0.9, "metadata": {"fact_id": content, **metadata}}


def _service_below_cache(b_facts: int = 1) -> RAGService:
    """``_service`` with the real ``advanced_search`` (and its real ``query_cache``) left running.

    Only the KB search and the cross-encoder are faked, so a second identical query is a true cache hit.
    """
    svc = _service()
    facts = [_kb_fact(f"{B_FACT}-{i}", owner_id="B", visibility="private") for i in range(b_facts)]
    facts.append(_kb_fact(A_FACT, owner_id="A", visibility="private"))
    del svc.optimizer.advanced_search  # drop the instance mock; the class method runs
    svc.optimizer.kb.search = AsyncMock(return_value=facts)
    svc.optimizer.kb.get_all_facts = AsyncMock(return_value=[])
    svc.optimizer._rerank_with_cross_encoder = AsyncMock(side_effect=lambda _q, results: results)
    return svc


@pytest.fixture(autouse=True)
def _no_firewall_and_no_chroma():
    """Pass the context through the firewall unchanged; leave the synthesis collections unreachable."""

    async def passthrough(content, **_):
        return SimpleNamespace(blocked=False, content=content)

    with (
        patch("security.content_firewall.inspect_rag_context", new=passthrough),
        patch("knowledge.backends.get_async_default_client", new=AsyncMock(side_effect=ConnectionError("down"))),
    ):
        yield


def _assert_scoped(context: str) -> None:
    assert A_FACT in context, f"positive control: A's own fact must be in A's context: {context!r}"
    assert B_FACT not in context, f"B's private fact leaked into A's context: {context!r}"


# --- the contract: a principal is required ------------------------------------------------------


@pytest.mark.asyncio
async def test_get_optimized_context_without_a_principal_raises_type_error_and_reads_nothing():
    svc = _service()
    with pytest.raises(TypeError):
        await svc.get_optimized_context(QUERY)
    svc.optimizer.advanced_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_optimized_context_with_a_none_principal_raises_value_error_and_reads_nothing():
    svc = _service()
    with pytest.raises(ValueError):
        await svc.get_optimized_context(QUERY, principal=None)
    svc.optimizer.advanced_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_optimizer_context_path_requires_a_principal_too():
    svc = _service()
    with pytest.raises(TypeError):
        await svc.optimizer.get_optimized_context(QUERY)
    with pytest.raises(ValueError):
        await svc.optimizer.get_optimized_context(QUERY, principal=None)
    svc.optimizer.advanced_search.assert_not_awaited()


# --- the service ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_optimized_context_keeps_only_what_the_principal_may_read():
    context, _ = await _service().get_optimized_context(QUERY, principal=kb_principal(USER_A))
    _assert_scoped(context)


@pytest.mark.asyncio
async def test_system_scope_context_holds_no_private_fact():
    context, _ = await _service().get_optimized_context(QUERY, principal=SYSTEM_SCOPE)
    assert A_FACT not in context and B_FACT not in context


@pytest.mark.asyncio
async def test_the_optimizer_cache_cannot_carry_one_callers_facts_to_another():
    """The optimizer's own query cache holds unfiltered results; each reader filters after the read."""
    svc = _service_below_cache()
    for_b, _ = await svc.get_optimized_context(QUERY, principal=kb_principal({"user_id": "B"}))
    searches_after_miss = svc.optimizer.kb.search.await_count  # primary query plus its expanded-query fan-out
    assert searches_after_miss >= 1
    for_a, _ = await svc.get_optimized_context(QUERY, principal=kb_principal(USER_A))
    # The key is query|max_results|rerank|min_score, with no principal: A is served B's cached, unfiltered result.
    assert svc.optimizer.kb.search.await_count == searches_after_miss, "the second call must be a real query_cache hit"
    assert len(svc.optimizer.query_cache) == 1
    assert f"{B_FACT}-0" in for_b and A_FACT not in for_b
    _assert_scoped(for_a)


@pytest.mark.asyncio
async def test_metrics_report_only_the_callers_visible_count_not_what_others_hold():
    """User B holds 5 private facts for the query; A's metrics must not reveal that (existence side-channel)."""
    svc = _service_below_cache(b_facts=5)
    _, for_b = await svc.get_optimized_context(QUERY, principal=kb_principal({"user_id": "B"}))
    searches_after_miss = svc.optimizer.kb.search.await_count  # primary query plus its expanded-query fan-out
    _, for_a = await svc.get_optimized_context(QUERY, principal=kb_principal(USER_A))
    _, for_b_again = await svc.get_optimized_context(QUERY, principal=kb_principal({"user_id": "B"}))
    assert svc.optimizer.kb.search.await_count == searches_after_miss, "calls 2 and 3 share the cached search"
    assert (for_a.final_results_count, for_a.documents_considered) == (1, 1)
    assert (for_b.final_results_count, for_b.documents_considered) == (5, 5)
    assert for_b_again.final_results_count == 5, "A's clamp must not mutate the cached metrics object"


@pytest.mark.asyncio
async def test_retrieval_context_rag_response_metrics_hide_other_users_fact_count():
    svc = _service_below_cache(b_facts=5)
    response = await retrieval_context(
        request=RetrievalContextRequest(query=QUERY, mode="rag"),
        http_request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
        rag_service=svc,
        current_user=USER_A,
    )
    assert response["metrics"]["final_results_count"] == 1
    assert response["metrics"]["documents_considered"] == 1


# --- the API layer ------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_advanced_search_return_context_hides_another_users_private_fact():
    result = await advanced_search(
        request=AdvancedSearchRequest(query=QUERY, return_context=True),
        rag_service=_service(),
        current_user=USER_A,
    )
    _assert_scoped(result["context"])


async def _retrieval_context(svc: RAGService, mode: str) -> str:
    response = await retrieval_context(
        request=RetrievalContextRequest(query=QUERY, mode=mode),
        http_request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace())),
        rag_service=svc,
        current_user=USER_A,
    )
    return response["context"]


@pytest.mark.asyncio
async def test_retrieval_context_rag_strategy_hides_another_users_private_fact():
    _assert_scoped(await _retrieval_context(_service(), "rag"))


@pytest.mark.asyncio
async def test_retrieval_context_cag_fallback_hides_another_users_private_fact():
    svc = _service()
    context = await _retrieval_context(svc, "cag")
    svc.advanced_search.assert_awaited_once()  # the CAG ranking ran and found nothing, so it fell back
    _assert_scoped(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("miss", ["unreadable", "over_budget"])
async def test_retrieval_context_cag_unreadable_or_budget_miss_fallback_hides_private_fact(miss):
    """CAG ranked a candidate but could not load it (unreadable / over budget): the RAG fallback is scoped."""
    svc = _service()
    svc.advanced_search = AsyncMock(return_value=([A_OWN], RAGMetrics()))  # a candidate, so no early fallback
    content = None if miss == "unreadable" else "x" * 400
    with (
        patch("services.cag_service._read_source_file", new=AsyncMock(return_value=content)),
        patch("services.cag_service.CAGService._budget", return_value=1),
    ):
        context = await _retrieval_context(svc, "cag")
    svc.advanced_search.assert_awaited_once()
    _assert_scoped(context)


# --- the derived-content legs -------------------------------------------------------------------


def _collection(docs: dict) -> AsyncMock:
    """A ChromaDB collection holding ``{doc: metadata}``."""
    col = AsyncMock()
    col.query = AsyncMock(
        return_value={
            "ids": [[f"id-{i}" for i in range(len(docs))]],
            "documents": [list(docs)],
            "metadatas": [list(docs.values())],
        }
    )
    return col


@pytest.mark.asyncio
async def test_synthesis_leg_drops_a_summary_the_caller_may_not_read():
    svc = _service()
    col = _collection(
        {
            "platform-summary": dict(PLATFORM_DOCS_GRANT),
            "summary-of-b-private": {"owner_id": "B", "visibility": "private"},
            "summary-without-metadata": {},
        }
    )
    client = AsyncMock()
    client.get_or_create_collection = AsyncMock(return_value=col)
    with patch("knowledge.backends.get_async_default_client", new=AsyncMock(return_value=client)):
        text = await svc._get_kb_synthesis_context(QUERY, kb_principal(USER_A))
    assert "platform-summary" in text
    assert "summary-of-b-private" not in text
    # Synthesis collections are platform-only by construction, so a pre-grant summary reads as platform docs.
    assert "summary-without-metadata" in text


@pytest.mark.asyncio
async def test_legacy_synthesis_summary_is_granted_at_read_time_and_never_rewritten():
    svc = _service()
    col = _collection({"legacy-summary": {"source_paths": "docs/a.md"}})
    client = AsyncMock()
    client.get_or_create_collection = AsyncMock(return_value=col)
    with patch("knowledge.backends.get_async_default_client", new=AsyncMock(return_value=client)):
        assert "legacy-summary" in await svc._get_kb_synthesis_context(QUERY, kb_principal(USER_A))
        assert "legacy-summary" in await svc._get_kb_synthesis_context(QUERY, SYSTEM_SCOPE)
    col.upsert.assert_not_called()
    col.update.assert_not_called()
    col.delete.assert_not_called()


@pytest.mark.asyncio
async def test_lessons_leg_keeps_only_lessons_the_caller_may_read():
    svc = _service(lessons=True)
    col = _collection({"a-lesson": {"owner_id": "A", "visibility": "private"}, "b-lesson": {"owner_id": "B"}})
    client = AsyncMock()
    client.get_or_create_collection = AsyncMock(return_value=col)
    with patch("knowledge.backends.get_async_default_client", new=AsyncMock(return_value=client)):
        text = await svc._get_analyzer_lessons_context(QUERY, kb_principal(USER_A))
    assert "a-lesson" in text and "b-lesson" not in text


@pytest.mark.asyncio
async def test_lessons_leg_grants_nothing_at_read_time_but_honours_a_written_grant():
    """``autobot_lessons`` can hold lessons derived from a user's query, so a scope-less one stays private."""
    svc = _service(lessons=True)
    col = _collection({"granted-lesson": dict(PLATFORM_DOCS_GRANT), "legacy-lesson": {"domain": "retrieval"}})
    client = AsyncMock()
    client.get_or_create_collection = AsyncMock(return_value=col)
    with patch("knowledge.backends.get_async_default_client", new=AsyncMock(return_value=client)):
        text = await svc._get_analyzer_lessons_context(QUERY, kb_principal(USER_A))
    assert "granted-lesson" in text and "legacy-lesson" not in text


# --- chat doc chunks ----------------------------------------------------------------------------


def _chat_service(chunks: list) -> ChatKnowledgeService:
    svc = ChatKnowledgeService.__new__(ChatKnowledgeService)
    svc.rag_service = _service()
    svc.doc_searcher = SimpleNamespace(is_documentation_query=lambda _q: True, search=lambda **_: list(chunks))
    return svc


@pytest.mark.asyncio
async def test_doc_chunks_carrying_the_platform_grant_pass_and_others_do_not():
    chunks = [
        {"content": "platform-doc", "metadata": dict(PLATFORM_DOCS_GRANT)},
        {"content": "b-private-chunk", "metadata": {"owner_id": "B", "visibility": "private"}},
        {"content": "chunk-without-metadata"},
    ]
    kept = await _chat_service(chunks)._retrieve_raw_doc_results(QUERY, principal=kb_principal(USER_A))
    assert [c["content"] for c in kept] == ["platform-doc"]


@pytest.mark.asyncio
async def test_doc_chunks_without_a_principal_raise_before_any_read():
    with pytest.raises(TypeError):
        await _chat_service([])._retrieve_raw_doc_results(QUERY)
    with pytest.raises(ValueError):
        await _chat_service([])._retrieve_raw_doc_results(QUERY, principal=None)
