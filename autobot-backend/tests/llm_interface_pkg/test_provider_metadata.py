# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for provider_metadata field on LLMResponse (#3262).

Verifies that each provider's chat_completion populates provider_metadata
with the expected keys and values.  All network calls are mocked so these
tests run fully offline.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Minimal stubs for optional heavy dependencies
# ---------------------------------------------------------------------------


def _stub_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# groq
if "groq" not in sys.modules:
    _stub_module("groq", AsyncGroq=MagicMock)

# xxhash (used by some llm_shared internals)
if "xxhash" not in sys.modules:
    _stub_module(
        "xxhash",
        xxh64=MagicMock(return_value=MagicMock(hexdigest=MagicMock(return_value="0" * 16))),
    )

# opentelemetry stubs (used by openai_provider)
for _otel_mod in [
    "opentelemetry",
    "opentelemetry.trace",
]:
    if _otel_mod not in sys.modules:
        _stub_module(_otel_mod)

if "opentelemetry" not in sys.modules or not hasattr(sys.modules["opentelemetry"], "trace"):
    _otel = sys.modules.get("opentelemetry", types.ModuleType("opentelemetry"))
    _otel_trace = sys.modules.get("opentelemetry.trace", types.ModuleType("opentelemetry.trace"))
    _tracer_stub = MagicMock()
    _span_stub = MagicMock()
    _span_stub.__enter__ = MagicMock(return_value=_span_stub)
    _span_stub.__exit__ = MagicMock(return_value=False)
    _span_stub.is_recording.return_value = False
    _tracer_stub.start_as_current_span = MagicMock(return_value=_span_stub)
    _otel_trace.get_tracer = MagicMock(return_value=_tracer_stub)
    _otel_trace.SpanKind = MagicMock()
    _otel_trace.Status = MagicMock()
    _otel_trace.StatusCode = MagicMock()
    _otel.trace = _otel_trace
    sys.modules["opentelemetry"] = _otel
    sys.modules["opentelemetry.trace"] = _otel_trace

# circuit_breaker stub
if "circuit_breaker" not in sys.modules:
    _cb = _stub_module("circuit_breaker")

    def _passthrough(name):
        def decorator(fn):
            return fn

        return decorator

    _cb.circuit_breaker_async = _passthrough

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from llm_shared.models import LLMRequest, LLMResponse  # noqa: E402
from llm_shared.providers.anthropic import AnthropicProvider  # noqa: E402
from llm_shared.providers.custom_openai import CustomOpenAIProvider  # noqa: E402
from llm_shared.providers.groq import GroqProvider  # noqa: E402
from llm_shared.providers.openai import OpenAIProvider  # noqa: E402

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _basic_request(model: str = "") -> LLMRequest:
    req = LLMRequest(messages=[{"role": "user", "content": "hello"}])
    if model:
        req.model_name = model
    return req


def _assert_provider_metadata(metadata: dict, provider: str, model: str) -> None:
    """Assert the standard shape of provider_metadata."""
    assert metadata is not None, "provider_metadata must not be None"
    assert metadata["provider"] == provider
    assert metadata["model_api_name"] == model
    assert "api_kwargs_applied" in metadata
    assert isinstance(metadata["api_kwargs_applied"], dict)
    # total_tokens key is optional but must be int when present
    if "total_tokens" in metadata:
        assert isinstance(metadata["total_tokens"], int)


# ---------------------------------------------------------------------------
# LLMResponse dataclass — field exists with default None
# ---------------------------------------------------------------------------


class TestLLMResponseProviderMetadataField:
    def test_field_defaults_to_none(self):
        resp = LLMResponse(content="hi")
        assert resp.provider_metadata is None

    def test_field_accepts_dict(self):
        resp = LLMResponse(
            content="hi",
            provider_metadata={"provider": "openai", "model_api_name": "gpt-4o-mini"},
        )
        assert resp.provider_metadata["provider"] == "openai"


# ---------------------------------------------------------------------------
# BaseProvider._build_provider_metadata helper
# ---------------------------------------------------------------------------


