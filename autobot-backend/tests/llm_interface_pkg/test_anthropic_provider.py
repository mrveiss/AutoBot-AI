# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for AnthropicProvider extended thinking support (#3258).

These tests are fully offline — the Anthropic SDK is mocked so no real API
calls are made.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Minimal stubs so the module can be imported without the real anthropic SDK
# or the full autobot runtime.
# ---------------------------------------------------------------------------


def _make_anthropic_stub():
    """Return a minimal ``anthropic`` module stub."""
    stub = types.ModuleType("anthropic")
    stub.AsyncAnthropic = MagicMock
    sys.modules["anthropic"] = stub
    return stub


def _make_xxhash_stub():
    stub = types.ModuleType("xxhash")
    stub.xxh64 = MagicMock(return_value=MagicMock(hexdigest=MagicMock(return_value="0" * 16)))
    sys.modules["xxhash"] = stub


_make_anthropic_stub()
_make_xxhash_stub()


from llm_shared.models import LLMRequest  # noqa: E402
from llm_shared.providers.anthropic import (  # noqa: E402  (import after stub)
    AnthropicProvider,
    _build_api_kwargs,
    _extract_content_pair,
    _extract_text_content,
    _extract_think_tag_content,
    _strip_think_blocks,
)

# ---------------------------------------------------------------------------
# _strip_think_blocks
# ---------------------------------------------------------------------------


class TestStripThinkBlocks:
    def test_removes_single_block(self):
        raw = "Hello <think>secret reasoning</think> world"
        assert _strip_think_blocks(raw) == "Hello  world"

    def test_removes_multiline_block(self):
        raw = "Result:\n<think>\nstep 1\nstep 2\n</think>\nDone."
        assert _strip_think_blocks(raw) == "Result:\n\nDone."

    def test_removes_multiple_blocks(self):
        raw = "<think>a</think> mid <think>b</think>"
        assert _strip_think_blocks(raw) == "mid"

    def test_no_block_unchanged(self):
        raw = "Just a plain response."
        assert _strip_think_blocks(raw) == "Just a plain response."

    def test_case_insensitive(self):
        raw = "<THINK>hidden</THINK> visible"
        assert _strip_think_blocks(raw) == "visible"


# ---------------------------------------------------------------------------
# _build_api_kwargs
# ---------------------------------------------------------------------------


class TestBuildApiKwargs:
    def test_thinking_key_forwarded(self):
        base = {"model": "m", "max_tokens": 4096}
        thinking = {"type": "enabled", "budget_tokens": 8000}
        merged, headers = _build_api_kwargs(base, {"thinking": thinking, "temperature": 1})
        assert merged["thinking"] == thinking
        assert merged["temperature"] == 1
        assert headers == {}

    def test_extra_headers_separated(self):
        base = {"model": "m"}
        api_kwargs = {"extra_headers": {"anthropic-beta": "output-128k-2025-02-19"}}
        merged, headers = _build_api_kwargs(base, api_kwargs)
        assert "extra_headers" not in merged
        assert headers == {"anthropic-beta": "output-128k-2025-02-19"}

    def test_preserve_reasoning_consumed(self):
        base = {"model": "m"}
        merged, headers = _build_api_kwargs(base, {"preserve_reasoning": True})
        assert "preserve_reasoning" not in merged
        assert headers == {}

    def test_betas_routed_to_extra_headers(self):
        base = {"model": "m"}
        merged, headers = _build_api_kwargs(base, {"betas": ["output-128k-2025-02-19"]})
        assert "betas" not in merged
        assert headers["anthropic-beta"] == "output-128k-2025-02-19"

    def test_betas_merged_with_existing_extra_headers(self):
        base = {"model": "m"}
        api_kwargs = {
            "betas": ["beta-b"],
            "extra_headers": {"anthropic-beta": "beta-a"},
        }
        merged, headers = _build_api_kwargs(base, api_kwargs)
        assert "betas" not in merged
        assert "beta-a" in headers["anthropic-beta"]
        assert "beta-b" in headers["anthropic-beta"]

    def test_multiple_betas_comma_joined(self):
        base = {"model": "m"}
        merged, headers = _build_api_kwargs(base, {"betas": ["beta-a", "beta-b", "beta-c"]})
        assert "betas" not in merged
        assert headers["anthropic-beta"] == "beta-a,beta-b,beta-c"

    def test_base_override(self):
        base = {"max_tokens": 4096}
        merged, _ = _build_api_kwargs(base, {"max_tokens": 64000})
        assert merged["max_tokens"] == 64000

    def test_empty_api_kwargs(self):
        base = {"model": "m", "max_tokens": 4096}
        merged, headers = _build_api_kwargs(base, {})
        assert merged == base
        assert headers == {}


