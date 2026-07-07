# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ContentReachSearchProvider — keyless web-search fallback via content_reach (#10932).

Wraps the ``content_reach`` ``web_search`` chain as a ``WebSearchProvider`` so it
slots into the search registry as the last-resort fallback.  No API key required;
the chain degrades gracefully through DdgsBackend → JinaSearchBackend →
BrowserSearchBackend.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from agent_loop.search.base import DEFAULT_RESULT_COUNT, SearchResult, WebSearchProvider

logger = logging.getLogger(__name__)


class ContentReachSearchProvider(WebSearchProvider):
    """Web-search provider backed by the ``content_reach`` web_search chain.

    Keyless — always registers; degrades gracefully when all backends fail.
    Returning ``[]`` on unsuccessful result is intentional: this is the last
    provider in the fallback chain, so an empty list is the safe terminal
    outcome.
    """

    provider_name = "content_reach"

    async def is_available(self) -> bool:
        """Always available — the chain is keyless and self-degrading."""
        return True

    def _ensure_registered(self, reg: Any) -> None:
        """Register the default content-reach sources if web_search chain is absent."""
        if reg.get_chain("web_search") is None:
            from content_reach.bootstrap import register_default_sources

            register_default_sources(reg)
            logger.debug("content_reach: registered default sources (defensive boot)")

    def _map_structured(
        self,
        items: List[Dict[str, Any]],
        count: int,
    ) -> List[SearchResult]:
        """Map a list of structured web-search dicts to SearchResult objects."""
        results: List[SearchResult] = []
        for r in items:
            url = r.get("href") or r.get("url") or ""
            if not url:
                continue
            results.append(
                SearchResult(
                    title=r.get("title", ""),
                    url=url,
                    snippet=(r.get("body") or r.get("snippet") or "")[:300],
                    source="content_reach",
                )
            )
            if len(results) >= count:
                break
        return results

    async def search(
        self,
        query: str,
        *,
        category: Optional[str] = None,
        count: int = DEFAULT_RESULT_COUNT,
    ) -> List[SearchResult]:
        """Fetch via content_reach web_search chain and map to SearchResult list."""
        from content_reach.base import ContentRequest
        from content_reach.registry import get_content_source_registry

        reg = get_content_source_registry()
        self._ensure_registered(reg)

        result = await reg.fetch(
            "web_search",
            ContentRequest(query=query, source="web_search", limit=count),
        )

        if not result.success:
            logger.debug(
                "content_reach web_search unsuccessful for %r: %s",
                query,
                result.metadata.get("error", ""),
            )
            return []

        structured_results = (result.structured or {}).get("results")
        if structured_results:
            return self._map_structured(structured_results, count)

        # Text-only fallback (JinaSearchBackend / BrowserSearchBackend)
        if result.url:
            return [
                SearchResult(
                    title=query,
                    url=result.url,
                    snippet=(result.text or "")[:300],
                    source="content_reach",
                )
            ]

        logger.debug("content_reach web_search returned no usable results for %r", query)
        return []
