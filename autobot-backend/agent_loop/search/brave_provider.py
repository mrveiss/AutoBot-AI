# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Brave Search API provider (#9023).

Independent search index for agent research diversity. Uses the REST API with
an ``X-Subscription-Token`` header (key from the secrets/config system). Web and
News endpoints are supported; 429/quota errors are surfaced as ``RuntimeError``
so the registry can fall back gracefully. Credential-gated: empty key = disabled.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from agent_loop.search.base import (
    CATEGORY_NEWS,
    DEFAULT_RESULT_COUNT,
    SearchResult,
    WebSearchProvider,
)
from autobot_shared.http_client import get_http_client

logger = logging.getLogger(__name__)

_WEB_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
_NEWS_ENDPOINT = "https://api.search.brave.com/res/v1/news/search"
_REQUEST_TIMEOUT_S = 15


class BraveSearchProvider(WebSearchProvider):
    """Search backend backed by the Brave Search API."""

    provider_name = "brave"

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        """Init from settings: ``api_key`` (required, from secrets/config)."""
        super().__init__(settings)
        self.api_key: str = str(self._get_setting("api_key", ""))

    async def is_available(self) -> bool:
        """Available when an API key is configured."""
        return bool(self.api_key)

    def _build_headers(self) -> Dict[str, str]:
        """Brave auth + JSON accept headers."""
        return {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }

    @staticmethod
    def _endpoint_for(category: Optional[str]) -> str:
        """Route news searches to the News endpoint, else Web."""
        if category == CATEGORY_NEWS:
            return _NEWS_ENDPOINT
        return _WEB_ENDPOINT

    async def search(
        self,
        query: str,
        *,
        category: Optional[str] = None,
        count: int = DEFAULT_RESULT_COUNT,
    ) -> List[SearchResult]:
        """Query Brave; raise on quota/error so the registry can fall back."""
        if not self.api_key:
            raise RuntimeError("Brave Search api_key not configured")

        endpoint = self._endpoint_for(category)
        params = {"q": query, "count": str(count)}
        timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
        client = get_http_client()
        async with await client.get(
            endpoint, params=params, headers=self._build_headers(), timeout=timeout
        ) as resp:
            if resp.status == 429:
                raise RuntimeError("Brave Search rate-limited (HTTP 429)")
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"Brave Search HTTP {resp.status}: {body[:200]}")
            data = await resp.json()

        return self._normalize(data, category, count)

    def _normalize(self, data: Dict[str, Any], category: Optional[str], count: int) -> List[SearchResult]:
        """Normalize Brave web/news payloads into SearchResult objects."""
        if category == CATEGORY_NEWS:
            items = data.get("results", [])
        else:
            items = (data.get("web") or {}).get("results", [])
        return [self._to_result(item) for item in items[:count]]

    @staticmethod
    def _to_result(item: Dict[str, Any]) -> SearchResult:
        """Map one Brave result item to a normalized SearchResult."""
        meta = item.get("meta_url") or {}
        return SearchResult(
            title=item.get("title", "") or "",
            url=item.get("url", "") or "",
            snippet=item.get("description", "") or "",
            freshness=item.get("age") or item.get("page_age"),
            source=meta.get("hostname"),
        )
