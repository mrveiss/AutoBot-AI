# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Plan storage is session-scoped with an env-backed TTL, and the provider comes from config (#21023)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from autobot_shared.env_registry import REGISTRY
from chat_workflow import llm_provider
from chat_workflow.plan_runner import PlanTracker, _build_planner
from llm_shared.types import ProviderType
from planner import LLMPlannerModule
from planner import planner as planner_mod
from planner.plan_storage import PLAN_TTL_SECONDS
from planner.planner import PlannerConfig

pytestmark = pytest.mark.asyncio

_PLAN = {"task_description": "t", "steps": [{"step_number": 1, "description": "a", "depends_on": []}]}


class _Llm:
    async def generate(self, prompt, temperature):
        return json.dumps(_PLAN)


class _Redis:
    def __init__(self):
        self.store, self.sets = {}, []

    async def set(self, key, value, ex=None):
        self.store[key] = value
        self.sets.append((key, ex))

    async def get(self, key):
        return self.store.get(key)


async def test_plan_key_is_session_scoped_and_carries_the_env_backed_ttl():
    redis = _Redis()
    manager = SimpleNamespace(redis_client=redis)
    planner = _build_planner(manager, "m", "sess-1", 5)
    planner.llm = _Llm()
    plan = await planner.create_plan("task")
    assert redis.sets == [(f"autobot:plans:sess-1:{plan.plan_id}", PLAN_TTL_SECONDS)]
    other = _build_planner(manager, "m", "sess-2", 5)
    assert await other.get_plan(plan.plan_id) is None  # another session cannot read it


def test_unscoped_planner_is_rejected():
    with pytest.raises(ValueError, match="key_scope"):
        LLMPlannerModule(_Llm(), None, redis_client=_Redis(), config=PlannerConfig())
    with pytest.raises(ValueError, match="key_scope"):
        LLMPlannerModule(_Llm(), None, redis_client=_Redis())


def test_ttl_is_an_env_backed_registered_constant():
    assert "AUTOBOT_PLAN_TTL_SECONDS" in REGISTRY
    assert PlannerConfig().plan_ttl_seconds == PLAN_TTL_SECONDS == planner_mod.PLAN_TTL_SECONDS


def test_refresh_is_synchronous():
    import inspect

    assert not inspect.iscoroutinefunction(PlanTracker._refresh)


@pytest.mark.parametrize("name,expected", [("ollama", ProviderType.OLLAMA), ("OpenAI", ProviderType.OPENAI)])
def test_provider_comes_from_config(monkeypatch, name, expected):
    monkeypatch.setattr(llm_provider.config.llm, "provider", name)
    assert llm_provider.configured_provider() is expected


async def test_planner_client_and_failover_use_the_configured_provider(monkeypatch):
    from chat_workflow import llm_failover, planner_client

    monkeypatch.setattr(llm_provider.config.llm, "provider", "openai")
    assert llm_failover.configured_provider is llm_provider.configured_provider
    assert planner_client.configured_provider is llm_provider.configured_provider
    seen = {}

    class _Registry:
        async def get_provider_for_request(self, provider_name, request):
            seen["name"] = provider_name
            return None

    monkeypatch.setattr(planner_client, "get_provider_registry", lambda: _Registry())
    with pytest.raises(RuntimeError):
        await planner_client.PlannerLLMClient("m", "s").generate("p", 0.1)
    assert seen["name"] == "openai"


def test_unknown_provider_falls_back_to_default_with_one_warning(caplog):
    from autobot_shared import ssot_chat_graph_settings as mod
    from autobot_shared.ssot_config import LLMConfig

    mod._PROVIDER_WARNED = False
    with caplog.at_level("WARNING", logger=mod.__name__):
        first = LLMConfig(AUTOBOT_LLM_PROVIDER="olama")
        second = LLMConfig(AUTOBOT_LLM_PROVIDER="olama")
    assert first.provider == second.provider == "ollama"
    assert llm_provider.ProviderType(first.provider) is ProviderType.OLLAMA
    warnings = [r for r in caplog.records if "AUTOBOT_LLM_PROVIDER" in r.getMessage()]
    assert len(warnings) == 1
    assert "allowed:" in warnings[0].getMessage() and "ollama" in warnings[0].getMessage()


def test_known_provider_is_kept_normalised():
    from autobot_shared.ssot_config import LLMConfig

    assert LLMConfig(AUTOBOT_LLM_PROVIDER=" OpenAI ").provider == "openai"


async def test_planner_call_records_its_spend_against_the_session(monkeypatch):
    from chat_workflow import planner_client
    from llm_shared.models import LLMResponse

    response = LLMResponse(
        content="plan", usage={"prompt_tokens": 3, "completion_tokens": 4}, provider="openai", model="m"
    )
    recorded = []

    class _Provider:
        async def chat_completion(self, request):
            return response

    class _Registry:
        async def get_provider_for_request(self, provider_name, request):
            return _Provider()

    async def _record(resp, session_id=None, **kwargs):
        recorded.append((resp, session_id, kwargs))

    monkeypatch.setattr(planner_client, "get_provider_registry", lambda: _Registry())
    monkeypatch.setattr(planner_client, "record_response_usage", _record)
    assert await planner_client.PlannerLLMClient("m", "sess-1").generate("p", 0.1) == "plan"
    assert recorded == [(response, "sess-1", {"endpoint": planner_client.PLANNER_ENDPOINT})]
