# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for LLMService cost-machinery wiring (#10597).

The test harness stubs ``services.llm_service`` in sys.modules (services/__init__
pulls in the heavy npu/Redis stack).  We load the real module file under a
private name so we can exercise ``chat()`` directly without replacing the
session-wide stub other tests rely on.  ``llm_shared`` stays stubbed, so the
import is lightweight (no provider SDKs, no Redis).

Covers:
- Response cache wired into chat(): a cache hit short-circuits the provider.
- A successful response is written to the cache.
- Chat tiered routing gated off by default (no model downgrade).
- Task-type cheap-model pin when routing is explicitly enabled.
- An explicit model_name always overrides routing.
- Anthropic prompt caching defaults on via config.
"""

from __future__ import annotations

import importlib.util as _ilu
import pathlib
import sys
from typing import Any, Dict, List

import pytest

from autobot_shared.ssot_config import config
from llm_shared.models import LLMRequest, LLMResponse
from llm_shared.types import LLMType

_BACKEND = pathlib.Path(__file__).resolve().parents[2]  # autobot-backend/


def _load_real_module(private_name: str, relpath: str):
    """Load a real module file under a private name (no sys.modules clobber)."""
    spec = _ilu.spec_from_file_location(private_name, str(_BACKEND / relpath))
    assert spec and spec.loader
    mod = _ilu.module_from_spec(spec)
    sys.modules[private_name] = mod
    spec.loader.exec_module(mod)
    return mod


# Real submodule llm_service imports that the harness doesn't pre-load.
if "llm_shared.rate_limit_backoff" not in sys.modules:
    _load_real_module("llm_shared.rate_limit_backoff", "llm_shared/rate_limit_backoff.py")

_llm_service_mod = _load_real_module("_real_llm_service_10597", "services/llm_service.py")
LLMService = _llm_service_mod.LLMService


class _FakeProvider:
    """Minimal provider that records the request and returns a fixed reply."""

    provider_name = "fake"

    def __init__(self) -> None:
        self.calls = 0
        self.last_request: LLMRequest | None = None

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        self.last_request = request
        return LLMResponse(
            content="hello world",
            model=request.model_name or "fake-default",
            provider=self.provider_name,
            request_id=request.request_id,
        )


class _FakeRegistry:
    """Registry stub returning a single fake provider."""

    def __init__(self, provider: _FakeProvider) -> None:
        self._provider = provider

    async def get_provider_for_request(self, provider_name=None, conversation_id=None):
        return self._provider

    def get_provider_by_name(self, name: str):
        return self._provider

    def list_providers(self):
        return [{"name": self._provider.provider_name}]


class _FakeCache:
    """In-memory stand-in for the L1/L2 response cache."""

    def __init__(self) -> None:
        self.store: Dict[str, Any] = {}
        self.gets = 0
        self.sets = 0

    def generate_cache_key(self, messages, model, temperature, top_k=40, top_p=0.9, max_tokens=None) -> str:
        last = messages[-1]["content"] if messages else ""
        return f"{model}|{temperature}|{max_tokens}|{last}"

    async def get(self, key):
        self.gets += 1
        return self.store.get(key)

    async def set(self, key, response, skip_redis: bool = False) -> None:
        self.sets += 1
        self.store[key] = response


def _make_service():
    provider = _FakeProvider()
    svc = LLMService(registry=_FakeRegistry(provider))
    cache = _FakeCache()
    svc._response_cache = cache
    return svc, provider, cache


@pytest.mark.asyncio
async def test_chat_cache_hit_short_circuits_provider():
    svc, provider, cache = _make_service()
    messages: List[Dict[str, str]] = [{"role": "user", "content": "hi there"}]

    # temperature=0 → deterministic → cacheable.
    r1 = await svc.chat(messages, temperature=0.0)
    assert r1.content == "hello world"
    assert provider.calls == 1
    assert cache.sets == 1  # stored on success

    r2 = await svc.chat(messages, temperature=0.0)
    assert provider.calls == 1  # served from cache, provider untouched
    assert r2.cached is True


@pytest.mark.asyncio
async def test_chat_different_max_tokens_do_not_collide():
    svc, provider, _ = _make_service()
    messages = [{"role": "user", "content": "same prompt"}]

    await svc.chat(messages, temperature=0.0, max_tokens=100)
    await svc.chat(messages, temperature=0.0, max_tokens=2000)
    # Different max_tokens → different cache key → no stale collision.
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_chat_high_temperature_not_cached():
    svc, provider, _ = _make_service()
    messages = [{"role": "user", "content": "be creative"}]

    await svc.chat(messages, temperature=0.9)
    await svc.chat(messages, temperature=0.9)
    # Above the determinism threshold → never cached, responses may vary.
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_chat_use_cache_false_bypasses():
    svc, provider, _ = _make_service()
    messages = [{"role": "user", "content": "x"}]

    await svc.chat(messages, temperature=0.0, use_cache=False)
    await svc.chat(messages, temperature=0.0, use_cache=False)
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_chat_structured_output_not_cached():
    svc, provider, _ = _make_service()
    messages = [{"role": "user", "content": "give json"}]

    await svc.chat(messages, temperature=0.0, structured_output=True)
    await svc.chat(messages, temperature=0.0, structured_output=True)
    # Structured-output responses are not safely reusable → not cached.
    assert provider.calls == 2


@pytest.mark.asyncio
async def test_chat_does_not_route_by_default(monkeypatch):
    monkeypatch.setattr(config, "chat_tiered_routing", False, raising=False)
    svc, provider, _ = _make_service()

    await svc.chat([{"role": "user", "content": "hi"}], llm_type=LLMType.CLASSIFICATION)
    # No model pinned + routing off → registry default (model_name None).
    assert provider.last_request.model_name is None


@pytest.mark.asyncio
async def test_chat_pins_cheap_model_when_routing_enabled(monkeypatch):
    monkeypatch.setattr(config, "chat_tiered_routing", True, raising=False)
    svc, provider, _ = _make_service()

    await svc.chat([{"role": "user", "content": "classify this"}], llm_type=LLMType.CLASSIFICATION)
    assert provider.last_request.model_name == config.classification_model


@pytest.mark.asyncio
async def test_explicit_model_overrides_routing(monkeypatch):
    monkeypatch.setattr(config, "chat_tiered_routing", True, raising=False)
    svc, provider, _ = _make_service()

    await svc.chat(
        [{"role": "user", "content": "x"}],
        model_name="explicit-model",
        llm_type=LLMType.CLASSIFICATION,
    )
    assert provider.last_request.model_name == "explicit-model"


def test_prompt_cache_default_flag_on():
    """Anthropic prompt caching is driven by this default (pure cost win)."""
    assert config.llm_prompt_cache_default is True


@pytest.mark.asyncio
async def test_rate_limit_honors_retry_after(monkeypatch):
    """#10601: a same-provider fallback waits the parsed Retry-After before retrying."""

    class _RateLimitedThenOk(_FakeProvider):
        async def chat_completion(self, request: LLMRequest) -> LLMResponse:
            self.calls += 1
            self.last_request = request
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    provider=self.provider_name,
                    request_id=request.request_id,
                    error="rate limit exceeded; retry after 5 seconds",
                )
            return LLMResponse(content="ok", model="m", provider=self.provider_name, request_id=request.request_id)

    provider = _RateLimitedThenOk()
    svc = LLMService(registry=_FakeRegistry(provider))
    svc._response_cache = _FakeCache()

    class _SameProviderFallback:
        def get_next_fallback(self, *args, **kwargs):
            return ("fallback-model", None)  # None → stay on same provider

    monkeypatch.setattr(_llm_service_mod, "get_fallback_chain_manager", lambda: _SameProviderFallback())
    slept: List[float] = []

    async def _record_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(_llm_service_mod.asyncio, "sleep", _record_sleep)

    result = await svc.chat([{"role": "user", "content": "hi"}], temperature=0.0)

    assert provider.calls == 2  # rate-limited, then retried successfully
    assert slept == [5.0]  # honored the parsed Retry-After (capped at 30)
    assert result.content == "ok"


