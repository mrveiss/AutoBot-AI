# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Web-search provider registry with selection + graceful fallback.

Mirrors ``llm_shared.provider_registry``: providers self-register, the registry
applies credential-gating (only registers configured providers) and a fallback
chain so an unreachable/erroring provider degrades to the next one. Both #9022
and #9023 require graceful fallback to the default provider.

Auto-population reads credentials/instance URLs from ``autobot_shared.ssot_config``
(empty/unset = provider disabled).
"""

from __future__ import annotations

import logging
import threading
from typing import Dict, List, Optional

from agent_loop.search.base import DEFAULT_RESULT_COUNT, SearchResult, WebSearchProvider

logger = logging.getLogger(__name__)


class SearchProviderRegistry:
    """Registry of web-search providers with an ordered fallback chain."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._providers: Dict[str, WebSearchProvider] = {}
        self._fallback_chain: List[str] = []

    def register(self, provider: WebSearchProvider) -> None:
        """Register a provider and append it to the fallback chain."""
        name = provider.provider_name
        if name in self._providers:
            logger.warning("Replacing existing search provider: %s", name)
        else:
            self._fallback_chain.append(name)
        self._providers[name] = provider

    def get_provider(self, name: str) -> Optional[WebSearchProvider]:
        """Return a registered provider by name (or None)."""
        return self._providers.get(name)

    def list_providers(self) -> List[str]:
        """Return registered provider names in fallback order."""
        return list(self._fallback_chain)

    def _ordered_candidates(self, preferred: Optional[str]) -> List[WebSearchProvider]:
        """Build the try-order: preferred first, then the fallback chain."""
        order: List[str] = []
        if preferred and preferred in self._providers:
            order.append(preferred)
        for name in self._fallback_chain:
            if name not in order:
                order.append(name)
        return [self._providers[name] for name in order]

    async def search(
        self,
        query: str,
        *,
        provider: Optional[str] = None,
        category: Optional[str] = None,
        count: int = DEFAULT_RESULT_COUNT,
    ) -> List[SearchResult]:
        """Search via the selected provider, falling back on error.

        Returns ``[]`` when no provider is configured or all candidates fail.
        A provider that returns ``[]`` (reachable, zero hits) is accepted as-is.
        """
        candidates = self._ordered_candidates(provider)
        if not candidates:
            logger.debug("No web-search provider configured; returning no results")
            return []

        last_error: Optional[Exception] = None
        for candidate in candidates:
            if not await candidate.is_available():
                continue
            try:
                return await candidate.search(query, category=category, count=count)
            except Exception as exc:  # graceful fallback to the next provider
                last_error = exc
                logger.warning(
                    "Search provider %s failed (%s); trying fallback",
                    candidate.provider_name,
                    exc,
                )
        if last_error:
            logger.error("All web-search providers failed; last error: %s", last_error)
        return []


_registry: Optional[SearchProviderRegistry] = None
_registry_lock = threading.Lock()


def _populate_default_providers(registry: SearchProviderRegistry) -> None:
    """Register credential-gated providers from ssot_config (#9022/#9023)."""
    # Import lazily so optional config/deps never break startup-import-smoke.
    from agent_loop.search.brave_provider import BraveSearchProvider
    from agent_loop.search.searxng_provider import SearXNGSearchProvider
    from autobot_shared.ssot_config import config

    searxng_url = getattr(config, "searxng_instance_url", "")
    if searxng_url:
        registry.register(
            SearXNGSearchProvider(
                settings={
                    "instance_url": searxng_url,
                    "basic_auth_user": getattr(config, "searxng_basic_auth_user", ""),
                    "basic_auth_pass": getattr(config, "searxng_basic_auth_pass", ""),
                    "token": getattr(config, "searxng_token", ""),
                }
            )
        )
    else:
        logger.debug("SEARXNG_INSTANCE_URL not set — SearXNG search provider not registered")

    brave_key = getattr(config, "brave_search_api_key", "")
    if brave_key:
        registry.register(BraveSearchProvider(settings={"api_key": brave_key}))
    else:
        logger.debug("BRAVE_SEARCH_API_KEY not set — Brave search provider not registered")

    from agent_loop.search.content_reach_provider import ContentReachSearchProvider

    registry.register(ContentReachSearchProvider())
    logger.debug("Registered content_reach as fallback web-search provider")


def get_search_registry() -> SearchProviderRegistry:
    """Return the process-wide registry, populating it on first use."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                registry = SearchProviderRegistry()
                try:
                    _populate_default_providers(registry)
                except Exception as exc:  # never let config issues break callers
                    logger.warning("Search provider auto-registration failed: %s", exc)
                _registry = registry
    return _registry


async def search(
    query: str,
    *,
    provider: Optional[str] = None,
    category: Optional[str] = None,
    count: int = DEFAULT_RESULT_COUNT,
) -> List[SearchResult]:
    """Module-level convenience: search via the default registry."""
    return await get_search_registry().search(query, provider=provider, category=category, count=count)
