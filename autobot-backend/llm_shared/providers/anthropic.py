# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from typing import Any, AsyncIterator, Dict, List, Optional

from autobot_shared.logging_manager import get_logger

# ---------------------------------------------------------------------------
# Adapter helpers — lazy so tests that don't boot the full app still work.
# ---------------------------------------------------------------------------


def _get_adapter_sync():
    """Return the live AutoBotClaudeAPIAdapter singleton without awaiting init.

    Returns None if the module has not been imported yet or the instance is
    absent.  Callers must handle None gracefully (fail-safe path).
    """
    try:
        from utils.claude_api_integration import AutoBotClaudeAPIAdapter

        return AutoBotClaudeAPIAdapter._instance
    except Exception:
        return None


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


def _extract_think_tag_content(text: str) -> Optional[str]:
    """Return the concatenated inner text of all ``<think>…</think>`` blocks, or None."""
    matches = _THINK_BLOCK_RE.findall(text)
    if not matches:
        return None
    # findall returns the full match including tags; strip the wrapper.
    inner_re = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
    parts = inner_re.findall(text)
    return "\n".join(p.strip() for p in parts if p.strip()) or None


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
    text, _ = _extract_content_pair(response_content, preserve_reasoning)
    return text


def _extract_content_pair(
    response_content: list, preserve_reasoning: bool
) -> tuple[str, Optional[str]]:
    """
    Extract ``(content, reasoning_content)`` from an Anthropic response block list.

    *content* has thinking blocks removed (or ``<think>`` tags stripped unless
    *preserve_reasoning* is True).  *reasoning_content* contains the captured
    reasoning text from native ``thinking`` blocks and ``<think>`` tags, or
    ``None`` if none were present.
    """
    reasoning_parts: List[str] = []
    text_parts: List[str] = []

    for block in response_content:
        block_type = getattr(block, "type", None)
        if block_type == "thinking":
            thinking_text = getattr(block, "thinking", None) or getattr(block, "text", None)
            if thinking_text:
                reasoning_parts.append(thinking_text.strip())
            continue
        text = getattr(block, "text", None)
        if text:
            text_parts.append(text)

    joined = "\n".join(text_parts)
    if preserve_reasoning:
        content = joined
    else:
        # Capture any <think> tags from the text blocks before stripping them.
        tag_reasoning = _extract_think_tag_content(joined)
        if tag_reasoning:
            reasoning_parts.append(tag_reasoning)
        content = _strip_think_blocks(joined)

    reasoning_content: Optional[str] = "\n".join(reasoning_parts) if reasoning_parts else None
    return content, reasoning_content


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
            # Prompt caching (#8171, #10597): the system message is sent as a
            # content-block list so Anthropic can cache it across repeated
            # requests.  Defaults on via config.llm_prompt_cache_default (pure
            # cost win on the large static system prompt); a caller may still
            # opt out per-request with enable_prompt_cache=False.
            if request.metadata.get("enable_prompt_cache", config.llm_prompt_cache_default):
                kwargs["system"] = [{"type": "text", "text": system_content, "cache_control": {"type": "ephemeral"}}]
            else:
                kwargs["system"] = system_content

        if request.tools:
            kwargs["tools"] = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in request.tools
            ]
            if request.tool_choice:
                kwargs["tool_choice"] = {"type": request.tool_choice}

        api_kwargs: Dict[str, Any] = dict(request.metadata.get("api_kwargs") or {})
        # #9017: expand thinking_tokens (from reasoning_effort mapping) into the
        # Anthropic extended-thinking dict if not already fully specified.
        thinking_tokens: int | None = api_kwargs.pop("thinking_tokens", None)
        if thinking_tokens and "thinking" not in api_kwargs:
            api_kwargs["thinking"] = {"type": "enabled", "budget_tokens": thinking_tokens}
            api_kwargs.setdefault("max_tokens", max(thinking_tokens + 1000, 8192))
            api_kwargs.setdefault("betas", ["interleaved-thinking-2025-05-14"])
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

        Issue #10849: outbound payload is routed through the AutoBotClaudeAPIAdapter
        pre-send pipeline (rate-limit check, payload optimization, metric recording)
        before being dispatched to the Anthropic API.  The adapter is accessed via
        its module-level singleton; when absent the call proceeds unchanged (fail-safe).
        """
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._get_setting("default_model", ANTHROPIC_CLAUDE_SONNET4_6)

        # --- Adapter pre-send: rate-limit + payload optimization (#10849) ----------
        # Serialize the user-visible content for the adapter pipeline.
        # The adapter operates on the text content; the full structured payload
        # (tools, extra_headers, etc.) flows unchanged to the Anthropic SDK.
        _adapter = _get_adapter_sync()
        _context_type: str = request.llm_type.value if hasattr(request.llm_type, "value") else "general"
        if _adapter is not None and _adapter.is_initialized:
            try:
                _raw_content = " ".join(m.get("content", "") for m in request.messages if isinstance(m, dict))
                await _adapter.optimize_for_send(
                    content=_raw_content,
                    context_type=_context_type,
                )
            except Exception as _adapt_err:
                logger.debug(
                    "Claude adapter pre-send optimization skipped (fail-safe): %s",
                    _adapt_err,
                )
        # --------------------------------------------------------------------------

        try:
            client = self._ensure_client()
            kwargs, extra_headers, preserve_reasoning = self._build_request_kwargs(model, request)

            call_kwargs: Dict[str, Any] = dict(kwargs)
            if extra_headers:
                call_kwargs["extra_headers"] = extra_headers
            call_kwargs = sorted_for_cache(call_kwargs)

            response = await client.messages.create(**call_kwargs)
            content, reasoning_content = _extract_content_pair(response.content, preserve_reasoning)
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

            llm_response = LLMResponse(
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
                reasoning_content=reasoning_content,
            )
            # --- Adapter post-send: metric recording (#10849) ---------------------
            if _adapter is not None and _adapter.is_initialized:
                try:
                    _raw_len = sum(len(m.get("content", "")) for m in request.messages if isinstance(m, dict))
                    await _adapter.record_send_result(
                        context_type=_context_type,
                        content_len=_raw_len,
                        response_time=processing_time,
                        success=True,
                    )
                except Exception as _rec_err:
                    logger.debug("Claude adapter post-send record skipped: %s", _rec_err)
            # ----------------------------------------------------------------------
            return llm_response
        except Exception as exc:
            self._total_errors += 1
            logger.error("Anthropic chat_completion error: %s", exc)
            processing_time = time.time() - start
            # --- Adapter post-send: error metric recording (#10849) ---------------
            if _adapter is not None and _adapter.is_initialized:
                try:
                    await _adapter.record_send_result(
                        context_type=_context_type,
                        content_len=sum(len(m.get("content", "")) for m in request.messages if isinstance(m, dict)),
                        response_time=processing_time,
                        success=False,
                        error_message=str(exc),
                    )
                except Exception as _rec_err:
                    logger.debug("Claude adapter post-send error record skipped: %s", _rec_err)
            # ----------------------------------------------------------------------
            return LLMResponse(
                content="",
                model=model,
                provider=self.provider_name,
                processing_time=processing_time,
                request_id=request.request_id,
                error=str(exc),
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a chat completion from Anthropic, yielding text chunks.

        Supports extended thinking when ``request.metadata["api_kwargs"]``
        contains a ``thinking`` key.  Thinking blocks are not yielded.

        Issue #10849: applies adapter pre-send optimization (rate-limit check,
        payload optimization) before streaming begins.  Post-send metric recording
        is not applied per-chunk; the adapter records the stream open as a single
        individual request.  Streaming cannot be routed through submit_request()
        which is non-streaming by design.
        """
        self._total_requests += 1
        model = request.model_name or self._get_setting("default_model", ANTHROPIC_CLAUDE_SONNET4_6)

        # --- Adapter pre-send: rate-limit + payload optimization (#10849) ----------
        _stream_adapter = _get_adapter_sync()
        _stream_context_type = request.llm_type.value if hasattr(request.llm_type, "value") else "general"
        if _stream_adapter is not None and _stream_adapter.is_initialized:
            try:
                _stream_raw = " ".join(m.get("content", "") for m in request.messages if isinstance(m, dict))
                await _stream_adapter.optimize_for_send(
                    content=_stream_raw,
                    context_type=_stream_context_type,
                )
            except Exception as _sadapt_err:
                logger.debug(
                    "Claude adapter stream pre-send optimization skipped (fail-safe): %s",
                    _sadapt_err,
                )
        # --------------------------------------------------------------------------

        _stream_start = time.time()
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

            # --- Adapter post-send: success metric (#10849) -----------------------
            if _stream_adapter is not None and _stream_adapter.is_initialized:
                try:
                    await _stream_adapter.record_send_result(
                        context_type=_stream_context_type,
                        content_len=sum(len(m.get("content", "")) for m in request.messages if isinstance(m, dict)),
                        response_time=time.time() - _stream_start,
                        success=True,
                    )
                except Exception as _srec_err:
                    logger.debug("Claude adapter stream post-send record skipped: %s", _srec_err)
            # ----------------------------------------------------------------------
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
    "_extract_content_pair",
    "_extract_text_content",
    "_extract_think_tag_content",
    "_strip_think_blocks",
]
