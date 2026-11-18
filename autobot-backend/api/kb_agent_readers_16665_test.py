# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent, chat-knowledge, research and task readers serve only what their user may read (#16665)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agents.knowledge_retrieval_agent import KnowledgeRetrievalAgent
from api.agent import comprehensive_research_task
from api.agent_kb_context import _enhance_context_with_kb
from api.chat_knowledge_manager import ChatKnowledgeManager
from api.schemas_agent_requests import ResearchTaskRequest
from knowledge.read_path_fakes_16665 import PRIVATE_A, FakeKB, text_of
from services.research.planner import SubQuestion, filter_skip_known
from task_handlers.knowledge_base_handlers import KBSearchHandler


class _Payload:
    goal, use_knowledge_base, context = "g", True, None


@pytest.mark.asyncio
async def test_orchestrated_goal_context_never_carries_another_users_private_fact():
    for_bob = await _enhance_context_with_kb(_Payload, FakeKB(), "bob")
    for_alice = await _enhance_context_with_kb(_Payload, FakeKB(), "alice")
    for_nobody = await _enhance_context_with_kb(_Payload, FakeKB(), None)

    assert PRIVATE_A not in str(for_bob) and PRIVATE_A not in str(for_nobody)
    assert PRIVATE_A in str(for_alice)


@pytest.mark.asyncio
async def test_research_task_route_scopes_its_kb_context_to_the_caller():
    ai_client = AsyncMock()
    ai_client.multi_agent_query.return_value = {"result": "ok"}

    async def run(user):
        with patch("api.agent.get_ai_stack_client", AsyncMock(return_value=ai_client)):
            await comprehensive_research_task(
                request_data=ResearchTaskRequest(research_query="q", include_web=False),
                knowledge_base=FakeKB(),
                current_user=user,
            )
        return ai_client.multi_agent_query.await_args.kwargs["query"]

    assert PRIVATE_A not in await run({"user_id": "bob"})
    assert PRIVATE_A in await run({"user_id": "alice"})
    assert PRIVATE_A not in await run({"user_id": "root", "role": "admin"})  # no admin bypass for an agent run


def _retrieval_agent():
    agent = object.__new__(KnowledgeRetrievalAgent)
    agent.knowledge_base, agent.model_name = FakeKB(), "m"
    agent._ensure_kb_initialized = AsyncMock()
    agent._generate_quick_summary = AsyncMock(return_value="")
    return agent


def _request(user_id):
    return SimpleNamespace(payload={"query": "q", "top_k": 5, "min_score": 0.0}, metadata={"user_id": user_id})


@pytest.mark.asyncio
async def test_knowledge_retrieval_agent_reads_as_the_requests_user_only():
    agent = _retrieval_agent()

    assert PRIVATE_A not in text_of(await agent._handle_find_similar(_request("bob")))
    assert PRIVATE_A in text_of(await agent._handle_find_similar(_request("alice")))
    assert PRIVATE_A not in text_of(await agent._handle_find_similar(_request(None)))
    assert PRIVATE_A not in text_of(await agent._handle_query(_request("bob")))


@pytest.mark.asyncio
async def test_a_payload_supplied_user_id_is_never_trusted():
    agent = _retrieval_agent()
    request = SimpleNamespace(payload={"query": "q", "user_id": "alice"}, metadata={})

    assert PRIVATE_A not in text_of(await agent._handle_find_similar(request))


@pytest.mark.asyncio
async def test_chat_knowledge_search_withholds_another_users_private_fact():
    manager = ChatKnowledgeManager()
    manager.knowledge_base = FakeKB()

    for_bob = await manager.search_chat_knowledge("q", include_temporary=False, user_id="bob")
    for_alice = await manager.search_chat_knowledge("q", include_temporary=False, user_id="alice")
    for_nobody = await manager.search_chat_knowledge("q", include_temporary=False)

    assert PRIVATE_A not in text_of(for_bob) and PRIVATE_A not in text_of(for_nobody)
    assert PRIVATE_A in text_of(for_alice)


@pytest.mark.asyncio
async def test_a_private_fact_the_user_cannot_read_never_makes_the_planner_skip_work():
    class _KB(FakeKB):
        async def search(self, *a, **k):
            fact = {
                "id": "f-a",
                "content": "x",
                "metadata": {"owner_id": "alice", "visibility": "private", "confidence": 0.99, "fact_id": "f-a"},
            }
            return [fact]

    questions = [SubQuestion(text="what is X", expected_value=1.0)]

    _, skipped_for_bob = await filter_skip_known(_KB(), questions, "bob")
    _, skipped_for_alice = await filter_skip_known(_KB(), questions, "alice")

    assert skipped_for_bob == [] and len(skipped_for_alice) == 1


@pytest.mark.asyncio
async def test_research_route_passes_the_asking_user_to_the_orchestrator():
    from services.research import routes
    from services.research.models import ResearchResponse

    orchestrator = MagicMock()
    orchestrator.research = AsyncMock(return_value=ResearchResponse(answer="a", confidence=0.5))
    app = FastAPI()
    app.include_router(routes.router, prefix="/research")
    app.dependency_overrides[routes.get_current_user] = lambda: {"user_id": "bob"}
    with patch.object(routes, "_get_orchestrator", return_value=orchestrator):
        TestClient(app).post("/research", json={"question": "why"})

    assert orchestrator.research.await_args.kwargs["user_id"].user_id == "bob"


@pytest.mark.asyncio
async def test_kb_search_task_reads_as_the_triggering_user_and_denies_without_one():
    async def run(metadata):
        kb = FakeKB()
        ctx = MagicMock(metadata=metadata)
        ctx.require_payload_value.return_value = "q"
        ctx.get_payload_value.return_value = 5
        ctx.worker.resolve_knowledge_base = AsyncMock(return_value=kb)
        return await KBSearchHandler().execute(ctx)

    assert PRIVATE_A in text_of(await run({"user_id": "alice"}))
    assert PRIVATE_A not in text_of(await run({"user_id": "bob"}))
    assert PRIVATE_A not in text_of(await run({}))