# ---------------------------------------------------------------------------
# _extract_text_content
# ---------------------------------------------------------------------------


class TestExtractTextContent:
    def _make_block(self, block_type: str, text: str = "") -> Any:
        block = MagicMock()
        block.type = block_type
        block.text = text
        return block

    def test_text_block_extracted(self):
        blocks = [self._make_block("text", "Hello world")]
        assert _extract_text_content(blocks, preserve_reasoning=False) == "Hello world"

    def test_thinking_block_excluded(self):
        blocks = [
            self._make_block("thinking", "secret chain-of-thought"),
            self._make_block("text", "Final answer"),
        ]
        result = _extract_text_content(blocks, preserve_reasoning=False)
        assert result == "Final answer"
        assert "secret" not in result

    def test_think_tags_stripped_by_default(self):
        blocks = [self._make_block("text", "<think>hidden</think>visible")]
        assert _extract_text_content(blocks, preserve_reasoning=False) == "visible"

    def test_think_tags_preserved_when_requested(self):
        blocks = [self._make_block("text", "<think>hidden</think>visible")]
        result = _extract_text_content(blocks, preserve_reasoning=True)
        assert "<think>" in result

    def test_multiple_text_blocks_joined(self):
        blocks = [
            self._make_block("text", "Part 1"),
            self._make_block("text", "Part 2"),
        ]
        result = _extract_text_content(blocks, preserve_reasoning=False)
        assert "Part 1" in result
        assert "Part 2" in result

    def test_empty_blocks_returns_empty(self):
        assert _extract_text_content([], preserve_reasoning=False) == ""


# ---------------------------------------------------------------------------
# AnthropicProvider._build_request_kwargs
# ---------------------------------------------------------------------------


class TestBuildRequestKwargs:
    def _make_request(self, metadata=None) -> LLMRequest:
        return LLMRequest(
            messages=[{"role": "user", "content": "hello"}],
            metadata=metadata or {},
        )

    def _provider(self) -> AnthropicProvider:
        return AnthropicProvider(settings={"api_key": "test-key"})

    def test_no_api_kwargs_defaults(self):
        provider = self._provider()
        kwargs, headers, preserve = provider._build_request_kwargs("claude-sonnet-4-6", self._make_request())
        assert kwargs["model"] == "claude-sonnet-4-6"
        assert kwargs["max_tokens"] == 4096
        assert headers == {}
        assert preserve is False

    def test_thinking_kwargs_forwarded(self):
        provider = self._provider()
        thinking = {"type": "enabled", "budget_tokens": 63000}
        request = self._make_request(
            metadata={
                "api_kwargs": {
                    "thinking": thinking,
                    "max_tokens": 64000,
                    "temperature": 1,
                    "extra_headers": {"anthropic-beta": "output-128k-2025-02-19"},
                }
            }
        )
        kwargs, headers, preserve = provider._build_request_kwargs("claude-sonnet-4-6", request)
        assert kwargs["thinking"] == thinking
        assert kwargs["max_tokens"] == 64000
        assert kwargs["temperature"] == 1
        assert headers == {"anthropic-beta": "output-128k-2025-02-19"}
        assert preserve is False

    def test_preserve_reasoning_flag(self):
        provider = self._provider()
        request = self._make_request(metadata={"api_kwargs": {"preserve_reasoning": True}})
        _, _, preserve = provider._build_request_kwargs("m", request)
        assert preserve is True

    def test_thinking_enforces_temperature_1(self):
        provider = self._provider()
        thinking = {"type": "enabled", "budget_tokens": 8000}
        request = self._make_request(
            metadata={
                "api_kwargs": {
                    "thinking": thinking,
                    "max_tokens": 16000,
                    # Deliberately omit temperature — must be auto-coerced to 1.
                }
            }
        )
        kwargs, _, _ = provider._build_request_kwargs("claude-sonnet-4-6", request)
        assert kwargs["temperature"] == 1

    def test_thinking_overrides_explicit_temperature(self):
        provider = self._provider()
        thinking = {"type": "enabled", "budget_tokens": 8000}
        request = self._make_request(
            metadata={
                "api_kwargs": {
                    "thinking": thinking,
                    "max_tokens": 16000,
                    "temperature": 0,  # Invalid with thinking — must be coerced to 1.
                }
            }
        )
        kwargs, _, _ = provider._build_request_kwargs("claude-sonnet-4-6", request)
        assert kwargs["temperature"] == 1

    def test_betas_routed_to_extra_headers_via_build_request_kwargs(self):
        provider = self._provider()
        request = self._make_request(
            metadata={
                "api_kwargs": {
                    "betas": ["output-128k-2025-02-19"],
                    "max_tokens": 64000,
                }
            }
        )
        kwargs, headers, _ = provider._build_request_kwargs("claude-sonnet-4-6", request)
        assert "betas" not in kwargs
        assert headers.get("anthropic-beta") == "output-128k-2025-02-19"

    def test_system_message_extracted(self):
        provider = self._provider()
        request = LLMRequest(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "hello"},
            ]
        )
        kwargs, _, _ = provider._build_request_kwargs("m", request)
        assert kwargs["system"] == "You are a helpful assistant."
        assert all(m["role"] != "system" for m in kwargs["messages"])


