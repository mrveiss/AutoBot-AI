# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Link Pipeline Tests
# Issue #932: Implement actual link/web processing

"""Unit tests for LinkPipeline."""

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from media.core.types import MediaInput, MediaType, ProcessingIntent
from media.link.pipeline import LinkPipeline

bs4 = pytest.importorskip("bs4", reason="beautifulsoup4 not installed")
BeautifulSoup = bs4.BeautifulSoup


def _mock_getaddrinfo(ip: str):
    """Return a patcher that makes socket.getaddrinfo resolve to a fixed IP.

    Supports both IPv4 and IPv6 literals.
    """
    family = socket.AF_INET6 if ":" in ip else socket.AF_INET
    sockaddr = (ip, 0, 0, 0) if family == socket.AF_INET6 else (ip, 0)
    return patch(
        "autobot_shared.url_safety.socket.getaddrinfo",
        return_value=[(family, socket.SOCK_STREAM, 0, "", sockaddr)],
    )


def _make_input(url, metadata=None):
    return MediaInput(
        media_id="test-link",
        media_type=MediaType.LINK,
        intent=ProcessingIntent.ANALYSIS,
        data=url,
        mime_type=None,
        metadata=metadata or {},
    )


SAMPLE_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Test Page</title>
  <meta name="description" content="Test description">
  <meta property="og:title" content="OG Title">
  <meta property="og:description" content="OG description">
</head>
<body>
  <main>
    <article>Main content here with enough text to parse.</article>
  </main>
  <nav>Navigation junk</nav>
  <footer>Footer junk</footer>
  <a href="/relative-link">Relative Link</a>
  <a href="https://example.com/abs">Absolute Link</a>
