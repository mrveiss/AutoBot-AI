# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
OpenRouter Provider - Unified interface for 200+ LLM models via OpenRouter API.

Issue #4341: Model Provider Flexibility & Vendor-Agnostic Switching

Configuration:
  - api_key: OpenRouter API key (from environment: OPENROUTER_API_KEY)
  - base_url: Optional custom base URL (default: https://openrouter.ai/api/v1)
  - default_model: Default model name for completions

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from llm_shared.models import LLMRequest, LLMResponse
from llm_shared.types import ProviderType

from ..base_provider import BaseProvider

logger = get_logger(__name__)


class OpenRouterProvider(BaseProvider):
    """
    OpenRouter provider implementation.

    Supports chat completion and streaming across 200+ models from:
    OpenAI, Anthropic, Meta, Mistral, Google, Cohere, and more.

    Requires: openai package (pip install openai)
              OPENROUTER_API_KEY environment variable
    """

    provider_name = ProviderType.OPENROUTER.value if hasattr(ProviderType, "OPENROUTER") else "openrouter"

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        super().__init__(settings)
        self._api_key: str | None = None
        self._base_url: str | None = None
        self._client = None

    def _resolve_api_key(self) -> str | None:
        """Resolve API key from settings or environment."""
        if self._api_key:
            return self._api_key
        key = self._get_setting("api_key") or config.openrouter_api_key
        self._api_key = key
        return self._api_key

    def _resolve_base_url(self) -> str:
        """Resolve base URL with default."""
        if self._base_url:
            return self._base_url
        url = self._get_setting("base_url") or config.openrouter_api_base_url or "https://openrouter.ai/api/v1"
        self._base_url = url
        return url

    def _ensure_client(self):
        """Lazily initialize the async OpenAI client."""
        if self._client is not None:
            return

        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("openai package not installed. Run: pip install openai") from exc

        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError("OpenRouter API key not found. Set OPENROUTER_API_KEY or provide api_key in settings.")

        base_url = self._resolve_base_url()
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        logger.info("OpenRouter client initialized")

    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        """Execute a chat completion via OpenRouter."""
        try:
            self._total_requests += 1
            self._ensure_client()

            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

            api_kwargs = request.metadata.get("api_kwargs", {})
            chat_kwargs = {
                "model": request.model_name or self._get_setting("default_model", "gpt-3.5-turbo"),
                "messages": messages,
                "temperature": api_kwargs.get("temperature", 0.7),
                "max_tokens": api_kwargs.get("max_tokens"),
                "top_p": api_kwargs.get("top_p", 0.95),
            }

            if "presence_penalty" in api_kwargs:
                chat_kwargs["presence_penalty"] = api_kwargs["presence_penalty"]
            if "frequency_penalty" in api_kwargs:
                chat_kwargs["frequency_penalty"] = api_kwargs["frequency_penalty"]
            if "stop" in api_kwargs:
                chat_kwargs["stop"] = api_kwargs["stop"]

            response = await self._client.chat.completions.create(**chat_kwargs)

            content = response.choices[0].message.content or ""
            usage = {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            }

            return LLMResponse(
                content=content,
                model_name=request.model_name or chat_kwargs["model"],
                provider_name=self.provider_name,
                usage=usage,
                provider_metadata=self._build_provider_metadata(
                    model_api_name=chat_kwargs["model"],
                    api_kwargs_applied=chat_kwargs,
                    total_tokens=usage["prompt_tokens"] + usage["completion_tokens"],
                ),
            )

        except Exception as exc:
            self._total_errors += 1
            error_msg = f"OpenRouter API error: {exc}"
            logger.error(error_msg)
            return LLMResponse(
                content="",
                model_name=request.model_name or "openrouter-model",
                provider_name=self.provider_name,
                error=error_msg,
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a chat completion from OpenRouter."""
        try:
            self._total_requests += 1
            self._ensure_client()

            messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

            api_kwargs = request.metadata.get("api_kwargs", {})
            chat_kwargs = {
                "model": request.model_name or self._get_setting("default_model", "gpt-3.5-turbo"),
                "messages": messages,
                "temperature": api_kwargs.get("temperature", 0.7),
                "max_tokens": api_kwargs.get("max_tokens"),
                "top_p": api_kwargs.get("top_p", 0.95),
                "stream": True,
            }

            if "stop" in api_kwargs:
                chat_kwargs["stop"] = api_kwargs["stop"]

            async with await self._client.chat.completions.create(**chat_kwargs) as stream:
                async for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content

        except Exception as exc:
            self._total_errors += 1
            logger.error("OpenRouter stream error: %s", exc)
            yield f"Error: {exc}"

    async def is_available(self) -> bool:
        """Check if OpenRouter is reachable and properly configured."""
        try:
            self._ensure_client()
            models = await self._client.models.list()
            return models is not None and len(models.data) > 0
        except Exception as exc:
            logger.warning("OpenRouter health check failed: %s", exc)
            return False

    async def list_models(self) -> List[str]:
        """List available models via OpenRouter API."""
        try:
            self._ensure_client()
            response = await self._client.models.list()
            return [model.id for model in response.data] if response.data else []
        except Exception as exc:
            logger.error("Failed to list OpenRouter models: %s", exc)
            return []


__all__ = ["OpenRouterProvider"]
