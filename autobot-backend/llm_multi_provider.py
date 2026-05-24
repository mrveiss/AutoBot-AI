# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Backward-compatibility shim for llm_multi_provider (#4411).

The plugin-per-provider architecture now lives in ``llm_providers/``.
This module re-exports everything that external callers relied on so that
no import sites need to change.

New code should import directly from ``llm_shared.providers``:

    from llm_shared.providers import OllamaProvider, ...
    from llm_shared import get_provider_registry
    from llm_shared.models import LLMRequest, LLMResponse
    from llm_shared.types import ProviderType, LLMType
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

from autobot_shared.logging_manager import get_logger

# ---------------------------------------------------------------------------
# Re-export the plugin registry and base classes from canonical location
# ---------------------------------------------------------------------------
from llm_shared import BaseProvider, ProviderRegistry, get_provider_registry

# ---------------------------------------------------------------------------
# Re-export canonical types from their authoritative modules
# ---------------------------------------------------------------------------
from llm_shared.models import LLMRequest, LLMResponse
from llm_shared.providers import (
    AnthropicProvider,
    CustomOpenAIProvider,
    GroqProvider,
    HuggingFaceProvider,
    NousPortalProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterProvider,
    VLLMProvider,
)
from llm_shared.types import LLMType, ProviderType

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# ProviderConfig — thin dataclass kept for callers that construct it directly
# ---------------------------------------------------------------------------
from dataclasses import dataclass, field


@dataclass
class ProviderConfig:
    """Configuration for a specific LLM provider (legacy shim type)."""

    provider_type: ProviderType
    enabled: bool = True
    base_url: str | None = None
    api_key: str | None = None
    default_model: str = ""
    available_models: List[str] = field(default_factory=list)
    max_concurrent_requests: int = 10
    timeout: int = 30
    retry_count: int = 3
    circuit_breaker_enabled: bool = True
    priority: int = 100
    config: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# LLMProvider — ABC alias kept for callers that subclass it directly
