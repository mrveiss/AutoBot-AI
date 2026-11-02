# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chat request over a configured budget is refused before the LLM call (#16845).

The gate sits at every chat entry: the workflow's per-iteration LLM call,
``LLMService.chat`` / ``chat_optimized`` / ``stream``, and both compat
gateways. Each ``*_removed_*`` test would pass with the gate deleted only if
the budget were not actually enforced, so they fail when the call is removed.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import fakeredis
import fakeredis.aioredis as fakeredis_async
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.budget_policy as bp_mod
import services.chat_budget_gate as gate
from api import anthropic_compat, openai_compat
from autobot_shared.time_utils import now_utc
from chat_workflow.budget_refusal import budget_refusal_message
from llm_shared.models import LLMResponse
from llm_shared.run_credentials import llm_principal_scope
from services.budget_policy import (
    ACTION_ALERT,
    ACTION_ALERT_THEN_PAUSE,
    PERIOD_DAY,
    PERIOD_MONTH,
    SCOPE_TENANT,
    SCOPE_USER,
    BudgetPolicy,
    create_policy,
)
from testkit.real_llm_service import load_real_llm_service

USER, ORG = "alice", "acme"
LLMService = load_real_llm_service().LLMService  # conftest stubs services.llm_service; the gate needs the real one


@pytest_asyncio.fixture
async def redis(monkeypatch):
    client = fakeredis_async.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)

    async def _client(*_a, **_k):
        return client

    monkeypatch.setattr(bp_mod, "get_async_redis_client", _client)
    monkeypatch.setattr(gate, "get_async_redis_client", _client)
    yield client
    await client.aclose()


@pytest.fixture
def audit(monkeypatch):
    recorded = AsyncMock()
    monkeypatch.setattr("services.audit.audit.record", recorded)
    return recorded


async def _policy(scope, scope_id, limit, period=PERIOD_DAY, action=ACTION_ALERT_THEN_PAUSE):
    await create_policy(BudgetPolicy(scope=scope, scope_id=scope_id, period=period, threshold_usd=limit, action=action))


async def _spend(redis, namespace, subject, usd):
    today = now_utc().strftime("%Y-%m-%d")
    await redis.incrbyfloat(f"{namespace}:{subject}:daily:{today}", usd)


class TestGate:
    @pytest.mark.asyncio
    async def test_no_policy_means_no_refusal(self, redis):
        await _spend(redis, gate.USER_SPEND_NS, USER, 999)
        with llm_principal_scope(USER, ORG):
            await gate.enforce_chat_budget()

    @pytest.mark.asyncio
    async def test_no_principal_means_no_refusal(self, redis):
        await _policy(SCOPE_USER, USER, 1)
        await _spend(redis, gate.USER_SPEND_NS, USER, 5)
        await gate.enforce_chat_budget()

    @pytest.mark.asyncio
    async def test_user_over_limit_is_refused_and_audited(self, redis, audit):
        await _policy(SCOPE_USER, USER, 5)
        await _spend(redis, gate.USER_SPEND_NS, USER, 5.5)
        with llm_principal_scope(USER, ORG), pytest.raises(gate.ChatBudgetExceeded) as caught:
            await gate.enforce_chat_budget()
        assert caught.value.status_code == 402
        assert caught.value.detail["error_code"] == gate.CHAT_BUDGET_ERROR_CODE
        assert caught.value.detail["i18n_key"] == gate.CHAT_BUDGET_I18N_KEY
        event = audit.await_args.args[0]
        assert (event.action, event.actor_id, event.outcome) == ("budget.chat_refused", USER, "denied")
        assert event.metadata["current_spend_usd"] == pytest.approx(5.5)

    @pytest.mark.asyncio
    async def test_user_under_limit_is_allowed(self, redis, audit):
        await _policy(SCOPE_USER, USER, 5)
        await _spend(redis, gate.USER_SPEND_NS, USER, 4.99)
        with llm_principal_scope(USER, ORG):
            await gate.enforce_chat_budget()
        audit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_tenant_policy_refuses_every_user_of_the_tenant(self, redis, audit):
        await _policy(SCOPE_TENANT, ORG, 10, period=PERIOD_MONTH)
        await _spend(redis, gate.TENANT_SPEND_NS, ORG, 10)
        with llm_principal_scope("bob", ORG), pytest.raises(gate.ChatBudgetExceeded):
            await gate.enforce_chat_budget()
        with llm_principal_scope("bob", "other-org"):
            await gate.enforce_chat_budget()

    @pytest.mark.asyncio
    async def test_user_without_a_tenant_is_checked_on_the_user_scope_only(self, redis):
        await _policy(SCOPE_TENANT, ORG, 1)
        await _spend(redis, gate.TENANT_SPEND_NS, ORG, 50)
        with llm_principal_scope(USER, None):
            await gate.enforce_chat_budget()

    @pytest.mark.asyncio
    async def test_alert_only_policy_never_refuses(self, redis):
        await _policy(SCOPE_USER, USER, 1, action=ACTION_ALERT)
        await _spend(redis, gate.USER_SPEND_NS, USER, 9)
        with llm_principal_scope(USER, ORG):
            await gate.enforce_chat_budget()

    @pytest.mark.asyncio
    async def test_unreadable_store_allows_the_request_and_logs(self, redis, monkeypatch, caplog):
        monkeypatch.setattr(gate, "list_policies_for_scope", AsyncMock(side_effect=ConnectionError("down")))
        with llm_principal_scope(USER, ORG):
            await gate.enforce_chat_budget()
        assert "Chat budget check failed" in caplog.text

    @pytest.mark.asyncio
    async def test_recorded_chat_spend_is_what_the_gate_compares(self, redis, monkeypatch):
        tracker = MagicMock()
        tracker.track_usage = AsyncMock(return_value=MagicMock(cost_usd=2.0))
        monkeypatch.setattr("services.llm_usage_recording.get_cost_tracker", lambda: tracker)
        from services.llm_usage_recording import record_response_usage

        with llm_principal_scope(USER, ORG):
            await record_response_usage(LLMResponse(content="x", usage={"prompt_tokens": 1, "completion_tokens": 1}))
        assert tracker.track_usage.await_args.kwargs["user_id"] == USER
        await _policy(SCOPE_TENANT, ORG, 2)
        with llm_principal_scope("bob", ORG), pytest.raises(gate.ChatBudgetExceeded):
            await gate.enforce_chat_budget()


