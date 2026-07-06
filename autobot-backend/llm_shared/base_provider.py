# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
from typing import Any, AsyncIterator, Dict, List, Optional

from autobot_shared.logging_manager import get_logger

from .cross_worker_rate_limiter import get_llm_rate_limiter
from .models import LLMRequest, LLMResponse
from .observability import registry as obs_registry
from .provider_auth import ApiKeyAuth, ProviderAuthError, ProviderAuthStrategy
from .rate_limit_backoff import get_backoff_handler, raise_if_rate_limited

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

    def __init__(
        self,
        settings: Dict[str, Any] | None = None,
        auth_strategy: Optional[ProviderAuthStrategy] = None,
    ) -> None:
        """
        Initialize the provider.

        Args:
            settings: Optional dict of provider-specific configuration values.
                      Keys are provider-specific (e.g., ``api_key``,
                      ``base_url``, ``default_model``).
            auth_strategy: Optional auth strategy (``ApiKeyAuth``, ``OAuthAuth``,
                           ``DeviceCodeAuth``, ``SessionAuth``).  When omitted, the
                           legacy ``settings["api_key"]`` path is used via
                           ``ApiKeyAuth`` — fully backward-compatible.
        """
        self.settings: Dict[str, Any] = settings or {}
        self._total_requests = 0
        self._total_errors = 0
        # Resolve auth strategy: explicit arg wins; fall back to ApiKeyAuth when an
        # api_key is present in settings; leave None for local providers (Ollama etc.)
        # that need no credential at all.
        if auth_strategy is not None:
            self._auth_strategy: Optional[ProviderAuthStrategy] = auth_strategy
        elif self.settings.get("api_key"):
            self._auth_strategy = ApiKeyAuth(self.settings["api_key"])
        else:
            self._auth_strategy = None
        logger.debug("Initialized %s provider (auth=%s)", self.provider_name, type(self._auth_strategy).__name__)

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Execute a chat completion and return a fully populated LLMResponse.

        Wraps ``_chat_completion_impl`` with:
        - Issue #8170: cross-worker Redis rate limiter (proactive token acquire)
        - GH#8502: exponential backoff + auto-resume on provider rate-limit / quota reset
        - Observer fan-out (GH#6593)

        Errors are returned via ``LLMResponse.error`` so the registry can
        perform fallback — implementations must not raise.
        """
        provider_key = self.provider_name or "default"
        handler = get_backoff_handler()

        async def _attempt() -> LLMResponse:
            # Issue #8170: acquire a rate-limit token shared across all uvicorn
            # workers via Redis.  Falls back to allow-all when Redis unavailable.
            async with get_llm_rate_limiter().acquire(provider_key):
                start = time.monotonic()
                try:
                    response = await self._chat_completion_impl(request)
                    latency_ms = (time.monotonic() - start) * 1000
                    try:
                        asyncio.get_running_loop().create_task(obs_registry.notify_response(response, latency_ms, 0.0))
                    except RuntimeError:
                        pass
                    # GH#8502: raise so the backoff handler can retry.
                    raise_if_rate_limited(response)
                    return response
                except Exception as exc:
                    try:
                        asyncio.get_running_loop().create_task(obs_registry.notify_error(exc, request))
                    except RuntimeError:
                        pass
                    raise

        try:
            return await handler.execute_with_retry(_attempt, provider=provider_key)
        except Exception:
            # Backoff exhausted — return the last error response if we have one,
            # otherwise let the exception propagate to the registry for fallback.
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
            "auth_strategy": type(self._auth_strategy).__name__ if self._auth_strategy else "none",
        }

    def _get_setting(self, key: str, default: Any = None) -> Any:
        """Safely retrieve a value from the settings dict."""
        return self.settings.get(key, default)

    async def _get_auth_token(self, session: Any = None) -> str | None:
        """Return a valid auth token via the active strategy, or None.

        Concrete providers call this instead of reading ``settings["api_key"]``
        directly so that OAuth / device-code / session auth is transparent.

        Args:
            session: SQLAlchemy ``AsyncSession`` required by vault-backed strategies
                     (``OAuthAuth``, ``DeviceCodeAuth``, ``SessionAuth``).

        Returns:
            Token string, or None when no auth strategy is configured (e.g. Ollama).

        Raises:
            ProviderAuthError: When a vault-backed strategy cannot obtain a token.
        """
        if self._auth_strategy is None:
            return None
        return await self._auth_strategy.resolve_token(session)

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


__all__ = ["BaseProvider", "ProviderAuthError"]
