# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Provider registry for the multi-provider LLM layer (#1806).

The ProviderRegistry is the single source of truth for which providers are
available at runtime.  It supports:

  - Registration of BaseProvider instances by name
  - Ordered fallback chains (primary → secondary → … )
  - Per-conversation provider override (keyed by conversation_id)
  - Async health check with caching to avoid hammering providers
  - Lazy initialisation of the default provider set from autobot_shared.ssot_config

Usage:

    from llm_providers.provider_registry import get_provider_registry

    registry = get_provider_registry()
    provider = await registry.get_provider_for_request(
        provider_name="openai",          # optional preference
        conversation_id="conv-abc123",   # optional per-conv override
    )
    response = await provider.chat_completion(request)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

from .base_provider import BaseProvider

logger = logging.getLogger(__name__)

# Cache health results for 30 s to avoid a health check on every request.
_HEALTH_CACHE_TTL = 30.0


class ProviderRegistry:
    """
    Manages the set of available LLM providers with fallback and per-conversation
    overrides.

    This is a per-process singleton (obtained via ``get_provider_registry()``).
    """

    def __init__(self) -> None:
        self._providers: Dict[str, BaseProvider] = {}
        self._fallback_chain: List[str] = []
        self._conversation_overrides: Dict[str, str] = {}
        # {provider_name: (is_available: bool, checked_at: float)}
        self._health_cache: Dict[str, tuple[bool, float]] = {}
        self._health_lock = asyncio.Lock()
        self._initialized = False

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, provider: BaseProvider) -> None:
        """
        Register a provider instance.

        If a provider with the same name already exists it is replaced and a
        warning is emitted.
        """
        name = provider.provider_name
        if not name:
            raise ValueError("Provider must set provider_name before registration.")
        if name in self._providers:
            logger.warning("Replacing existing provider: %s", name)
        self._providers[name] = provider
        logger.info("Registered provider: %s", name)

    def unregister(self, name: str) -> None:
        """Remove a provider from the registry."""
        if name in self._providers:
            del self._providers[name]
            self._health_cache.pop(name, None)
            logger.info("Unregistered provider: %s", name)

    def set_fallback_chain(self, chain: List[str]) -> None:
        """
        Define the ordered list of provider names to try when no explicit
        provider is requested.  Local providers should appear before cloud
        providers to honour the local-first philosophy.
        """
        self._fallback_chain = list(chain)
        logger.info("Provider fallback chain: %s", chain)

    # ------------------------------------------------------------------
    # Per-conversation overrides
    # ------------------------------------------------------------------

    def set_conversation_provider(
        self, conversation_id: str, provider_name: str
    ) -> None:
        """Pin a specific provider for a given conversation."""
        self._conversation_overrides[conversation_id] = provider_name
        logger.debug(
            "Conversation %s pinned to provider %s", conversation_id, provider_name
        )

    def clear_conversation_provider(self, conversation_id: str) -> None:
        """Remove the per-conversation provider override."""
        self._conversation_overrides.pop(conversation_id, None)

    def get_conversation_provider_name(self, conversation_id: str) -> Optional[str]:
        """Return the provider name pinned to this conversation, or None."""
        return self._conversation_overrides.get(conversation_id)

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    async def _check_health_cached(self, name: str) -> bool:
        """Check provider availability with a 30-second in-process cache."""
        now = time.monotonic()
        cached = self._health_cache.get(name)
        if cached and (now - cached[1]) < _HEALTH_CACHE_TTL:
            return cached[0]
        provider = self._providers.get(name)
        if provider is None:
            return False
        try:
            available = await provider.is_available()
        except Exception as exc:
            logger.warning("Health check for %s raised: %s", name, exc)
            available = False
        async with self._health_lock:
            self._health_cache[name] = (available, now)
        return available

    async def health_check_all(self) -> Dict[str, bool]:
        """
        Run availability checks for every registered provider in parallel.

        Returns a dict of {provider_name: is_available}.
        """
        results = await asyncio.gather(
            *[self._check_health_cached(n) for n in self._providers],
            return_exceptions=False,
        )
        return dict(zip(self._providers.keys(), results))

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------

    async def get_provider(self, name: str) -> Optional[BaseProvider]:
        """Return the named provider if registered and available, else None."""
        provider = self._providers.get(name)
        if provider is None:
            logger.debug("Provider not found: %s", name)
            return None
        if not await self._check_health_cached(name):
            logger.warning("Provider %s is unavailable", name)
            return None
        return provider

    async def get_provider_for_request(
        self,
        provider_name: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Optional[BaseProvider]:
        """
        Return the best provider for a request, applying:

        1. Explicit ``provider_name`` argument (highest priority)
        2. Per-conversation override from ``conversation_id``
        3. Fallback chain order
        4. Any remaining registered provider

        Returns None only if every registered provider is unreachable.
        """
        # Build candidate list in priority order
        candidates: List[str] = []
        if provider_name:
            candidates.append(provider_name)
        if conversation_id:
            conv_pref = self._conversation_overrides.get(conversation_id)
            if conv_pref and conv_pref not in candidates:
                candidates.append(conv_pref)
        for name in self._fallback_chain:
            if name not in candidates:
                candidates.append(name)
        for name in self._providers:
            if name not in candidates:
                candidates.append(name)

        for name in candidates:
            provider = await self.get_provider(name)
            if provider is not None:
                return provider

        logger.error("All providers unavailable or not configured")
        return None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_providers(self) -> List[Dict[str, object]]:
        """Return a serialisable summary of registered providers."""
        return [
            {
                "name": name,
                "class": type(p).__name__,
            }
            for name, p in self._providers.items()
        ]

    def get_stats(self) -> Dict[str, object]:
        """Aggregate stats across all registered providers."""
        return {
            "providers": {n: p.get_stats() for n, p in self._providers.items()},
            "fallback_chain": list(self._fallback_chain),
        }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_registry_instance: Optional[ProviderRegistry] = None
_registry_lock = asyncio.Lock()


def get_provider_registry() -> ProviderRegistry:
    """
    Return the process-level ProviderRegistry singleton.

    The first caller triggers lazy initialisation of default providers from the
    SSOT config.  Use ``initialize_default_providers()`` explicitly during
    application startup to control when this happens and to catch errors early.
    """
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ProviderRegistry()
        _populate_default_providers(_registry_instance)
    return _registry_instance


def _populate_default_providers(registry: ProviderRegistry) -> None:
    """
    Register provider instances based on available configuration.

    Providers are registered only when they are enabled and (for cloud
    providers) when an API key is found.  Missing optional dependencies are
    handled gracefully so the application always starts.
    """
    import os

    from autobot_shared.ssot_config import get_config as get_ssot_config

    from .anthropic_provider import AnthropicProvider
    from .custom_openai_provider import CustomOpenAIProvider
    from .huggingface_provider import HuggingFaceProvider
    from .openai_provider import OpenAIProvider

    fallback: List[str] = []

    # Ollama (local) — always registered, highest priority
    try:
        ssot = get_ssot_config()
        ollama_url = (
            ssot.ollama_url
            if ssot
            else os.getenv("AUTOBOT_OLLAMA_ENDPOINT", "http://127.0.0.1:11434")
        )
        from llm_providers.ollama_provider import OllamaProvider

        ollama_provider = OllamaProvider(settings={"base_url": ollama_url})
        registry.register(ollama_provider)
        fallback.append(ollama_provider.provider_name)
    except Exception as exc:
        logger.debug("Ollama provider not registered: %s", exc)

    # OpenAI — registered when API key is present
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        openai_provider = OpenAIProvider(settings={"api_key": openai_key})
        registry.register(openai_provider)
        fallback.append(openai_provider.provider_name)
    else:
        logger.debug("OPENAI_API_KEY not set — OpenAI provider not registered")

    # Anthropic — registered when API key is present
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if anthropic_key:
        anthropic_provider = AnthropicProvider(settings={"api_key": anthropic_key})
        registry.register(anthropic_provider)
        fallback.append(anthropic_provider.provider_name)
    else:
        logger.debug("ANTHROPIC_API_KEY not set — Anthropic provider not registered")

    # HuggingFace — registered when HF token is present
    hf_token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_API_TOKEN")
    if hf_token:
        hf_provider = HuggingFaceProvider(settings={"api_token": hf_token})
        registry.register(hf_provider)
        fallback.append(hf_provider.provider_name)
    else:
        logger.debug("HF_TOKEN not set — HuggingFace provider not registered")

    # Custom OpenAI-compatible endpoint — registered when base URL is configured
    custom_url = os.getenv("CUSTOM_OPENAI_BASE_URL")
    if custom_url:
        custom_provider = CustomOpenAIProvider(
            settings={
                "base_url": custom_url,
                "api_key": os.getenv("CUSTOM_OPENAI_API_KEY", "none"),
                "default_model": os.getenv("CUSTOM_OPENAI_DEFAULT_MODEL", ""),
            }
        )
        registry.register(custom_provider)
        fallback.append(custom_provider.provider_name)
    else:
        logger.debug(
            "CUSTOM_OPENAI_BASE_URL not set — custom OpenAI provider not registered"
        )

    registry.set_fallback_chain(fallback)
    logger.info(
        "Provider registry initialised with %d providers: %s",
        len(fallback),
        fallback,
    )


__all__ = ["ProviderRegistry", "get_provider_registry"]