class TestBuildProviderMetadata:
    def test_standard_fields_present(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        meta = provider._build_provider_metadata(
            model_api_name="llama-3.1-8b-instant",
            api_kwargs_applied={"temperature": 0.7},
            total_tokens=42,
        )
        assert meta["provider"] == "groq"
        assert meta["model_api_name"] == "llama-3.1-8b-instant"
        assert meta["api_kwargs_applied"] == {"temperature": 0.7}
        assert meta["total_tokens"] == 42

    def test_total_tokens_omitted_when_none(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        meta = provider._build_provider_metadata(
            model_api_name="llama-3.1-8b-instant",
            api_kwargs_applied={},
            total_tokens=None,
        )
        assert "total_tokens" not in meta


# ---------------------------------------------------------------------------
# GroqProvider — chat_completion populates provider_metadata
# ---------------------------------------------------------------------------


def _make_groq_response(content: str, model: str = "llama-3.1-8b-instant") -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    resp.model = model
    resp.usage = MagicMock(prompt_tokens=5, completion_tokens=10, total_tokens=15)
    return resp


class TestGroqProviderMetadata:
    @pytest.mark.asyncio
    async def test_provider_metadata_populated(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_make_groq_response("Hello!"))
        provider._client = mock_client

        response = await provider.chat_completion(_basic_request())

        assert response.provider_metadata is not None
        _assert_provider_metadata(response.provider_metadata, "groq", "llama-3.1-8b-instant")
        assert response.provider_metadata["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_provider_metadata_contains_model_in_kwargs(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_make_groq_response("ok", model="llama3-70b-8192"))
        provider._client = mock_client

        response = await provider.chat_completion(_basic_request("llama3-70b-8192"))

        assert response.provider_metadata["model_api_name"] == "llama3-70b-8192"
        assert response.provider_metadata["api_kwargs_applied"]["model"] == "llama3-70b-8192"

    @pytest.mark.asyncio
    async def test_provider_metadata_none_on_error(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("rate limited"))
        provider._client = mock_client

        response = await provider.chat_completion(_basic_request())

        assert response.error is not None
        assert response.provider_metadata is None


# ---------------------------------------------------------------------------
# AnthropicProvider — chat_completion populates provider_metadata
# ---------------------------------------------------------------------------


def _make_anthropic_response(text: str, model: str = "claude-sonnet-4-6") -> MagicMock:
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    resp = MagicMock()
    resp.model = model
    resp.content = [text_block]
    resp.usage = MagicMock(input_tokens=8, output_tokens=12)
    return resp


class TestAnthropicProviderMetadata:
    @pytest.mark.asyncio
    async def test_provider_metadata_populated(self):
        provider = AnthropicProvider(settings={"api_key": "sk-ant-test"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_make_anthropic_response("Hi!"))
        provider._client = mock_client

        response = await provider.chat_completion(_basic_request())

        assert response.provider_metadata is not None
        _assert_provider_metadata(response.provider_metadata, "anthropic", "claude-sonnet-4-6")
        assert response.provider_metadata["total_tokens"] == 20  # 8 + 12

    @pytest.mark.asyncio
    async def test_provider_metadata_none_on_error(self):
        provider = AnthropicProvider(settings={"api_key": "sk-ant-test"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(side_effect=RuntimeError("overloaded"))
        provider._client = mock_client

        response = await provider.chat_completion(_basic_request())

        assert response.error is not None
        assert response.provider_metadata is None


# ---------------------------------------------------------------------------
# OpenAIProvider — chat_completion populates provider_metadata
# ---------------------------------------------------------------------------


def _make_openai_response(content: str, model: str = "gpt-4o-mini") -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    resp.model = model
    resp.usage = MagicMock(prompt_tokens=6, completion_tokens=9, total_tokens=15)
    return resp


class TestOpenAIProviderMetadata:
    @pytest.mark.asyncio
    async def test_provider_metadata_populated(self):
        provider = OpenAIProvider(settings={"api_key": "sk-test"})
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_make_openai_response("Hello!"))
        provider._client = mock_client

        response = await provider.chat_completion(_basic_request())

        assert response.provider_metadata is not None
        _assert_provider_metadata(response.provider_metadata, "openai", "gpt-4o-mini")
        assert response.provider_metadata["total_tokens"] == 15

    @pytest.mark.asyncio
    async def test_provider_metadata_none_on_error(self):
        provider = OpenAIProvider(settings={"api_key": "sk-test"})
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("quota exceeded"))
        provider._client = mock_client

        response = await provider.chat_completion(_basic_request())

        assert response.error is not None
        assert response.provider_metadata is None


# ---------------------------------------------------------------------------
# CustomOpenAIProvider — chat_completion populates provider_metadata
# ---------------------------------------------------------------------------


def _make_custom_response(content: str, model: str = "local-model") -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    resp.model = model
    resp.usage = MagicMock(prompt_tokens=4, completion_tokens=8, total_tokens=12)
    return resp


class TestCustomOpenAIProviderMetadata:
    @pytest.mark.asyncio
    async def test_provider_metadata_populated(self):
        provider = CustomOpenAIProvider(
            settings={"base_url": "http://localhost:8000/v1", "default_model": "local-model"}
        )
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_make_custom_response("Hello from local!"))
        provider._client = mock_client

        response = await provider.chat_completion(_basic_request())

        assert response.provider_metadata is not None
        _assert_provider_metadata(response.provider_metadata, "custom_openai", "local-model")
        assert response.provider_metadata["total_tokens"] == 12