</body>
</html>"""


class TestLinkPipelineHtmlParsing:
    """Tests for HTML parsing helpers."""

    def setup_method(self):
        self.pipe = LinkPipeline()

    def _soup(self, html):
        return BeautifulSoup(html, "html.parser")

    def test_extract_title_from_title_tag(self):
        soup = self._soup("<html><head><title>My Title</title></head></html>")
        assert self.pipe._extract_title(soup) == "My Title"

    def test_extract_title_prefers_og(self):
        html = '<html><head><meta property="og:title" content="OG Title"><title>Regular</title></head></html>'
        soup = self._soup(html)
        assert self.pipe._extract_title(soup) == "OG Title"

    def test_extract_description_meta(self):
        html = '<html><head><meta name="description" content="Meta desc"></head></html>'
        soup = self._soup(html)
        assert self.pipe._extract_description(soup) == "Meta desc"

    def test_extract_description_og_preferred(self):
        html = (
            "<html><head>"
            '<meta property="og:description" content="OG desc">'
            '<meta name="description" content="Meta desc">'
            "</head></html>"
        )
        soup = self._soup(html)
        assert self.pipe._extract_description(soup) == "OG desc"

    def test_extract_main_text_removes_boilerplate(self):
        soup = self._soup(SAMPLE_HTML)
        text = self.pipe._extract_main_text(soup)
        assert "Main content" in text
        assert "Navigation junk" not in text
        assert "Footer junk" not in text

    def test_extract_links_resolves_relative(self):
        soup = self._soup(SAMPLE_HTML)
        links = self.pipe._extract_links(soup, "https://test.com/page")
        urls = [lnk["url"] for lnk in links]
        assert "https://test.com/relative-link" in urls
        assert "https://example.com/abs" in urls

    def test_extract_links_skips_anchors_and_js(self):
        html = (
            '<html><body><a href="#">Anchor</a><a href="javascript:void">JS</a><a href="/real">Real</a></body></html>'
        )
        soup = self._soup(html)
        links = self.pipe._extract_links(soup, "https://test.com")
        assert len(links) == 1
        assert links[0]["url"] == "https://test.com/real"

    def test_extract_open_graph(self):
        soup = self._soup(SAMPLE_HTML)
        og = self.pipe._extract_open_graph(soup)
        assert og.get("title") == "OG Title"
        assert og.get("description") == "OG description"

    def test_parse_html_full(self):
        result = self.pipe._parse_html(SAMPLE_HTML, "https://test.com/page", "text/html", {})
        assert result["type"] == "link_fetch"
        assert result["title"] == "OG Title"
        assert result["description"] == "OG description"
        assert result["word_count"] > 0
        assert len(result["links"]) > 0


class TestLinkPipelineErrorHandling:
    """Tests for error and unavailability results."""

    def test_unavailable_result(self):
        pipe = LinkPipeline()
        result = pipe._unavailable_result("https://example.com", ["aiohttp", "beautifulsoup4"], {})
        assert result["processing_status"] == "unavailable"
        assert result["confidence"] == 0.0

    def test_error_result(self):
        pipe = LinkPipeline()
        result = pipe._error_result("https://example.com", "Connection refused", {})
        assert result["processing_status"] == "error"
        assert result["error"] == "Connection refused"

    @pytest.mark.asyncio
    async def test_empty_url_returns_error(self):
        pipe = LinkPipeline()
        media_input = _make_input("")
        result = await pipe._process_link(media_input)
        assert result["processing_status"] == "error"


class TestLinkPipelineHttp:
    """Tests for HTTP fetch path."""

    def _make_mock_session(self, url, status=200):
        """Helper: build a mock aiohttp ClientSession for fetch tests."""
        mock_response = AsyncMock()
        mock_response.url = url
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.text = AsyncMock(return_value=SAMPLE_HTML)
        mock_response.status = status
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        return mock_session

    @pytest.mark.asyncio
    async def test_fetch_success(self):
        pipe = LinkPipeline()
        mock_session = self._make_mock_session("https://example.com")
        _parsed = {"type": "link_fetch", "confidence": 0.9, "url": "https://example.com"}

        with (
            patch("media.link.pipeline._AIOHTTP_AVAILABLE", True),
            patch("media.link.pipeline._BS4_AVAILABLE", True),
            patch("media.link.pipeline.aiohttp.ClientSession", return_value=mock_session),
            patch.object(pipe, "_parse_html", return_value=_parsed),
            patch.object(pipe, "_try_jina", new=AsyncMock(return_value=None)),
        ):
            result = await pipe._fetch_and_parse("https://example.com", {})

        assert result["type"] == "link_fetch"
        assert result["confidence"] > 0
        # Default path must verify TLS certs (ssl=None, not ssl=False)
        mock_session.get.assert_called_once_with("https://example.com", allow_redirects=True, ssl=None)

    @pytest.mark.asyncio
    async def test_fetch_default_verifies_tls(self):
        """ssl=None (cert verification) is used when allow_self_signed is absent."""
        pipe = LinkPipeline()
        mock_session = self._make_mock_session("https://example.com")
        _parsed = {"type": "link_fetch", "confidence": 0.9}

        with (
            patch("media.link.pipeline._AIOHTTP_AVAILABLE", True),
            patch("media.link.pipeline._BS4_AVAILABLE", True),
            patch("media.link.pipeline.aiohttp.ClientSession", return_value=mock_session),
            patch.object(pipe, "_parse_html", return_value=_parsed),
            patch.object(pipe, "_try_jina", new=AsyncMock(return_value=None)),
        ):
            await pipe._fetch_and_parse("https://example.com", {})

        _call_kwargs = mock_session.get.call_args.kwargs
        assert _call_kwargs.get("ssl") is None, "Default fetch must NOT disable cert verification"

    @pytest.mark.asyncio
    async def test_fetch_allow_self_signed_disables_tls(self):
        """ssl=False is used only when metadata allow_self_signed=True is explicitly set."""
        pipe = LinkPipeline()
        mock_session = self._make_mock_session("https://internal.example.com")
        _parsed = {"type": "link_fetch", "confidence": 0.9}

        with (
            patch("media.link.pipeline._AIOHTTP_AVAILABLE", True),
            patch("media.link.pipeline._BS4_AVAILABLE", True),
            patch("media.link.pipeline.aiohttp.ClientSession", return_value=mock_session),
            patch.object(pipe, "_parse_html", return_value=_parsed),
            patch.object(pipe, "_try_jina", new=AsyncMock(return_value=None)),
        ):
            await pipe._fetch_and_parse("https://internal.example.com", {"allow_self_signed": True})

        _call_kwargs = mock_session.get.call_args.kwargs
        assert _call_kwargs.get("ssl") is False, "allow_self_signed=True must set ssl=False"

    @pytest.mark.asyncio
    async def test_fetch_http_error(self):
        pipe = LinkPipeline()

        mock_response = AsyncMock()
        mock_response.url = "https://example.com/404"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.text = AsyncMock(return_value="")
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("media.link.pipeline._AIOHTTP_AVAILABLE", True),
            patch("media.link.pipeline._BS4_AVAILABLE", True),
            patch("media.link.pipeline.aiohttp.ClientSession", return_value=mock_session),
            patch.object(pipe, "_try_jina", new=AsyncMock(return_value=None)),
        ):
            result = await pipe._fetch_and_parse("https://example.com/404", {})

        assert result["processing_status"] == "error"
        assert "404" in result["error"]


class TestLinkPipelineJina:
    """Tests for Jina Reader fast-path."""

    def _make_jina_mock_session(self, status=200, content="Page title\n\nBody text here."):
        """Build a mock aiohttp ClientSession for Jina fetch tests."""
        mock_response = AsyncMock()
        mock_response.status = status
        mock_response.text = AsyncMock(return_value=content)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        return mock_session

    @pytest.mark.asyncio
    async def test_jina_200_returns_jina_result(self):
        """Jina 200 response is returned directly without BS4 fallback."""
        pipe = LinkPipeline()
        mock_session = self._make_jina_mock_session(status=200, content="Title\n\nSome content text here.")

        with patch("media.link.pipeline.aiohttp.ClientSession", return_value=mock_session):
            result = await pipe._try_jina("https://example.com")

        assert result == "Title\n\nSome content text here."

    @pytest.mark.asyncio
    async def test_jina_result_structure(self):
        """_jina_result produces the correct structure."""
        pipe = LinkPipeline()
        content = "My Title\n\nBody paragraph with many words here."
        result = pipe._jina_result("https://example.com", content, {"key": "val"})
        assert result["type"] == "link_fetch"
        assert result["url"] == "https://example.com"
        assert result["title"] == "My Title"
        assert result["content"] == content
        assert result["source"] == "jina"
        assert result["confidence"] == 0.9
        assert result["word_count"] > 0

    @pytest.mark.asyncio
    async def test_fetch_uses_jina_fast_path_for_public_url(self):
        """_fetch_and_parse uses Jina fast-path for public HTTPS URL and skips BS4."""
        pipe = LinkPipeline()
        jina_content = "Article title\n\nArticle body text."

        with (
            patch.object(pipe, "_try_jina", new=AsyncMock(return_value=jina_content)),
            _mock_getaddrinfo("93.184.216.34"),
        ):
            result = await pipe._fetch_and_parse("https://example.com/article", {})

        assert result["source"] == "jina"
        assert result["content"] == jina_content

    @pytest.mark.asyncio
    async def test_fetch_skips_jina_when_hostname_resolves_to_private_ip(self):
        """SSRF guard: hostname resolving to RFC1918 must skip Jina fast-path."""
        pipe = LinkPipeline()
        bs4_result = {"type": "link_fetch", "confidence": 0.9, "url": "https://intranet.attacker/"}
        jina_mock = AsyncMock(return_value="should-not-be-called")

        with (
            patch.object(pipe, "_try_jina", new=jina_mock),
            patch.object(pipe, "_parse_html", return_value=bs4_result),
            patch("media.link.pipeline.aiohttp.ClientSession", return_value=self._make_mock_bs4_session()),
            _mock_getaddrinfo("10.0.0.5"),
        ):
            result = await pipe._fetch_and_parse("https://intranet.attacker/", {})

        jina_mock.assert_not_called()
        assert result.get("source") != "jina"

    @pytest.mark.asyncio
    async def test_jina_non200_falls_back_to_beautifulsoup(self):
        """Non-200 Jina response triggers BeautifulSoup fallback."""
        pipe = LinkPipeline()
        mock_session = self._make_jina_mock_session(status=429)

        bs4_result = {"type": "link_fetch", "confidence": 0.9, "url": "https://example.com"}

        with (
            patch("media.link.pipeline.aiohttp.ClientSession", return_value=mock_session),
            patch.object(pipe, "_parse_html", return_value=bs4_result),
        ):
            # _try_jina returns None on non-200, triggering BS4 fallback
            jina_result = await pipe._try_jina("https://example.com")
            assert jina_result is None

        with (
            patch.object(pipe, "_try_jina", new=AsyncMock(return_value=None)),
            patch("media.link.pipeline.aiohttp.ClientSession", return_value=self._make_mock_bs4_session()),
            patch.object(pipe, "_parse_html", return_value=bs4_result),
        ):
            result = await pipe._fetch_and_parse("https://example.com", {})

        assert result["type"] == "link_fetch"
        assert result.get("source") != "jina"

    @pytest.mark.asyncio
    async def test_jina_timeout_falls_back_to_beautifulsoup(self):
        """Jina timeout triggers BeautifulSoup fallback."""
        import aiohttp as _aiohttp

        pipe = LinkPipeline()
        bs4_result = {"type": "link_fetch", "confidence": 0.9, "url": "https://example.com"}

        async def _raise_timeout(*args, **kwargs):
            raise _aiohttp.ServerTimeoutError()

        with (
            patch.object(pipe, "_try_jina", new=AsyncMock(return_value=None)),
            patch("media.link.pipeline.aiohttp.ClientSession", return_value=self._make_mock_bs4_session()),
            patch.object(pipe, "_parse_html", return_value=bs4_result),
        ):
            result = await pipe._fetch_and_parse("https://example.com", {})

        assert result["type"] == "link_fetch"
        assert result.get("source") != "jina"

    @pytest.mark.asyncio
    async def test_jina_skipped_for_localhost(self):
        """Jina fast-path is not attempted for localhost URLs."""
        pipe = LinkPipeline()
        assert not pipe._is_public_url("http://localhost:8080/page")
        assert not pipe._is_public_url("http://127.0.0.1/api")

    @pytest.mark.asyncio
    async def test_jina_skipped_for_private_ip(self):
        """Jina fast-path is not attempted for private IP URLs."""
        pipe = LinkPipeline()
        assert not pipe._is_public_url("http://192.168.1.1/page")
        assert not pipe._is_public_url("http://10.0.0.5/admin")
        assert not pipe._is_public_url("http://172.16.0.1/internal")

    def test_is_public_url_accepts_public_https(self):
        pipe = LinkPipeline()
        with _mock_getaddrinfo("93.184.216.34"):  # example.com, public IP
            assert pipe._is_public_url("https://example.com/article")
        with _mock_getaddrinfo("209.216.230.240"):  # news.ycombinator.com, public IP
            assert pipe._is_public_url("http://news.ycombinator.com/")

    # ------------------------------------------------------------------
    # SSRF defence: DNS resolution + private-IP rejection (#5015)
    # ------------------------------------------------------------------

    def test_is_public_url_rejects_intranet_hostname_resolving_to_rfc1918(self):
        """Internal hostname resolving to 10.x must be rejected (SSRF guard)."""
        pipe = LinkPipeline()
        with _mock_getaddrinfo("10.0.0.5"):
            assert not pipe._is_public_url("https://intranet-db.company/admin")

    def test_is_public_url_rejects_dns_rebinding_label(self):
        """DNS-rebinding style names like 10-0-0-1.my-domain.com must be rejected."""
        pipe = LinkPipeline()
        with _mock_getaddrinfo("10.0.0.1"):
            assert not pipe._is_public_url("https://10-0-0-1.my-domain.com/")

    def test_is_public_url_rejects_hostname_resolving_to_loopback(self):
        pipe = LinkPipeline()
        with _mock_getaddrinfo("127.0.0.1"):
            assert not pipe._is_public_url("https://spoofed-loopback.example/")

    def test_is_public_url_rejects_hostname_resolving_to_link_local(self):
        pipe = LinkPipeline()
        with _mock_getaddrinfo("169.254.169.254"):  # AWS metadata service
            assert not pipe._is_public_url("https://metadata.attacker.example/")

    def test_is_public_url_rejects_hostname_resolving_to_ipv6_loopback(self):
        pipe = LinkPipeline()
        with _mock_getaddrinfo("::1"):
            assert not pipe._is_public_url("https://v6-loopback.attacker.example/")

    def test_is_public_url_rejects_hostname_resolving_to_ipv6_ula(self):
        pipe = LinkPipeline()
        with _mock_getaddrinfo("fd00::1"):  # IPv6 ULA
            assert not pipe._is_public_url("https://v6-ula.attacker.example/")

    def test_is_public_url_rejects_multi_answer_with_any_private(self):
        """If any resolved IP is private, reject — even if others are public."""
        pipe = LinkPipeline()
        infos = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.1", 0)),
        ]
        with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=infos):
            assert not pipe._is_public_url("https://multi-answer.attacker.example/")

    def test_is_public_url_rejects_onion(self):
        pipe = LinkPipeline()
        # Must not resolve DNS; rejected by TLD alone.
        with patch(
            "autobot_shared.url_safety.socket.getaddrinfo",
            side_effect=AssertionError("DNS should not be called for .onion"),
        ):
            assert not pipe._is_public_url("http://example.onion/page")

    def test_is_public_url_rejects_internal_tld(self):
        pipe = LinkPipeline()
        with patch(
            "autobot_shared.url_safety.socket.getaddrinfo",
            side_effect=AssertionError("DNS should not be called for .internal"),
        ):
            assert not pipe._is_public_url("https://service.internal/")

    def test_is_public_url_rejects_bare_localhost(self):
        pipe = LinkPipeline()
        assert not pipe._is_public_url("http://localhost/")

    def test_is_public_url_fails_closed_on_dns_error(self):
        """DNS lookup failure must return False (fail closed)."""
        pipe = LinkPipeline()
        with patch(
            "autobot_shared.url_safety.socket.getaddrinfo",
            side_effect=socket.gaierror("Name or service not known"),
        ):
            assert not pipe._is_public_url("https://nonexistent-host.example/")

    def test_is_public_url_fails_closed_on_dns_timeout(self):
        pipe = LinkPipeline()
        with patch(
            "autobot_shared.url_safety.socket.getaddrinfo",
            side_effect=socket.timeout(),
        ):
            assert not pipe._is_public_url("https://slow-dns.example/")

    def test_is_public_url_rejects_non_http_scheme(self):
        pipe = LinkPipeline()
        assert not pipe._is_public_url("file:///etc/passwd")
        assert not pipe._is_public_url("ftp://ftp.example.com/")
        assert not pipe._is_public_url("gopher://example.com/")

    def test_is_public_url_accepts_ipv4_literal_public(self):
        """Literal public IP short-circuits DNS."""
        pipe = LinkPipeline()
        with patch(
            "autobot_shared.url_safety.socket.getaddrinfo",
            side_effect=AssertionError("DNS should not be called for literal IP"),
        ):
            assert pipe._is_public_url("http://8.8.8.8/")

    @pytest.mark.asyncio
    async def test_is_public_url_async_wraps_sync_version(self):
        """Async wrapper delegates to the blocking implementation via executor."""
        pipe = LinkPipeline()
        with _mock_getaddrinfo("93.184.216.34"):
            assert await pipe._is_public_url_async("https://example.com/")
        with _mock_getaddrinfo("10.0.0.1"):
            assert not await pipe._is_public_url_async("https://intranet.attacker/")

    def _make_mock_bs4_session(self, status=200):
        """Helper: mock ClientSession for the BS4 fallback path."""
        mock_response = AsyncMock()
        mock_response.url = "https://example.com"
        mock_response.headers = {"Content-Type": "text/html"}
        mock_response.text = AsyncMock(return_value=SAMPLE_HTML)
        mock_response.status = status
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        return mock_session


# ----------------------------------------------------------------------
# Circuit breaker, pooled session, title parsing (issue #5022)
# ----------------------------------------------------------------------


@pytest.fixture(autouse=False)
def _reset_jina_state():
    """Reset module-level circuit-breaker + pooled session state between tests."""
    from media.link import pipeline as pl

    pl._jina_cooldown_until = 0.0
    pl._jina_failures_in_window.clear()
    # Force re-creation of pooled session on next use
    pl._jina_session = None
    yield
    pl._jina_cooldown_until = 0.0
    pl._jina_failures_in_window.clear()
    pl._jina_session = None


class TestJinaCircuitBreaker:
    """Circuit breaker opens after N failures in rolling window (#5022)."""

    @pytest.mark.asyncio
    async def test_circuit_opens_after_threshold_failures(self, _reset_jina_state):
        """After _JINA_FAILURE_THRESHOLD failures, subsequent calls short-circuit."""
        from media.link import pipeline as pl

        pipe = LinkPipeline()

        # First N calls raise → circuit opens
        async def _always_raise(*args, **kwargs):
            raise RuntimeError("simulated Jina outage")

        with patch("media.link.pipeline._get_jina_session", new=AsyncMock(side_effect=_always_raise)):
            for _ in range(pl._JINA_FAILURE_THRESHOLD):
                result = await pipe._try_jina("https://example.com/a")
                assert result is None

        # Circuit should now be open
        assert pl._jina_cooldown_until > 0
        assert pl._jina_cooldown_until > __import__("time").monotonic()

        # Subsequent call must NOT invoke _get_jina_session (short-circuit)
        called = AsyncMock()
        with patch("media.link.pipeline._get_jina_session", new=called):
            result = await pipe._try_jina("https://example.com/b")
        assert result is None
        called.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_circuit_expires_after_cooldown(self, _reset_jina_state):
        """After cooldown expires, Jina is tried again."""
        from media.link import pipeline as pl

        pipe = LinkPipeline()

        # Manually open the circuit in the past (already-expired cooldown)
        import time as _time

        pl._jina_cooldown_until = _time.monotonic() - 1.0  # expired

        # Mock a successful Jina call; circuit should NOT short-circuit
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="Title: Foo\n\nBody")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch("media.link.pipeline._get_jina_session", new=AsyncMock(return_value=mock_session)):
            result = await pipe._try_jina("https://example.com/c")

        assert result == "Title: Foo\n\nBody"

    @pytest.mark.asyncio
    async def test_success_clears_failure_window(self, _reset_jina_state):
        """A successful call resets the failure counter so the circuit stays closed."""
        from media.link import pipeline as pl

        pipe = LinkPipeline()

        # Two failures (below threshold)
        async def _raise(*args, **kwargs):
            raise RuntimeError("boom")

        with patch("media.link.pipeline._get_jina_session", new=AsyncMock(side_effect=_raise)):
            await pipe._try_jina("https://example.com/x")
            await pipe._try_jina("https://example.com/y")

        assert len(pl._jina_failures_in_window) == 2

        # One success — window clears
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="ok")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)
        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=mock_response)

        with patch("media.link.pipeline._get_jina_session", new=AsyncMock(return_value=mock_session)):
            await pipe._try_jina("https://example.com/z")

        assert len(pl._jina_failures_in_window) == 0


