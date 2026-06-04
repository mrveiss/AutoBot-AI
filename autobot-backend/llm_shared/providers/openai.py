# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
OpenAI provider for the multi-provider LLM layer (#1806).

Supports chat completion and streaming for all GPT/o1 model families.
API key is read (in priority order) from:
  1. ``settings["api_key"]``
  2. Environment variable ``OPENAI_API_KEY``
  3. ConfigManager (backward-compatible path)

API keys are never logged.

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from circuit_breaker import circuit_breaker_async
from constants.model_constants import OPENAI_O1_MINI  # used in _OPENAI_MODELS list
from constants.model_constants import (
    OPENAI_GPT4,
    OPENAI_GPT4_TURBO,
    OPENAI_GPT4O,
    OPENAI_GPT4O_MINI,
    OPENAI_GPT35_TURBO,
)
from llm_shared.models import LLMRequest, LLMResponse, ToolCall
from llm_shared.types import ProviderType

from ..base_provider import BaseProvider
from .cache_utils import sorted_for_cache

logger = get_logger(__name__)

_OPENAI_MODELS = [
    OPENAI_GPT4O,
    OPENAI_GPT4O_MINI,
    OPENAI_GPT4_TURBO,
    OPENAI_GPT4,
    OPENAI_GPT35_TURBO,
    "o1-preview",
    OPENAI_O1_MINI,
]


class OpenAIProvider(BaseProvider):
    """
    OpenAI provider implementation.

    Supports chat completion and streaming for all GPT/o1 model families.
    Requires the ``openai`` package (``pip install openai``).
    """

    provider_name = ProviderType.OPENAI.value

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._client = None

    def _resolve_api_key(self) -> str | None:
        """Resolve API key from settings, environment, or config."""
        if self._api_key:
            return self._api_key
        key = self._get_setting("api_key") or config.openai_api_key
        if not key:
            try:
                from autobot_shared.ssot_config import config as _ssot_config

                key = _ssot_config.llm.openai_api_key
            except Exception:
                pass
        self._api_key = key
        return self._api_key

    def _ensure_client(self):
        """Lazily initialize the async OpenAI client."""
        if self._client is not None:
            return self._client
        try:
            import openai
        except ImportError as exc:
            raise ImportError("openai package not installed. Run: pip install openai") from exc
        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError(
                "OpenAI API key not configured. " "Set OPENAI_API_KEY or provide api_key in provider settings."
            )
        base_url = self._get_setting("base_url") or config.openai_api_base_url
        kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.AsyncOpenAI(**kwargs)
        return self._client

    @circuit_breaker_async("openai_service")
    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion via OpenAI.

        Protected by the openai_service circuit breaker.  Errors are returned
        via ``LLMResponse.error`` so the registry can perform fallback.
        """
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._get_setting("default_model", OPENAI_GPT4O_MINI)
        try:
            client = self._ensure_client()
            params: Dict[str, Any] = {
                "model": model,
                "messages": request.messages,
                "temperature": request.temperature,
                "top_p": request.top_p,
            }
            if request.max_tokens:
                params["max_tokens"] = request.max_tokens
            if request.stop:
                params["stop"] = request.stop
            if request.tools:
                params["tools"] = [
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
                if request.tool_choice:
                    params["tool_choice"] = request.tool_choice
            params = sorted_for_cache(params)
            response = await client.chat.completions.create(**params)
            choice = response.choices[0]
            processing_time = time.time() - start
            tool_calls = []
            if choice.message.tool_calls:
                import json as _json

                for tc in choice.message.tool_calls:
                    try:
                        args = _json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except Exception:
                        args = {}
                    tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
            return LLMResponse(
                content=choice.message.content or "",
                model=response.model,
                provider=self.provider_name,
                processing_time=processing_time,
                request_id=request.request_id,
                finish_reason=choice.finish_reason,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
                tool_calls=tool_calls or None,
                provider_metadata=self._build_provider_metadata(
                    model_api_name=response.model,
                    api_kwargs_applied=params,
                    total_tokens=response.usage.total_tokens,
                ),
            )
        except Exception as exc:
            self._total_errors += 1
            logger.error("OpenAI chat_completion error: %s", exc)
            return LLMResponse(
                content="",
                model=model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                error=str(exc),
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a chat completion from OpenAI, yielding text chunks."""
        self._total_requests += 1
        model = request.model_name or self._get_setting("default_model", OPENAI_GPT4O_MINI)
        try:
            client = self._ensure_client()
            params: Dict[str, Any] = {
                "model": model,
                "messages": request.messages,
                "temperature": request.temperature,
                "stream": True,
            }
            if request.max_tokens:
                params["max_tokens"] = request.max_tokens
            params = sorted_for_cache(params)
            stream = await client.chat.completions.create(**params)
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            self._total_errors += 1
            logger.error("OpenAI stream_completion error: %s", exc)
            raise

    async def is_available(self) -> bool:
        """Return True if the API key is set and the models endpoint responds."""
        try:
            client = self._ensure_client()
            await client.models.list()
            return True
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """Return available OpenAI models, falling back to a static list."""
        try:
            client = self._ensure_client()
            model_list = await client.models.list()
            return [m.id for m in model_list.data]
        except Exception:
            return list(_OPENAI_MODELS)


__all__ = ["OpenAIProvider"]
