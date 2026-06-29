# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for MCP tool wiring across Anthropic/OpenAI/Groq/CustomOpenAI providers.
GH#7910
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_shared.models import LLMRequest, ToolCall, ToolDefinition
from llm_shared.providers.anthropic import AnthropicProvider
from llm_shared.providers.custom_openai import CustomOpenAIProvider
from llm_shared.providers.groq import GroqProvider
from llm_shared.providers.openai import OpenAIProvider

_TOOL = ToolDefinition(
    name="get_weather",
    description="Get the current weather",
    input_schema={"type": "object", "properties": {"location": {"type": "string"}}},
)


def _make_request(tools=None, tool_choice=None):
    return LLMRequest(
        messages=[{"role": "user", "content": "What is the weather in Paris?"}],
        model_name="test-model",
        tools=tools,
        tool_choice=tool_choice,
    )


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------


class TestAnthropicToolWiring:
    def _make_provider(self):
        p = AnthropicProvider(settings={"api_key": "test-key"})
        return p

    def _fake_response(self, *, with_tool: bool):
        """Build a mock Anthropic messages.create response."""
        usage = SimpleNamespace(input_tokens=10, output_tokens=5)
        if with_tool:
            block = SimpleNamespace(
                type="tool_use",
                id="toolu_01",
                name="get_weather",
                input={"location": "Paris"},
            )
            content = [block]
        else:
            text_block = SimpleNamespace(type="text", text="It's sunny.", reasoning=None)
            content = [text_block]
        return SimpleNamespace(
            content=content,
            model="claude-sonnet-4-6",
            stop_reason="end_turn",
            usage=usage,
        )

    @pytest.mark.asyncio
    async def test_tool_call_extracted(self):
        provider = self._make_provider()
        fake_resp = self._fake_response(with_tool=True)
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=fake_resp)
        provider._client = mock_client

        req = _make_request(tools=[_TOOL], tool_choice="auto")
        resp = await provider._chat_completion_impl(req)

        assert resp.tool_calls is not None
        assert len(resp.tool_calls) == 1
        tc = resp.tool_calls[0]
        assert isinstance(tc, ToolCall)
        assert tc.id == "toolu_01"
        assert tc.name == "get_weather"
        assert tc.arguments == {"location": "Paris"}
        assert resp.finish_reason == "tool_calls"

    @pytest.mark.asyncio
    async def test_no_tools_request_unchanged(self):
        provider = self._make_provider()
        fake_resp = self._fake_response(with_tool=False)
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=fake_resp)
        provider._client = mock_client

        req = _make_request()  # tools=None
        resp = await provider._chat_completion_impl(req)

        assert resp.tool_calls is None
        assert resp.finish_reason == "end_turn"
        # tools must NOT be in the SDK call kwargs
        call_kwargs = mock_client.messages.create.call_args[1]
        assert "tools" not in call_kwargs

    @pytest.mark.asyncio
    async def test_tools_wired_into_sdk_call(self):
        provider = self._make_provider()
        fake_resp = self._fake_response(with_tool=False)
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=fake_resp)
        provider._client = mock_client

        req = _make_request(tools=[_TOOL], tool_choice="auto")
        await provider._chat_completion_impl(req)

        call_kwargs = mock_client.messages.create.call_args[1]
        assert "tools" in call_kwargs
        assert call_kwargs["tools"][0]["name"] == "get_weather"
        assert call_kwargs["tool_choice"] == {"type": "auto"}


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------


def _openai_tool_call_mock(tc_id, name, args_json):
    tc = MagicMock()
    tc.id = tc_id
    tc.function.name = name
    tc.function.arguments = args_json
    return tc


def _openai_response(content=None, tool_calls=None, finish_reason="stop"):
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], model="gpt-4o", usage=usage)


