# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base provider abstraction for the multi-provider LLM layer (#1806).

All provider implementations in this package inherit from BaseProvider and
return the shared LLMResponse / use the shared LLMRequest dataclasses that
are already defined in llm_shared.models.
"""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List

from autobot_shared.logging_manager import get_logger

from .cross_worker_rate_limiter import get_llm_rate_limiter
from .models import LLMRequest, LLMResponse
from .observability import registry as obs_registry

logger = get_logger(__name__)


class BaseProvider(ABC):
    """
    Abstract base class for all LLM provider implementations.

    Concrete providers must implement:
      - _chat_completion_impl(request) -> LLMResponse
      - stream_completion(request) -> AsyncIterator[str]
      - is_available() -> bool
      - list_models() -> List[str]

    Provider name must be set as a class attribute on each subclass and
    must match a ProviderType enum value (lowercase).
    """

    #: Override in each subclass with the provider's string identifier.
    provider_name: str = ""

    def __init__(self, settings: Dict[str, Any] | None = None) -> None:
        """
        Initialize the provider.

        Args:
            settings: Optional dict of provider-specific configuration values.
                      Keys are provider-specific (e.g., ``api_key``,
                      ``base_url``, ``default_model``).
        """
        self.settings: Dict[str, Any] = settings or {}
        self._total_requests = 0
        self._total_errors = 0
        logger.debug("Initialized %s provider", self.provider_name)

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Execute a chat completion and return a fully populated LLMResponse.

        Wraps ``_chat_completion_impl`` with:
        - Issue #8170: cross-worker Redis rate limiter (proactive token acquire)
        - Observer fan-out (GH#6593)

        Errors are returned via ``LLMResponse.error`` so the registry can
        perform fallback — implementations must not raise.
        """
        # Issue #8170: acquire a rate-limit token shared across all uvicorn
        # workers via Redis.  Falls back to allow-all when Redis unavailable.
        provider_key = self.provider_name or "default"
        async with get_llm_rate_limiter().acquire(provider_key):
            start = time.monotonic()
            try:
                response = await self._chat_completion_impl(request)
                latency_ms = (time.monotonic() - start) * 1000
                try:
                    asyncio.get_running_loop().create_task(obs_registry.notify_response(response, latency_ms, 0.0))
                except RuntimeError:
                    pass
                return response
            except Exception as exc:
                try:
                    asyncio.get_running_loop().create_task(obs_registry.notify_error(exc, request))
                except RuntimeError:
                    pass
                raise

    @abstractmethod
    async def _chat_completion_impl(self, request: LLMRequest) -> LLMResponse:
        """
        Provider-specific chat completion implementation.

        Implementations must not raise — errors are returned via
        ``LLMResponse.error`` so the registry can perform fallback.

        Args:
            request: Standardized request object.

        Returns:
            LLMResponse with content populated, or error field set.
        """

    @abstractmethod
    async def stream_completion(self, request: LLMRequest) -> AsyncIterator[str]:
        """
        Stream a chat completion, yielding text chunks as they arrive.

        Args:
            request: Standardized request object.

        Yields:
            String chunks of the generated text.
        """

    @abstractmethod
    async def is_available(self) -> bool:
        """
        Return True if the provider is reachable and properly configured.

        This is used by the registry before dispatching a request and must
        be cheap (single lightweight check, no billable inference).
        """

    @abstractmethod
    async def list_models(self) -> List[str]:
        """Return the list of model identifiers available via this provider."""

    def get_stats(self) -> Dict[str, Any]:
        """Return basic request/error counters for monitoring."""
        return {
            "provider": self.provider_name,
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "error_rate": (self._total_errors / self._total_requests if self._total_requests else 0.0),
        }

    def _get_setting(self, key: str, default: Any = None) -> Any:
        """Safely retrieve a value from the settings dict."""
        return self.settings.get(key, default)

    def _build_provider_metadata(
        self,
        model_api_name: str,
        api_kwargs_applied: Dict[str, Any],
        total_tokens: int | None = None,
    ) -> Dict[str, Any]:
        """
        Build the standard ``provider_metadata`` dict for an LLMResponse.

        Args:
            model_api_name:    Exact model name sent to the API (may differ from
                               request.model_name after aliasing or fallback).
            api_kwargs_applied: Merged kwargs actually sent to the provider API.
            total_tokens:      Total token count from the response usage, or None.

        Returns:
            Dict suitable for ``LLMResponse.provider_metadata``.
        """
        metadata: Dict[str, Any] = {
            "provider": self.provider_name,
            "model_api_name": model_api_name,
            "api_kwargs_applied": api_kwargs_applied,
        }
        if total_tokens is not None:
            metadata["total_tokens"] = total_tokens
        return metadata


__all__ = ["BaseProvider"]