# ---------------------------------------------------------------------------
from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base class for LLM providers (legacy shim).

    New providers should subclass ``llm_shared.providers.base_provider.BaseProvider``
    instead.
    """

    def __init__(self, config: ProviderConfig) -> None:
        self.config = config
        self.provider_type = config.provider_type
        self._active_requests = 0
        self._total_requests = 0
        self._total_errors = 0

    @abstractmethod
    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Execute a chat completion request."""

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is available."""

    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Get list of available models."""

    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics."""
        return {
            "provider": self.provider_type.value,
            "enabled": self.config.enabled,
            "active_requests": self._active_requests,
            "total_requests": self._total_requests,
            "total_errors": self._total_errors,
            "error_rate": self._total_errors / max(1, self._total_requests),
            "available_models": len(self.get_available_models()),
        }


# ---------------------------------------------------------------------------
# MockProvider — kept for tests that import it from this module
# ---------------------------------------------------------------------------
import asyncio

from constants.threshold_constants import TimingConstants


class MockProvider(LLMProvider):
    """Mock LLM provider for testing (legacy shim)."""

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        self._active_requests += 1
        self._total_requests += 1
        try:
            await asyncio.sleep(TimingConstants.MICRO_DELAY)
            if request.llm_type == LLMType.EXTRACTION:
                content = '{"facts": [{"subject": "Test", "predicate": "is", "object": "example"}]}'
            elif request.llm_type == LLMType.CLASSIFICATION:
                content = "POSITIVE"
            else:
                user_content = next(
                    (m["content"] for m in request.messages if m["role"] == "user"),
                    "",
                )
                content = f"Mock response to: {user_content[:50]}..."
            return LLMResponse(
                content=content,
                provider=ProviderType.MOCK.value,
                model="mock-model",
                finish_reason="stop",
            )
        except Exception as exc:
            self._total_errors += 1
            return LLMResponse(
                content="Mock error response",
                provider=ProviderType.MOCK.value,
                model="mock-model",
                error=str(exc),
            )
        finally:
            self._active_requests -= 1

    async def is_available(self) -> bool:
        return True

    def get_available_models(self) -> List[str]:
        return ["mock-model", "mock-fast", "mock-accurate"]


# ---------------------------------------------------------------------------
# get_provider() — convenience function for backward compat
# ---------------------------------------------------------------------------


async def get_provider(
    provider_name: str | None = None,
    conversation_id: str | None = None,
) -> BaseProvider | None:
    """
    Return a provider instance from the registry.

    Backward-compatible wrapper around
    ``get_provider_registry().get_provider_for_request()``.
    """
    registry = get_provider_registry()
    return await registry.get_provider_for_request(
        provider_name=provider_name,
        conversation_id=conversation_id,
    )


def list_providers() -> List[Dict[str, object]]:
    """Return a serialisable list of registered providers."""
    return get_provider_registry().list_providers()


# ---------------------------------------------------------------------------
# UnifiedLLMInterface — backward-compat wrapper backed by the plugin registry
# ---------------------------------------------------------------------------


class UnifiedLLMInterface:
    """
    Backward-compatible facade over the plugin-per-provider registry.

    **Deprecated** — new code should use ``LLMService`` from
    ``services.llm_service`` (the canonical post-#3185 entry point).
    This class exists solely to avoid breaking call sites that still
    instantiate ``UnifiedLLMInterface()``; it is not the canonical
    interface and should not be imported in new code.
    """

    def __init__(self) -> None:
        self._registry: ProviderRegistry | None = None

    async def initialize(self) -> None:
        """Initialise the underlying provider registry (idempotent)."""
        self._registry = get_provider_registry()

    def _get_registry(self) -> ProviderRegistry:
        if self._registry is None:
            self._registry = get_provider_registry()
        return self._registry

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        llm_type: str | LLMType = LLMType.GENERAL,
        provider: str | ProviderType | None = None,
        model_name: str | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Execute a chat completion using the best available provider."""
        provider_name: str | None = None
        if isinstance(provider, ProviderType):
            provider_name = provider.value
        elif isinstance(provider, str):
            provider_name = provider

        registry = self._get_registry()
        request = LLMRequest(
            messages=messages,
            llm_type=llm_type if isinstance(llm_type, LLMType) else LLMType.GENERAL,
            model_name=model_name,
            metadata=kwargs,
        )

        # Claude escalation (#8171): attempt top-tier routing before local providers.
        # Returns None when disabled, score too low, or Claude errors — safe fallthrough.
        from llm_shared.tiered_routing.complexity_router import ComplexityRouter
        _escalation_result = await ComplexityRouter().route_with_escalation(request)
        if _escalation_result is not None:
            return _escalation_result

        selected = await registry.get_provider_for_request(
            provider_name=provider_name,
            request=request,
        )
        if selected is None:
            return LLMResponse(
                content="",
                provider=ProviderType.MOCK.value,
                model="failed",
                error="All providers unavailable",
            )
        return await selected.chat_completion(request)

    async def generate_response(self, prompt: str, llm_type: str = "task", **kwargs: Any) -> str:
        """Legacy helper: run a single-turn prompt and return the text."""
        messages = [{"role": "user", "content": prompt}]
        response = await self.chat_completion(messages, llm_type=llm_type, **kwargs)
        return response.content

    async def safe_query(self, prompt: str, **kwargs: Any) -> Dict[str, Any]:
        """Legacy safe_query: returns OpenAI-shaped dict."""
        messages = [{"role": "user", "content": prompt}]
        response = await self.chat_completion(messages, **kwargs)
        return {"choices": [{"message": {"content": response.content}}]}

    async def health_check(self) -> Dict[str, Any]:
        """Run health checks on all registered providers."""
        return await self._get_registry().health_check_all()

    def get_provider_stats(self) -> Dict[str, Any]:
        """Return registry stats."""
        return self._get_registry().get_stats()

    async def get_available_models(self, provider: ProviderType | None = None) -> Dict[str, List[str]]:
        """Return available models per provider."""
        registry = self._get_registry()
        name_filter = provider.value if provider else None
        providers = registry._providers
        result: Dict[str, List[str]] = {}
        for name, p in providers.items():
            if name_filter and name != name_filter:
                continue
            try:
                result[name] = await p.list_models()
            except Exception as exc:
                logger.error("Error listing models for %s: %s", name, exc)
                result[name] = []
        return result


# ---------------------------------------------------------------------------
# Legacy aliases
# ---------------------------------------------------------------------------
LLMInterface = UnifiedLLMInterface
get_llm_interface = lambda: UnifiedLLMInterface()  # noqa: E731
get_unified_llm_interface = get_llm_interface


__all__ = [
    # Types
    "ProviderType",
    "LLMType",
    # Models
    "LLMRequest",
    "LLMResponse",
    "ProviderConfig",
    # ABC (legacy)
    "LLMProvider",
    # Providers from plugin package
    "OllamaProvider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GroqProvider",
    "HuggingFaceProvider",
    "CustomOpenAIProvider",
    "OpenRouterProvider",
    "NousPortalProvider",
    "VLLMProvider",
    "BaseProvider",
    # Mock (legacy)
    "MockProvider",
    # Registry
    "ProviderRegistry",
    "get_provider_registry",
    # Convenience
    "get_provider",
    "list_providers",
    # Unified facade (backward compat)
    "UnifiedLLMInterface",
    "LLMInterface",
    "get_llm_interface",
    "get_unified_llm_interface",
]