@pytest.mark.asyncio
async def test_rate_limit_no_sleep_when_switching_provider(monkeypatch):
    """A cross-provider fallback should NOT wait the primary's Retry-After."""

    class _RateLimitedThenOk(_FakeProvider):
        async def chat_completion(self, request: LLMRequest) -> LLMResponse:
            self.calls += 1
            self.last_request = request
            if self.calls == 1:
                return LLMResponse(
                    content="",
                    provider=self.provider_name,
                    request_id=request.request_id,
                    error="429 too many requests; retry after 9 seconds",
                )
            return LLMResponse(content="ok", model="m", provider=self.provider_name, request_id=request.request_id)

    provider = _RateLimitedThenOk()
    svc = LLMService(registry=_FakeRegistry(provider))
    svc._response_cache = _FakeCache()

    class _OtherProviderFallback:
        def get_next_fallback(self, *args, **kwargs):
            return ("other-model", "other-provider")  # different provider

    monkeypatch.setattr(_llm_service_mod, "get_fallback_chain_manager", lambda: _OtherProviderFallback())
    slept: List[float] = []
    monkeypatch.setattr(_llm_service_mod.asyncio, "sleep", lambda s: slept.append(s))

    await svc.chat([{"role": "user", "content": "hi"}], temperature=0.0)
    assert slept == []  # no wait when moving to a healthy different provider
