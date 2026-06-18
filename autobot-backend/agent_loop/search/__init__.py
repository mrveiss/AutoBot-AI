# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pluggable web-search provider abstraction for agent research.

Mirrors the ``llm_shared`` provider-registry idiom (registration,
credential-gating, fallback chain, ``get_provider``) for web search.

Issues #9022 (SearXNG self-hosted backend) and #9023 (Brave Search API).
"""

from agent_loop.search.base import SearchResult, WebSearchProvider
from agent_loop.search.registry import (
    SearchProviderRegistry,
    get_search_registry,
)
from agent_loop.search.registry import search as registry_search

__all__ = [
    "SearchResult",
    "WebSearchProvider",
    "SearchProviderRegistry",
    "get_search_registry",
    "registry_search",
]
