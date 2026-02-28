# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Web Crawler Connector

Issue #1254: Ingests content from web URLs using the Playwright service
on the browser VM (.25).  Mirrors the pattern from
``agents/librarian_assistant.py``.
"""

import hashlib
import logging
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlparse

from knowledge.connectors.base import AbstractConnector
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
)
from knowledge.connectors.registry import ConnectorRegistry

logger = logging.getLogger(__name__)


def _url_to_source_id(url: str) -> str:
    """Derive a stable, filesystem-safe source_id from a URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


@ConnectorRegistry.register("web_crawler")
class WebCrawlerConnector(AbstractConnector):
    """Connector that fetches web pages via the Playwright browser service.

    Config keys (all under ``config.config``):
        urls (list[str]): Seed URLs to crawl.
        max_depth (int): Crawl depth. Default 1 (seed URLs only).
        playwright_service_url (str): Override for the Playwright service URL.
            Falls back to service registry ("playwright-vnc").
    """

    connector_type = "web_crawler"

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._seed_urls: List[str] = cfg.get("urls", [])
        self._max_depth: int = int(cfg.get("max_depth", 1))
        self._playwright_url: str = cfg.get(
            "playwright_service_url", self._default_playwright_url()
        )

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Check that the Playwright service health endpoint responds 200."""
        from autobot_shared.http_client import get_http_client

        try:
            client = get_http_client()
            async with await client.get("%s/health" % self._playwright_url) as resp:
                if resp.status == 200:
                    self.logger.info(
                        "Playwright service healthy at %s", self._playwright_url
                    )
                    return True
                self.logger.warning("Playwright health returned %s", resp.status)
                return False
        except Exception as exc:
            self.logger.error("Cannot reach Playwright service: %s", exc)
            return False

    async def discover_sources(self) -> List[SourceInfo]:
        """Return a SourceInfo entry for each seed URL (depth=1 only)."""
        sources = []
        for url in self._seed_urls:
            source_id = _url_to_source_id(url)
            domain = _get_domain(url)
            sources.append(
                SourceInfo(
                    source_id=source_id,
                    name=domain,
                    path=url,
                    content_type="text/html",
                    size_bytes=0,
                    last_modified=datetime.utcnow(),
                    metadata={"url": url, "domain": domain},
                )
            )
        return sources

    async def fetch_content(self, source_id: str) -> Optional[ContentResult]:
        """Fetch a page from the Playwright service by source_id.

        Looks up the URL from the seed list matching *source_id*.
        """
        url = self._find_url_for_source_id(source_id)
        if url is None:
            self.logger.warning("No URL found for source_id: %s", source_id)
            return None
        return await self._extract_url(url)

    async def detect_changes(
        self, since: Optional[datetime] = None
    ) -> List[ChangeInfo]:
        """Detect page changes by comparing content hash against stored hash.

        When *since* is None (first sync), all URLs are treated as 'added'.
        On subsequent syncs the stored hash is compared to freshly fetched
        content and a 'modified' change is emitted on mismatch.
        """
        from autobot_shared.redis_client import get_redis_client

        changes: List[ChangeInfo] = []

        for url in self._seed_urls:
            source_id = _url_to_source_id(url)

            if since is None:
                changes.append(
                    ChangeInfo(
                        source_id=source_id,
                        change_type="added",
                        timestamp=datetime.utcnow(),
                        details={"url": url},
                    )
                )
                continue

            # Compare stored content hash with current page hash
            changed = await self._has_content_changed(url, source_id, get_redis_client)
            if changed:
                changes.append(
                    ChangeInfo(
                        source_id=source_id,
                        change_type="modified",
                        timestamp=datetime.utcnow(),
                        details={"url": url},
                    )
                )

        return changes

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _default_playwright_url() -> str:
        """Resolve Playwright service URL from service registry."""
        try:
            from utils.service_registry import get_service_url

            return get_service_url("playwright-vnc")
        except Exception:
            return "http://172.16.168.25:3000"

    def _find_url_for_source_id(self, source_id: str) -> Optional[str]:
        """Return the URL that corresponds to *source_id* from seed list."""
        for url in self._seed_urls:
            if _url_to_source_id(url) == source_id:
                return url
        return None

    async def _extract_url(self, url: str) -> Optional[ContentResult]:
        """POST to the Playwright /extract endpoint and return ContentResult."""
        from autobot_shared.http_client import get_http_client

        source_id = _url_to_source_id(url)
        try:
            client = get_http_client()
            payload = {"url": url}
            async with await client.post(
                "%s/extract" % self._playwright_url, json=payload
            ) as resp:
                if resp.status != 200:
                    self.logger.error(
                        "Playwright /extract returned %s for %s", resp.status, url
                    )
                    return None

                data = await resp.json()

                if not data.get("success"):
                    self.logger.error(
                        "Playwright extraction failed for %s: %s",
                        url,
                        data.get("error", "unknown"),
                    )
                    return None

                content = data.get("content", "")
                domain = data.get("domain", _get_domain(url))

                return ContentResult(
                    source_id=source_id,
                    content=content,
                    content_type="text/html",
                    metadata={
                        "url": url,
                        "domain": domain,
                        "title": data.get("title", ""),
                        "content_length": data.get("content_length", len(content)),
                        "connector_id": self.config.connector_id,
                    },
                )
        except Exception as exc:
            self.logger.error("Error extracting %s: %s", url, exc)
            return None

    async def _has_content_changed(
        self, url: str, source_id: str, get_redis_client_fn
    ) -> bool:
        """Return True when the current page hash differs from the stored hash."""
        try:
            result = await self._extract_url(url)
            if result is None:
                return False

            current_hash = hashlib.sha256(result.content.encode("utf-8")).hexdigest()

            redis = get_redis_client_fn(database="knowledge")
            stored_hash_bytes = await _redis_get_async(
                redis, "connector:hash:%s" % source_id
            )
            stored_hash = (
                stored_hash_bytes.decode("utf-8")
                if isinstance(stored_hash_bytes, bytes)
                else stored_hash_bytes
            )

            if stored_hash != current_hash:
                # Update stored hash
                await _redis_set_async(
                    redis,
                    "connector:hash:%s" % source_id,
                    current_hash,
                )
                return True
            return False
        except Exception as exc:
            self.logger.warning("Hash comparison failed for %s: %s", url, exc)
            return True  # treat as changed to avoid silent data staleness


async def _redis_get_async(client, key: str):
    """Async-safe Redis GET that handles both sync and async clients."""
    import asyncio

    try:
        result = client.get(key)
        if asyncio.iscoroutine(result):
            return await result
        return result
    except Exception:
        return None


async def _redis_set_async(client, key: str, value: str) -> None:
    """Async-safe Redis SET that handles both sync and async clients."""
    import asyncio

    try:
        result = client.set(key, value)
        if asyncio.iscoroutine(result):
            await result
    except Exception:
        pass


def _get_domain(url: str) -> str:
    """Extract the domain from *url*, or return the raw url on failure."""
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url