class TestOpenAIToolWiring:
    def _make_provider(self):
        p = OpenAIProvider(settings={"api_key": "test-key"})
        return p

    @pytest.mark.asyncio
    async def test_tool_call_extracted(self):
        provider = self._make_provider()
        tc_mock = _openai_tool_call_mock("call_01", "get_weather", '{"location":"Paris"}')
        fake_resp = _openai_response(tool_calls=[tc_mock], finish_reason="tool_calls")
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)
        provider._client = mock_client

        req = _make_request(tools=[_TOOL], tool_choice="auto")
        resp = await provider._chat_completion_impl(req)

        assert resp.tool_calls is not None
        assert len(resp.tool_calls) == 1
        tc = resp.tool_calls[0]
        assert tc.id == "call_01"
        assert tc.name == "get_weather"
        assert tc.arguments == {"location": "Paris"}

    @pytest.mark.asyncio
    async def test_no_tools_request_unchanged(self):
        provider = self._make_provider()
        fake_resp = _openai_response(content="Sunny!", tool_calls=None)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)
        provider._client = mock_client

        req = _make_request()
        resp = await provider._chat_completion_impl(req)

        assert resp.tool_calls is None
        call_params = mock_client.chat.completions.create.call_args[1]
        assert "tools" not in call_params

    @pytest.mark.asyncio
    async def test_invalid_json_arguments_fallback(self):
        provider = self._make_provider()
        tc_mock = _openai_tool_call_mock("call_02", "get_weather", "NOT_JSON")
        fake_resp = _openai_response(tool_calls=[tc_mock], finish_reason="tool_calls")
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)
        provider._client = mock_client

        req = _make_request(tools=[_TOOL])
        resp = await provider._chat_completion_impl(req)

        assert resp.tool_calls is not None
        assert resp.tool_calls[0].arguments == {}


# ---------------------------------------------------------------------------
# Groq (same OpenAI-compat pattern)
# ---------------------------------------------------------------------------


class TestGroqToolWiring:
    def _make_provider(self):
        p = GroqProvider(settings={"api_key": "test-key"})
        return p

    @pytest.mark.asyncio
    async def test_tool_call_extracted(self):
        provider = self._make_provider()
        tc_mock = _openai_tool_call_mock("call_groq_01", "get_weather", '{"location":"Berlin"}')
        fake_resp = _openai_response(tool_calls=[tc_mock], finish_reason="tool_calls")
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)
        provider._client = mock_client

        req = _make_request(tools=[_TOOL])
        resp = await provider.chat_completion(req)

        assert resp.tool_calls is not None
        assert resp.tool_calls[0].name == "get_weather"
        assert resp.tool_calls[0].arguments == {"location": "Berlin"}

    @pytest.mark.asyncio
    async def test_no_tools_request_unchanged(self):
        provider = self._make_provider()
        fake_resp = _openai_response(content="Sunny!", tool_calls=None)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)
        provider._client = mock_client

        req = _make_request()
        resp = await provider.chat_completion(req)

        assert resp.tool_calls is None
        call_params = mock_client.chat.completions.create.call_args[1]
        assert "tools" not in call_params


# ---------------------------------------------------------------------------
# CustomOpenAI
# ---------------------------------------------------------------------------


class TestCustomOpenAIToolWiring:
    def _make_provider(self):
        p = CustomOpenAIProvider(settings={"base_url": "http://localhost:8080", "api_key": "none"})  # canonical: ignore py-hardcoded-url — test fixture/mock URL, not an executable default
        return p

    @pytest.mark.asyncio
    async def test_tool_call_extracted(self):
        provider = self._make_provider()
        tc_mock = _openai_tool_call_mock("call_custom_01", "get_weather", '{"location":"Tokyo"}')
        fake_resp = _openai_response(tool_calls=[tc_mock], finish_reason="tool_calls")
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)
        provider._client = mock_client

        req = _make_request(tools=[_TOOL])
        resp = await provider.chat_completion(req)

        assert resp.tool_calls is not None
        assert resp.tool_calls[0].name == "get_weather"
        assert resp.tool_calls[0].arguments == {"location": "Tokyo"}

    @pytest.mark.asyncio
    async def test_no_tools_request_unchanged(self):
        provider = self._make_provider()
        fake_resp = _openai_response(content="Cloudy.", tool_calls=None)
        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=fake_resp)
        provider._client = mock_client

        req = _make_request()
        resp = await provider.chat_completion(req)

        assert resp.tool_calls is None
        call_params = mock_client.chat.completions.create.call_args[1]
        assert "tools" not in call_params
