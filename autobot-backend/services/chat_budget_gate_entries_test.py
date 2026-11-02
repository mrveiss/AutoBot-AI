# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The chat budget gate at the entries that found it missing in review (#16845).

Compare, the REST send path, the two transcript streams, graph resume, and the
hourly-policy rule. See ``chat_budget_gate_test.py`` for the gate itself.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import fakeredis
import fakeredis.aioredis as fakeredis_async
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.budget_policy as bp_mod
import services.chat_budget_gate as gate
from autobot_shared.time_utils import now_utc
from llm_shared.models import LLMRequest, LLMResponse
from llm_shared.run_credentials import get_llm_principal, llm_principal_scope
from services.budget_policy import (
    ACTION_ALERT_THEN_PAUSE,
    PERIOD_DAY,
    PERIOD_HOUR,
    SCOPE_USER,
    BudgetPolicy,
    create_policy,
)

USER, ORG = "alice", "acme"


@pytest_asyncio.fixture
async def redis(monkeypatch):
    client = fakeredis_async.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)

    async def _client(*_a, **_k):
        return client

    monkeypatch.setattr(bp_mod, "get_async_redis_client", _client)
    monkeypatch.setattr(gate, "get_async_redis_client", _client)
    monkeypatch.setattr("services.audit.audit.record", AsyncMock())
    yield client
    await client.aclose()


async def _over_budget(redis, user=USER, period=PERIOD_DAY, limit=1.0):
    await create_policy(
        BudgetPolicy(
            scope=SCOPE_USER, scope_id=user, period=period, threshold_usd=limit, action=ACTION_ALERT_THEN_PAUSE
        )
    )
    key = f"{gate.USER_SPEND_NS}:{user}:daily:{now_utc().strftime('%Y-%m-%d')}"
    await redis.incrbyfloat(key, limit * 3)


@pytest.mark.asyncio
async def test_hourly_policy_is_skipped_until_an_hourly_counter_exists(redis):
    await _over_budget(redis, period=PERIOD_HOUR)
    with llm_principal_scope(USER, ORG):
        await gate.enforce_chat_budget()


