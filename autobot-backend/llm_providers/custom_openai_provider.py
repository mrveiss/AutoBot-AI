# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Custom OpenAI-compatible endpoint provider for the multi-provider LLM layer (#1806).

Works with any server that exposes the OpenAI ``/v1/chat/completions`` API,
including vLLM, llama.cpp server, LM Studio, Ollama in OpenAI-compat mode,
Jan.ai, and similar projects.

Configuration (via settings dict or environment variables):

  - ``base_url`` / ``CUSTOM_OPENAI_BASE_URL``   — required base URL, e.g.
      ``http://localhost:8000/v1``
  - ``api_key``  / ``CUSTOM_OPENAI_API_KEY``    — optional (defaults to "none")
  - ``default_model``                            — model to use when not specified
      in a request (required for servers that need an explicit model name)

A single AutoBot instance can hold multiple CustomOpenAIProvider instances with
different ``base_url`` values.  The ``provider_registry`` identifies each by the
``instance_name`` kwarg supplied at construction time (defaults to "custom_openai").
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from llm_interface_pkg.models import LLMRequest, LLMResponse

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)


class CustomOpenAIProvider(BaseProvider):
    """
    Provider for any server exposing an OpenAI-compatible REST API.

    Backed by the ``openai`` Python SDK configured to point at a custom
    ``base_url``, so it benefits from the SDK's retry/backoff logic and
    async streaming support without extra dependencies.
    """

    #: Override at construction time via ``instance_name`` to register
    #: multiple custom endpoints in the same registry.
    provider_name = "custom_openai"

    def __init__(
        self,
        settings: Optional[Dict[str, Any]] = None,
        instance_name: Optional[str] = None,
    ) -> None:
        """
        Initialize a custom OpenAI-compatible provider.

        Args:
            settings: Provider settings dict.  Recognised keys:
                ``base_url``, ``api_key``, ``default_model``.
            instance_name: Override for ``provider_name`` to allow multiple
                custom endpoints coexisting in the same registry.
        """
        super().__init__(settings)
        if instance_name:
            self.provider_name = instance_name
        self._client = None

    def _resolve_base_url(self) -> str:
        """Resolve the endpoint base URL from settings or environment."""
        url = self._get_setting("base_url") or os.getenv(
            "CUSTOM_OPENAI_BASE_URL", ""
        )
        if not url:
            raise ValueError(
                "Custom OpenAI base_url not configured. "
                "Provide base_url in provider settings or set CUSTOM_OPENAI_BASE_URL."
            )
        return url.rstrip("/")

    def _resolve_api_key(self) -> str:
        """Resolve the API key (many local servers accept any non-empty string)."""
        return (
            self._get_setting("api_key")
            or os.getenv("CUSTOM_OPENAI_API_KEY")
            or "none"
        )

    def _ensure_client(self):
        """Lazily initialize the async OpenAI client pointed at the custom URL."""
        if self._client is not None:
            return self._client
        try:
            import openai
        except ImportError as exc:
            raise ImportError(
                "openai package not installed. Run: pip install openai"
            ) from exc
        self._client = openai.AsyncOpenAI(
            base_url=self._resolve_base_url(),
            api_key=self._resolve_api_key(),
        )
        return self._client

    def _default_model(self) -> str:
        """Return configured default model or an empty string."""
        return self._get_setting("default_model", "")

    def _build_params(self, request: LLMRequest, model: str) -> Dict[str, Any]:
        """Build chat completion parameters from an LLMRequest."""
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
        return params

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion via the custom endpoint."""
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._default_model()
        try:
            client = self._ensure_client()
            response = await client.chat.completions.create(
                **self._build_params(request, model)
            )
            choice = response.choices[0]
            usage = response.usage
            return LLMResponse(
                content=choice.message.content or "",
                model=response.model or model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                finish_reason=choice.finish_reason,
                usage={
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                },
            )
        except Exception as exc:
            self._total_errors += 1
            logger.error(
                "CustomOpenAI (%s) chat_completion error: %s",
                self.provider_name,
                exc,
            )
            return LLMResponse(
                content="",
                model=model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                error=str(exc),
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream chat completion from the custom endpoint."""
        self._total_requests += 1
        model = request.model_name or self._default_model()
        try:
            client = self._ensure_client()
            params = self._build_params(request, model)
            params["stream"] = True
            async with await client.chat.completions.create(**params) as stream:
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
        except Exception as exc:
            self._total_errors += 1
            logger.error(
                "CustomOpenAI (%s) stream_completion error: %s",
                self.provider_name,
                exc,
            )
            raise

    async def is_available(self) -> bool:
        """Return True if the custom endpoint responds to a model listing."""
        try:
            client = self._ensure_client()
            await client.models.list()
            return True
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """Discover models available at the custom endpoint."""
        try:
            client = self._ensure_client()
            model_list = await client.models.list()
            return [m.id for m in model_list.data]
        except Exception:
            configured = self._default_model()
            return [configured] if configured else []


__all__ = ["CustomOpenAIProvider"]
