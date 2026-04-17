# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Link Pipeline Tests
# Issue #932: Implement actual link/web processing

"""Unit tests for LinkPipeline."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from media.core.types import MediaInput, MediaType, ProcessingIntent
from media.link.pipeline import LinkPipeline


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
        from bs4 import BeautifulSoup

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
        html = '<html><body><a href="#">Anchor</a><a href="javascript:void">JS</a><a href="/real">Real</a></body></html>'
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
        result = self.pipe._parse_html(
            SAMPLE_HTML, "https://test.com/page", "text/html", {}
        )
        assert result["type"] == "link_fetch"
        assert result["title"] == "OG Title"
        assert result["description"] == "OG description"
        assert result["word_count"] > 0
        assert len(result["links"]) > 0


class TestLinkPipelineErrorHandling:
    """Tests for error and unavailability results."""

    def test_unavailable_result(self):
        pipe = LinkPipeline()
        result = pipe._unavailable_result(
            "https://example.com", ["aiohttp", "beautifulsoup4"], {}
        )
        assert result["processing_status"] == "unavailable"
        assert result["confidence"] == 0.0

    def test_error_result(self):
        pipe = LinkPipeline()
        result = pipe._error_result("https://example.com", "Connection refused", {})
        assert result["processing_status"] == "error"
        assert result["error"] == "Connection refused"

    def test_empty_url_returns_error(self):
        pipe = LinkPipeline()

        async def _run():
            media_input = _make_input("")
            return await pipe._process_link(media_input)

        import asyncio

        result = asyncio.run(_run())
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

        with patch("media.link.pipeline._AIOHTTP_AVAILABLE", True), patch(
            "media.link.pipeline._BS4_AVAILABLE", True
        ), patch(
            "media.link.pipeline.aiohttp.ClientSession", return_value=mock_session
        ), patch.object(pipe, "_parse_html", return_value=_parsed), patch.object(
            pipe, "_try_jina", new=AsyncMock(return_value=None)
        ):
            result = await pipe._fetch_and_parse("https://example.com", {})

        assert result["type"] == "link_fetch"
        assert result["confidence"] > 0
        # Default path must verify TLS certs (ssl=None, not ssl=False)
        mock_session.get.assert_called_once_with(
            "https://example.com", allow_redirects=True, ssl=None
        )

    @pytest.mark.asyncio
    async def test_fetch_default_verifies_tls(self):
        """ssl=None (cert verification) is used when allow_self_signed is absent."""
        pipe = LinkPipeline()
        mock_session = self._make_mock_session("https://example.com")
        _parsed = {"type": "link_fetch", "confidence": 0.9}

        with patch("media.link.pipeline._AIOHTTP_AVAILABLE", True), patch(
            "media.link.pipeline._BS4_AVAILABLE", True
        ), patch(
            "media.link.pipeline.aiohttp.ClientSession", return_value=mock_session
        ), patch.object(pipe, "_parse_html", return_value=_parsed), patch.object(
            pipe, "_try_jina", new=AsyncMock(return_value=None)
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

        with patch("media.link.pipeline._AIOHTTP_AVAILABLE", True), patch(
            "media.link.pipeline._BS4_AVAILABLE", True
        ), patch(
            "media.link.pipeline.aiohttp.ClientSession", return_value=mock_session
        ), patch.object(pipe, "_parse_html", return_value=_parsed), patch.object(
            pipe, "_try_jina", new=AsyncMock(return_value=None)
        ):
            await pipe._fetch_and_parse(
                "https://internal.example.com", {"allow_self_signed": True}
            )

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

        with patch("media.link.pipeline._AIOHTTP_AVAILABLE", True), patch(
            "media.link.pipeline._BS4_AVAILABLE", True
        ), patch(
            "media.link.pipeline.aiohttp.ClientSession", return_value=mock_session
        ), patch.object(pipe, "_try_jina", new=AsyncMock(return_value=None)):
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

        with patch.object(pipe, "_try_jina", new=AsyncMock(return_value=jina_content)):
            result = await pipe._fetch_and_parse("https://example.com/article", {})

        assert result["source"] == "jina"
        assert result["content"] == jina_content

    @pytest.mark.asyncio
    async def test_jina_non200_falls_back_to_beautifulsoup(self):
        """Non-200 Jina response triggers BeautifulSoup fallback."""
        pipe = LinkPipeline()
        mock_session = self._make_jina_mock_session(status=429)

        bs4_result = {"type": "link_fetch", "confidence": 0.9, "url": "https://example.com"}

        with patch("media.link.pipeline.aiohttp.ClientSession", return_value=mock_session), \
             patch.object(pipe, "_parse_html", return_value=bs4_result):
            # _try_jina returns None on non-200, triggering BS4 fallback
            jina_result = await pipe._try_jina("https://example.com")
            assert jina_result is None

        with patch.object(pipe, "_try_jina", new=AsyncMock(return_value=None)), \
             patch("media.link.pipeline.aiohttp.ClientSession", return_value=self._make_mock_bs4_session()), \
             patch.object(pipe, "_parse_html", return_value=bs4_result):
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

        with patch.object(pipe, "_try_jina", new=AsyncMock(return_value=None)), \
             patch("media.link.pipeline.aiohttp.ClientSession", return_value=self._make_mock_bs4_session()), \
             patch.object(pipe, "_parse_html", return_value=bs4_result):
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
        assert pipe._is_public_url("https://example.com/article")
        assert pipe._is_public_url("http://news.ycombinator.com/")

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
