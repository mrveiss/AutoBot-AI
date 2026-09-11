# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The summarizer reaches a real LLM entry point, with the settings it asks for (#14840).

``_get_gateway`` imported ``llm_shared.gateway.get_llm_gateway``, a module that
never existed, so every summarization raised and took the failure path. The
existing tests could not see it: they replace ``_get_gateway`` itself, the seam
that existed "for test patching". Every test here leaves ``_get_gateway`` alone
and stubs one level below it, at the ``get_llm_service`` accessor its import
names, so that import really runs. Against the old import each of these fails.
"""

import dataclasses
import importlib.util
import sys
from pathlib import Path

import pytest

import services.llm_service as llm_service_module
from chat_history.context_overflow import ConversationSummarizer, SummarizationFailed
from llm_shared.models import LLMResponse

_MESSAGES = [{"sender": "user", "text": "Hello"}]


class _RecordingService:
    """Stands in for ``LLMService`` at its public ``chat`` boundary, recording each call."""

    def __init__(self, response: LLMResponse) -> None:
        self.calls: list[dict] = []
        self._response = response

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


def _serve(monkeypatch, service: _RecordingService) -> _RecordingService:
    """Make the accessor ``_get_gateway`` imports hand back *service*."""
    monkeypatch.setattr(llm_service_module, "get_llm_service", lambda: service, raising=False)
    return service


@pytest.mark.asyncio
async def test_the_real_gateway_resolves_through_the_llm_service_accessor(monkeypatch):
    """With the old ``llm_shared.gateway`` import this raises ModuleNotFoundError."""
    service = _serve(monkeypatch, _RecordingService(LLMResponse(content="S")))

    assert await ConversationSummarizer()._get_gateway() is service


@pytest.mark.asyncio
async def test_a_summary_comes_back_through_the_real_gateway(monkeypatch):
    service = _serve(monkeypatch, _RecordingService(LLMResponse(content="S")))

    assert await ConversationSummarizer().summarize_messages(_MESSAGES, "model-x") == "S"
    assert len(service.calls) == 1, "the service was never called"


@pytest.mark.asyncio
async def test_the_settings_reach_the_service_as_its_named_parameters(monkeypatch):
    """``model_name``, ``temperature`` and ``max_tokens`` are ``LLMService.chat``'s own
    parameters, which it copies into ``LLMRequest`` fields. The old call's ``model=``
    would have gone to ``**kwargs`` and on into ``LLMRequest(**kwargs)``, which has no
    such field."""
    service = _serve(monkeypatch, _RecordingService(LLMResponse(content="S")))

    await ConversationSummarizer().summarize_messages(_MESSAGES, "model-x")

    call = service.calls[0]
    assert (call["model_name"], call["temperature"], call["max_tokens"]) == ("model-x", 0.3, 500)
    assert "model" not in call


@pytest.mark.asyncio
async def test_a_provider_error_is_named_in_the_failure(monkeypatch):
    """``LLMService`` reports a provider failure in ``.error`` with empty content, not by raising."""
    _serve(monkeypatch, _RecordingService(LLMResponse(content="", error="upstream 503")))

    with pytest.raises(SummarizationFailed, match="upstream 503"):
        await ConversationSummarizer().summarize_messages(_MESSAGES, "model-x")


# ---------------------------------------------------------------------------
# One boundary further down: what the provider actually receives
# ---------------------------------------------------------------------------


def _real_llm_service_module(monkeypatch):
    """Load ``services/llm_service.py`` for real, under a name nothing else imports.

    The root conftest keeps ``services.llm_service`` a deliberate stub (its
    Redis/NPU import chain), so importing it by name yields a MagicMock surface
    with no real ``chat``. Loading the file privately leaves that stub in place
    for every other test. If the file cannot load here this test fails. It must
    not skip, or the request-field criterion would read as checked when it was not.
    """
    name = "_llm_service_real_14840"
    path = Path(__file__).resolve().parents[1] / "services" / "llm_service.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


class _RecordingProvider:
    """The provider boundary: receives the ``LLMRequest`` that ``LLMService.chat`` builds."""

    provider_name = "stub"

    def __init__(self) -> None:
        self.requests: list = []

    async def chat_completion(self, request):
        self.requests.append(request)
        return LLMResponse(content="S", provider="stub", model=request.model_name or "")


class _StubRegistry:
    def __init__(self, provider: _RecordingProvider) -> None:
        self._provider = provider

    async def get_provider_for_request(self, **_kwargs):
        return self._provider


@pytest.mark.asyncio
async def test_the_provider_receives_the_settings_as_request_fields(monkeypatch):
    """The criterion in its own words: the request the provider receives carries them.

    Only the provider registry is a stub. The summarizer, its real ``_get_gateway``
    and a real ``LLMService.chat`` build the request. The deprecated ``LLMInterface``
    this was once meant to reach would have put all three in ``metadata``.
    """
    provider = _RecordingProvider()
    service = _real_llm_service_module(monkeypatch).LLMService(registry=_StubRegistry(provider))
    monkeypatch.setattr(service, "_response_cache", None)  # no L1/L2 response cache, so no Redis
    _serve(monkeypatch, service)

    assert await ConversationSummarizer().summarize_messages(_MESSAGES, "model-x") == "S"

    request = provider.requests[0]
    assert dataclasses.is_dataclass(request) and type(request).__name__ == "LLMRequest"
    assert (request.model_name, request.temperature, request.max_tokens) == ("model-x", 0.3, 500)
    assert not {"model", "temperature", "max_tokens"} & set(request.metadata)
