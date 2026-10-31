# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Golden payloads for the Anthropic-family message split (#16815).

`anthropic.py` (Anthropic API), `vertexai.py` (Claude-on-Vertex) and `bedrock.py` (Claude-on-Bedrock)
each carried a copy of the same split: the last `system` message is lifted out, every other message
is kept as `{"role", "content"}` with `content` passed through unchanged. They now share
`anthropic_format.split_system_and_chat`. The fixture `golden/anthropic_family_16815.json` was
generated from the pre-refactor code; these tests assert each provider's request payload is
byte-identical to it.

The Vertex payloads pin that Claude-on-Vertex sends no `tools`/`tool_choice` today; fixing that
(#18627) must regenerate exactly those payloads and nothing else.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from llm_shared.models import LLMRequest, ToolDefinition
from llm_shared.providers.anthropic import AnthropicProvider
from llm_shared.providers.bedrock import BedrockProvider
from llm_shared.providers.vertexai import VertexAIProvider

GOLDEN = Path(__file__).parent / "golden" / "anthropic_family_16815.json"

_BLOCKS = [{"type": "text", "text": "look"}, {"type": "image", "source": {"type": "base64", "data": "AAA"}}]
MESSAGES: dict[str, list[dict[str, Any]]] = {
    "system_user": [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}],
    "multi_turn": [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ],
    "no_system": [{"role": "user", "content": "hi"}],
    "empty_content": [{"role": "system", "content": ""}, {"role": "user", "content": ""}],
    "empty_list": [],
    "two_systems_last_wins": [
        {"role": "system", "content": "first"},
        {"role": "user", "content": "u"},
        {"role": "system", "content": "second"},
    ],
    "content_blocks": [
        {"role": "user", "content": _BLOCKS},
        {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
    ],
    "tool_messages": [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "f", "input": {"x": 1}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "r"}]},
        {"role": "tool", "content": "raw"},
    ],
    "missing_keys": [{"content": "no role"}, {"role": "user"}, {}],
}
_TOOLS = [ToolDefinition(name="f", description="d", input_schema={"type": "object"})]


def _request(messages: list, tools: bool = False) -> LLMRequest:
    return LLMRequest(
        messages=messages,
        model_name="m",
        max_tokens=7,
        temperature=0.5,
        stop=["END"],
        tools=_TOOLS if tools else None,
        tool_choice="auto" if tools else None,
    )


class _Capture:
    """Stands in for the AnthropicVertex client and records the `messages.create` kwargs."""

    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}
        self.messages = MagicMock()
        self.messages.create = self._create

    async def _create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        raise RuntimeError("captured")


def _anthropic(messages: list, tools: bool) -> dict:
    provider = AnthropicProvider({"api_key": "k"})
    kwargs, headers, preserve = provider._build_request_kwargs("m", _request(messages, tools))
    return {"kwargs": kwargs, "headers": headers, "preserve": preserve}


def _vertexai(messages: list, tools: bool) -> dict:
    provider = VertexAIProvider({})
    client = _Capture()
    provider._ensure_anthropic_vertex_client = lambda: client  # type: ignore[method-assign]
    asyncio.run(provider._claude_chat_completion(_request(messages, tools)))
    return client.kwargs


def _bedrock(messages: list, tools: bool) -> dict:
    return BedrockProvider({})._build_claude_request(_request(messages, tools))


PROVIDERS = {"anthropic": _anthropic, "vertexai": _vertexai, "bedrock": _bedrock}


def capture_all() -> dict[str, dict[str, Any]]:
    """Every provider's payload for every message list, with and without tools."""
    return {
        f"{prov}/{name}/{'tools' if tools else 'plain'}": fn(msgs, tools)
        for prov, fn in PROVIDERS.items()
        for name, msgs in MESSAGES.items()
        for tools in (False, True)
    }


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=1, default=str)


_GOLDEN = json.loads(GOLDEN.read_text(encoding="utf-8")) if GOLDEN.exists() else {}


@pytest.mark.parametrize("key", sorted(_GOLDEN))
def test_payload_matches_the_pre_refactor_golden(key: str) -> None:
    prov, name, mode = key.split("/")
    got = PROVIDERS[prov](MESSAGES[name], mode == "tools")
    assert _canon(got) == _canon(_GOLDEN[key]), f"#16815: {key} payload drifted"


def test_golden_covers_every_provider_and_case() -> None:
    assert len(_GOLDEN) == len(PROVIDERS) * len(MESSAGES) * 2
