# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anthropic provider for the multi-provider LLM layer (#1806).

API key is read (in priority order) from:
  1. ``settings["api_key"]``
  2. Environment variable ``ANTHROPIC_API_KEY``

API keys are never logged.

Extended thinking (#3258):
  Pass a ``thinking`` dict in ``request.metadata["api_kwargs"]`` to enable
  chain-of-thought reasoning on supported models (claude-3-7-sonnet and later):

      api_kwargs = {
          "thinking": {"type": "enabled", "budget_tokens": 63000},
          "max_tokens": 64000,
          "temperature": 1,
          "extra_headers": {"anthropic-beta": "output-128k-2025-02-19"},
      }

  Thinking blocks are stripped from the returned ``content`` unless
  ``preserve_reasoning=True`` is present in ``api_kwargs``.

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
"""

from __future__ import annotations

import re
import time
from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.model_constants import (
    ANTHROPIC_CLAUDE3_OPUS_DATED,
    ANTHROPIC_CLAUDE35_HAIKU,
    ANTHROPIC_CLAUDE_HAIKU4_5,
    ANTHROPIC_CLAUDE_OPUS4_6,
    ANTHROPIC_CLAUDE_SONNET4,
    ANTHROPIC_CLAUDE_SONNET4_6,
)
from llm_shared.models import LLMRequest, LLMResponse, ToolCall
from llm_shared.types import ProviderType

from ..base_provider import BaseProvider
from .cache_utils import sorted_for_cache

logger = get_logger(__name__)

_ANTHROPIC_MODELS = [
    ANTHROPIC_CLAUDE_OPUS4_6,
    ANTHROPIC_CLAUDE_SONNET4_6,
    ANTHROPIC_CLAUDE_SONNET4,
    ANTHROPIC_CLAUDE_HAIKU4_5,
    ANTHROPIC_CLAUDE35_HAIKU,
    ANTHROPIC_CLAUDE3_OPUS_DATED,
]

# Regex that matches <think>…</think> blocks (case-insensitive, dotall).
_THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_think_blocks(text: str) -> str:
    """Remove ``<think>…</think>`` wrapper blocks from *text*."""
    return _THINK_BLOCK_RE.sub("", text).strip()


def _build_api_kwargs(
    base: Dict[str, Any],
    api_kwargs: Dict[str, Any],
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Merge caller-supplied *api_kwargs* into *base* request parameters.

    Handles the three extended-thinking keys that need special treatment:

    - ``thinking``      — forwarded directly to the SDK call.
    - ``betas``         — converted to ``extra_headers["anthropic-beta"]`` as a
                          comma-joined string; the SDK does not accept a ``betas``
                          kwarg on ``messages.create()``.
    - ``extra_headers`` — collected separately for the SDK ``extra_headers``
                          keyword argument (not part of the messages payload).
    - ``preserve_reasoning`` — consumed here; not forwarded to the SDK.

    All remaining keys in *api_kwargs* (e.g. ``max_tokens``, ``temperature``)
    are merged into *base*, overriding any previously set value.

    Returns:
        (merged_kwargs, extra_headers)
    """
    extra_headers: Dict[str, Any] = {}
    preserved_keys = {"preserve_reasoning", "extra_headers", "betas"}

    for key, value in api_kwargs.items():
        if key in preserved_keys:
            continue
        base[key] = value

    extra_headers = dict(api_kwargs.get("extra_headers") or {})

    betas: List[str] = api_kwargs.get("betas") or []
    if betas:
        existing = extra_headers.get("anthropic-beta", "")
        merged_betas = [b for b in existing.split(",") if b] + list(betas)
        extra_headers["anthropic-beta"] = ",".join(merged_betas)

    return base, extra_headers


def _extract_text_content(response_content: list, preserve_reasoning: bool) -> str:
    """
    Extract the text from an Anthropic response content block list.

    When *preserve_reasoning* is False (default) ``<think>…</think>`` wrapper
    blocks written by the model are stripped before returning.
    """
    parts: List[str] = []
    for block in response_content:
        block_type = getattr(block, "type", None)
        if block_type == "thinking":
            continue
        text = getattr(block, "text", None)
        if text:
            parts.append(text)

    joined = "\n".join(parts)
    return joined if preserve_reasoning else _strip_think_blocks(joined)


class AnthropicProvider(BaseProvider):
    """
    Anthropic Claude provider implementation.

    Supports chat completion and streaming for all Claude model families.
    Requires the ``anthropic`` package (``pip install anthropic``).

    Extended thinking (#3258):
      Set ``request.metadata["api_kwargs"]["thinking"]`` to enable chain-of-
      thought reasoning.  See module docstring for a full example.

    OTel tracing (#697): every inference call emits an ``llm.inference`` span.
    """

    provider_name = ProviderType.ANTHROPIC.value

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self._api_key: str | None = None
        self._client = None

    def _resolve_api_key(self) -> str | None:
        """Resolve API key from settings or environment."""
        if self._api_key:
            return self._api_key
        self._api_key = self._get_setting("api_key") or config.anthropic_api_key
        return self._api_key

    def _ensure_client(self):
        """Lazily initialize the async Anthropic client."""
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError("anthropic package not installed. Run: pip install anthropic") from exc
        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError(
                "Anthropic API key not configured. " "Set ANTHROPIC_API_KEY or provide api_key in provider settings."
            )
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        return self._client

    def _split_messages(self, messages: list) -> tuple[str, list]:
        """Separate the optional system message from conversational messages."""
        system_content = ""
        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                chat_messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
        return system_content, chat_messages

    def _build_request_kwargs(self, model: str, request: LLMRequest) -> tuple[Dict[str, Any], Dict[str, Any], bool]:
        """Build kwargs and extra_headers for an Anthropic SDK call."""
        system_content, chat_messages = self._split_messages(request.messages)
        kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens or 4096,
            "messages": chat_messages,
            "temperature": request.temperature,
        }
        if system_content:
            # Prompt caching (#8171): when enable_prompt_cache=True is set in
            # request metadata the system message is sent as a content-block
            # list so Anthropic can cache it across repeated requests.
            if request.metadata.get("enable_prompt_cache"):
                kwargs["system"] = [{"type": "text", "text": system_content, "cache_control": {"type": "ephemeral"}}]
            else:
                kwargs["system"] = system_content

        if request.tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in request.tools
            ]
            if request.tool_choice:
                kwargs["tool_choice"] = {"type": request.tool_choice}

        api_kwargs: Dict[str, Any] = request.metadata.get("api_kwargs") or {}
        preserve_reasoning: bool = bool(api_kwargs.get("preserve_reasoning", False))
        kwargs, extra_headers = _build_api_kwargs(kwargs, api_kwargs)

        # The Anthropic API requires temperature=1 when extended thinking is enabled.
        if "thinking" in api_kwargs:
            kwargs["temperature"] = 1

        return kwargs, extra_headers, preserve_reasoning

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion via Anthropic.

        Supports extended thinking when ``request.metadata["api_kwargs"]``
        contains a ``thinking`` key.
        """
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._get_setting("default_model", ANTHROPIC_CLAUDE_SONNET4_6)
        try:
            client = self._ensure_client()
            kwargs, extra_headers, preserve_reasoning = self._build_request_kwargs(model, request)

            call_kwargs: Dict[str, Any] = dict(kwargs)
            if extra_headers:
                call_kwargs["extra_headers"] = extra_headers
            call_kwargs = sorted_for_cache(call_kwargs)

            response = await client.messages.create(**call_kwargs)
            content = _extract_text_content(response.content, preserve_reasoning)
            total_tokens = response.usage.input_tokens + response.usage.output_tokens
            processing_time = time.time() - start

            tool_calls = []
            for block in response.content:
                if getattr(block, "type", None) == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input if isinstance(block.input, dict) else {},
                        )
                    )
            finish_reason = "tool_calls" if tool_calls else response.stop_reason

            # MVA-3089: Extract thinking metadata from Anthropic response
            usage_dict = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": total_tokens,
            }
            output_details = getattr(response.usage, "output_tokens_details", None)
            if output_details:
                thinking_tokens = getattr(output_details, "thinking_tokens", None)
                if thinking_tokens is not None and thinking_tokens > 0:
                    usage_dict["thinking_tokens"] = thinking_tokens

            return LLMResponse(
                content=content,
                model=response.model,
                provider=self.provider_name,
                processing_time=processing_time,
                request_id=request.request_id,
                finish_reason=finish_reason,
                usage=usage_dict,
                tool_calls=tool_calls or None,
                provider_metadata=self._build_provider_metadata(
                    model_api_name=response.model,
                    api_kwargs_applied=call_kwargs,
                    total_tokens=total_tokens,
                ),
            )
        except Exception as exc:
            self._total_errors += 1
            logger.error("Anthropic chat_completion error: %s", exc)
            return LLMResponse(
                content="",
                model=model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                error=str(exc),
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a chat completion from Anthropic, yielding text chunks.

        Supports extended thinking when ``request.metadata["api_kwargs"]``
        contains a ``thinking`` key.  Thinking blocks are not yielded.
        """
        self._total_requests += 1
        model = request.model_name or self._get_setting("default_model", ANTHROPIC_CLAUDE_SONNET4_6)
        try:
            client = self._ensure_client()
            kwargs, extra_headers, _preserve = self._build_request_kwargs(model, request)

            call_kwargs: Dict[str, Any] = dict(kwargs)
            if extra_headers:
                call_kwargs["extra_headers"] = extra_headers
            call_kwargs = sorted_for_cache(call_kwargs)

            async with client.messages.stream(**call_kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            self._total_errors += 1
            logger.error("Anthropic stream_completion error: %s", exc)
            raise

    async def is_available(self) -> bool:
        """Return True if the API key is set and the token-count endpoint responds."""
        try:
            client = self._ensure_client()
            await client.messages.count_tokens(
                model="claude-haiku-4-5-20251001",
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """Return known Anthropic models (static — no discovery endpoint)."""
        return list(_ANTHROPIC_MODELS)


__all__ = [
    "AnthropicProvider",
    "_ANTHROPIC_MODELS",
    "_build_api_kwargs",
    "_extract_text_content",
    "_strip_think_blocks",
]
