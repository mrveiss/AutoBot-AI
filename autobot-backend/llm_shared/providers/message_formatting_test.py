# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Byte-identical provider payloads across the #16815 formatter consolidation.

``_legacy_*`` below are frozen verbatim copies of the per-provider inlined code that
``message_formatting.py`` replaced. Every provider's real request builder is driven over
the same conversations and its messages/system/tools JSON must equal the frozen output
byte for byte, so a change to the shared formatter that alters what a provider sends
fails here.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_shared.models import LLMRequest, LLMSettings, ToolDefinition
from llm_shared.providers.anthropic import AnthropicProvider
from llm_shared.providers.anthropic_format import split_system_and_chat
from llm_shared.providers.bedrock import BedrockProvider
from llm_shared.providers.cache_utils import sorted_for_cache
from llm_shared.providers.message_formatting import anthropic_tool_schemas, openai_function_tool_schemas
from llm_shared.providers.mistral import MistralProvider
from llm_shared.providers.ollama import OllamaRequestExecutor
from llm_shared.providers.openai import OpenAIProvider
from llm_shared.providers.vertexai import VertexAIProvider

_TOOLS = [
    ToolDefinition("get_weather", "Get the weather", {"type": "object", "properties": {"city": {"type": "string"}}}),
    ToolDefinition("noop", "", {}),
]
_IMAGE = [
    {"type": "text", "text": "what is this?"},
    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0="}},
]
_CONVERSATIONS = {
    "system_and_user": [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "hi"}],
    "multi_turn": [
        {"role": "system", "content": "S"},
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ],
    "tool_call_and_result": [
        {"role": "user", "content": "weather in Paris?"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "t1", "function": {"name": "get_weather"}}]},
        {"role": "tool", "content": '{"temp": 21}', "tool_call_id": "t1"},
    ],
    "image_blocks": [{"role": "user", "content": _IMAGE}],
    "two_system_messages_last_wins": [
        {"role": "system", "content": "first"},
        {"role": "user", "content": "x"},
        {"role": "system", "content": "second"},
    ],
    "missing_role_and_content": [{"content": "no role"}, {"role": "assistant"}],
    "no_system": [{"role": "user", "content": "only"}],
    "unicode": [{"role": "user", "content": 'Rīga ☃ "quoted"'}],
}
_TOOL_CASES = {"no_tools": (None, None), "tools_auto": (_TOOLS, "auto"), "tools_no_choice": (_TOOLS, None)}

_PARAMS = [pytest.param(m, t, id=f"{cn}-{tn}") for cn, m in _CONVERSATIONS.items() for tn, t in _TOOL_CASES.items()]


def _legacy_split(messages: list) -> tuple[str, list]:
    system_content = ""
    chat_messages = []
    for msg in messages:
        if msg.get("role") == "system":
            system_content = msg.get("content", "")
        else:
            chat_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    return system_content, chat_messages


def _legacy_anthropic_tools(tools) -> List[Dict[str, Any]]:
    return [{"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in tools]


def _legacy_openai_tools(tools) -> List[Dict[str, Any]]:
    return [
        {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.input_schema}}
        for t in tools
    ]


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _sent(value: Any) -> str:
    """Providers whose send path runs ``sorted_for_cache`` are compared as sent (key-sorted)."""
    return _j(sorted_for_cache({"v": value})["v"])


def _request(messages, tools, tool_choice) -> LLMRequest:
    return LLMRequest(
        messages=messages, model_name="m", tools=tools, tool_choice=tool_choice, metadata={"enable_prompt_cache": False}
    )


@pytest.mark.parametrize(("messages", "tools"), _PARAMS)
def test_shared_helpers_equal_the_frozen_inlined_code(messages, tools) -> None:
    tools, _choice = tools
    assert _j(split_system_and_chat(messages)) == _j(_legacy_split(messages))
    if tools:
        assert _j(anthropic_tool_schemas(tools)) == _j(_legacy_anthropic_tools(tools))
        assert _j(openai_function_tool_schemas(tools)) == _j(_legacy_openai_tools(tools))


@pytest.mark.parametrize(("messages", "tools"), _PARAMS)
def test_anthropic_payload(messages, tools) -> None:
    tools, choice = tools
    kwargs, _headers, _ = AnthropicProvider(settings={"api_key": "k"})._build_request_kwargs(
        "m", _request(messages, tools, choice)
    )
    system, chat = _legacy_split(messages)
    assert _j(kwargs["messages"]) == _j(chat)
    assert kwargs.get("system") == (system or None)
    assert _j(kwargs.get("tools")) == _j(_legacy_anthropic_tools(tools) if tools else None)
    assert kwargs.get("tool_choice") == ({"type": choice} if tools and choice else None)


@pytest.mark.parametrize(("messages", "tools"), _PARAMS)
def test_bedrock_claude_payload(messages, tools) -> None:
    tools, choice = tools
    body = BedrockProvider(settings={})._build_claude_request(_request(messages, tools, choice))
    system, chat = _legacy_split(messages)
    assert _j(body["messages"]) == _j(chat)
    assert body.get("system") == (system or None)
    assert _j(body.get("tools")) == _j(_legacy_anthropic_tools(tools) if tools else None)
    assert body.get("tool_choice") == ({"type": choice} if tools and choice else None)


@pytest.mark.asyncio
@pytest.mark.parametrize(("messages", "tools"), _PARAMS)
async def test_vertex_claude_payload(messages, tools) -> None:
    tools, choice = tools
    provider = VertexAIProvider(settings={})
    client = MagicMock()
    client.messages.create = AsyncMock(side_effect=RuntimeError("stop after capture"))
    provider._anthropic_vertex_client = client
    await provider._claude_chat_completion(_request(messages, tools, choice))
    sent = client.messages.create.call_args.kwargs
    system, chat = _legacy_split(messages)
    assert _sent(sent["messages"]) == _sent(chat)
    assert sent.get("system") == (system or None)
    assert "tools" not in sent  # the Vertex Claude path never sent tools; unchanged


@pytest.mark.parametrize(("messages", "tools"), _PARAMS)
def test_openai_compatible_payload(messages, tools) -> None:
    tools, choice = tools
    params = OpenAIProvider(settings={"api_key": "k"})._build_params(_request(messages, tools, choice), "m")
    assert _sent(params["messages"]) == _sent(messages)
    assert _sent(params.get("tools")) == _sent(_legacy_openai_tools(tools) if tools else None)


@pytest.mark.parametrize(("messages", "tools"), _PARAMS)
def test_mistral_payload(messages, tools) -> None:
    tools, choice = tools
    params = MistralProvider(settings={"api_key": "k"})._build_params(
        _request(messages, tools, choice), "m", stream=False
    )
    assert _j(params["messages"]) == _j(messages)
    assert _j(params.get("tools")) == _j(_legacy_openai_tools(tools) if tools else None)
    assert params.get("tool_choice") == (choice if tools else None)


@pytest.mark.parametrize(("messages", "tools"), _PARAMS)
def test_ollama_payload(messages, tools) -> None:
    tools, choice = tools
    manager = MagicMock()
    manager.should_use_streaming.return_value = False
    provider = OllamaRequestExecutor(settings=LLMSettings(), streaming_manager=manager)
    data = provider.build_request_data(_request(messages, tools, choice), "llama3.1:8b", use_streaming=False)
    assert _j(data["messages"]) == _j(messages)
    assert _j(data.get("tools")) == _j(_legacy_openai_tools(tools) if tools else None)
    assert data.get("tool_choice") == (choice if tools else None)