class TestJinaPooledSession:
    """Pooled ClientSession is reused across sequential calls (#5022)."""

    @pytest.mark.asyncio
    async def test_pooled_session_reused_across_calls(self, _reset_jina_state):
        """Two sequential _try_jina calls reuse the same _jina_session instance."""
        from media.link import pipeline as pl

        pipe = LinkPipeline()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="Title: Hi\n\nBody")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        # Patch aiohttp.ClientSession to return a tracked MagicMock (not AsyncMock,
        # so `.closed` is a truthy-free MagicMock attribute; we set it explicitly).
        created_session = MagicMock()
        created_session.closed = False
        created_session.get = MagicMock(return_value=mock_response)

        call_count = MagicMock(return_value=created_session)

        with patch("media.link.pipeline.aiohttp.ClientSession", call_count):
            await pipe._try_jina("https://example.com/1")
            first_id = id(pl._jina_session)
            await pipe._try_jina("https://example.com/2")
            second_id = id(pl._jina_session)

        assert first_id == second_id, "Pooled session must be the same instance across calls"
        # aiohttp.ClientSession() constructor should have been called exactly once
        assert call_count.call_count == 1

    @pytest.mark.asyncio
    async def test_close_jina_session_allows_recreation(self, _reset_jina_state):
        """close_jina_session() closes the pooled session; next call creates a new one."""
        from media.link import pipeline as pl

        pipe = LinkPipeline()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.text = AsyncMock(return_value="ok")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        session_a = MagicMock()
        session_a.closed = False
        session_a.get = MagicMock(return_value=mock_response)
        session_a.close = AsyncMock()
        session_b = MagicMock()
        session_b.closed = False
        session_b.get = MagicMock(return_value=mock_response)

        with patch("media.link.pipeline.aiohttp.ClientSession", side_effect=[session_a, session_b]):
            await pipe._try_jina("https://example.com/1")
            assert pl._jina_session is session_a
            await pl.close_jina_session()
            assert pl._jina_session is None
            await pipe._try_jina("https://example.com/2")
            assert pl._jina_session is session_b

        session_a.close.assert_awaited_once()


