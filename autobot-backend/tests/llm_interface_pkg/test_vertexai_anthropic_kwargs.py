# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the Claude-on-Vertex sampling-kwargs fix (#15016).

``VertexAIProvider._claude_chat_completion`` / ``_claude_stream_completion``
call the same ``anthropic`` SDK's ``messages.create()``/``.stream()`` through
``AsyncAnthropicVertex`` and were building their own ``temperature`` kwarg
independently of ``llm_shared/providers/anthropic.py`` -- a second, unconverged
call site the issue's own sweep missed. These tests are fully offline (the
Vertex client is mocked); the signature-binding tests bind the real,
installed ``anthropic`` SDK signature, which a mocked client cannot exercise.
"""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock

import anthropic
import pytest

from llm_shared.models import LLMRequest
from llm_shared.providers.vertexai import VertexAIProvider


def _make_sdk_response() -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = "ok"
    resp = MagicMock()
    resp.content = [block]
    resp.model = "claude-opus-4@20251101"
    resp.stop_reason = "end_turn"
    resp.usage = MagicMock(input_tokens=10, output_tokens=5)
    return resp


class TestClaudeOnVertexSamplingKwargs:
    def _provider_with_mock_client(self) -> tuple[VertexAIProvider, AsyncMock]:
        provider = VertexAIProvider(settings={"vertex_ai_project": "test-project"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=_make_sdk_response())
        provider._anthropic_vertex_client = mock_client
        return provider, mock_client

    @pytest.mark.asyncio
    async def test_temperature_not_passed_as_top_level_kwarg(self):
        provider, mock_client = self._provider_with_mock_client()
        request = LLMRequest(
            messages=[{"role": "user", "content": "hi"}],
            model_name="claude-opus-4@20251101",
        )

        await provider._claude_chat_completion(request)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "temperature" not in call_kwargs
        assert "temperature" in call_kwargs["extra_body"]

    @pytest.mark.asyncio
    async def test_call_kwargs_bind_to_real_create_signature(self):
        provider, mock_client = self._provider_with_mock_client()
        request = LLMRequest(
            messages=[{"role": "user", "content": "hi"}],
            model_name="claude-opus-4@20251101",
        )

        await provider._claude_chat_completion(request)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        sig = inspect.signature(anthropic.resources.messages.messages.AsyncMessages.create)
        sig.bind(self=object(), **call_kwargs)
