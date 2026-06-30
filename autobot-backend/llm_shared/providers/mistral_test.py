# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the Mistral provider (#10549).

The HTTP layer (the ``openai`` AsyncOpenAI client pointed at Mistral) is
mocked, so these tests never hit the network. They cover:
  - non-streaming chat completion (content + usage accounting)
  - streaming chat completion (chunk yielding)
  - credential-gating (no key -> is_available() False, no crash)
  - tool-call parsing
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_shared.models import LLMRequest, ToolDefinition
from llm_shared.providers.mistral import MISTRAL_MODELS, MistralProvider


def _make_request(model: str = "mistral-small-latest", tools=None, tool_choice=None) -> LLMRequest:
    return LLMRequest(
        messages=[{"role": "user", "content": "Hello Mistral"}],
        model_name=model,
        tools=tools,
        tool_choice=tool_choice,
    )


def _fake_completion(content: str = "Bonjour", tool_calls=None):
    """Build an object shaped like an OpenAI ChatCompletion response."""
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason="stop")
    usage = SimpleNamespace(prompt_tokens=11, completion_tokens=5, total_tokens=16)
    return SimpleNamespace(choices=[choice], model="mistral-small-latest", usage=usage)


def _provider_with_mock_client(client) -> MistralProvider:
    provider = MistralProvider(settings={"api_key": "test-key"})
    provider._client = client  # bypass lazy SDK import
    return provider


# ---------------------------------------------------------------------------
# Non-streaming chat completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_completion_returns_content_and_usage():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_fake_completion("Bonjour le monde"))
    provider = _provider_with_mock_client(client)

    response = await provider.chat_completion(_make_request())

    assert response.error is None
    assert response.content == "Bonjour le monde"
    assert response.provider == "mistral"
    assert response.usage["total_tokens"] == 16
    assert response.usage["prompt_tokens"] == 11
    sent = client.chat.completions.create.await_args.kwargs
    assert sent["model"] == "mistral-small-latest"
    assert "stream" not in sent


@pytest.mark.asyncio
async def test_chat_completion_parses_tool_calls():
    tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="get_weather", arguments='{"city": "Paris"}'),
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_fake_completion("", tool_calls=[tc]))
    provider = _provider_with_mock_client(client)

    tool = ToolDefinition(name="get_weather", description="weather", input_schema={"type": "object"})
    response = await provider.chat_completion(_make_request(tools=[tool], tool_choice="auto"))

    assert response.tool_calls is not None
    assert response.tool_calls[0].name == "get_weather"
    assert response.tool_calls[0].arguments == {"city": "Paris"}
    sent = client.chat.completions.create.await_args.kwargs
    assert sent["tools"][0]["function"]["name"] == "get_weather"
    assert sent["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_chat_completion_error_returned_not_raised():
    client = MagicMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
    provider = _provider_with_mock_client(client)

    response = await provider.chat_completion(_make_request())

    assert response.content == ""
    assert response.error is not None
    assert "boom" in response.error


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_completion_yields_chunks():
    async def _agen():
        for piece in ["Bon", "jour"]:
            delta = SimpleNamespace(content=piece)
            yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=_agen())
    provider = _provider_with_mock_client(client)

    chunks = [c async for c in provider.stream_completion(_make_request())]

    assert chunks == ["Bon", "jour"]
    assert client.chat.completions.create.await_args.kwargs["stream"] is True


# ---------------------------------------------------------------------------
# Credential gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_key_makes_provider_unavailable(monkeypatch):
    monkeypatch.setattr("llm_shared.providers.mistral.config.mistral_api_key", "", raising=False)
    provider = MistralProvider(settings={})

    # No key -> ensure_client raises internally -> is_available() must be False, not crash.
    assert await provider.is_available() is False


@pytest.mark.asyncio
async def test_list_models_falls_back_to_static_on_error():
    client = MagicMock()
    client.models.list = AsyncMock(side_effect=RuntimeError("offline"))
    provider = _provider_with_mock_client(client)

    models = await provider.list_models()

    assert models == MISTRAL_MODELS
    assert "codestral-latest" in models
