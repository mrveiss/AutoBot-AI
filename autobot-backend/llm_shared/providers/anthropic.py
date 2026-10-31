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
          "extra_headers": {"anthropic-beta": "output-128k-2025-02-19"},
      }

  Thinking blocks are stripped from the returned ``content`` unless
  ``preserve_reasoning=True`` is present in ``api_kwargs``.

Sampling parameters (#15016):
  ``anthropic>=1.0`` dropped ``temperature``/``top_p``/``top_k`` from the
  ``messages.create()``/``.stream()`` signature (passing one is now a
  client-side ``TypeError``). ``_route_sampling_kwargs`` moves a genuinely
  set value into ``extra_body``, which the API still honours for every
  model this codebase targets, instead of passing it as a keyword; the old
  "thinking implies temperature=1" compensation is gone outright since
  current models reject a ``temperature`` kwarg regardless of its value.

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


async def _apply_adapter_pre_send(request: LLMRequest, context_type: str) -> None:
    """Route the outbound payload through the adapter's structured pre-send hook.

    Issue #10849 added the hook; Issue #10945 switched it from the flat-string
    ``optimize_for_send`` (whose optimized result was discarded) to the
    structured ``optimize_request``, which mutates ``request.messages`` in
    place so payload-mutation and batching machinery actually reach the
    payload sent to the Anthropic API. Fail-safe: adapter absent, not
    initialized, or raising leaves ``request`` unchanged.
    """
    adapter = _get_adapter_sync()
    if adapter is None or not adapter.is_initialized:
        return
    try:
        await adapter.optimize_request(request, context_type=context_type)
    except Exception as exc:
        logger.debug("Claude adapter pre-send optimization skipped (fail-safe): %s", exc)


from autobot_shared.ssot_config import config
from autobot_shared.ssot_hosted_models import hosted_default_model
from constants.model_constants import (
    ANTHROPIC_CLAUDE3_OPUS_DATED,
    ANTHROPIC_CLAUDE35_HAIKU,
    ANTHROPIC_CLAUDE_HAIKU4_5,
    ANTHROPIC_CLAUDE_OPUS4_6,
    ANTHROPIC_CLAUDE_SONNET4,
    ANTHROPIC_CLAUDE_SONNET4_6,
)
from llm_shared.models import LLMRequest, LLMResponse, ToolCall
from llm_shared.structured_output import StructuredOutputMode, apply_anthropic_output_config
from llm_shared.types import ProviderType
from services.provider_key_vault import resolve_provider_key

from ..base_provider import BaseProvider
from .anthropic_format import split_system_and_chat

# Re-exported: the request-shaping unit moved to anthropic_request.py when this
# file hit its size ceiling (#17305). `_thinking_budget_to_effort` is unused here
# and kept importable for tests/llm_interface_pkg/test_anthropic_sampling_kwargs.py.
from .anthropic_request import (  # noqa: F401
    _REMOVED_SAMPLING_KWARGS,
    _apply_thinking_budget,
    _build_api_kwargs,
    _route_sampling_kwargs,
    _thinking_budget_to_effort,
)
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


def _extract_text_content(response_content: list, preserve_reasoning: bool) -> str:
    """
    Extract the text from an Anthropic response content block list.

    When *preserve_reasoning* is False (default) ``<think>…</think>`` wrapper
    blocks written by the model are stripped before returning.
    """
    text, _ = _extract_content_pair(response_content, preserve_reasoning)
    return text


def _tool_calls_from(response_content: list) -> list:
    """The ``tool_use`` blocks of an Anthropic response as ToolCalls (from _chat_completion_impl)."""
    return [
        ToolCall(id=block.id, name=block.name, arguments=block.input if isinstance(block.input, dict) else {})
        for block in response_content
        if getattr(block, "type", None) == "tool_use"
    ]


def _usage_from(usage: Any, total_tokens: int) -> Dict[str, Any]:
    """Token usage, with thinking tokens when the response reports them (MVA-3089)."""
    usage_dict: Dict[str, Any] = {
        "prompt_tokens": usage.input_tokens,
        "completion_tokens": usage.output_tokens,
        "total_tokens": total_tokens,
    }
    output_details = getattr(usage, "output_tokens_details", None)
    thinking_tokens = getattr(output_details, "thinking_tokens", None) if output_details else None
    if thinking_tokens is not None and thinking_tokens > 0:
        usage_dict["thinking_tokens"] = thinking_tokens
    return usage_dict


async def _record_adapter_send(
    adapter: Any, context_type: str, request: LLMRequest, response_time: float, error: str | None = None
) -> None:
    """Adapter post-send metric recording (#10849); best-effort, never raises."""
    if adapter is None or not adapter.is_initialized:
        return
    outcome: Dict[str, Any] = {"success": error is None}
    if error is not None:
        outcome["error_message"] = error
    try:
        await adapter.record_send_result(
            context_type=context_type,
            content_len=sum(len(m.get("content", "")) for m in request.messages if isinstance(m, dict)),
            response_time=response_time,
            **outcome,
        )
    except Exception as rec_err:
        logger.debug("Claude adapter post-send record skipped: %s", rec_err)


def _extract_content_pair(response_content: list, preserve_reasoning: bool) -> tuple[str, Optional[str]]:
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
    # #17305: `output_config.format` enforces a supplied JSON Schema; it has
    # no schema-less variant, so a bare flag maps to nothing native here.
    structured_output_mode = StructuredOutputMode.JSON_SCHEMA
    structured_output_requires_schema = True

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self._api_key: str | None = None
        self._client = None
        self._oauth_client = None  # #19241: base client for signed-in tokens

    def _resolve_api_key(self) -> str | None:
        """Resolve API key from settings or environment."""
        if self._api_key:
            return self._api_key
        self._api_key = self._get_setting("api_key") or resolve_provider_key(
            "ANTHROPIC_API_KEY", config.anthropic_api_key
        )
        return self._api_key

    def _ensure_client(self):
        """Lazily initialize the async Anthropic client."""
        if self._client is not None:
            return self._client
        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError(
                "Anthropic API key not configured. " "Set ANTHROPIC_API_KEY or provide api_key in provider settings."
            )
        self._client = self._new_client(api_key=api_key)
        return self._client

    def _new_client(self, **credential: str):
        """An ``AsyncAnthropic`` for one credential: ``api_key=`` or a signed-in ``auth_token=`` (#19241)."""
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError("anthropic package not installed. Run: pip install anthropic") from exc
        kwargs: Dict[str, Any] = dict(credential)
        http_client = self._headroom_http_client(getattr(anthropic, "DefaultAsyncHttpxClient", None))
        if http_client is not None:
            kwargs["http_client"] = http_client  # #15026: harvest rate-limit headers
        return anthropic.AsyncAnthropic(**kwargs)

    async def _request_client(self):
        """The client for this call: a signed-in bearer token when there is one, else the API key (#19241).

        An explicit ``auth_token`` stops the SDK reading ANTHROPIC_API_KEY, so the
        request carries the bearer only; copies share the base client's pool.
        """
        token = await self._signed_in_token()
        if not token:
            return self._ensure_client()
        if self._oauth_client is None:
            self._oauth_client = self._new_client(auth_token=token)
        return self._oauth_client.with_options(auth_token=token)

    def _apply_system_content(self, kwargs: Dict[str, Any], request: LLMRequest, system_content: str) -> None:
        """Set ``kwargs["system"]``, in place. Prompt caching (#8171, #10597):

        the system message is sent as a content-block list so Anthropic can
        cache it across repeated requests. Defaults on via
        config.llm_prompt_cache_default (pure cost win on the large static
        system prompt); a caller may opt out per-request with
        enable_prompt_cache=False.
        """
        if not system_content:
            return
        if request.metadata.get("enable_prompt_cache", config.llm_prompt_cache_default):
            kwargs["system"] = [{"type": "text", "text": system_content, "cache_control": {"type": "ephemeral"}}]
        else:
            kwargs["system"] = system_content

    def _apply_tools(self, kwargs: Dict[str, Any], request: LLMRequest) -> None:
        """Set ``kwargs["tools"]``/``["tool_choice"]`` from *request*, in place."""
        if not request.tools:
            return
        kwargs["tools"] = [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema} for t in request.tools
        ]
        if request.tool_choice:
            kwargs["tool_choice"] = {"type": request.tool_choice}

    def _build_request_kwargs(self, model: str, request: LLMRequest) -> tuple[Dict[str, Any], Dict[str, Any], bool]:
        """Build kwargs and extra_headers for an Anthropic SDK call."""
        system_content, chat_messages = split_system_and_chat(request.messages)
        kwargs: Dict[str, Any] = {
            "model": model,
            "max_tokens": request.max_tokens or 4096,
            "messages": chat_messages,
            "temperature": request.temperature,
        }
        self._apply_system_content(kwargs, request, system_content)
        self._apply_tools(kwargs, request)

        api_kwargs: Dict[str, Any] = dict(request.metadata.get("api_kwargs") or {})
        # #9017: expand thinking_tokens (from reasoning_effort mapping) into the
        # Anthropic extended-thinking dict if not already fully specified.
        thinking_tokens: int | None = api_kwargs.pop("thinking_tokens", None)
        if thinking_tokens and "thinking" not in api_kwargs:
            _apply_thinking_budget(api_kwargs, model, thinking_tokens)
        preserve_reasoning: bool = bool(api_kwargs.get("preserve_reasoning", False))
        kwargs, extra_headers = _build_api_kwargs(kwargs, api_kwargs)
        kwargs = _route_sampling_kwargs(kwargs)
        # #17305: after the api_kwargs merge, so an `effort` tier already in
        # `output_config` survives and the format is added beside it.
        apply_anthropic_output_config(kwargs, request)

        return kwargs, extra_headers, preserve_reasoning

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion via Anthropic.

        Supports extended thinking when ``request.metadata["api_kwargs"]``
        contains a ``thinking`` key.

        Issue #10849: outbound payload is routed through the AutoBotClaudeAPIAdapter
        pre-send pipeline (rate-limit check, payload optimization, metric recording)
        before being dispatched to the Anthropic API.  The adapter is accessed via
        its module-level singleton; when absent the call proceeds unchanged (fail-safe).
        Issue #10945: the pre-send hook now mutates ``request.messages`` through the
        structured ``optimize_request`` path, so payload optimization actually
        reaches the messages sent below (previously the optimized string was
        computed and discarded).
        """
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._get_setting("default_model", hosted_default_model("anthropic"))

        _adapter = _get_adapter_sync()
        _context_type: str = request.llm_type.value if hasattr(request.llm_type, "value") else "general"
        await _apply_adapter_pre_send(request, _context_type)

        try:
            client = await self._request_client()
            kwargs, extra_headers, preserve_reasoning = self._build_request_kwargs(model, request)

            call_kwargs: Dict[str, Any] = dict(kwargs)
            if extra_headers:
                call_kwargs["extra_headers"] = extra_headers
            call_kwargs = sorted_for_cache(call_kwargs)

            response = await client.messages.create(**call_kwargs)
            content, reasoning_content = _extract_content_pair(response.content, preserve_reasoning)
            total_tokens = response.usage.input_tokens + response.usage.output_tokens
            processing_time = time.time() - start

            tool_calls = _tool_calls_from(response.content)
            finish_reason = "tool_calls" if tool_calls else response.stop_reason
            usage_dict = _usage_from(response.usage, total_tokens)

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
            await _record_adapter_send(_adapter, _context_type, request, processing_time)
            return llm_response
        except Exception as exc:
            self._total_errors += 1
            logger.error("Anthropic chat_completion error: %s", exc)
            processing_time = time.time() - start
            await _record_adapter_send(_adapter, _context_type, request, processing_time, error=str(exc))
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
        Issue #10945: the pre-send hook mutates ``request.messages`` through the
        structured ``optimize_request`` path so optimization reaches the streamed
        payload instead of only computing (and discarding) an optimized string.
        """
        self._total_requests += 1
        model = request.model_name or self._get_setting("default_model", hosted_default_model("anthropic"))

        _stream_adapter = _get_adapter_sync()
        _stream_context_type = request.llm_type.value if hasattr(request.llm_type, "value") else "general"
        await _apply_adapter_pre_send(request, _stream_context_type)

        _stream_start = time.time()
        try:
            client = await self._request_client()
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
                model=hosted_default_model("anthropic", "light"),  # #15501: the cheap tier for a ping
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
    "_REMOVED_SAMPLING_KWARGS",
    "_build_api_kwargs",
    "_extract_content_pair",
    "_extract_text_content",
    "_extract_think_tag_content",
    "_route_sampling_kwargs",
    "_strip_think_blocks",
    "_thinking_budget_to_effort",
]
