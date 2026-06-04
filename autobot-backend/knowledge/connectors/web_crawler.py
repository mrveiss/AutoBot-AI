# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Web Crawler Connector

Issue #1254: Ingests content from web URLs using the web_fetch foundation package.
Issue #7402: Wire dead ``max_depth`` parameter to Frontier + RobotsCache + WebFetcher.
Issue #8144: Migrated HTTP fetches to use AbstractConnector.fetch_with_retry() so
transient 429/5xx responses are retried with exponential backoff instead of failing.
Issue #8284: sync() override now integrates #8146 checkpoint (read/write/clear).
Issue #8286: Connection-level failures (status_code=None) now also raise RetryableError.
Issue #8152: Added config_version=2 and migrate_config() (v1→v2: max_depth→crawl_depth).
"""

import hashlib
import os
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import List
from urllib.parse import urlparse

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from knowledge.connectors.base import AbstractConnector, RetryableError
from knowledge.connectors.models import (
    ChangeInfo,
    ConnectorConfig,
    ContentResult,
    SourceInfo,
    SyncResult,
)
from knowledge.connectors.registry import ConnectorRegistry
from web_fetch import ERR_CONNECTION, FetchResult, Frontier, RenderMode, RobotsCache, WebFetcher
from web_fetch.extractors import extract_markdown
from web_fetch.frontier import extract_links

logger = get_logger(__name__)


def _url_to_source_id(url: str) -> str:
    """Derive a stable, filesystem-safe source_id from a URL."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]


def _get_domain(url: str) -> str:
    """Extract the domain from *url*, or return the raw url on failure."""
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def _fetch_result_to_content(result: FetchResult, connector_id: str) -> ContentResult | None:
    """Convert a successful FetchResult to a ContentResult for KB ingestion."""
    if not result.success or not result.markdown.strip():
        return None
    source_id = _url_to_source_id(result.url)
    return ContentResult(
        source_id=source_id,
        content=result.markdown,
        content_type="text/html",
        metadata={
            "url": result.url,
            "domain": _get_domain(result.url),
            "title": result.title,
            "connector_id": connector_id,
            "source": result.source,
        },
    )


async def _ingest_results_to_kb(
    results: List[FetchResult],
    connector: "WebCrawlerConnector",
    sync_result: SyncResult,
) -> None:
    """Batch-ingest a list of FetchResult into the KB via _ingest_content."""
    for fetch_result in results:
        content = _fetch_result_to_content(fetch_result, connector.config.connector_id)
        if content is None:
            sync_result.errors.append("empty/failed: %s" % fetch_result.url)
            continue
        try:
            await connector._ingest_content(content)
            sync_result.added += 1
        except Exception as exc:
            logger.error("Ingest failed for %s: %s", fetch_result.url, exc)
            sync_result.errors.append("%s: %s" % (fetch_result.url, exc))


