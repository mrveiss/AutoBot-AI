# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anthropic provider for the multi-provider LLM layer (#1806).

Delegates execution to the existing AnthropicAdapter from
llm_interface_pkg.adapters, wrapping it in the BaseProvider interface so
the provider registry can treat all providers uniformly.

API key is read (in priority order) from:
  1. ``settings["api_key"]``
  2. Environment variable ``ANTHROPIC_API_KEY``

API keys are never logged.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from constants.model_constants import (
    ANTHROPIC_CLAUDE3_OPUS_DATED,
    ANTHROPIC_CLAUDE35_HAIKU,
    ANTHROPIC_CLAUDE_HAIKU4_5,
    ANTHROPIC_CLAUDE_SONNET4,
)
from llm_interface_pkg.models import LLMRequest, LLMResponse
from llm_interface_pkg.types import ProviderType

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

_ANTHROPIC_MODELS = [
    "claude-opus-4-6",   # release alias — no dated constant yet
    "claude-sonnet-4-6",  # release alias — no dated constant yet
    ANTHROPIC_CLAUDE_SONNET4,
    ANTHROPIC_CLAUDE_HAIKU4_5,
    ANTHROPIC_CLAUDE35_HAIKU,
    ANTHROPIC_CLAUDE3_OPUS_DATED,
]


class AnthropicProvider(BaseProvider):
    """
    Anthropic Claude provider implementation.

    Supports chat completion and streaming for all Claude model families.
    Requires the ``anthropic`` package (``pip install anthropic``).
    """

    provider_name = ProviderType.ANTHROPIC.value

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(settings)
        self._api_key: Optional[str] = None
        self._client = None

    def _resolve_api_key(self) -> Optional[str]:
        """Resolve API key from settings or environment."""
        if self._api_key:
            return self._api_key
        self._api_key = self._get_setting("api_key") or os.getenv("ANTHROPIC_API_KEY")
        return self._api_key

    def _ensure_client(self):
        """Lazily initialize the async Anthropic client."""
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:
            raise ImportError(
                "anthropic package not installed. Run: pip install anthropic"
            ) from exc
        api_key = self._resolve_api_key()
        if not api_key:
            raise ValueError(
                "Anthropic API key not configured. "
                "Set ANTHROPIC_API_KEY or provide api_key in provider settings."
            )
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        return self._client

    def _split_messages(self, messages: list) -> tuple[str, list]:
        """
        Separate the optional system message from conversational messages.

        Returns:
            Tuple of (system_content, non_system_messages).
        """
        system_content = ""
        chat_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                system_content = msg.get("content", "")
            else:
                chat_messages.append(
                    {"role": msg.get("role", "user"), "content": msg.get("content", "")}
                )
        return system_content, chat_messages

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Execute a non-streaming chat completion via Anthropic."""
        self._total_requests += 1
        start = time.time()
        model = request.model_name or self._get_setting(
            "default_model", "claude-sonnet-4-6"
        )
        try:
            client = self._ensure_client()
            system_content, chat_messages = self._split_messages(request.messages)
            kwargs: Dict[str, Any] = {
                "model": model,
                "max_tokens": request.max_tokens or 4096,
                "messages": chat_messages,
                "temperature": request.temperature,
            }
            if system_content:
                kwargs["system"] = system_content
            response = await client.messages.create(**kwargs)
            content = response.content[0].text if response.content else ""
            return LLMResponse(
                content=content,
                model=response.model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                usage={
                    "prompt_tokens": response.usage.input_tokens,
                    "completion_tokens": response.usage.output_tokens,
                    "total_tokens": (
                        response.usage.input_tokens + response.usage.output_tokens
                    ),
                },
            )
        except Exception as exc:
            self._total_errors += 1
            logger.error("Anthropic chat_completion error: %s", exc)
            return LLMResponse(
                content="",
                model=model,
                provider=self.provider_name,
                processing_time=time.time() - start,
                request_id=request.request_id,
                error=str(exc),
            )

    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream a chat completion from Anthropic, yielding text chunks."""
        self._total_requests += 1
        model = request.model_name or self._get_setting(
            "default_model", "claude-sonnet-4-6"
        )
        try:
            client = self._ensure_client()
            system_content, chat_messages = self._split_messages(request.messages)
            kwargs: Dict[str, Any] = {
                "model": model,
                "max_tokens": request.max_tokens or 4096,
                "messages": chat_messages,
                "temperature": request.temperature,
            }
            if system_content:
                kwargs["system"] = system_content
            async with client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text
        except Exception as exc:
            self._total_errors += 1
            logger.error("Anthropic stream_completion error: %s", exc)
            raise

    async def is_available(self) -> bool:
        """Return True if the API key is set and the token-count endpoint responds."""
        try:
            client = self._ensure_client()
            await client.messages.count_tokens(
                model="claude-haiku-4-5-20251001",
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False

    async def list_models(self) -> List[str]:
        """Return known Anthropic models (static — no discovery endpoint)."""
        return list(_ANTHROPIC_MODELS)


__all__ = ["AnthropicProvider"]
