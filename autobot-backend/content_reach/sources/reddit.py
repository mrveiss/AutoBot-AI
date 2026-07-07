# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reddit/HN content source: RedditJsonBackend → HnAlgoliaBackend → BrowserBackend (#10932).

Chain priority:
  1. RedditJsonBackend — Reddit public JSON API (no auth required)
  2. HnAlgoliaBackend  — HN Algolia search API (https://hn.algolia.com/api/v1/search)
  3. BrowserBackend    — Playwright-backed page fetch (browser required)
"""

from __future__ import annotations

import json
import logging

import httpx

from content_reach._http import http_get
from content_reach._url_guard import ensure_public_url
from content_reach.backends.browser import BrowserBackend
from content_reach.base import BackendError, ContentBackend, ContentRequest, ContentResult
from content_reach.chain import ContentSourceChain
from source_attribution import SourceReliability, SourceType

logger = logging.getLogger(__name__)

# Reddit API user-agent string.
_USER_AGENT = "autobot-content-reach/1.0"


class RedditJsonBackend(ContentBackend):
    """Reddit content backend using the public Reddit JSON API.

    probe() always returns True — liveness validated at fetch-time via circuit breaker.
    fetch() uses request.url (appending .json) when a reddit.com URL is provided,
    otherwise falls back to the Reddit search endpoint using request.query.

    Accepts an optional injected httpx.AsyncClient for testing.
    """

    name = "reddit_json"
    source_type = SourceType.REDDIT

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def probe(self) -> bool:
        """Always return True — liveness validated at fetch-time via circuit breaker."""
        return True

    async def fetch(self, request: ContentRequest) -> ContentResult:
        """Fetch Reddit posts; raise BackendError on network, HTTP, or parse failure."""
        headers = {"User-Agent": _USER_AGENT}

        if request.url and "reddit.com" in request.url:
            await ensure_public_url(request.url)
            url = request.url if request.url.endswith(".json") else request.url + ".json"
            try:
                response = await http_get(url, client=self._client, headers=headers)
            except httpx.HTTPError as exc:
                logger.debug("RedditJsonBackend: HTTP error for %r: %s", url, exc)
                raise BackendError(str(exc)) from exc
        else:
            try:
                response = await http_get(
                    "https://www.reddit.com/search.json",
                    client=self._client,
                    headers=headers,
                    params={"q": request.query, "limit": request.limit},
                )
            except httpx.HTTPError as exc:
                logger.debug("RedditJsonBackend: HTTP error for query %r: %s", request.query, exc)
                raise BackendError(str(exc)) from exc

        if response.status_code != 200:
            logger.debug("RedditJsonBackend: HTTP %s", response.status_code)
            raise BackendError(f"Reddit HTTP {response.status_code}")

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.debug("RedditJsonBackend: JSON decode error: %s", exc)
            raise BackendError("Reddit: invalid JSON response") from exc

        children = data.get("data", {}).get("children", [])
        if not children:
            raise BackendError("Reddit: no posts returned")

        posts = []
        text_lines = []
        for child in children:
            post_data = child.get("data", {})
            title = str(post_data.get("title", ""))
            selftext = str(post_data.get("selftext", ""))
            permalink = str(post_data.get("permalink", ""))
            if permalink and not permalink.startswith("http"):
                permalink = "https://www.reddit.com" + permalink
            posts.append({"title": title, "selftext": selftext, "permalink": permalink})
            if selftext:
                text_lines.append(f"{title}\n{selftext}")
            else:
                text_lines.append(title)

        return ContentResult(
            success=True,
            source_type=SourceType.REDDIT,
            backend_used=self.name,
            text="\n".join(text_lines),
            structured={"posts": posts},
            reliability=SourceReliability.MEDIUM,
        )


class HnAlgoliaBackend(ContentBackend):
    """HN content backend using the Algolia search API for Hacker News.

    probe() always returns True — pure-HTTP backend, always capable.
    fetch() searches via hn.algolia.com and maps hits to ContentResult.

    Accepts an optional injected httpx.AsyncClient for testing.
    """

    name = "hn_algolia"
    source_type = SourceType.REDDIT

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client

    async def probe(self) -> bool:
        """Always return True — pure-HTTP backend, always capable."""
        return True

    async def fetch(self, request: ContentRequest) -> ContentResult:
        """Fetch HN hits from Algolia; raise BackendError on failure."""
        try:
            response = await http_get(
                "https://hn.algolia.com/api/v1/search",
                client=self._client,
                params={"query": request.query, "hitsPerPage": request.limit},
            )
        except httpx.HTTPError as exc:
            logger.debug("HnAlgoliaBackend: HTTP error for query %r: %s", request.query, exc)
            raise BackendError(str(exc)) from exc

        if response.status_code != 200:
            logger.debug("HnAlgoliaBackend: HTTP %s", response.status_code)
            raise BackendError(f"HN Algolia HTTP {response.status_code}")

        try:
            data = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            logger.debug("HnAlgoliaBackend: JSON decode error: %s", exc)
            raise BackendError("HN Algolia: invalid JSON response") from exc

        raw_hits = data.get("hits", [])
        if not raw_hits:
            raise BackendError("HN Algolia: no hits returned")

        hits = []
        text_lines = []
        for hit in raw_hits:
            title = str(hit.get("story_title") or hit.get("title") or "")
            object_id = str(hit.get("objectID", ""))
            hn_url = f"https://news.ycombinator.com/item?id={object_id}"
            url = hit.get("url") or hn_url
            points = int(hit.get("points") or 0)
            hits.append({"title": title, "url": url, "points": points, "hn_url": hn_url})
            text_lines.append(f"{title} — {url}")

        return ContentResult(
            success=True,
            source_type=SourceType.REDDIT,
            backend_used=self.name,
            text="\n".join(text_lines),
            structured={"hits": hits},
            reliability=SourceReliability.MEDIUM,
        )


def build_reddit_chain() -> ContentSourceChain:
    """Build the reddit/HN fallback chain: reddit_json → hn_algolia → browser."""
    return ContentSourceChain(
        source="reddit",
        source_type=SourceType.REDDIT,
        backends=[RedditJsonBackend(), HnAlgoliaBackend(), BrowserBackend(SourceType.REDDIT)],
    )