@ConnectorRegistry.register("web_crawler")
class WebCrawlerConnector(AbstractConnector):
    """Connector that crawls web pages using the web_fetch foundation.

    Config keys (all under ``config.config``):
        urls (list[str]): Seed URLs to crawl.
        max_depth (int): Crawl depth. Default 1 (seed URLs only).
        max_pages (int): Hard cap on pages per seed. Default 100.
        respect_robots (bool): Honour robots.txt. Default True.
        same_origin (bool): Restrict crawl to same domain. Default True.
        playwright_service_url (str): Unused legacy key (kept for compat).
    """

    connector_type = "web_crawler"
    # Issue #4421: zero-config — unauthenticated crawl via web_fetch.
    tier = 0
    # Issue #8152: v2 renamed max_depth → crawl_depth.
    config_version = 2

    @classmethod
    def output_schema(cls) -> dict:
        """Issue #8147: JSONSchema for WebCrawlerConnector ContentResult.metadata."""
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "domain": {"type": "string"},
                "title": {"type": "string"},
                "connector_id": {"type": "string"},
                "source": {"type": "string"},
            },
            "required": ["url", "domain"],
        }

    @classmethod
    def migrate_config(cls, stored_version: int, config: dict) -> dict:
        """Migrate WebCrawlerConnector config to current version (Issue #8152).

        v1→v2: renamed ``max_depth`` to ``crawl_depth``.
        """
        if stored_version < 2:
            if "max_depth" in config and "crawl_depth" not in config:
                config["crawl_depth"] = config.pop("max_depth")
        return config

    @property
    def max_concurrency(self) -> int:
        """Issue #8148: default 5 concurrent page fetches; config overrides."""
        cfg_val = self.config.max_concurrency
        return cfg_val if cfg_val is not None else 5

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        cfg = config.config
        self._seed_urls: List[str] = cfg.get("urls", [])
        self._max_depth: int = int(cfg.get("crawl_depth", cfg.get("max_depth", 1)))
        self._max_pages: int = int(cfg.get("max_pages", 100))
        self._respect_robots: bool = bool(cfg.get("respect_robots", True))
        self._same_origin: bool = bool(cfg.get("same_origin", True))

    # ------------------------------------------------------------------
    # AbstractConnector interface
    # ------------------------------------------------------------------

    async def test_connection(self) -> bool:
        """Check that at least one seed URL is reachable via web_fetch."""
        if not self._seed_urls:
            return False
        url = self._seed_urls[0]

        async def _do_fetch():
            r = await WebFetcher.fetch(url)
            if not r.success and (r.status_code is None or r.status_code in (429, 500, 502, 503, 504)):
                raise RetryableError("HTTP %s" % (r.status_code or "connection error"), r.status_code or 0)
            return r

        try:
            result = await self.fetch_with_retry(_do_fetch)
            if result.success:
                self.logger.info("web_fetch connectivity OK for %s", url)
                return True
            self.logger.warning("web_fetch connectivity check failed: %s", result.error_code)
            return False
        except Exception:
            return False
        result = await WebFetcher.fetch(self._seed_urls[0])
        if result.success:
            self.logger.info("web_fetch connectivity OK for %s", self._seed_urls[0])
            return True
        self.logger.warning("web_fetch connectivity check failed: %s", result.error_code)
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
                    last_modified=now_utc(),
                    metadata={"url": url, "domain": domain},
                )
            )
        return sources

    async def fetch_content(self, source_id: str) -> ContentResult | None:
        """Fetch a single seed URL by source_id (depth=1 backward-compat path)."""
        url = self._find_url_for_source_id(source_id)
        if url is None:
            self.logger.warning("No URL found for source_id: %s", source_id)
            return None

        async def _do_fetch():
            r = await WebFetcher.fetch(url)
            if not r.success and (r.status_code is None or r.status_code in (429, 500, 502, 503, 504)):
                raise RetryableError("HTTP %s" % (r.status_code or "connection error"), r.status_code or 0)
            return r

        try:
            result = await self.fetch_with_retry(_do_fetch)
        except Exception:
            return None
        return _fetch_result_to_content(result, self.config.connector_id)

    async def detect_changes(self, since: datetime | None = None) -> List[ChangeInfo]:
        """Return all seed URLs as 'added' changes (crawl runs via sync override)."""
        changes: List[ChangeInfo] = []
        for url in self._seed_urls:
            source_id = _url_to_source_id(url)
            changes.append(
                ChangeInfo(
                    source_id=source_id,
                    change_type="added",
                    timestamp=now_utc(),
                    details={"url": url},
                )
            )
        return changes

    async def sync(self, incremental: bool = True) -> SyncResult:
        """Override base sync to run full BFS crawl via crawl().

        Calls ``crawl()`` with config-driven depth and ingests all results.
        Integrates the #8146 checkpoint so crash-resume skips already-crawled
        seeds and full-refresh (incremental=False) restarts from scratch (#8284).
        """
        from datetime import datetime as _dt

        started_at = _dt.utcnow()
        result = SyncResult(
            connector_id=self.config.connector_id,
            started_at=started_at,
            completed_at=None,
            status="failed",
        )

        if not incremental:
            await self._clear_checkpoint()

        already_processed = await self._read_checkpoint()
        pending_seeds = [url for url in self._seed_urls if _url_to_source_id(url) not in already_processed]
        if already_processed:
            result.resumed_from_checkpoint = True
            self.logger.info(
                "WebCrawlerConnector %s resuming from checkpoint (%d seeds already processed)",
                self.config.connector_id,
                len(already_processed),
            )

        try:

            async def _on_seed_done(url: str) -> None:
                await self._write_checkpoint(_url_to_source_id(url))

            fetched = await self.crawl(
                seed_urls=pending_seeds,
                max_depth=self._max_depth,
                max_pages=self._max_pages,
                respect_robots=self._respect_robots,
                ingest=False,
                same_origin=self._same_origin,
                on_seed_complete=_on_seed_done,
            )
            await _ingest_results_to_kb(fetched, self, result)
            result.status = "success" if not result.errors else "partial"
            if result.status == "success":
                await self._clear_checkpoint()
            self.logger.info(
                "WebCrawlerConnector sync complete: %d pages fetched, %d ingested, %d errors",
                len(fetched),
                result.added,
                len(result.errors),
            )
        except Exception as exc:
            self.logger.error("WebCrawlerConnector sync failed: %s", exc)
            result.errors.append(str(exc))
            result.status = "failed"
        finally:
            result.completed_at = _dt.utcnow()
        return result

    # ------------------------------------------------------------------
    # Core crawl API (Issue #7402)
    # ------------------------------------------------------------------

    async def crawl(
        self,
        seed_urls: List[str],
        max_depth: int = 1,
        max_pages: int = 100,
        respect_robots: bool = True,
        ingest: bool = True,
        same_origin: bool = True,
        on_seed_complete: Callable[[str], Awaitable[None]] | None = None,
    ) -> List[FetchResult]:
        """BFS crawl starting from *seed_urls*.

        Uses web_fetch.Frontier for BFS queue/dedup, web_fetch.RobotsCache
        for per-domain robots.txt enforcement, and ``WebFetcher.fetch_raw_html``
        for every URL (single request yields both HTML for link extraction and
        content for KB ingest).

        Args:
            seed_urls: Starting URLs. Each gets its own Frontier instance.
            max_depth: How many link-hops to follow (1 = seed URLs only).
            max_pages: Hard cap on total pages fetched across all seeds.
            respect_robots: When True, skip URLs disallowed by robots.txt.
            ingest: When True, write successful pages to the KB.
            same_origin: When True, restrict crawl to same scheme+host per seed.

        Returns:
            List of FetchResult (successful + failed pages encountered).
        """
        robots_cache = await self._build_robots_cache(respect_robots)
        fetcher = WebFetcher(robots_cache=robots_cache if respect_robots else None)

        all_results: List[FetchResult] = []
        pages_remaining = max_pages

        for seed in seed_urls:
            if pages_remaining <= 0:
                break
            seed_results = await self._crawl_seed(seed, max_depth, pages_remaining, same_origin, fetcher)
            all_results.extend(seed_results)
            pages_remaining -= len(seed_results)
            if on_seed_complete is not None:
                await on_seed_complete(seed)

        if ingest:
            sync_result = SyncResult(
                connector_id=self.config.connector_id,
                started_at=now_utc(),
                completed_at=None,
                status="running",
            )
            await _ingest_results_to_kb(all_results, self, sync_result)

        return all_results

    async def _build_robots_cache(self, respect_robots: bool) -> RobotsCache | None:
        """Return a RobotsCache backed by Redis, or None when robots disabled."""
        if not respect_robots:
            return None
        try:
            from autobot_shared.redis_client import get_async_redis_client

            redis = await get_async_redis_client()
            return RobotsCache(redis_client=redis)
        except Exception as exc:
            self.logger.warning("Could not get Redis for RobotsCache — using in-memory only: %s", exc)
            return RobotsCache()

    async def _crawl_seed(
        self,
        seed: str,
        max_depth: int,
        max_pages: int,
        same_origin: bool,
        fetcher: WebFetcher,
    ) -> List[FetchResult]:
        """Run BFS crawl for a single seed URL; return all FetchResults.

        ``max_depth`` follows the connector convention: 1 = seeds only, 2 = seeds
        + one hop, N = N-1 hops from the seed.  Internally the Frontier receives
        ``max_depth - 1`` so that depth=0 (seed) is the only level visited when
        max_depth=1, preserving the pre-#7402 default behaviour.

        Uses _fetch_page_with_html to obtain raw HTML for both link extraction
        and markdown conversion in a single HTTP request per URL.
        """
        frontier_depth = max(0, max_depth - 1)
        frontier = Frontier(seed, max_pages=max_pages, max_depth=frontier_depth, same_origin=same_origin)
        results: List[FetchResult] = []

        while (item := frontier.next()) is not None:
            url, depth = item
            fetch_result, raw_html = await self._fetch_page_with_html(fetcher, url)
            results.append(fetch_result)
            if fetch_result.success and raw_html and depth < frontier_depth:
                links = extract_links(raw_html, url, same_origin_only=same_origin)
                frontier.add_links(links, depth + 1)
            self.logger.debug("crawl: %s depth=%d success=%s", url, depth, fetch_result.success)

        self.logger.info(
            "Crawl complete for seed %s: %d pages emitted, %d visited",
            seed,
            frontier.pages_emitted,
            frontier.visited_count,
        )
        return results

    async def _fetch_page_with_html(self, fetcher: WebFetcher, url: str) -> tuple:
        """Fetch a page via bs4; return (FetchResult, raw_html_str).

        Using bs4 directly yields the raw HTML needed for extract_links and
        avoids a second HTTP request.  The robots check uses the fetcher's
        embedded RobotsCache so respect_robots is still honoured.  Transient
        HTTP errors (429/5xx) are retried via fetch_with_retry() (Issue #8144).

        Returns (FetchResult(success=False, ...), "") on any error.
        """
        if fetcher._robots is not None:
            if not await fetcher._robots.is_allowed(url):
                return FetchResult(url=url, success=False, error_code="robots_blocked"), ""

        async def _do_fetch():
            h, s = await WebFetcher.fetch_raw_html(url, timeout=30.0)
            if s is None or s in (429, 500, 502, 503, 504):
                raise RetryableError("HTTP %s" % (s or "connection error"), s or 0)
            return h, s

        try:
            html, status = await self.fetch_with_retry(_do_fetch)
        except RetryableError as exc:
            return FetchResult(url=url, success=False, error_code=ERR_CONNECTION, status_code=exc.status_code), ""
        except Exception:
            return FetchResult(url=url, success=False, error_code=ERR_CONNECTION), ""

        if html is None or status is None or status >= 400:
            return (
                FetchResult(url=url, success=False, error_code=ERR_CONNECTION, status_code=status),
                "",
            )

        title, markdown = extract_markdown(html)
        fetch_result = FetchResult(
            url=url,
            success=True,
            markdown=markdown,
            title=title,
            render_mode=RenderMode.FAST,
            source="bs4",
            status_code=status,
        )
        return fetch_result, html

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _find_url_for_source_id(self, source_id: str) -> str | None:
        """Return the URL that corresponds to *source_id* from seed list."""
        for url in self._seed_urls:
            if _url_to_source_id(url) == source_id:
                return url
        return None

    @staticmethod
    def _default_playwright_url() -> str:
        """Legacy helper — kept for compat with existing config readers."""
        try:
            from utils.service_registry import get_service_url

            return get_service_url("playwright-vnc")
        except Exception:
            from constants.network_constants import NetworkConstants

            return f"http://{os.environ.get('AUTOBOT_BROWSER_SERVICE_HOST', '')}:{NetworkConstants.BROWSER_SERVICE_PORT}"  # ssot-config-exempt: fallback path, empty-string default differs from config  # noqa: E501