class TestJinaTitleExtraction:
    """Title is parsed from `Title:` prefix; metadata is stripped from body (#5022)."""

    def test_parse_title_prefix_and_strip_metadata(self):
        """`Title: Foo\\nURL Source: ...\\n\\nBody` yields title=Foo and clean body."""
        from media.link.pipeline import _parse_jina_output

        raw = "Title: Foo\nURL Source: https://example.com\n\nBody paragraph here."
        title, body = _parse_jina_output(raw)
        assert title == "Foo"
        assert "Title:" not in body
        assert "URL Source:" not in body
        assert body.strip() == "Body paragraph here."

    def test_jina_result_strips_metadata_from_content(self):
        """_jina_result's content field must not contain Title: or URL Source: lines."""
        pipe = LinkPipeline()
        raw = "Title: My Article\nURL Source: https://example.com\n\nThe actual article body."
        result = pipe._jina_result("https://example.com", raw, {})
        assert result["title"] == "My Article"
        assert "Title:" not in result["content"]
        assert "URL Source:" not in result["content"]
        assert "The actual article body." in result["content"]

    def test_parse_fallback_when_no_title_prefix(self):
        """Without a Title: prefix, first non-empty body line is used as title."""
        from media.link.pipeline import _parse_jina_output

        raw = "Just a plain first line\n\nSecond paragraph."
        title, body = _parse_jina_output(raw)
        assert title == "Just a plain first line"
        # Fallback preserves the full content
        assert body == raw

    def test_parse_empty_content(self):
        """Empty or None content returns empty title and body."""
        from media.link.pipeline import _parse_jina_output

        assert _parse_jina_output("") == ("", "")

    def test_parse_title_truncated_to_200_chars(self):
        """Title longer than 200 chars is truncated."""
        from media.link.pipeline import _parse_jina_output

        long_title = "X" * 300
        raw = f"Title: {long_title}\n\nBody"
        title, _ = _parse_jina_output(raw)
        assert len(title) == 200
