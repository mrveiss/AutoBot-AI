# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PROVIDER_FALLBACK event emission from LLMService.chat()/stream() (#11995).

LLMService's inline fallback loop (GH#8998) is a divergent path from
ModelFallbackCoordinator — this suite proves it is NOT inert for the new
canonical event (cf. llm_shared/model_fallback_coordinator_test.py for the
coordinator-side equivalent).

Uses the same real-module-load harness as test_llm_service_caching.py so
``services.llm_service`` (globally stubbed in conftest.py) can be exercised
directly.
"""

from __future__ import annotations

import importlib.util as _ilu
import pathlib
import sys
from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[2]  # autobot-backend/


def _load_real_module(private_name: str, relpath: str):
    """Load a real module file under a private name (no sys.modules clobber)."""
    spec = _ilu.spec_from_file_location(private_name, str(_BACKEND / relpath))
    assert spec and spec.loader
    mod = _ilu.module_from_spec(spec)
    sys.modules[private_name] = mod
    spec.loader.exec_module(mod)
    return mod


if "llm_shared.rate_limit_backoff" not in sys.modules:
    _load_real_module("llm_shared.rate_limit_backoff", "llm_shared/rate_limit_backoff.py")
if "llm_shared.fallback_events" not in sys.modules:
    _load_real_module("llm_shared.fallback_events", "llm_shared/fallback_events.py")

_llm_service_mod = _load_real_module("_real_llm_service_11995", "services/llm_service.py")
LLMService = _llm_service_mod.LLMService

from llm_shared.models import LLMRequest, LLMResponse  # noqa: E402


class _FlakyProvider:
    """Rate-limited on the first call, succeeds on the second."""

    provider_name = "fake"

    def __init__(self) -> None:
        self.calls = 0

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(
                content="", model=request.model_name, provider=self.provider_name, error="429 rate limit exceeded"
            )
        return LLMResponse(content="ok", model=request.model_name, provider=self.provider_name)

    async def stream_completion(self, request: LLMRequest):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("429 rate limit exceeded")
        yield "ok"


class _AlwaysLimitedProvider:
    """Always rate-limited — exhausts the fallback chain."""

    provider_name = "fake"

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content="", model=request.model_name, provider=self.provider_name, error="429 rate limit exceeded"
        )

    async def stream_completion(self, request: LLMRequest):
        raise RuntimeError("429 rate limit exceeded")
        yield  # pragma: no cover — unreachable, makes this an async generator


class _FakeRegistry:
    def __init__(self, provider) -> None:
        self._provider = provider

    async def get_provider_for_request(self, provider_name=None, conversation_id=None):
        return self._provider


class _FakeFallbackChainManager:
    """Returns one fallback hop then None (single-hop chain)."""

    def __init__(self, next_model: str = "fallback-model", next_provider: str = "fake") -> None:
        self._next = (next_model, next_provider)
        self.calls = 0

    def get_next_fallback(self, current_model, provider_name):
        self.calls += 1
        return self._next if self.calls == 1 else None


def _make_service(provider) -> Any:
    svc = LLMService(registry=_FakeRegistry(provider))
    svc._response_cache = None
    return svc


@pytest.mark.asyncio
async def test_chat_emits_provider_fallback_event_on_success(monkeypatch):
    provider = _FlakyProvider()
    svc = _make_service(provider)
    monkeypatch.setattr(_llm_service_mod, "get_fallback_chain_manager", lambda: _FakeFallbackChainManager())
    mock_emit = AsyncMock()
    monkeypatch.setattr(_llm_service_mod, "emit_fallback_event", mock_emit)

    messages: List[Dict[str, str]] = [{"role": "user", "content": "hi"}]
    response = await svc.chat(messages, model_name="primary-model", conversation_id="conv-1", use_cache=False)

    assert response.content == "ok"
    mock_emit.assert_awaited_once()
    kwargs = mock_emit.await_args.kwargs
    assert kwargs["conversation_id"] == "conv-1"
    assert kwargs["primary_model"] == "primary-model"
    assert kwargs["fallback_model"] == "fallback-model"
    assert kwargs.get("exhausted", False) is False


@pytest.mark.asyncio
async def test_chat_emits_provider_fallback_event_on_exhaustion(monkeypatch):
    provider = _AlwaysLimitedProvider()
    svc = _make_service(provider)
    monkeypatch.setattr(_llm_service_mod, "get_fallback_chain_manager", lambda: _FakeFallbackChainManager())
    mock_emit = AsyncMock()
    monkeypatch.setattr(_llm_service_mod, "emit_fallback_event", mock_emit)

    messages: List[Dict[str, str]] = [{"role": "user", "content": "hi"}]
    response = await svc.chat(messages, model_name="primary-model", conversation_id="conv-2", use_cache=False)

    assert response.error
    mock_emit.assert_awaited_once()
    assert mock_emit.await_args.kwargs["exhausted"] is True


@pytest.mark.asyncio
async def test_stream_emits_provider_fallback_event_on_success(monkeypatch):
    provider = _FlakyProvider()
    svc = _make_service(provider)
    monkeypatch.setattr(_llm_service_mod, "get_fallback_chain_manager", lambda: _FakeFallbackChainManager())
    mock_emit = AsyncMock()
    monkeypatch.setattr(_llm_service_mod, "emit_fallback_event", mock_emit)

    chunks = [c async for c in svc.stream([{"role": "user", "content": "hi"}], model_name="primary-model")]

    assert chunks == ["ok"]
    mock_emit.assert_awaited_once()
    assert mock_emit.await_args.kwargs["fallback_model"] == "fallback-model"


@pytest.mark.asyncio
async def test_chat_no_event_when_primary_succeeds(monkeypatch):
    """No fallback hop → no PROVIDER_FALLBACK event (existing behavior unchanged)."""

    class _OkProvider:
        provider_name = "fake"

        async def chat_completion(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(content="ok", model=request.model_name, provider=self.provider_name)

    svc = _make_service(_OkProvider())
    mock_emit = AsyncMock()
    monkeypatch.setattr(_llm_service_mod, "emit_fallback_event", mock_emit)

    response = await svc.chat([{"role": "user", "content": "hi"}], model_name="primary-model", use_cache=False)

    assert response.content == "ok"
    mock_emit.assert_not_awaited()
