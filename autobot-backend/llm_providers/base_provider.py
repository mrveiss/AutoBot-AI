# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base provider abstraction for the multi-provider LLM layer (#1806).

All provider implementations in this package inherit from BaseProvider and
return the shared LLMResponse / use the shared LLMRequest dataclasses that
are already defined in llm_interface_pkg.models.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

from llm_interface_pkg.models import LLMRequest, LLMResponse

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """
    Abstract base class for all LLM provider implementations.

    Concrete providers must implement:
      - chat_completion(request) -> LLMResponse
      - stream_completion(request) -> AsyncIterator[str]
      - is_available() -> bool
      - list_models() -> List[str]

    Provider name must be set as a class attribute on each subclass and
    must match a ProviderType enum value (lowercase).
    """

    #: Override in each subclass with the provider's string identifier.
    provider_name: str = ""

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
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

    @abstractmethod
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """
        Execute a chat completion and return a fully populated LLMResponse.

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
            "error_rate": (
                self._total_errors / self._total_requests
                if self._total_requests
                else 0.0
            ),
        }

    def _get_setting(self, key: str, default: Any = None) -> Any:
        """Safely retrieve a value from the settings dict."""
        return self.settings.get(key, default)


__all__ = ["BaseProvider"]
