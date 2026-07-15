# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared base for providers speaking the OpenAI chat-completions dialect (#11517).

OpenAI, Groq, OpenRouter, CustomOpenAI, and NousPortal all speak the same
OpenAI-compatible Chat Completions API.  The request-building,
response-mapping, tool-call parsing, streaming, and model-listing flow lives
here exactly once; concrete subclasses supply only their genuine deltas:
client construction, credential/base-url resolution, default model, static
fallback model list, and provider-specific params.

Circuit-breaker protection lives in ``BaseProvider._guarded_completion``
(GH#11488) — ``_chat_completion_impl`` must not raise; errors travel via
``LLMResponse.error`` so the registry can perform fallback.
"""

from __future__ import annotations

import json
import time
from typing import Any, AsyncIterator, Dict, List, Sequence

from autobot_shared.logging_manager import get_logger
from llm_shared.models import LLMRequest, LLMResponse, ToolCall

from ..base_provider import BaseProvider
from .cache_utils import sorted_for_cache

logger = get_logger(__name__)


class OpenAICompatibleProvider(BaseProvider):
    """
    Base implementation for any OpenAI-compatible chat-completions provider.

    Subclasses set the class attributes below and override the hook methods
    (``_resolve_api_key`` / ``_resolve_base_url`` / ``_create_client`` /
    ``_extra_params`` / ``_fallback_model_list``) only where their behavior
    genuinely differs from the shared flow.
    """

    #: Default model used when neither the request nor settings specify one.
    default_model: str = ""
    #: Static model list returned when the live models endpoint is unreachable.
    fallback_models: Sequence[str] = ()
    #: Whether ``top_p`` is forwarded to the API (Groq historically omits it).
    include_top_p: bool = True
    #: Whether payloads are normalised for prompt-cache determinism (#7368).
    sort_params_for_cache: bool = False
    #: Default ``max_tokens`` applied when the request does not set one.
    default_max_tokens: int | None = None
    #: Forward presence/frequency penalties supplied via ``metadata["api_kwargs"]``
    #: (historically honoured by OpenRouter and NousPortal only).
    forward_penalty_params: bool = False
    #: Error message raised when no API key can be resolved.
    missing_key_error: str = "API key not configured. Provide api_key in provider settings."

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._client = None

    # ------------------------------------------------------------------
    # Subclass hooks — override only genuine per-provider deltas
    # ------------------------------------------------------------------

    def _resolve_api_key(self) -> str | None:
        """Resolve the API key (subclasses add their config fallback chain)."""
        if self._api_key:
            return self._api_key
        self._api_key = self._get_setting("api_key")
        return self._api_key

    def _resolve_base_url(self) -> str | None:
        """Resolve the endpoint base URL, or None for the SDK default."""
        return self._get_setting("base_url")

    def _extra_params(self, request: LLMRequest) -> Dict[str, Any]:
        """Provider-specific params merged into the payload (e.g. #9017)."""
        return {}

    def _create_client(self):
        """Construct the async SDK client (Groq swaps in its own SDK)."""
        try:
            import openai
        except ImportError as exc:
            raise ImportError("openai package not installed. Run: pip install openai") from exc
        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError(self.missing_key_error)
        kwargs: Dict[str, Any] = {"api_key": api_key}
        base_url = self._resolve_base_url()
        if base_url:
            kwargs["base_url"] = base_url
        return openai.AsyncOpenAI(**kwargs)

    def _fallback_model_list(self) -> List[str]:
        """Models reported when the live listing fails or comes back empty."""
        if self.fallback_models:
            return list(self.fallback_models)
        configured = self._default_model_name()
        return [configured] if configured else []

    # ------------------------------------------------------------------
    # Shared flow
    # ------------------------------------------------------------------

    def _default_model_name(self) -> str:
        """Return the settings-configured default model, else the class default."""
        return self._get_setting("default_model", self.default_model)

    def _ensure_client(self):
        """Lazily initialize and cache the async client."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _build_params(self, request: LLMRequest, model: str) -> Dict[str, Any]:
        """Build the chat-completions payload from an LLMRequest."""
        params: Dict[str, Any] = {
            "model": model,
            "messages": request.messages,
            "temperature": request.temperature,
        }
        if self.include_top_p:
            params["top_p"] = request.top_p
        max_tokens = request.max_tokens or self.default_max_tokens
        if max_tokens:
            params["max_tokens"] = max_tokens
        if request.stop:
            params["stop"] = request.stop
        if request.tools:
            params["tools"] = self._tools_payload(request)
            if request.tool_choice:
                params["tool_choice"] = request.tool_choice
        if self.forward_penalty_params:
            api_kwargs: Dict[str, Any] = request.metadata.get("api_kwargs") or {}
            for key in ("presence_penalty", "frequency_penalty"):
                if key in api_kwargs:
                    params[key] = api_kwargs[key]
        extra = self._extra_params(request)
        if extra:
            params.update(extra)
        if self.sort_params_for_cache:
            params = sorted_for_cache(params)
        return params

    @staticmethod
    def _tools_payload(request: LLMRequest) -> List[Dict[str, Any]]:
        """Map ToolDefinition objects to OpenAI function-tool dicts."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in request.tools
        ]

    @staticmethod
    def _parse_tool_calls(message: Any) -> List[ToolCall]:
        """Parse SDK tool calls, falling back to ``{}`` on malformed JSON args."""
        calls: List[ToolCall] = []
        if not getattr(message, "tool_calls", None):
            return calls
        for tc in message.tool_calls:
            try:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except Exception:
                args = {}
            calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return calls

    def _build_response(
        self,
        request: LLMRequest,
        response: Any,
        params: Dict[str, Any],
        start: float,
    ) -> LLMResponse:
        """Map an SDK chat-completions response onto the shared LLMResponse."""
        choice = response.choices[0]
        usage = response.usage
        api_model = response.model or params["model"]
        total_tokens = usage.total_tokens if usage else 0
        tool_calls = self._parse_tool_calls(choice.message)
        # #10582: reasoning/thinking text surfaced by o1/o3, DeepSeek-R1, QwQ,
        # SGLang, and similar OpenAI-compat servers.
        reasoning_content: str | None = getattr(choice.message, "reasoning_content", None) or None
        return LLMResponse(
            content=choice.message.content or "",
            model=api_model,
            provider=self.provider_name,
            processing_time=time.time() - start,
            request_id=request.request_id,
            finish_reason=choice.finish_reason,
            usage={
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "total_tokens": total_tokens,
            },
            tool_calls=tool_calls or None,
            provider_metadata=self._build_provider_metadata(
                model_api_name=api_model,
                api_kwargs_applied=params,
                total_tokens=total_tokens,
            ),
            reasoning_content=reasoning_content,
        )

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion.

        Must not raise — errors are returned via ``LLMResponse.error`` so the
        registry can fall back; circuit-breaker accounting happens in
        ``BaseProvider._guarded_completion`` (GH#11488).
        """
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._default_model_name()
        try:
            client = self._ensure_client()
            params = self._build_params(request, model)
            response = await client.chat.completions.create(**params)
            return self._build_response(request, response, params, start)
        except Exception as exc:
            self._total_errors += 1
            logger.error("%s chat_completion error: %s", self.provider_name, exc)
            return LLMResponse(
                content="",
                model=model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                error=str(exc),
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a chat completion, yielding text chunks as they arrive."""
        self._total_requests += 1
        model = request.model_name or self._default_model_name()
        try:
            client = self._ensure_client()
            params = self._build_params(request, model)
            params["stream"] = True
            stream = await client.chat.completions.create(**params)
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            self._total_errors += 1
            logger.error("%s stream_completion error: %s", self.provider_name, exc)
            raise

    async def is_available(self) -> bool:
        """Return True if credentials resolve and the models endpoint responds."""
        try:
            client = self._ensure_client()
            await client.models.list()
            return True
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """Return live models, falling back to the provider's static list."""
        try:
            client = self._ensure_client()
            model_list = await client.models.list()
            models = [m.id for m in (model_list.data or [])]
            return models or self._fallback_model_list()
        except Exception:
            return self._fallback_model_list()


__all__ = ["OpenAICompatibleProvider"]
