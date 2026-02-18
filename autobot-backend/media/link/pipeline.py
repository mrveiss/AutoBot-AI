# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Link Processing Pipeline
# Issue #735: Organize media processing into dedicated pipelines
# Issue #932: Implement actual link/web processing

"""Link processing pipeline for web content and URLs."""

import logging
import re
from typing import Any, Dict, List
from urllib.parse import urljoin

from media.core.pipeline import BasePipeline
from media.core.types import MediaInput, MediaType, ProcessingResult

# aiohttp for async HTTP
try:
    import aiohttp

    _AIOHTTP_AVAILABLE = True
except ImportError:
    _AIOHTTP_AVAILABLE = False

# BeautifulSoup for HTML parsing
try:
    from bs4 import BeautifulSoup

    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = aiohttp.ClientTimeout(total=15) if _AIOHTTP_AVAILABLE else None
_MAX_CONTENT_LENGTH = 1_000_000  # 1 MB cap on HTML download
_USER_AGENT = "AutoBot/1.0 (media-pipeline)"


class LinkPipeline(BasePipeline):
    """Pipeline for processing web links and URLs."""

    def __init__(self):
        """Initialize link processing pipeline."""
        super().__init__(
            pipeline_name="link",
            supported_types=[MediaType.LINK],
        )

    async def _process_impl(self, media_input: MediaInput) -> ProcessingResult:
        """Process link content."""
        result_data = await self._process_link(media_input)
        confidence = self._calculate_confidence(result_data)

        return ProcessingResult(
            result_id=f"link_{media_input.media_id}",
            media_id=media_input.media_id,
            media_type=media_input.media_type,
            intent=media_input.intent,
            success=True,
            confidence=confidence,
            result_data=result_data,
            processing_time=0.0,  # Set by BasePipeline
        )

    async def _process_link(self, media_input: MediaInput) -> Dict[str, Any]:
        """Fetch and parse the URL from media_input.data."""
        url = media_input.data if isinstance(media_input.data, str) else ""
        if not url:
            return self._error_result("", "No URL provided", media_input.metadata)

        if not _AIOHTTP_AVAILABLE or not _BS4_AVAILABLE:
            missing = []
            if not _AIOHTTP_AVAILABLE:
                missing.append("aiohttp")
            if not _BS4_AVAILABLE:
                missing.append("beautifulsoup4")
            return self._unavailable_result(url, missing, media_input.metadata)

        return await self._fetch_and_parse(url, media_input.metadata)

    # ------------------------------------------------------------------
    # HTTP fetch
    # ------------------------------------------------------------------

    async def _fetch_and_parse(self, url: str, metadata: Dict) -> Dict[str, Any]:
        """Fetch URL and parse the HTML response."""
        headers = {"User-Agent": _USER_AGENT}
        try:
            async with aiohttp.ClientSession(
                headers=headers, timeout=_DEFAULT_TIMEOUT
            ) as session:
                async with session.get(
                    url, allow_redirects=True, ssl=False
                ) as response:
                    final_url = str(response.url)
                    content_type = response.headers.get("Content-Type", "")
                    raw_html = await response.text(encoding="utf-8", errors="replace")
                    status = response.status

            if status >= 400:
                return self._error_result(
                    url,
                    f"HTTP {status} for {url}",
                    metadata,
                )
            return self._parse_html(raw_html, final_url, content_type, metadata)

        except aiohttp.ClientConnectorError as exc:
            logger.warning("Link pipeline connection error: %s", exc)
            return self._error_result(url, f"Connection error: {exc}", metadata)
        except aiohttp.ClientError as exc:
            logger.warning("Link pipeline HTTP error: %s", exc)
            return self._error_result(url, str(exc), metadata)

    # ------------------------------------------------------------------
    # HTML parsing
    # ------------------------------------------------------------------

    def _parse_html(
        self,
        html: str,
        url: str,
        content_type: str,
        metadata: Dict,
    ) -> Dict[str, Any]:
        """Parse HTML with BeautifulSoup and extract structured content."""
        soup = BeautifulSoup(html, "html.parser")

        title = self._extract_title(soup)
        description = self._extract_description(soup)
        main_text = self._extract_main_text(soup)
        links = self._extract_links(soup, url)
        og_data = self._extract_open_graph(soup)

        word_count = len(main_text.split()) if main_text else 0
        confidence = 0.9 if main_text else 0.5

        return {
            "type": "link_fetch",
            "url": url,
            "title": title,
            "description": description,
            "content": main_text,
            "word_count": word_count,
            "links": links[:50],  # Cap at 50 outbound links
            "open_graph": og_data,
            "content_type": content_type,
            "confidence": confidence,
            "metadata": metadata,
        }

    def _extract_title(self, soup: Any) -> str:
        """Extract page title from <title> or og:title."""
        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            return og_title["content"].strip()
        title_tag = soup.find("title")
        return title_tag.get_text(strip=True) if title_tag else ""

    def _extract_description(self, soup: Any) -> str:
        """Extract meta description or og:description."""
        for attrs in [
            {"property": "og:description"},
            {"name": "description"},
        ]:
            tag = soup.find("meta", attrs=attrs)
            if tag and tag.get("content"):
                return tag["content"].strip()
        return ""

    def _extract_main_text(self, soup: Any) -> str:
        """Extract readable main text, removing boilerplate tags."""
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()

        # Prefer <article> or <main> content if present
        main = soup.find("article") or soup.find("main") or soup.find("body")
        if main is None:
            return ""

        text = main.get_text(separator=" ", strip=True)
        # Collapse whitespace
        return re.sub(r"\s{2,}", " ", text).strip()

    def _extract_links(self, soup: Any, base_url: str) -> List[Dict[str, str]]:
        """Extract and resolve all <a href> links on the page."""
        links = []
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            resolved = urljoin(base_url, href)
            text = anchor.get_text(strip=True)
            links.append({"url": resolved, "text": text[:200]})
        return links

    def _extract_open_graph(self, soup: Any) -> Dict[str, str]:
        """Extract Open Graph metadata tags."""
        og: Dict[str, str] = {}
        for tag in soup.find_all("meta", property=re.compile(r"^og:")):
            key = tag.get("property", "")[3:]  # strip "og:"
            content = tag.get("content", "")
            if key and content:
                og[key] = content
        return og

    # ------------------------------------------------------------------
    # Error/fallback helpers
    # ------------------------------------------------------------------

    def _unavailable_result(
        self, url: str, missing_libs: List[str], metadata: Dict
    ) -> Dict[str, Any]:
        """Return structured result when dependencies are missing."""
        reason = f"Missing libraries: {', '.join(missing_libs)}"
        logger.warning("Link pipeline unavailable: %s", reason)
        return {
            "type": "link_fetch",
            "url": url,
            "title": "",
            "content": "",
            "links": [],
            "processing_status": "unavailable",
            "unavailability_reason": reason,
            "confidence": 0.0,
            "metadata": metadata,
        }

    def _error_result(self, url: str, error: str, metadata: Dict) -> Dict[str, Any]:
        """Return structured result on fetch/parse error."""
        return {
            "type": "link_fetch",
            "url": url,
            "title": "",
            "content": "",
            "links": [],
            "processing_status": "error",
            "error": error,
            "confidence": 0.0,
            "metadata": metadata,
        }

    def _calculate_confidence(self, result_data: Dict[str, Any]) -> float:
        """Calculate confidence score from result data."""
        return result_data.get("confidence", 0.5)
