# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bootstrap assembler — registers all five default content-source chains (#10932)."""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger
from content_reach.registry import ContentSourceRegistry
from content_reach.sources.reddit import build_reddit_chain
from content_reach.sources.social import build_social_chain
from content_reach.sources.web_page import build_web_page_chain
from content_reach.sources.web_search import build_web_search_chain
from content_reach.sources.youtube import build_youtube_chain

logger = get_logger(__name__)

_DEFAULT_CHAIN_FACTORIES = [
    build_web_search_chain,
    build_web_page_chain,
    build_youtube_chain,
    build_reddit_chain,
    build_social_chain,
]


def register_default_sources(registry: ContentSourceRegistry) -> None:
    """Register all five default content-source chains into *registry*."""
    for factory in _DEFAULT_CHAIN_FACTORIES:
        registry.register_chain(factory())
    logger.info("content_reach: registered %d default sources", len(_DEFAULT_CHAIN_FACTORIES))


def build_default_registry() -> ContentSourceRegistry:
    """Return a fresh ContentSourceRegistry pre-loaded with all default sources."""
    registry = ContentSourceRegistry()
    register_default_sources(registry)
    return registry
