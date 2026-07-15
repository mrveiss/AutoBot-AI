# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Mistral provider for the multi-provider LLM layer (#10549).

Mistral (Le Chat / Codestral / Devstral) exposes an OpenAI-compatible Chat
Completions API at ``https://api.mistral.ai/v1`` so this implementation
delegates to the ``openai`` SDK pointed at that base URL — mirroring the
sibling Groq / OpenRouter providers rather than inventing a new pattern.
The ``openai`` package is imported lazily so the application boots normally
when it is absent.

API key is read (in priority order) from:
  1. ``settings["api_key"]``
  2. Environment variable ``MISTRAL_API_KEY`` (via ssot_config)

API keys are never logged. The provider is credential-gated: with no key it
reports ``is_available() is False`` instead of crashing.
"""

from __future__ import annotations

import json as _json
import time
from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.model_constants import (
    MISTRAL_CODESTRAL_LATEST,
    MISTRAL_DEVSTRAL_LATEST,
    MISTRAL_LARGE_LATEST,
    MISTRAL_MEDIUM_LATEST,
    MISTRAL_NEMO,
    MISTRAL_SMALL_LATEST,
)
from llm_shared.models import LLMRequest, LLMResponse, ToolCall
from llm_shared.types import ProviderType

from ..base_provider import BaseProvider

logger = get_logger(__name__)

MISTRAL_API_BASE_URL = "https://api.mistral.ai/v1"

MISTRAL_MODELS: List[str] = [
    MISTRAL_LARGE_LATEST,
    MISTRAL_MEDIUM_LATEST,
    MISTRAL_SMALL_LATEST,
    MISTRAL_CODESTRAL_LATEST,
    MISTRAL_DEVSTRAL_LATEST,
    MISTRAL_NEMO,
]

_DEFAULT_MODEL = MISTRAL_SMALL_LATEST


class MistralProvider(BaseProvider):
    """
    Mistral LLM provider implementation.

    Supports chat completion, streaming, and tool/function calling for the
    Mistral model family (mistral-large/-medium/-small, Codestral for code,
    Devstral, Nemo) via Mistral's OpenAI-compatible API.
    Requires the ``openai`` package (``pip install openai``).
    """

    provider_name = ProviderType.MISTRAL.value

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._client = None

    def _resolve_api_key(self) -> str | None:
        """Resolve API key from settings or environment."""
        if self._api_key:
            return self._api_key
        self._api_key = self._get_setting("api_key") or config.mistral_api_key
        return self._api_key

    def _resolve_base_url(self) -> str:
        """Resolve base URL, defaulting to the public Mistral endpoint."""
        if self._base_url:
            return self._base_url
        self._base_url = self._get_setting("base_url") or config.mistral_api_base_url or MISTRAL_API_BASE_URL
        return self._base_url

    def _ensure_client(self):
        """Lazily initialize the async OpenAI client aimed at Mistral."""
        if self._client is not None:
            return self._client
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("openai package not installed. Run: pip install openai") from exc
        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError(
                "Mistral API key not configured. Set MISTRAL_API_KEY or provide api_key in provider settings."
            )
        self._client = AsyncOpenAI(api_key=api_key, base_url=self._resolve_base_url())
        return self._client

    def _build_params(self, request: LLMRequest, model: str, *, stream: bool) -> Dict[str, Any]:
        """Assemble the kwargs sent to the OpenAI-compatible chat endpoint."""
        params: Dict[str, Any] = {
            "model": model,
            "messages": request.messages,
            "temperature": request.temperature,
        }
        if stream:
            params["stream"] = True
        if request.max_tokens:
            params["max_tokens"] = request.max_tokens
        if request.stop:
            params["stop"] = request.stop
        if not stream and request.tools:
            params["tools"] = [
                {
                    "type": "function",
                    "function": {"name": t.name, "description": t.description, "parameters": t.input_schema},
                }
                for t in request.tools
            ]
            if request.tool_choice:
                params["tool_choice"] = request.tool_choice
        return params

    @staticmethod
    def _parse_tool_calls(choice) -> List[ToolCall]:
        """Convert OpenAI-style tool_calls into shared ToolCall objects."""
        tool_calls: List[ToolCall] = []
        for tc in choice.message.tool_calls or []:
            try:
                args = _json.loads(tc.function.arguments) if tc.function.arguments else {}
            except Exception:
                args = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return tool_calls

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion via Mistral."""
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._get_setting("default_model", _DEFAULT_MODEL)
        try:
            client = self._ensure_client()
            params = self._build_params(request, model, stream=False)
            response = await client.chat.completions.create(**params)
            return self._build_response(request, response, params, start)
        except Exception as exc:
            self._total_errors += 1
            logger.error("Mistral chat_completion error: %s", exc)
            return LLMResponse(
                content="",
                model=model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                error=str(exc),
            )

    def _build_response(self, request: LLMRequest, response, params: Dict[str, Any], start: float) -> LLMResponse:
        """Map a successful API response onto the shared LLMResponse."""
        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
        }
        tool_calls = self._parse_tool_calls(choice)
        return LLMResponse(
            content=choice.message.content or "",
            model=response.model,
            provider=self.provider_name,
            processing_time=time.time() - start,
            request_id=request.request_id,
            finish_reason=choice.finish_reason,
            usage=usage,
            tool_calls=tool_calls or None,
            provider_metadata=self._build_provider_metadata(
                model_api_name=response.model,
                api_kwargs_applied=params,
                total_tokens=usage["total_tokens"],
            ),
        )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a chat completion from Mistral, yielding text chunks."""
        self._total_requests += 1
        model = request.model_name or self._get_setting("default_model", _DEFAULT_MODEL)
        try:
            client = self._ensure_client()
            params = self._build_params(request, model, stream=True)
            stream = await client.chat.completions.create(**params)
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            self._total_errors += 1
            logger.error("Mistral stream_completion error: %s", exc)
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
        """Return available Mistral models, falling back to the static list."""
        try:
            client = self._ensure_client()
            model_list = await client.models.list()
            return [m.id for m in model_list.data]
        except Exception:
            return list(MISTRAL_MODELS)


__all__ = ["MistralProvider", "MISTRAL_MODELS", "MISTRAL_API_BASE_URL"]
