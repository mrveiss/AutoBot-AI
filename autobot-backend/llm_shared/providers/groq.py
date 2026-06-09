# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Groq provider for the multi-provider LLM layer (#4096).

Groq exposes an OpenAI-compatible Chat Completions API so this implementation
delegates directly to the ``groq`` SDK (which mirrors the ``openai`` SDK
surface).  The local ``groq`` package is imported lazily so the rest of the
application boots normally when the package is absent.

API key is read (in priority order) from:
  1. ``settings["api_key"]``
  2. Environment variable ``GROQ_API_KEY``

API keys are never logged.

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
"""

from __future__ import annotations

import time
from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.model_constants import (
    GROQ_GEMMA2_9B,
    GROQ_LLAMA3_8B,
    GROQ_LLAMA3_70B,
    GROQ_LLAMA31_8B,
    GROQ_LLAMA33_70B,
    GROQ_MIXTRAL_8X7B,
)
from llm_shared.models import LLMRequest, LLMResponse, ToolCall
from llm_shared.types import ProviderType

from ..base_provider import BaseProvider

logger = get_logger(__name__)

GROQ_MODELS: List[str] = [
    GROQ_LLAMA33_70B,
    GROQ_LLAMA3_70B,
    GROQ_LLAMA31_8B,
    GROQ_LLAMA3_8B,
    GROQ_MIXTRAL_8X7B,
    GROQ_GEMMA2_9B,
]

_DEFAULT_MODEL = GROQ_LLAMA31_8B


class GroqProvider(BaseProvider):
    """
    Groq LLM provider implementation.

    Supports chat completion and streaming for Llama, Mixtral, and Gemma
    model families hosted on Groq's ultra-low-latency inference API.
    Requires the ``groq`` package (``pip install groq``).
    """

    provider_name = ProviderType.GROQ.value

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self._api_key: str | None = None
        self._client = None

    def _resolve_api_key(self) -> str | None:
        """Resolve API key from settings or environment."""
        if self._api_key:
            return self._api_key
        self._api_key = self._get_setting("api_key") or config.groq_api_key
        return self._api_key

    def _ensure_client(self):
        """Lazily initialize the async Groq client."""
        if self._client is not None:
            return self._client
        try:
            import groq
        except ImportError as exc:
            raise ImportError("groq package not installed. Run: pip install groq") from exc
        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError(
                "Groq API key not configured. " "Set GROQ_API_KEY or provide api_key in provider settings."
            )
        self._client = groq.AsyncGroq(api_key=api_key)
        return self._client

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion via Groq."""
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._get_setting("default_model", _DEFAULT_MODEL)
        try:
            client = self._ensure_client()
            params: Dict[str, Any] = {
                "model": model,
                "messages": request.messages,
                "temperature": request.temperature,
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
            logger.error("Groq chat_completion error: %s", exc)
            return LLMResponse(
                content="",
                model=model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                error=str(exc),
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a chat completion from Groq, yielding text chunks."""
        self._total_requests += 1
        model = request.model_name or self._get_setting("default_model", _DEFAULT_MODEL)
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
            stream = await client.chat.completions.create(**params)
            async for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            self._total_errors += 1
            logger.error("Groq stream_completion error: %s", exc)
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
        """Return available Groq models, falling back to the static list."""
        try:
            client = self._ensure_client()
            model_list = await client.models.list()
            return [m.id for m in model_list.data]
        except Exception:
            return list(GROQ_MODELS)


__all__ = ["GroqProvider", "GROQ_MODELS"]
