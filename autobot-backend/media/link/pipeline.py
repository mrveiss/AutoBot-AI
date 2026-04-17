# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Link Processing Pipeline
# Issue #735: Organize media processing into dedicated pipelines
# Issue #932: Implement actual link/web processing

"""Link processing pipeline for web content and URLs."""

import asyncio
import ipaddress
import logging
import re
import socket
from typing import Any, Dict, List
from urllib.parse import urljoin, urlparse

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
_JINA_TIMEOUT = aiohttp.ClientTimeout(total=5) if _AIOHTTP_AVAILABLE else None
_MAX_CONTENT_LENGTH = 1_000_000  # 1 MB cap on HTML download
_USER_AGENT = "AutoBot/1.0 (media-pipeline)"
_JINA_BASE_URL = "https://r.jina.ai/"

# TLDs that are never public — rejected before DNS resolution.
_PRIVATE_TLDS = (".onion", ".internal", ".local", ".localhost", ".lan", ".home", ".corp")
# IPv6 Unique Local Address block — ipaddress.is_private already covers this,
# but we declare it explicitly for documentation.
_IPV6_ULA = ipaddress.ip_network("fc00::/7")
# Short DNS timeout to prevent the SSRF check itself from becoming a DoS vector.
_DNS_TIMEOUT_SECONDS = 2.0


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

    @staticmethod
    def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
        """Return True only if an IP address is routable on the public internet."""
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
        # IPv6 Unique Local Addresses (fc00::/7) — redundant with is_private on
        # modern Python but kept explicit as defence-in-depth.
        if isinstance(ip, ipaddress.IPv6Address) and ip in _IPV6_ULA:
            return False
        return True

    def _is_public_url(self, url: str) -> bool:
        """Return True only for public HTTP/HTTPS URLs.

        Resolves the hostname via DNS and rejects if *any* resolved address is
        private, loopback, link-local, multicast, reserved, or unspecified.
        This closes the SSRF hole where an internal hostname like
        ``intranet-db.company`` or a DNS-rebinding label like
        ``10-0-0-1.my-domain.com`` would otherwise be proxied via Jina Reader.

        Note: this performs a blocking DNS lookup; callers on the async path
        must use :meth:`_is_public_url_async` instead.
        """
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            host = (parsed.hostname or "").lower()
            if not host:
                return False
            # Reject bare private names and private TLDs outright — no DNS needed.
            if host in ("localhost",) or any(host.endswith(tld) for tld in _PRIVATE_TLDS):
                return False
            # If host is a literal IP, check directly without DNS.
            try:
                return self._ip_is_public(ipaddress.ip_address(host))
            except ValueError:
                pass
            # Resolve hostname and reject if *any* A/AAAA record is non-public.
            prev_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(_DNS_TIMEOUT_SECONDS)
            try:
                infos = socket.getaddrinfo(host, None)
            finally:
                socket.setdefaulttimeout(prev_timeout)
            if not infos:
                return False
            for info in infos:
                addr = info[4][0]
                # Strip IPv6 scope id (e.g. "fe80::1%eth0") before parsing.
                addr = addr.split("%", 1)[0]
                if not self._ip_is_public(ipaddress.ip_address(addr)):
                    return False
            return True
        except (socket.gaierror, socket.timeout, ValueError, OSError):
            # Fail closed — any failure to verify means "not public".
            return False

    async def _is_public_url_async(self, url: str) -> bool:
        """Async wrapper: run the blocking DNS check in the default executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._is_public_url, url)

    async def _try_jina(self, url: str) -> str | None:
        """Attempt to fetch URL via Jina Reader. Returns text content or None on failure."""
        jina_url = f"{_JINA_BASE_URL}{url}"
        try:
            async with aiohttp.ClientSession(timeout=_JINA_TIMEOUT) as session:
                async with session.get(jina_url, allow_redirects=True) as response:
                    if response.status == 200:
                        return await response.text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.debug("Jina Reader fast-path failed for %s: %s", url, exc)
        return None

    def _jina_result(self, url: str, content: str, metadata: Dict) -> Dict[str, Any]:
        """Build a result dict from Jina Reader plain-text response."""
        word_count = len(content.split()) if content else 0
        # Extract a title from the first non-empty line if present
        first_line = next((ln.strip() for ln in content.splitlines() if ln.strip()), "")
        title = first_line[:200] if first_line else ""
        return {
            "type": "link_fetch",
            "url": url,
            "title": title,
            "description": "",
            "content": content,
            "word_count": word_count,
            "links": [],
            "open_graph": {},
            "content_type": "text/plain",
            "confidence": 0.9 if word_count > 0 else 0.5,
            "source": "jina",
            "metadata": metadata,
        }

    async def _fetch_and_parse(self, url: str, metadata: Dict) -> Dict[str, Any]:
        """Fetch URL — tries Jina Reader fast-path first, falls back to BeautifulSoup."""
        # Fast-path: Jina Reader (public URLs only, 5-second timeout).
        # DNS resolution runs in a thread to avoid blocking the event loop.
        if await self._is_public_url_async(url):
            content = await self._try_jina(url)
            if content is not None:
                logger.debug("Jina Reader fast-path succeeded for %s", url)
                return self._jina_result(url, content, metadata)

        # Fallback: direct fetch + BeautifulSoup parse
        headers = {"User-Agent": _USER_AGENT}
        # ssl=None uses the default aiohttp SSL context (cert verification enabled).
        # Callers may pass metadata={"allow_self_signed": True} to opt-in to skipping
        # cert verification for known-safe internal URLs.
        ssl_context = False if metadata.get("allow_self_signed") else None
        try:
            async with aiohttp.ClientSession(
                headers=headers, timeout=_DEFAULT_TIMEOUT
            ) as session:
                async with session.get(
                    url, allow_redirects=True, ssl=ssl_context
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
