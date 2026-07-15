# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for chat_template_loader wiring into ollama and vllm providers.

Covers:
  - render_chat_template for chatml, zephyr, vicuna (happy path)
  - render_chat_template unknown-template fallback
  - VLLMProvider._messages_to_prompt uses render_chat_template
  - OllamaProvider.stream_completion builds prompt payload when chat_template set
  - OllamaProvider.chat_completion pre-renders messages when chat_template set
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_shared.providers.chat_template_loader import (
    SUPPORTED_TEMPLATES,
    render_chat_template,
)

MESSAGES = [
    {"role": "system", "content": "You are helpful."},
    {"role": "user", "content": "Hello!"},
]


# ---------------------------------------------------------------------------
# render_chat_template — unit tests
# ---------------------------------------------------------------------------


def test_render_chatml_contains_im_start():
    result = render_chat_template(MESSAGES, "chatml")
    assert "<|im_start|>system" in result
    assert "<|im_start|>user" in result
    assert "<|im_start|>assistant" in result


def test_render_zephyr_contains_system_tag():
    result = render_chat_template(MESSAGES, "zephyr")
    assert "<|system|>" in result
    assert "<|user|>" in result
    assert "<|assistant|>" in result


def test_render_vicuna_contains_user_label():
    result = render_chat_template(MESSAGES, "vicuna")
    assert "You are helpful." in result
    assert "USER: Hello!" in result
    assert "ASSISTANT:" in result


def test_render_unknown_template_falls_back_to_default(caplog):
    with caplog.at_level(logging.WARNING, logger="llm_shared.providers.chat_template_loader"):
        result = render_chat_template(MESSAGES, "unknown_tmpl")
    assert "Unknown chat template" in caplog.text
    # Should fall back to chatml
    assert "<|im_start|>user" in result


def test_all_supported_templates_render_without_error():
    for name in SUPPORTED_TEMPLATES:
        rendered = render_chat_template(MESSAGES, name)
        assert isinstance(rendered, str)
        assert len(rendered) > 0


# ---------------------------------------------------------------------------
# VLLMProvider._messages_to_prompt — uses render_chat_template
# ---------------------------------------------------------------------------


def _make_vllm_provider():
    """Return a VLLMProvider with vllm import mocked out."""
    import sys

    vllm_mock = MagicMock()
    sys.modules.setdefault("vllm", vllm_mock)
    # Re-import after patching so VLLM_AVAILABLE reflects mock
    import importlib

    import llm_shared.providers.vllm as mod

    importlib.reload(mod)
    provider = mod.VLLMProvider.__new__(mod.VLLMProvider)
    provider.config = {"model": "test-model"}
    provider.model_name = "test-model"
    provider.is_initialized = False
    provider.llm = None
    return provider, mod


def test_vllm_messages_to_prompt_chatml():
    provider, mod = _make_vllm_provider()
    result = provider._messages_to_prompt(MESSAGES, chat_template="chatml")
    assert "<|im_start|>system" in result
    assert "<|im_start|>user" in result


def test_vllm_messages_to_prompt_zephyr():
    provider, mod = _make_vllm_provider()
    result = provider._messages_to_prompt(MESSAGES, chat_template="zephyr")
    assert "<|system|>" in result
    assert "<|user|>" in result


def test_vllm_messages_to_prompt_vicuna():
    provider, mod = _make_vllm_provider()
    result = provider._messages_to_prompt(MESSAGES, chat_template="vicuna")
    assert "USER: Hello!" in result


def test_vllm_messages_to_prompt_default_is_chatml():
    provider, _ = _make_vllm_provider()
    result = provider._messages_to_prompt(MESSAGES)
    assert "<|im_start|>user" in result


def test_vllm_messages_to_prompt_unknown_falls_back(caplog):
    provider, _ = _make_vllm_provider()
    with caplog.at_level(logging.WARNING, logger="llm_shared.providers.chat_template_loader"):
        result = provider._messages_to_prompt(MESSAGES, chat_template="nonexistent")
    assert "Unknown chat template" in caplog.text
    assert "<|im_start|>user" in result


# ---------------------------------------------------------------------------
# OllamaProvider.stream_completion — payload uses prompt when chat_template set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_stream_uses_prompt_payload_when_template_set():
    """When chat_template is in request.metadata, stream_completion must use
    the rendered ``prompt`` key (generate API) instead of ``messages``."""
    from llm_shared.models import LLMRequest
    from llm_shared.providers.ollama_provider import OllamaProvider

    provider = OllamaProvider(
        settings={"base_url": "http://localhost:11434"}
    )  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default

    request = LLMRequest(
        messages=[
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hi"},
        ],
        model_name="llama3",
        metadata={"chat_template": "chatml"},
    )

    captured_payload = {}

    async def fake_post(url, headers, json, timeout):
        captured_payload.update(json)

        async def fake_content():
            import json as _json

            yield _json.dumps({"response": "Hello", "done": False}).encode("utf-8")
            yield _json.dumps({"response": "", "done": True}).encode("utf-8")

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.status = 200
        ctx.content = fake_content()
        return ctx

    with patch("llm_shared.providers.ollama_provider.get_http_client") as mock_client:
        client = MagicMock()
        client.post = fake_post
        mock_client.return_value = client

        chunks = []
        async for chunk in provider.stream_completion(request):
            chunks.append(chunk)

    assert "prompt" in captured_payload
    assert "messages" not in captured_payload
    assert "<|im_start|>" in captured_payload["prompt"]
    assert chunks == ["Hello"]


