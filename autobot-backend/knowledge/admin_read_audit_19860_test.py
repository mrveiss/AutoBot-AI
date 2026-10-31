# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Explicit admin reads and the root read are audited on the route, committed, bounded and 503 on failure (#19860)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from knowledge.ownership import KnowledgeOwnership
from knowledge.remote_read import admit_remote_read
from knowledge.root_read import admin_read_audit
from knowledge.search_filters import filter_search_results_by_permission, kb_principal

STORE = "services.audit.store.insert_event"
PRIVATE_OF_B = {"id": "f-b", "content": "b-secret", "metadata": {"owner_id": "B", "visibility": "private"}}
OWN = {"id": "f-a", "content": "a-own", "metadata": {"owner_id": "A", "visibility": "private"}}
ADMIN = {"user_id": "A", "role": "admin", "auth_method": "jwt"}
DEV_ADMIN = {"username": "dev_admin", "role": "admin", "auth_method": "development"}
SUPERADMIN = {"user_id": "A", "role": "superadmin", "auth_method": "jwt"}
USER = {"user_id": "A", "role": "user", "auth_method": "jwt"}


class _Audit:
    """The real audit write path with the store replaced; analysis is a no-op, Redis is left to the caller."""

    def __init__(self, store, redis=None):
        self.store = store
        self.redis = redis if redis is not None else AsyncMock(return_value=None)

    def __enter__(self):
        self._p = [
            patch(STORE, new=self.store),
            patch("services.audit.audit._analyse_for_threats", new=AsyncMock()),
            patch("services.audit.audit.get_async_redis_client", new=self.redis),
        ]
        for p in self._p:
            p.start()
        return self.store

    def __exit__(self, *exc):
        for p in self._p:
            p.stop()


def _kb(facts):
    return SimpleNamespace(ownership_manager=KnowledgeOwnership(MagicMock()), search=AsyncMock(return_value=facts))


async def _drain():
    for _ in range(5):
        await asyncio.sleep(0)


# -- defect 1: the unaudited is_admin_role reads on the search routes --------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("who", [ADMIN, DEV_ADMIN])
async def test_an_admin_read_through_the_filter_is_audited_once_with_the_fact_ids(who):
    with _Audit(AsyncMock()) as store:
        async with admin_read_audit(who, "A", "kb.search") as scope:
            await filter_search_results_by_permission(
                [PRIVATE_OF_B, OWN], "A", None, [], ownership_manager=KnowledgeOwnership(MagicMock()), is_admin=scope
            )
    store.assert_awaited_once()
    event = store.await_args.args[0]
    assert event.action == "kb.admin_read" and event.metadata["details"]["fact_ids"] == ["f-b", "f-a"]
    assert "b-secret" not in str(event.metadata)  # ids, never content


@pytest.mark.asyncio
async def test_a_failing_store_turns_the_admin_search_into_503_and_returns_nothing():
    with _Audit(AsyncMock(side_effect=RuntimeError("db down"))), pytest.raises(HTTPException) as refused:
        async with admin_read_audit(ADMIN, "A", "kb.search") as scope:
            await filter_search_results_by_permission(
                [PRIVATE_OF_B], "A", None, [], ownership_manager=KnowledgeOwnership(MagicMock()), is_admin=scope
            )
            return_value = "the response"  # noqa: F841 -- never reaches the caller: exit raises
    assert refused.value.status_code == 503


@pytest.mark.asyncio
async def test_a_non_admin_is_scoped_and_never_audited_on_the_search_routes():
    with _Audit(AsyncMock()) as store:
        async with admin_read_audit(USER, "A", "kb.search") as scope:
            assert scope is False
            kept = await filter_search_results_by_permission(
                [PRIVATE_OF_B, OWN], "A", None, [], ownership_manager=KnowledgeOwnership(MagicMock()), is_admin=scope
            )
    assert [r["id"] for r in kept] == ["f-a"]
    store.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_multi_source_search_route_audits_an_admin_and_503s_on_a_failing_store():
    from api import knowledge_search_aggregator as agg

    body = SimpleNamespace(
        query="q", limit=5, include_sources=["facts"], expand_relations=False, doc_results=0, min_score=0.0
    )
    kb = _kb({"results": [PRIVATE_OF_B, OWN]})
    with patch.object(agg, "get_or_create_knowledge_base", new=AsyncMock(return_value=kb)):
        with _Audit(AsyncMock()) as store:
            out = await agg.search(MagicMock(), body, ADMIN)
        assert [f["id"] for f in out["facts"]] == ["f-b", "f-a"] and store.await_count == 1
        with _Audit(AsyncMock(side_effect=RuntimeError("db down"))), pytest.raises(HTTPException) as refused:
            await agg.search(MagicMock(), body, ADMIN)
        assert refused.value.status_code == 503
        with _Audit(AsyncMock()) as store:
            out = await agg.search(MagicMock(), body, USER)
        assert [f["id"] for f in out["facts"]] == ["f-a"]
        store.assert_not_awaited()


