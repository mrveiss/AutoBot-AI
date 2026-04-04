# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
OpenAI provider for the multi-provider LLM layer (#1806).

Wraps the existing llm_interface_pkg OpenAIProvider, adding streaming support
and conforming to the BaseProvider interface so the provider registry can
treat all providers uniformly.

API key is read (in priority order) from:
  1. ``settings["api_key"]``
  2. Environment variable ``OPENAI_API_KEY``
  3. ConfigManager (backward-compatible path)

API keys are never logged.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from llm_interface_pkg.models import LLMRequest, LLMResponse
from llm_interface_pkg.types import ProviderType

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

_OPENAI_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "o1-preview",
    "o1-mini",
]


class OpenAIProvider(BaseProvider):
    """
    OpenAI provider implementation.

    Supports chat completion and streaming for all GPT/o1 model families.
    Requires the ``openai`` package (``pip install openai``).
    """

    provider_name = ProviderType.OPENAI.value

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(settings)
        self._api_key: Optional[str] = None
        self._base_url: Optional[str] = None
        self._client = None

    def _resolve_api_key(self) -> Optional[str]:
        """Resolve API key from settings, environment, or config."""
        if self._api_key:
            return self._api_key
        key = self._get_setting("api_key") or os.getenv("OPENAI_API_KEY")
        if not key:
            try:
                from config import ConfigManager

                key = ConfigManager().get_api_key("openai")
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
            raise ImportError(
                "openai package not installed. Run: pip install openai"
            ) from exc
        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError(
                "OpenAI API key not configured. "
                "Set OPENAI_API_KEY or provide api_key in provider settings."
            )
        base_url = self._get_setting("base_url") or os.getenv("OPENAI_API_BASE_URL")
        kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.AsyncOpenAI(**kwargs)
        return self._client

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion via OpenAI."""
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._get_setting("default_model", "gpt-4o-mini")
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
            response = await client.chat.completions.create(**params)
            choice = response.choices[0]
            return LLMResponse(
                content=choice.message.content or "",
                model=response.model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                finish_reason=choice.finish_reason,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                },
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
        model = request.model_name or self._get_setting("default_model", "gpt-4o-mini")
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
            async with await client.chat.completions.create(**params) as stream:
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
