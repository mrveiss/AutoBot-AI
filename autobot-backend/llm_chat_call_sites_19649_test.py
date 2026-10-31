# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
The four sites that called ``chat_completion`` on an ``LLMService`` (#19649).

Each double is ``make_llm_service_double()``, so a call to a
method ``LLMService`` does not define (``chat_completion``, ``llm_interface``)
raises ``AttributeError`` and fails the test, instead of passing against a
``MagicMock`` that accepts anything.
"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.agent_orchestration.routing import AgentRouter
from agents.agent_orchestration.types import AgentType
from async_chat_workflow import AsyncChatWorkflow
from autobot_shared.retry_mechanism import RetryExhaustedError
from llm_shared.models import LLMResponse
from modern_ai_integration import AIModelConfig, AIProvider, AIRequest, LocalModelProvider
from task_handlers.llm_handlers import LLMChatCompletionHandler
from tests.helpers._llm_service_double import make_llm_service_double

_ROUTE = json.dumps({"strategy": "single_agent", "primary_agent": "chat", "confidence": 0.9, "reasoning": "r"})


def _llm(content: str = "hi", error: str | None = None) -> MagicMock:
    llm = make_llm_service_double()
    llm.chat.return_value = LLMResponse(content=content, model="m", provider="p", error=error, usage={"total": 3})
    return llm


# -- routing ---------------------------------------------------------------


def _router(llm) -> AgentRouter:
    router = AgentRouter(agent_capabilities={AgentType.CHAT: MagicMock()}, llm_interface=llm)
    router._rl_router = None
    router.rl_routing_enabled = False
    return router


_AMBIGUOUS = "something ambiguous here please help me decide"


async def test_routing_calls_chat_and_parses_the_response_object():
    llm = _llm(_ROUTE)
    result = await _router(llm)._determine_routing_base(_AMBIGUOUS, {"session_id": "s1"})
    assert result["primary_agent"] == AgentType.CHAT and result["confidence"] == 0.9
    assert llm.chat.await_args.kwargs["conversation_id"] == "s1"


async def test_routing_falls_back_to_quick_route_on_error_response():
    llm = _llm("", error="provider down")
    result = await _router(llm)._determine_routing_base(_AMBIGUOUS, None)
    assert result["confidence"] != 0.9
    assert llm.chat.await_count == 1


# -- async chat workflow ---------------------------------------------------


async def test_workflow_calls_chat_with_dict_messages_and_chat_id():
    llm = _llm("answer")
    response = await AsyncChatWorkflow()._generate_llm_response("q", llm, [], "chat-7")
    assert response.content == "answer"
    messages = llm.chat.await_args.args[0]
    assert [m["role"] for m in messages] == ["system", "user"]
    assert llm.chat.await_args.kwargs["conversation_id"] == "chat-7"


async def test_workflow_raises_on_error_response_so_retry_sees_it():
    llm = _llm("", "provider down")
    with patch("autobot_shared.retry_mechanism.asyncio.sleep", new=AsyncMock()):
        with pytest.raises(RetryExhaustedError, match="provider down"):
            await AsyncChatWorkflow()._generate_llm_response("q", llm, [], "c")
    assert llm.chat.await_count == 3


# -- task handler ----------------------------------------------------------


def _ctx(llm, payload=None):
    worker = SimpleNamespace(llm_service=llm)
    ctx = MagicMock(worker=worker, task_id="t-1")
    values = {"model_name": "mm", "messages": [{"role": "user", "content": "x"}], **(payload or {})}
    ctx.require_payload_value.side_effect = values.__getitem__
    ctx.get_payload_value.side_effect = lambda k, d=None: values.get(k, d)
    return ctx


async def test_handler_calls_worker_llm_service_chat():
    llm = _llm("done")
    result = await LLMChatCompletionHandler().execute(_ctx(llm, {"kwargs": {"temperature": 0.1}}))
    kwargs = llm.chat.await_args.kwargs
    assert (kwargs["model_name"], kwargs["conversation_id"], kwargs["temperature"]) == ("mm", "t-1", 0.1)
    assert result["status"] == "success" and result["data"]["response"]["content"] == "done"


async def test_handler_reports_error_response_as_task_error():
    result = await LLMChatCompletionHandler().execute(_ctx(_llm("", "boom")))
    assert result["status"] == "error"


# -- modern AI local provider ----------------------------------------------


def _provider(llm) -> LocalModelProvider:
    config = AIModelConfig(
        provider=AIProvider.LOCAL_MODEL,
        model_name="llama3",
        capabilities=[],
        api_endpoint="",
        api_key=None,
        max_tokens=100,
        temperature=0.5,
        supports_streaming=False,
        rate_limit_per_minute=60,
        cost_per_token=0.0,
        metadata={},
    )
    provider = LocalModelProvider(config)
    provider._llm_service = llm
    return provider


def _ai_request(**extra) -> AIRequest:
    return AIRequest(request_id="r1", provider=AIProvider.LOCAL_MODEL, model_name="llama3", prompt="p", **extra)


async def test_local_provider_calls_chat_and_maps_the_response():
    llm = _llm("text")
    response = await _provider(llm).generate_text(_ai_request(system_message="sys", metadata={"session_id": "s9"}))
    assert response.content == "text" and response.usage == {"total": 3}
    assert llm.chat.await_args.kwargs["conversation_id"] == "s9"
    assert [m["role"] for m in llm.chat.await_args.args[0]] == ["system", "user"]


async def test_local_provider_surfaces_an_error_response():
    response = await _provider(_llm("", "boom")).generate_text(_ai_request())
    assert response.finish_reason == "error" and "boom" in response.metadata["error"]