@pytest.mark.asyncio
async def test_ollama_stream_uses_messages_payload_without_template():
    """Without chat_template, stream_completion must keep the messages payload."""
    from llm_shared.models import LLMRequest
    from llm_shared.providers.ollama_provider import OllamaProvider

    provider = OllamaProvider(
        settings={"base_url": "http://localhost:11434"}
    )  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default

    request = LLMRequest(
        messages=[{"role": "user", "content": "Hi"}],
        model_name="llama3",
    )

    captured_payload = {}

    async def fake_post(url, headers, json, timeout):
        captured_payload.update(json)

        async def fake_content():
            import json as _json

            yield _json.dumps({"message": {"content": "Hey"}, "done": True}).encode("utf-8")

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.status = 200
        ctx.content = fake_content()
        return ctx

    with patch("llm_shared.providers.ollama_provider.get_http_client") as mock_client:
        client = MagicMock()
        client.post = fake_post
        mock_client.return_value = client

        chunks = []
        async for chunk in provider.stream_completion(request):
            chunks.append(chunk)

    assert "messages" in captured_payload
    assert "prompt" not in captured_payload
    assert chunks == ["Hey"]


# ---------------------------------------------------------------------------
# OllamaProvider.chat_completion — uses generate endpoint when template set
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_chat_completion_pre_renders_when_template_set():
    """When chat_template is in request.metadata, chat_completion must POST to
    the generate endpoint with a rendered ``prompt`` key containing template
    markers (e.g. ``<|im_start|>``) instead of forwarding to the delegate."""
    from llm_shared.models import LLMRequest
    from llm_shared.providers.ollama_provider import OllamaProvider

    provider = OllamaProvider(
        settings={"base_url": "http://localhost:11434"}
    )  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default

    request = LLMRequest(
        messages=[
            {"role": "system", "content": "Be concise."},
            {"role": "user", "content": "Hi"},
        ],
        model_name="llama3",
        metadata={"chat_template": "chatml"},
    )

    captured_payload = {}
    captured_url = {}

    async def fake_post(url, headers, json, timeout):
        captured_url["url"] = url
        captured_payload.update(json)

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=ctx)
        ctx.__aexit__ = AsyncMock(return_value=False)
        ctx.status = 200
        ctx.json = AsyncMock(
            return_value={
                "response": "Hello there!",
                "prompt_eval_count": 10,
                "eval_count": 5,
                "total_duration": 1_000_000_000,
            }
        )
        return ctx

    with patch("llm_shared.providers.ollama_provider.get_http_client") as mock_client:
        client = MagicMock()
        client.post = fake_post
        mock_client.return_value = client

        response = await provider.chat_completion(request)

    # Must use the generate endpoint, not the chat endpoint
    from constants.api_constants import PATH_OLLAMA_GENERATE

    assert PATH_OLLAMA_GENERATE in captured_url["url"]

    # Payload must carry rendered prompt with chatml markers
    assert "prompt" in captured_payload
    assert "messages" not in captured_payload
    assert "<|im_start|>" in captured_payload["prompt"]

    # stream must be False for non-streaming call
    assert captured_payload.get("stream") is False

    # Response must be correctly populated
    assert response.content == "Hello there!"
    assert response.model == "llama3"
    assert response.usage["prompt_tokens"] == 10
    assert response.usage["completion_tokens"] == 5
    assert response.usage["total_tokens"] == 15


@pytest.mark.asyncio
async def test_ollama_chat_completion_passes_through_without_template():
    """Without chat_template in metadata, chat_completion must delegate to the
    llm_shared OllamaProvider (messages passed through unchanged)."""
    from llm_shared.models import LLMRequest, LLMResponse
    from llm_shared.providers.ollama_provider import OllamaProvider

    provider = OllamaProvider(
        settings={"base_url": "http://localhost:11434"}
    )  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default

    request = LLMRequest(
        messages=[{"role": "user", "content": "Hello"}],
        model_name="llama3",
    )

    expected_response = LLMResponse(
        content="Hi from delegate",
        model="llama3",
        provider="ollama",
        processing_time=0.1,
        request_id=request.request_id,
        usage={"prompt_tokens": 5, "completion_tokens": 4, "total_tokens": 9},
    )

    mock_delegate = MagicMock()
    mock_delegate.chat_completion = AsyncMock(return_value=expected_response)
    mock_delegate.ollama_host = "http://localhost:11434"  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default

    with patch.object(provider, "_ensure_delegate", return_value=mock_delegate):
        response = await provider.chat_completion(request)

    # Delegate must have been called exactly once with the original request
    mock_delegate.chat_completion.assert_called_once_with(request)

    # Response content must be forwarded
    assert response.content == "Hi from delegate"
    assert response.error is None