def test_compare_refuses_with_402_before_the_stream_starts(redis, monkeypatch):
    from api import chat_compare
    from auth_middleware import get_current_user

    app = FastAPI()
    app.include_router(chat_compare.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": USER, "org_id": ORG}
    monkeypatch.setattr(chat_compare, "_get_compare_interface", AsyncMock())
    fan_out = MagicMock()
    monkeypatch.setattr(chat_compare, "_fan_out_stream", fan_out)
    import asyncio

    asyncio.run(_over_budget(redis))
    response = TestClient(app).post("/chat/compare", json={"prompt": "hi", "models": ["a/b"]})
    assert response.status_code == 402
    assert response.json()["detail"]["i18n_key"] == "chat.errors.budgetExhausted"
    fan_out.assert_not_called()


@pytest.mark.asyncio
async def test_rest_send_shows_the_refusal_not_a_generic_retry(redis):
    from api.chat import _generate_ai_response

    request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    with llm_principal_scope(USER, ORG):
        await _over_budget(redis)
        refusal = await gate.chat_budget_refusal(request)
    service = MagicMock(chat=AsyncMock(return_value=refusal))
    reply, raw = await _generate_ai_response(service, [], "s", "r")
    assert raw is None
    assert reply["role"] == "assistant" and reply["content"] == refusal.error
    assert reply["metadata"]["error_code"] == gate.CHAT_BUDGET_ERROR_CODE
    assert reply["metadata"]["i18n_key"] == gate.CHAT_BUDGET_I18N_KEY

    other = MagicMock(chat=AsyncMock(return_value=LLMResponse(content="", error="Please try again. quota")))
    reply, _ = await _generate_ai_response(other, [], "s", "r")
    assert "try again" in reply["content"] and "metadata" not in reply


@pytest.mark.asyncio
async def test_a_text_that_looks_like_a_refusal_is_not_one():
    from services.chat_budget_gate import is_budget_refusal

    assert not is_budget_refusal(LLMResponse(content="", error=gate.ChatBudgetExceeded.__name__))


@pytest.mark.asyncio
async def test_transcript_stream_sends_the_refusal_message(monkeypatch):
    from api import transcripts

    policy = BudgetPolicy(scope=SCOPE_USER, scope_id=USER, period=PERIOD_DAY, threshold_usd=2.0)
    exc = gate.ChatBudgetExceeded(policy, 3.0)

    async def _stream(*_a, **_k):
        raise exc
        yield  # pragma: no cover

    monkeypatch.setattr(transcripts, "get_llm_service", lambda: SimpleNamespace(stream=_stream))
    monkeypatch.setattr(transcripts, "_analysis_messages", lambda *_: [])
    chunks = [c async for c in transcripts._stream_analysis("t", MagicMock(), user_id=USER)]
    assert exc.message in "".join(chunks) and "Analysis failed" not in "".join(chunks)


@pytest.mark.asyncio
async def test_transcript_websocket_runs_under_the_canonical_principal(monkeypatch):
    from api import transcripts

    seen = {}

    async def _stream(_content, _request, *, user_id, recording_id):
        seen["principal"], seen["spend_id"] = get_llm_principal(), user_id
        yield "x"

    ws = MagicMock(receive_json=AsyncMock(return_value={}), send_text=AsyncMock(), close=AsyncMock())
    ws.client_state = transcripts.WebSocketState.CONNECTED
    monkeypatch.setattr(transcripts, "TranscriptAnalyzeRequest", lambda **_: MagicMock())
    monkeypatch.setattr(transcripts, "_validate_analysis_request", lambda _r: None)
    monkeypatch.setattr(transcripts, "_load_transcript_content", AsyncMock(return_value="c"))
    monkeypatch.setattr(transcripts, "_stream_analysis", _stream)
    # ``id`` differs from ``user_id``: the transcriber id is user_id, the principal id (chat's key) is id.
    user = {"id": "principal-1", "user_id": "legacy-1", "org_id": ORG}
    await transcripts._run_analysis_session(ws, "7", user)
    assert seen["principal"] == ("principal-1", ORG)
    assert seen["spend_id"] == "principal-1"


@pytest.mark.asyncio
async def test_transcriber_ask_sends_the_refusal_as_an_error_event(monkeypatch):
    from transcriber.routes import ai

    policy = BudgetPolicy(scope=SCOPE_USER, scope_id=USER, period=PERIOD_DAY, threshold_usd=2.0)
    exc = gate.ChatBudgetExceeded(policy, 3.0)

    async def _stream(*_a, **_k):
        assert get_llm_principal() == ("principal-1", ORG)
        raise exc
        yield  # pragma: no cover

    monkeypatch.setattr(ai, "get_llm_service", lambda: SimpleNamespace(stream=_stream))
    monkeypatch.setattr(ai, "build_segment_list", AsyncMock(return_value=[]))
    monkeypatch.setattr(ai, "caller_can_access", lambda *_: True)
    monkeypatch.setattr(ai, "get_system_prompt", lambda *_a, **_k: "s")
    monkeypatch.setattr(ai, "build_context", lambda _s: "c")
    db = MagicMock(get_recording=AsyncMock(return_value=object()))
    request = SimpleNamespace(
        state=SimpleNamespace(user=SimpleNamespace(id="legacy-1", principal_id="principal-1", org_id=ORG))
    )
    response = await ai.ai_ask(3, SimpleNamespace(action="summary", custom_question=None), request, db)
    body = "".join([c async for c in response.body_iterator])
    assert exc.message in body and "AI analysis failed" not in body


@pytest.mark.asyncio
async def test_resumed_graph_turn_runs_under_the_principal(monkeypatch):
    import chat_workflow.graph as graph_mod
    from chat_workflow import manager as manager_mod

    seen = {}

    async def _turn(*_a, **_k):
        seen["principal"] = get_llm_principal()
        yield "msg"

    monkeypatch.setattr(graph_mod, "get_compiled_graph", AsyncMock(return_value=object()))
    monkeypatch.setattr(manager_mod, "stream_graph_turn", _turn)
    out = [
        m
        async for m in manager_mod.ChatWorkflowManager.resume_graph(
            MagicMock(), "s", {"approved": True}, auth_scope={"user_id": USER, "org_id": ORG}
        )
    ]
    assert out == ["msg"] and seen["principal"] == (USER, ORG)
    assert get_llm_principal() is None