# -- defect 2: the audited root results are the returned ones -------------------------------------------------


@pytest.mark.asyncio
async def test_the_rag_route_returns_the_root_results_the_service_audited():
    from api import knowledge_rag

    private = {"content": "x", "metadata": {"fact_id": "f-b", "owner_id": "B", "visibility": "private"}}
    service = SimpleNamespace(
        advanced_search=AsyncMock(return_value=([object()], MagicMock())),
        kb_adapter=SimpleNamespace(kb=SimpleNamespace(ownership_manager=KnowledgeOwnership(MagicMock()))),
    )
    request = SimpleNamespace(query="q", max_results=5, enable_reranking=False, timeout=None, return_context=False)
    with (
        patch.object(knowledge_rag, "_convert_results_to_dicts", return_value=[dict(private, id="f-b")]),
        patch.object(knowledge_rag, "_build_search_metrics", return_value={}),
    ):
        root = await knowledge_rag.advanced_search(request, service, SUPERADMIN)
        scoped = await knowledge_rag.advanced_search(request, service, USER)
    assert root["total_results"] == 1  # audited by the service's root view, so it is returned
    assert scoped["total_results"] == 0
    assert service.advanced_search.await_args_list[0].kwargs["principal"].is_superadmin is True


# -- defect 3: a failed audit is a 503 that is told apart from "no facts" ---------------------------------------


@pytest.mark.asyncio
async def test_the_refusal_is_a_503_with_a_stable_detail_not_an_empty_200():
    with _Audit(AsyncMock(side_effect=RuntimeError("db down"))), pytest.raises(HTTPException) as refused:
        async with admin_read_audit(ADMIN, "A", "kb.search") as scope:
            await filter_search_results_by_permission(
                [OWN], "A", None, [], ownership_manager=KnowledgeOwnership(MagicMock()), is_admin=scope
            )
    assert refused.value.detail == "Audit unavailable; the read is withheld"


# -- items 4 and 5: Redis down after a commit; a slow store; the background legs -----------------------------------


@pytest.mark.asyncio
async def test_a_redis_outage_after_the_commit_still_counts_as_written():
    from services.audit import audit as canonical
    from services.audit.taxonomy import AuditCategory, AuditEvent

    event = AuditEvent(category=AuditCategory.KNOWLEDGE, action="kb.admin_read", actor_id="A")
    with _Audit(AsyncMock(), redis=AsyncMock(side_effect=ConnectionError("redis down"))) as store:
        assert await canonical.record(event) is True
        assert await canonical.record_committed(event) is True
        await _drain()
    assert store.await_count == 2


@pytest.mark.asyncio
async def test_an_admin_read_succeeds_when_only_redis_is_down():
    with _Audit(AsyncMock(), redis=AsyncMock(side_effect=ConnectionError("redis down"))):
        async with admin_read_audit(ADMIN, "A", "kb.search") as scope:
            kept = await filter_search_results_by_permission(
                [PRIVATE_OF_B], "A", None, [], ownership_manager=KnowledgeOwnership(MagicMock()), is_admin=scope
            )
        await _drain()
    assert [r["id"] for r in kept] == ["f-b"]


@pytest.mark.asyncio
async def test_a_store_slower_than_the_timeout_is_a_failed_write_and_a_503():
    async def hang(_event):
        await asyncio.sleep(5)

    with _Audit(hang), patch("services.audit.audit.AUDIT_DURABLE_TIMEOUT_SECONDS", 0.05):
        with pytest.raises(HTTPException) as refused:
            async with admin_read_audit(ADMIN, "A", "kb.search") as scope:
                await filter_search_results_by_permission(
                    [OWN], "A", None, [], ownership_manager=KnowledgeOwnership(MagicMock()), is_admin=scope
                )
    assert refused.value.status_code == 503