# ---------------------------------------------------------------------------
# AnthropicProvider.chat_completion (async, SDK mocked)
# ---------------------------------------------------------------------------


class TestChatCompletionWithThinking:
    def _make_block(self, block_type: str, text: str = "") -> Any:
        block = MagicMock()
        block.type = block_type
        block.text = text
        return block

    def _make_sdk_response(self, content_blocks):
        resp = MagicMock()
        resp.content = content_blocks
        resp.model = "claude-sonnet-4-6"
        resp.usage = MagicMock(input_tokens=100, output_tokens=200)
        return resp

    @pytest.mark.asyncio
    async def test_thinking_blocks_stripped_from_response(self):
        thinking_block = self._make_block("thinking", "chain of thought")
        text_block = self._make_block("text", "Final answer")
        sdk_response = self._make_sdk_response([thinking_block, text_block])

        provider = AnthropicProvider(settings={"api_key": "test-key"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=sdk_response)
        provider._client = mock_client

        request = LLMRequest(
            messages=[{"role": "user", "content": "hello"}],
            metadata={
                "api_kwargs": {
                    "thinking": {"type": "enabled", "budget_tokens": 8000},
                    "max_tokens": 16000,
                }
            },
        )

        response = await provider.chat_completion(request)

        assert response.error is None
        assert response.content == "Final answer"
        assert "chain of thought" not in response.content

    @pytest.mark.asyncio
    async def test_extra_headers_passed_to_sdk(self):
        text_block = self._make_block("text", "ok")
        sdk_response = self._make_sdk_response([text_block])

        provider = AnthropicProvider(settings={"api_key": "test-key"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=sdk_response)
        provider._client = mock_client

        request = LLMRequest(
            messages=[{"role": "user", "content": "hello"}],
            metadata={
                "api_kwargs": {
                    "extra_headers": {"anthropic-beta": "output-128k-2025-02-19"},
                }
            },
        )

        await provider.chat_completion(request)

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs.get("extra_headers") == {"anthropic-beta": "output-128k-2025-02-19"}

    @pytest.mark.asyncio
    async def test_normal_request_unaffected(self):
        text_block = self._make_block("text", "Hello!")
        sdk_response = self._make_sdk_response([text_block])

        provider = AnthropicProvider(settings={"api_key": "test-key"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=sdk_response)
        provider._client = mock_client

        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])

        response = await provider.chat_completion(request)

        assert response.error is None
        assert response.content == "Hello!"
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert "thinking" not in call_kwargs
        assert "extra_headers" not in call_kwargs

    @pytest.mark.asyncio
    async def test_preserve_reasoning_keeps_think_tags(self):
        text_block = self._make_block("text", "<think>visible reasoning</think>answer")
        sdk_response = self._make_sdk_response([text_block])

        provider = AnthropicProvider(settings={"api_key": "test-key"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=sdk_response)
        provider._client = mock_client

        request = LLMRequest(
            messages=[{"role": "user", "content": "think out loud"}],
            metadata={"api_kwargs": {"preserve_reasoning": True}},
        )

        response = await provider.chat_completion(request)

        assert "<think>" in response.content
        assert "visible reasoning" in response.content


# ---------------------------------------------------------------------------
# _extract_think_tag_content  (#10582)
# ---------------------------------------------------------------------------


class TestExtractThinkTagContent:
    def test_single_block_extracted(self):
        result = _extract_think_tag_content("<think>reasoning</think>answer")
        assert result == "reasoning"

    def test_no_block_returns_none(self):
        assert _extract_think_tag_content("plain text") is None

    def test_multiple_blocks_joined(self):
        result = _extract_think_tag_content("<think>step1</think>mid<think>step2</think>")
        assert result is not None
        assert "step1" in result
        assert "step2" in result

    def test_empty_tag_returns_none(self):
        assert _extract_think_tag_content("<think></think>text") is None


# ---------------------------------------------------------------------------
# _extract_content_pair  (#10582)
# ---------------------------------------------------------------------------


class TestExtractContentPair:
    def _make_block(self, block_type: str, text: str = "", thinking: str = "") -> Any:
        block = MagicMock()
        block.type = block_type
        block.text = text or None
        block.thinking = thinking or None
        return block

    def test_think_tag_in_text_block_captured(self):
        blocks = [self._make_block("text", "<think>reasoning</think>answer")]
        content, reasoning = _extract_content_pair(blocks, preserve_reasoning=False)
        assert content == "answer"
        assert reasoning == "reasoning"

    def test_native_thinking_block_captured(self):
        thinking_block = self._make_block("thinking", thinking="native reasoning")
        text_block = self._make_block("text", "answer")
        content, reasoning = _extract_content_pair([thinking_block, text_block], preserve_reasoning=False)
        assert content == "answer"
        assert reasoning == "native reasoning"

    def test_no_reasoning_returns_none(self):
        blocks = [self._make_block("text", "plain response")]
        content, reasoning = _extract_content_pair(blocks, preserve_reasoning=False)
        assert content == "plain response"
        assert reasoning is None

    def test_preserve_reasoning_keeps_tags_no_reasoning_field(self):
        blocks = [self._make_block("text", "<think>visible</think>shown")]
        content, reasoning = _extract_content_pair(blocks, preserve_reasoning=True)
        assert "<think>" in content
        # When preserve_reasoning=True, think tags are NOT stripped — reasoning captured separately only on strip path
        assert reasoning is None


# ---------------------------------------------------------------------------
# reasoning_content wired into LLMResponse  (#10582)
# ---------------------------------------------------------------------------


class TestReasoningContentInResponse:
    def _make_block(self, block_type: str, text: str = "", thinking: str = "") -> Any:
        block = MagicMock()
        block.type = block_type
        block.text = text or None
        block.thinking = thinking or None
        return block

    def _make_sdk_response(self, content_blocks):
        resp = MagicMock()
        resp.content = content_blocks
        resp.model = "claude-sonnet-4-6"
        resp.stop_reason = "end_turn"
        resp.usage = MagicMock(input_tokens=100, output_tokens=200)
        resp.usage.output_tokens_details = None
        return resp

    @pytest.mark.asyncio
    async def test_think_tag_response_content_and_reasoning_split(self):
        """A response with <think>reasoning</think>answer yields content=='answer'
        and reasoning_content=='reasoning' (#10582 acceptance criterion)."""
        text_block = self._make_block("text", "<think>reasoning</think>answer")
        sdk_response = self._make_sdk_response([text_block])

        provider = AnthropicProvider(settings={"api_key": "test-key"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=sdk_response)
        provider._client = mock_client

        request = LLMRequest(messages=[{"role": "user", "content": "think"}])
        response = await provider.chat_completion(request)

        assert response.content == "answer"
        assert response.reasoning_content == "reasoning"

    @pytest.mark.asyncio
    async def test_native_thinking_block_in_reasoning_content(self):
        thinking_block = self._make_block("thinking", thinking="chain of thought")
        text_block = self._make_block("text", "Final answer")
        sdk_response = self._make_sdk_response([thinking_block, text_block])

        provider = AnthropicProvider(settings={"api_key": "test-key"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=sdk_response)
        provider._client = mock_client

        request = LLMRequest(messages=[{"role": "user", "content": "hello"}])
        response = await provider.chat_completion(request)

        assert response.content == "Final answer"
        assert response.reasoning_content == "chain of thought"

    @pytest.mark.asyncio
    async def test_no_reasoning_content_is_none(self):
        text_block = self._make_block("text", "Hello!")
        sdk_response = self._make_sdk_response([text_block])

        provider = AnthropicProvider(settings={"api_key": "test-key"})
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=sdk_response)
        provider._client = mock_client

        request = LLMRequest(messages=[{"role": "user", "content": "hi"}])
        response = await provider.chat_completion(request)

        assert response.content == "Hello!"
        assert response.reasoning_content is None
