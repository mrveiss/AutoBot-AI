# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Provider Health Manager - Orchestrates health checks across all providers
"""

import asyncio
import logging
import time
from typing import Dict, Optional

from .base import ProviderHealthResult, ProviderStatus
from .providers import (
    AnthropicHealth,
    GoogleHealth,
    LMStudioHealth,
    OllamaHealth,
    OpenAIHealth,
    VLLMHealth,
)

logger = logging.getLogger(__name__)


class ProviderHealthManager:
    """
    Manages health checking for all LLM providers (Issue #746)

    Features:
    - Parallel health checking for all providers
    - 30-second in-memory cache to avoid excessive checks
    - Automatic provider registry
    - Thread-safe caching with asyncio.Lock

    Supported Providers:
    - ollama: Local Ollama service
    - openai: OpenAI API
    - anthropic: Anthropic Claude API
    - google: Google Gemini API
    - lmstudio: LM Studio local server
    - vllm: vLLM inference server
    """

    # Cache structure: {provider_name: {"result": ProviderHealthResult, "timestamp": float}}
    _cache: Dict[str, Dict] = {}
    _cache_ttl: float = 30.0  # 30 seconds

    # Thread-safety lock for cache operations
    _cache_lock: asyncio.Lock = None

    # Provider instances (singleton pattern)
    _providers: Dict[str, any] = None

    @classmethod
    def _initialize_providers(cls):
        """Initialize all provider health checkers (singleton)"""
        if cls._providers is None:
            cls._providers = {
                "ollama": OllamaHealth(),
                "openai": OpenAIHealth(),
                "anthropic": AnthropicHealth(),
                "google": GoogleHealth(),
                "lmstudio": LMStudioHealth(),
                "vllm": VLLMHealth(),
            }
        return cls._providers

    @classmethod
    def _initialize_cache_lock(cls):
        """Initialize cache lock (singleton)"""
        if cls._cache_lock is None:
            cls._cache_lock = asyncio.Lock()
        return cls._cache_lock

    @classmethod
    async def check_provider_health(
        cls,
        provider: str,
        timeout: float = 5.0,
        use_cache: bool = True,
    ) -> ProviderHealthResult:
        """
        Check health of a specific provider

        Args:
            provider: Provider name (ollama, openai, anthropic, google)
            timeout: Maximum time to wait for health check
            use_cache: Whether to use cached results (default True)

        Returns:
            ProviderHealthResult with health status
        """
        # Initialize providers if needed
        providers = cls._initialize_providers()

        # Validate provider exists
        if provider not in providers:
            return ProviderHealthResult(
                status=ProviderStatus.UNKNOWN,
                available=False,
                message=f"Unknown provider: {provider}",
                response_time=0.0,
                provider=provider,
            )

        # Initialize cache lock
        cls._initialize_cache_lock()

        # Check cache if enabled (with lock for thread-safety)
        if use_cache:
            async with cls._cache_lock:
                cached = cls._get_from_cache(provider)
                if cached:
                    logger.debug("Using cached health status for %s", provider)
                    return cached

        # Perform health check
        try:
            provider_checker = providers[provider]
            result = await provider_checker.check_health(timeout=timeout)

            # Cache the result (with lock for thread-safety)
            async with cls._cache_lock:
                cls._store_in_cache(provider, result)

            return result

        except Exception as e:
            logger.error("Error checking %s health: %s", provider, str(e))
            return ProviderHealthResult(
                status=ProviderStatus.UNKNOWN,
                available=False,
                message=f"Health check failed: {str(e)}",
                response_time=0.0,
                provider=provider,
                details={"error": str(e)},
            )

    @classmethod
    async def check_all_providers(
        cls,
        timeout: float = 5.0,
        use_cache: bool = True,
    ) -> Dict[str, ProviderHealthResult]:
        """
        Check health of all providers in parallel

        Args:
            timeout: Maximum time to wait for each health check
            use_cache: Whether to use cached results (default True)

        Returns:
            Dictionary mapping provider names to their health results
        """
        providers = cls._initialize_providers()

        # Create tasks for all providers
        tasks = {
            provider: cls.check_provider_health(provider, timeout, use_cache)
            for provider in providers
        }

        # Execute all checks in parallel
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        # Map results back to provider names
        health_status = {}
        for provider, result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error(
                    f"Provider {provider} health check raised exception: {str(result)}"
                )
                health_status[provider] = ProviderHealthResult(
                    status=ProviderStatus.UNKNOWN,
                    available=False,
                    message=f"Health check exception: {str(result)}",
                    response_time=0.0,
                    provider=provider,
                )
            else:
                health_status[provider] = result

        return health_status

    @classmethod
    def _get_from_cache(cls, provider: str) -> Optional[ProviderHealthResult]:
        """
        Get cached health result if available and not expired

        Args:
            provider: Provider name

        Returns:
            Cached ProviderHealthResult or None if not cached/expired
        """
        if provider not in cls._cache:
            return None

        cached_entry = cls._cache[provider]
        timestamp = cached_entry.get("timestamp", 0)
        current_time = time.time()

        # Check if cache is still valid
        if current_time - timestamp < cls._cache_ttl:
            return cached_entry.get("result")

        # Cache expired, remove it
        del cls._cache[provider]
        return None

    @classmethod
    def _store_in_cache(cls, provider: str, result: ProviderHealthResult):
        """
        Store health result in cache

        Args:
            provider: Provider name
            result: Health check result to cache
        """
        cls._cache[provider] = {
            "result": result,
            "timestamp": time.time(),
        }

    @classmethod
    async def clear_cache(cls, provider: Optional[str] = None):
        """
        Clear cached health results (thread-safe)

        Args:
            provider: Specific provider to clear, or None to clear all
        """
        cls._initialize_cache_lock()

        async with cls._cache_lock:
            if provider:
                if provider in cls._cache:
                    del cls._cache[provider]
                    logger.debug("Cleared cache for provider: %s", provider)
            else:
                cls._cache.clear()
                logger.debug("Cleared all provider health caches")

    @classmethod
    def get_cache_stats(cls) -> Dict[str, any]:
        """
        Get cache statistics for monitoring

        Returns:
            Dictionary with cache statistics
        """
        current_time = time.time()
        cached_providers = []

        for provider, entry in cls._cache.items():
            age = current_time - entry.get("timestamp", 0)
            if age < cls._cache_ttl:
                cached_providers.append(
                    {
                        "provider": provider,
                        "age_seconds": round(age, 2),
                        "expires_in": round(cls._cache_ttl - age, 2),
                    }
                )

        return {
            "total_cached": len(cached_providers),
            "cache_ttl": cls._cache_ttl,
            "cached_providers": cached_providers,
        }