@pytest.mark.asyncio
async def test_the_threat_analysis_does_not_hold_the_request():
    from services.audit import audit as canonical
    from services.audit.taxonomy import AuditCategory, AuditEvent

    gate = asyncio.Event()

    async def slow_analysis(_event):
        await gate.wait()

    event = AuditEvent(category=AuditCategory.KNOWLEDGE, action="kb.admin_read", actor_id="A")
    with patch(STORE, new=AsyncMock()), patch("services.audit.audit._analyse_for_threats", new=slow_analysis):
        with patch("services.audit.audit._project", new=AsyncMock()):
            assert await asyncio.wait_for(canonical.record_committed(event), timeout=1.0) is True
            gate.set()
            await _drain()


# -- item 7: a read that names no facts does not need the audit DB ----------------------------------------------


@pytest.mark.asyncio
async def test_a_remote_read_that_names_no_facts_is_admitted_while_the_audit_store_is_down():
    with _Audit(AsyncMock(side_effect=RuntimeError("db down"))):
        await admit_remote_read(ADMIN, "ai_stack_stats")  # no 503: the write is scheduled, not awaited
        await _drain()


# -- item 6: the AI-stack routes deliver the superadmin's root read ------------------------------------------------


def _ai_client():
    client = MagicMock()
    client.rag_query = AsyncMock(return_value={"answer": "ok"})
    client.chat_message = AsyncMock(return_value={"answer": "ok"})
    return client


def _ai_kb():
    kb = _kb([PRIVATE_OF_B, OWN])
    return kb


@pytest.mark.asyncio
@pytest.mark.parametrize("who,expected", [(SUPERADMIN, ["f-b", "f-a"]), (ADMIN, ["f-a"]), (USER, ["f-a"])])
async def test_the_ai_stack_rag_routes_read_root_for_a_superadmin_only(who, expected):
    from api import ai_stack_integration as integration
    from api import knowledge_ai_stack as ai_stack

    kb = _ai_kb()
    client = _ai_client()
    request = SimpleNamespace(query="q", max_results=5, documents=None, context=None)
    stack_request = SimpleNamespace(query="q", documents=None, context=None, max_results=5, include_reasoning=False)
    with _Audit(AsyncMock()), patch.object(integration, "get_ai_stack_client", AsyncMock(return_value=client)):
        await integration.rag_query(request, True, kb, who)
    assert [d["id"] for d in client.rag_query.await_args.kwargs["documents"]] == expected
    client2 = _ai_client()
    with _Audit(AsyncMock()), patch.object(ai_stack, "get_ai_stack_client", AsyncMock(return_value=client2)):
        await ai_stack.rag_search(stack_request, kb, who)
    assert [d["id"] for d in client2.rag_query.await_args.kwargs["documents"]] == expected


@pytest.mark.asyncio
async def test_the_ai_stack_chat_route_reads_root_for_a_superadmin_and_503s_when_the_audit_is_down():
    from api import ai_stack_integration as integration

    kb = _ai_kb()
    client = _ai_client()
    request = SimpleNamespace(message="m", use_knowledge_base=True, context="", chat_history=None)
    with _Audit(AsyncMock()), patch.object(integration, "get_ai_stack_client", AsyncMock(return_value=client)):
        await integration.chat(request, True, kb, SUPERADMIN)
    assert "b-secret" in client.chat_message.await_args.kwargs["context"]
    client = _ai_client()
    with (
        _Audit(AsyncMock(side_effect=RuntimeError("db down"))),
        patch.object(integration, "get_ai_stack_client", AsyncMock(return_value=client)),
    ):
        with pytest.raises(HTTPException) as refused:
            await integration.chat(request, True, kb, SUPERADMIN)
    assert refused.value.status_code == 503
    client.chat_message.assert_not_awaited()


def test_the_principal_of_a_superadmin_still_comes_from_the_verified_identity():
    assert kb_principal(SUPERADMIN).is_superadmin is True
