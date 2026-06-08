# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for GroqProvider (#4096).

These tests are fully offline — the Groq SDK is mocked so no real API calls
are made.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Minimal stubs so the module can be imported without the real groq SDK
# or the full autobot runtime.
# ---------------------------------------------------------------------------


def _make_groq_stub():
    """Return a minimal ``groq`` module stub."""
    stub = types.ModuleType("groq")
    stub.AsyncGroq = MagicMock
    sys.modules["groq"] = stub
    return stub


def _make_xxhash_stub():
    stub = types.ModuleType("xxhash")
    stub.xxh64 = MagicMock(return_value=MagicMock(hexdigest=MagicMock(return_value="0" * 16)))
    sys.modules["xxhash"] = stub


_make_groq_stub()
_make_xxhash_stub()


from llm_shared.models import LLMRequest  # noqa: E402
from llm_shared.providers.groq import GroqProvider  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sdk_response(content: str, model: str = "llama-3.1-8b-instant") -> MagicMock:
    choice = MagicMock()
    choice.message.content = content
    choice.finish_reason = "stop"
    resp = MagicMock()
    resp.choices = [choice]
    resp.model = model
    resp.usage = MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30)
    return resp


# ---------------------------------------------------------------------------
# GroqProvider.chat_completion
# ---------------------------------------------------------------------------


class TestGroqProviderChatCompletion:
    @pytest.mark.asyncio
    async def test_successful_completion(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_make_sdk_response("Hello from Groq!"))
        provider._client = mock_client

        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
        response = await provider.chat_completion(request)

        assert response.error is None
        assert response.content == "Hello from Groq!"
        assert response.provider == "groq"

    @pytest.mark.asyncio
    async def test_error_returned_in_response(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("rate limit exceeded"))
        provider._client = mock_client

        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
        response = await provider.chat_completion(request)

        assert response.error is not None
        assert "rate limit" in response.error
        assert response.content == ""

    @pytest.mark.asyncio
    async def test_usage_populated(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_make_sdk_response("ok"))
        provider._client = mock_client

        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
        response = await provider.chat_completion(request)

        assert response.usage["prompt_tokens"] == 10
        assert response.usage["completion_tokens"] == 20
        assert response.usage["total_tokens"] == 30

    @pytest.mark.asyncio
    async def test_custom_model_used(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=_make_sdk_response("ok", model="llama3-70b-8192"))
        provider._client = mock_client

        request = LLMRequest(
            messages=[{"role": "user", "content": "hi"}],
            model_name="llama3-70b-8192",
        )
        response = await provider.chat_completion(request)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "llama3-70b-8192"
        assert response.model == "llama3-70b-8192"


# ---------------------------------------------------------------------------
# GroqProvider.list_models
# ---------------------------------------------------------------------------


class TestGroqProviderListModels:
    @pytest.mark.asyncio
    async def test_live_models_returned(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        model_a = MagicMock()
        model_a.id = "llama3-8b-8192"
        model_b = MagicMock()
        model_b.id = "mixtral-8x7b-32768"
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=MagicMock(data=[model_a, model_b]))
        provider._client = mock_client

        models = await provider.list_models()
        assert "llama3-8b-8192" in models
        assert "mixtral-8x7b-32768" in models

    @pytest.mark.asyncio
    async def test_fallback_to_static_list_on_error(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(side_effect=RuntimeError("network error"))
        provider._client = mock_client

        models = await provider.list_models()
        assert len(models) > 0
        assert "llama-3.1-8b-instant" in models


# ---------------------------------------------------------------------------
# GroqProvider.is_available
# ---------------------------------------------------------------------------


class TestGroqProviderIsAvailable:
    @pytest.mark.asyncio
    async def test_available_when_models_endpoint_responds(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(return_value=MagicMock(data=[]))
        provider._client = mock_client

        assert await provider.is_available() is True

    @pytest.mark.asyncio
    async def test_not_available_when_api_raises(self):
        provider = GroqProvider(settings={"api_key": "gsk_test"})
        mock_client = AsyncMock()
        mock_client.models.list = AsyncMock(side_effect=RuntimeError("unauthorized"))
        provider._client = mock_client

        assert await provider.is_available() is False
