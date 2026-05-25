# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
OpenRouter Provider - Unified interface for 200+ LLM models via OpenRouter API.

Issue #4341: Model Provider Flexibility & Vendor-Agnostic Switching

OpenRouter provides a single API gateway to dozens of LLM providers
(OpenAI, Anthropic, Meta, Mistral, etc.) enabling transparent provider
switching without changing client code.

API Reference: https://openrouter.ai/docs/api/v1

Configuration:
  - api_key: OpenRouter API key (from environment: OPENROUTER_API_KEY)
  - base_url: Optional custom base URL (default: https://openrouter.ai/api/v1)
  - default_model: Default model name for completions
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from llm_interface_pkg.models import LLMRequest, LLMResponse
from llm_interface_pkg.types import ProviderType

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)
_tracer = trace.get_tracer("autobot.llm.openrouter", "1.0.0")


class OpenRouterProvider(BaseProvider):
    """
    OpenRouter provider implementation.

    Supports chat completion and streaming across 200+ models from:
    - OpenAI (GPT-4, GPT-3.5)
    - Anthropic (Claude)
    - Meta (Llama)
    - Mistral (Mistral, Mixtral)
    - Google (Gemini, Palm)
    - Cohere, Aleph Alpha, and more

    Requires: openai package (pip install openai)
              OPENROUTER_API_KEY environment variable
    """

    provider_name = ProviderType.OPENROUTER.value if hasattr(ProviderType, "OPENROUTER") else "openrouter"

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(settings)
        self._api_key: Optional[str] = None
        self._base_url: Optional[str] = None
        self._client = None

    def _resolve_api_key(self) -> Optional[str]:
        """Resolve API key from settings or environment."""
        if self._api_key:
            return self._api_key
        key = self._get_setting("api_key") or os.getenv("OPENROUTER_API_KEY")
        self._api_key = key
        return self._api_key

    def _resolve_base_url(self) -> str:
        """Resolve base URL with default."""
        if self._base_url:
            return self._base_url
        url = self._get_setting("base_url") or os.getenv("OPENROUTER_API_BASE_URL") or "https://openrouter.ai/api/v1"
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
            raise ValueError("OpenRouter API key not found. Set OPENROUTER_API_KEY or " "provide api_key in settings.")

        base_url = self._resolve_base_url()
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        logger.info("OpenRouter client initialized")

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Execute a chat completion via OpenRouter.

        Args:
            request: Standardized LLM request.

        Returns:
            LLMResponse with content populated or error field set.
        """
        with _tracer.start_as_current_span("openrouter.chat_completion", kind=SpanKind.CLIENT) as span:
            try:
                self._total_requests += 1
                self._ensure_client()

                # Convert to OpenAI format
                messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]

                # Merge API kwargs
                api_kwargs = request.metadata.get("api_kwargs", {})
                chat_kwargs = {
                    "model": request.model_name or self._get_setting("default_model", "gpt-3.5-turbo"),
                    "messages": messages,
                    "temperature": api_kwargs.get("temperature", 0.7),
                    "max_tokens": api_kwargs.get("max_tokens"),
                    "top_p": api_kwargs.get("top_p", 0.95),
                }

                # Optional parameters
                if "presence_penalty" in api_kwargs:
                    chat_kwargs["presence_penalty"] = api_kwargs["presence_penalty"]
                if "frequency_penalty" in api_kwargs:
                    chat_kwargs["frequency_penalty"] = api_kwargs["frequency_penalty"]
                if "stop" in api_kwargs:
                    chat_kwargs["stop"] = api_kwargs["stop"]

                start_time = time.monotonic()
                response = await self._client.chat.completions.create(**chat_kwargs)
                latency = time.monotonic() - start_time

                # Extract response content
                content = response.choices[0].message.content or ""
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                }

                span.set_attribute("openrouter.model", chat_kwargs["model"])
                span.set_attribute("openrouter.latency_ms", int(latency * 1000))
                span.set_attribute("openrouter.tokens", usage["prompt_tokens"] + usage["completion_tokens"])
                span.set_status(Status(StatusCode.OK))

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
                span.set_status(Status(StatusCode.ERROR))
                span.record_exception(exc)
                return LLMResponse(
                    content="",
                    model_name=request.model_name or "openrouter-model",
                    provider_name=self.provider_name,
                    error=error_msg,
                )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Stream a chat completion from OpenRouter.

        Args:
            request: Standardized LLM request.

        Yields:
            String chunks of the generated text.
        """
        with _tracer.start_as_current_span("openrouter.stream_completion", kind=SpanKind.CLIENT) as span:
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

                start_time = time.monotonic()
                async with await self._client.chat.completions.create(**chat_kwargs) as stream:
                    async for chunk in stream:
                        if chunk.choices[0].delta.content:
                            yield chunk.choices[0].delta.content

                latency = time.monotonic() - start_time
                span.set_attribute("openrouter.model", chat_kwargs["model"])
                span.set_attribute("openrouter.latency_ms", int(latency * 1000))
                span.set_status(Status(StatusCode.OK))

            except Exception as exc:
                self._total_errors += 1
                logger.error("OpenRouter stream error: %s", exc)
                span.set_status(Status(StatusCode.ERROR))
                span.record_exception(exc)
                yield f"Error: {exc}"

    async def is_available(self) -> bool:
        """
        Check if OpenRouter is reachable and properly configured.

        Performs a lightweight health check by listing available models.

        Returns:
            True if provider is reachable, False otherwise.
        """
        try:
            self._ensure_client()
            # OpenRouter supports models endpoint
            models = await self._client.models.list()
            return models is not None and len(models.data) > 0
        except Exception as exc:
            logger.warning("OpenRouter health check failed: %s", exc)
            return False

    async def list_models(self) -> List[str]:
        """
        List available models via OpenRouter API.

        Returns 200+ model identifiers available through OpenRouter,
        including models from OpenAI, Anthropic, Meta, Mistral, Google, etc.

        Returns:
            List of model identifiers.
        """
        try:
            self._ensure_client()
            response = await self._client.models.list()
            return [model.id for model in response.data] if response.data else []
        except Exception as exc:
            logger.error("Failed to list OpenRouter models: %s", exc)
            return []


# Add to ProviderType enum if needed
def _ensure_provider_type():
    """Ensure OPENROUTER is in ProviderType enum."""
    try:
        from llm_interface_pkg.types import ProviderType

        if not hasattr(ProviderType, "OPENROUTER"):
            logger.info("ProviderType.OPENROUTER not defined; using string 'openrouter'")
    except Exception:
        pass


_ensure_provider_type()

__all__ = ["OpenRouterProvider"]
