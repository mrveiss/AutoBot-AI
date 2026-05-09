# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
OpenAI provider for the multi-provider LLM layer (#1806).

Supports chat completion and streaming for all GPT/o1 model families.
OTel tracing spans are emitted for every inference call (Issue #697).

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

from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

from circuit_breaker import circuit_breaker_async
from constants.model_constants import OPENAI_O1_MINI  # used in _OPENAI_MODELS list
from constants.model_constants import (
    OPENAI_GPT4,
    OPENAI_GPT4_TURBO,
    OPENAI_GPT4O,
    OPENAI_GPT4O_MINI,
    OPENAI_GPT35_TURBO,
)
from llm_interface_pkg.models import LLMRequest, LLMResponse
from llm_interface_pkg.types import ProviderType

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

# Issue #697: tracer for LLM operations — mirrors llm_interface_pkg/providers/openai_provider.py
_tracer = trace.get_tracer("autobot.llm.openai", "2.0.0")

_OPENAI_MODELS = [
    OPENAI_GPT4O,
    OPENAI_GPT4O_MINI,
    OPENAI_GPT4_TURBO,
    OPENAI_GPT4,
    OPENAI_GPT35_TURBO,
    "o1-preview",  # not yet in model_constants — preview variant
    OPENAI_O1_MINI,
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
                from autobot_shared.ssot_config import config as _ssot_config

                # ssot_config reads OPENAI_API_KEY from .env (Issue #3829)
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
        base_url = self._get_setting("base_url") or os.getenv("OPENAI_API_BASE_URL")
        kwargs: Dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.AsyncOpenAI(**kwargs)
        return self._client

    @circuit_breaker_async("openai_service")
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion via OpenAI.

        Emits an OpenTelemetry span (Issue #697) and is protected by the
        openai_service circuit breaker.  Errors are returned via
        ``LLMResponse.error`` so the registry can perform fallback.
        """
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._get_setting("default_model", OPENAI_GPT4O_MINI)
        span_attrs: Dict[str, Any] = {
            "llm.provider": self.provider_name,
            "llm.model": model,
            "llm.request_id": request.request_id,
            "llm.temperature": request.temperature,
            "llm.max_tokens": request.max_tokens or 0,
            "llm.prompt_messages": len(request.messages),
        }
        with _tracer.start_as_current_span("llm.inference", kind=SpanKind.CLIENT, attributes=span_attrs) as span:
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
                processing_time = time.time() - start
                if span.is_recording():
                    span.set_attribute("llm.duration_ms", processing_time * 1000)
                    span.set_attribute("llm.response_length", len(choice.message.content or ""))
                    span.set_attribute("llm.prompt_tokens", response.usage.prompt_tokens)
                    span.set_attribute("llm.completion_tokens", response.usage.completion_tokens)
                    span.set_attribute("llm.total_tokens", response.usage.total_tokens)
                    span.set_status(Status(StatusCode.OK))
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
                    provider_metadata=self._build_provider_metadata(
                        model_api_name=response.model,
                        api_kwargs_applied=params,
                        total_tokens=response.usage.total_tokens,
                    ),
                )
            except Exception as exc:
                self._total_errors += 1
                logger.error("OpenAI chat_completion error: %s", exc)
                if span.is_recording():
                    span.set_status(Status(StatusCode.ERROR, str(exc)))
                    span.record_exception(exc)
                    span.set_attribute("llm.error", True)
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
