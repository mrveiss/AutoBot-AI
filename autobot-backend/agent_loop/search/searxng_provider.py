# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SearXNG self-hosted meta-search provider (#9022).

Privacy-preserving search: queries a user-run SearXNG instance via its JSON
API. No API key required — only the instance URL. Supports instances behind
HTTP Basic auth or a bearer/token header, and per-search engine categories
(general / news / code / academic). Credential-gated: empty URL = disabled.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import aiohttp

from agent_loop.search.base import (
    CATEGORY_ACADEMIC,
    CATEGORY_CODE,
    CATEGORY_GENERAL,
    CATEGORY_NEWS,
    DEFAULT_RESULT_COUNT,
    SearchResult,
    WebSearchProvider,
)
from autobot_shared.http_client import get_http_client

logger = logging.getLogger(__name__)

# Map normalized categories onto SearXNG ``categories`` query values.
_CATEGORY_MAP = {
    CATEGORY_GENERAL: "general",
    CATEGORY_NEWS: "news",
    CATEGORY_CODE: "it",
    CATEGORY_ACADEMIC: "science",
}

_REQUEST_TIMEOUT_S = 15


class SearXNGSearchProvider(WebSearchProvider):
    """Search backend backed by a self-hosted SearXNG instance."""

    provider_name = "searxng"

    def __init__(self, settings: Optional[Dict[str, Any]] = None) -> None:
        """Init from settings: ``instance_url`` (required), optional auth."""
        super().__init__(settings)
        self.instance_url: str = str(self._get_setting("instance_url", "")).rstrip("/")
        self.basic_auth_user: str = str(self._get_setting("basic_auth_user", ""))
        self.basic_auth_pass: str = str(self._get_setting("basic_auth_pass", ""))
        self.token: str = str(self._get_setting("token", ""))

    async def is_available(self) -> bool:
        """Available when an instance URL is configured."""
        return bool(self.instance_url)

    def _build_headers(self) -> Dict[str, str]:
        """Bearer-token header for instances fronted by token auth."""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    def _build_auth(self) -> Optional[aiohttp.BasicAuth]:
        """HTTP Basic auth when user/pass are configured."""
        if self.basic_auth_user:
            return aiohttp.BasicAuth(self.basic_auth_user, self.basic_auth_pass)
        return None

    def _build_params(self, query: str, category: Optional[str]) -> Dict[str, str]:
        """Assemble the SearXNG JSON-API query parameters."""
        params = {"q": query, "format": "json"}
        mapped = _CATEGORY_MAP.get(category or CATEGORY_GENERAL)
        if mapped:
            params["categories"] = mapped
        return params

    async def search(
        self,
        query: str,
        *,
        category: Optional[str] = None,
        count: int = DEFAULT_RESULT_COUNT,
    ) -> List[SearchResult]:
        """Query the SearXNG instance; raise on unreachable for fallback."""
        if not self.instance_url:
            raise RuntimeError("SearXNG instance_url not configured")

        url = f"{self.instance_url}/search"
        timeout = aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT_S)
        client = get_http_client()
        async with await client.get(
            url,
            params=self._build_params(query, category),
            headers=self._build_headers(),
            auth=self._build_auth(),
            timeout=timeout,
        ) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"SearXNG HTTP {resp.status}: {body[:200]}")
            data = await resp.json()

        return self._normalize(data, count)

    @staticmethod
    def _normalize(data: Dict[str, Any], count: int) -> List[SearchResult]:
        """Turn the SearXNG JSON payload into normalized results."""
        results: List[SearchResult] = []
        for item in data.get("results", [])[:count]:
            results.append(
                SearchResult(
                    title=item.get("title", "") or "",
                    url=item.get("url", "") or "",
                    snippet=item.get("content", "") or "",
                    freshness=item.get("publishedDate"),
                    source=item.get("engine"),
                )
            )
        return results