class TestEveryEntryIsGated:
    @pytest.mark.asyncio
    async def test_workflow_turn_gets_an_error_message_with_an_i18n_key(self, redis, audit):
        await _policy(SCOPE_USER, USER, 1)
        await _spend(redis, gate.USER_SPEND_NS, USER, 2)
        with llm_principal_scope(USER, ORG):
            message = await budget_refusal_message()
        assert message.type == "error"
        assert message.metadata["i18n_key"] == "chat.errors.budgetExhausted"
        with llm_principal_scope("carol", ORG):
            assert await budget_refusal_message() is None

    @pytest.mark.asyncio
    async def test_llm_service_chat_returns_the_refusal_without_calling_a_provider(self, redis, audit, monkeypatch):
        await _policy(SCOPE_USER, USER, 1)
        await _spend(redis, gate.USER_SPEND_NS, USER, 2)
        service = LLMService(registry=MagicMock())
        monkeypatch.setattr(service, "_check_response_cache", AsyncMock(return_value=(None, None)))
        with llm_principal_scope(USER, ORG):
            response = await service.chat([{"role": "user", "content": "hi"}])
        assert "spending limit" in response.error
        service._registry.get_provider_for_request.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_service_stream_raises_before_any_provider_work(self, redis, audit):
        await _policy(SCOPE_USER, USER, 1)
        await _spend(redis, gate.USER_SPEND_NS, USER, 2)
        service = LLMService(registry=MagicMock())
        with llm_principal_scope(USER, ORG), pytest.raises(gate.ChatBudgetExceeded):
            async for _ in service.stream([{"role": "user", "content": "hi"}]):
                pass

    @pytest.mark.parametrize(
        "fn",
        [LLMService.chat, LLMService.stream, LLMService.chat_optimized, openai_compat._complete_chat]
        + [anthropic_compat._handle_messages],
    )
    def test_gate_call_removed_would_be_caught(self, fn):
        source = inspect.getsource(fn)
        assert "enforce_chat_budget" in source or "chat_budget_refusal" in source

    def test_workflow_llm_iteration_calls_the_gate(self):
        from chat_workflow.manager import ChatWorkflowManager

        assert "budget_refusal_message" in inspect.getsource(ChatWorkflowManager._process_single_llm_iteration)


def _compat_client(monkeypatch):
    app = FastAPI()
    app.include_router(openai_compat.router)
    monkeypatch.setattr(openai_compat, "_resolve_auth", AsyncMock(return_value=({"id": USER, "org_id": ORG}, None)))
    monkeypatch.setattr(openai_compat._oai_limiter, "check_or_429", AsyncMock())
    provider = MagicMock(provider_name="fake")

    async def _stream(_request):
        yield "ok"

    provider.stream_completion = _stream
    registry = MagicMock()
    registry.get_provider_for_request = AsyncMock(return_value=provider)
    monkeypatch.setattr(openai_compat, "get_provider_registry", lambda: registry)
    coordinator = MagicMock()
    answer = LLMResponse(content="hello", usage={"prompt_tokens": 1, "completion_tokens": 1}, model="m")
    coordinator.execute_with_fallback = AsyncMock(return_value=answer)
    monkeypatch.setattr(openai_compat, "get_fallback_coordinator", lambda: coordinator)
    monkeypatch.setattr(openai_compat, "record_response_usage", AsyncMock())
    return TestClient(app), coordinator


_BODY = {"model": "m", "messages": [{"role": "user", "content": "hi"}]}


class TestChatRequestEndToEnd:
    @pytest.mark.asyncio
    async def test_request_over_the_policy_is_refused_and_under_it_is_served(self, redis, audit, monkeypatch):
        client, coordinator = _compat_client(monkeypatch)
        await _policy(SCOPE_USER, USER, 5)

        await _spend(redis, gate.USER_SPEND_NS, USER, 4)
        assert client.post("/chat/completions", json=_BODY).status_code == 200
        assert coordinator.execute_with_fallback.await_count == 1

        await _spend(redis, gate.USER_SPEND_NS, USER, 1)
        refused = client.post("/chat/completions", json=_BODY)
        assert refused.status_code == 402
        assert refused.json()["detail"]["i18n_key"] == "chat.errors.budgetExhausted"
        assert coordinator.execute_with_fallback.await_count == 1
        assert audit.await_count == 1
