# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for web_fetch.site_mapper — sitemap parsing, sitemapindex recursion, crawl fallback.

All HTTP fetches are mocked — no network calls.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from web_fetch.site_mapper import (
    SiteMapEntry,
    SiteMapper,
    _domain_to_seed,
    _parse_sitemapindex,
    _parse_urlset,
    _resolve_sitemap_urls,
    _safe_parse,
)

# ---------------------------------------------------------------------------
# Sitemap XML fixtures
# ---------------------------------------------------------------------------

_URLSET_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/</loc></url>
  <url><loc>https://example.com/about</loc></url>
  <url><loc>https://example.com/contact</loc></url>
</urlset>
"""

_SITEMAPINDEX_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://example.com/sitemap-posts.xml</loc></sitemap>
  <sitemap><loc>https://example.com/sitemap-pages.xml</loc></sitemap>
</sitemapindex>
"""

_CHILD_SITEMAP_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://example.com/post/1</loc></url>
  <url><loc>https://example.com/post/2</loc></url>
</urlset>
"""

_MALFORMED_XML = "<<not valid xml>>"


# ---------------------------------------------------------------------------
# _safe_parse
# ---------------------------------------------------------------------------


class TestSafeParse:
    def test_valid_xml_returns_element(self) -> None:
        root = _safe_parse(_URLSET_XML, "https://example.com/sitemap.xml")
        assert root is not None

    def test_malformed_xml_returns_none(self) -> None:
        root = _safe_parse(_MALFORMED_XML, "https://example.com/sitemap.xml")
        assert root is None


# ---------------------------------------------------------------------------
# _parse_urlset / _parse_sitemapindex
# ---------------------------------------------------------------------------


class TestParseUrlset:
    def test_extracts_all_locs(self) -> None:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(_URLSET_XML)  # nosec B314 - test code uses controlled/trusted XML data
        urls = _parse_urlset(root)
        assert urls == ["https://example.com/", "https://example.com/about", "https://example.com/contact"]

    def test_empty_urlset(self) -> None:
        import xml.etree.ElementTree as ET

        xml = '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"></urlset>'
        root = ET.fromstring(xml)  # nosec B314 - test code uses controlled/trusted XML data
        assert _parse_urlset(root) == []


class TestParseSitemapindex:
    def test_extracts_child_locs(self) -> None:
        import xml.etree.ElementTree as ET

        root = ET.fromstring(_SITEMAPINDEX_XML)  # nosec B314 - test code uses controlled/trusted XML data
        locs = _parse_sitemapindex(root)
        assert locs == [
            "https://example.com/sitemap-posts.xml",
            "https://example.com/sitemap-pages.xml",
        ]


# ---------------------------------------------------------------------------
# _domain_to_seed
# ---------------------------------------------------------------------------


class TestDomainToSeed:
    def test_bare_domain_gets_https(self) -> None:
        assert _domain_to_seed("example.com") == "https://example.com"

    def test_https_url_unchanged(self) -> None:
        assert _domain_to_seed("https://example.com") == "https://example.com"

    def test_http_url_unchanged(self) -> None:
        assert _domain_to_seed("http://example.com") == "http://example.com"


# ---------------------------------------------------------------------------
# _resolve_sitemap_urls — urlset success path
# ---------------------------------------------------------------------------


class TestResolveSitemapUrls:
    @pytest.mark.asyncio
    async def test_urlset_returns_locs(self) -> None:
        with patch("web_fetch.site_mapper._fetch_xml", new=AsyncMock(return_value=_URLSET_XML)):
            urls = await _resolve_sitemap_urls("https://example.com/sitemap.xml")
        assert urls == ["https://example.com/", "https://example.com/about", "https://example.com/contact"]

    @pytest.mark.asyncio
    async def test_fetch_failure_returns_none(self) -> None:
        with patch("web_fetch.site_mapper._fetch_xml", new=AsyncMock(return_value=None)):
            result = await _resolve_sitemap_urls("https://example.com/sitemap.xml")
        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_xml_returns_none(self) -> None:
        with patch("web_fetch.site_mapper._fetch_xml", new=AsyncMock(return_value=_MALFORMED_XML)):
            result = await _resolve_sitemap_urls("https://example.com/sitemap.xml")
        assert result is None

    @pytest.mark.asyncio
    async def test_sitemapindex_recurses_one_level(self) -> None:
        """sitemapindex fetches child sitemaps and merges their URLs."""

        async def _fake_fetch_xml(url: str) -> str | None:
            if url.endswith("sitemap.xml"):
                return _SITEMAPINDEX_XML
            return _CHILD_SITEMAP_XML  # both children return same content for simplicity

        with patch("web_fetch.site_mapper._fetch_xml", new=_fake_fetch_xml):
            urls = await _resolve_sitemap_urls("https://example.com/sitemap.xml")

        assert urls is not None
        assert "https://example.com/post/1" in urls
        assert "https://example.com/post/2" in urls
        # Two child sitemaps each with 2 URLs = 4 total
        assert len(urls) == 4


# ---------------------------------------------------------------------------
# SiteMapper.map_site — sitemap happy path
# ---------------------------------------------------------------------------


class TestSiteMapperSitemapPath:
    @pytest.mark.asyncio
    async def test_returns_sitemap_source(self) -> None:
        with patch("web_fetch.site_mapper._fetch_xml", new=AsyncMock(return_value=_URLSET_XML)):
            result = await SiteMapper.map_site("example.com", max_urls=500)
        assert result.source == "sitemap"
        assert result.domain == "example.com"
        assert len(result.entries) == 3

    @pytest.mark.asyncio
    async def test_entries_have_depth_zero(self) -> None:
        with patch("web_fetch.site_mapper._fetch_xml", new=AsyncMock(return_value=_URLSET_XML)):
            result = await SiteMapper.map_site("example.com")
        for entry in result.entries:
            assert entry.depth == 0

    @pytest.mark.asyncio
    async def test_entries_have_null_title(self) -> None:
        with patch("web_fetch.site_mapper._fetch_xml", new=AsyncMock(return_value=_URLSET_XML)):
            result = await SiteMapper.map_site("example.com")
        for entry in result.entries:
            assert entry.title is None

    @pytest.mark.asyncio
    async def test_max_urls_caps_sitemap_results(self) -> None:
        with patch("web_fetch.site_mapper._fetch_xml", new=AsyncMock(return_value=_URLSET_XML)):
            result = await SiteMapper.map_site("example.com", max_urls=2)
        assert len(result.entries) == 2


# ---------------------------------------------------------------------------
# SiteMapper.map_site — crawl fallback
# ---------------------------------------------------------------------------


class TestSiteMapperCrawlFallback:
    @pytest.mark.asyncio
    async def test_falls_back_when_sitemap_absent(self) -> None:
        """When sitemap.xml returns None, crawl fallback is used."""
        _crawl_html = """\
        <html><head><title>Home</title></head><body>
          <a href="/page1">Page 1</a>
          <a href="/page2">Page 2</a>
        </body></html>"""

        async def _fake_fetch_bs4(url, timeout=10.0):
            if url == "https://example.com":
                return _crawl_html, 200
            return "", 200

        with (
            patch("web_fetch.site_mapper._fetch_xml", new=AsyncMock(return_value=None)),
            patch(
                "web_fetch.site_mapper._crawl_fallback_with_robots",
                new=AsyncMock(
                    return_value=[
                        SiteMapEntry("https://example.com", None, 0),
                        SiteMapEntry("https://example.com/page1", None, 1),
                    ]
                ),
            ),
        ):
            result = await SiteMapper.map_site("example.com", respect_robots=False)

        assert result.source == "crawl"
        assert len(result.entries) >= 1

    @pytest.mark.asyncio
    async def test_crawl_entries_have_null_title(self) -> None:
        """Crawl fallback never fetches page bodies — title is always null."""
        crawl_entries = [
            SiteMapEntry("https://example.com", None, 0),
            SiteMapEntry("https://example.com/about", None, 1),
        ]

        with (
            patch("web_fetch.site_mapper._fetch_xml", new=AsyncMock(return_value=None)),
            patch("web_fetch.site_mapper._crawl_fallback_with_robots", new=AsyncMock(return_value=crawl_entries)),
        ):
            result = await SiteMapper.map_site("example.com")

        for entry in result.entries:
            assert entry.title is None

    @pytest.mark.asyncio
    async def test_crawl_respects_max_urls(self) -> None:
        """max_urls is passed through to crawl fallback."""
        crawl_entries = [SiteMapEntry(f"https://example.com/{i}", None, 1) for i in range(10)]

        with (
            patch("web_fetch.site_mapper._fetch_xml", new=AsyncMock(return_value=None)),
            patch(
                "web_fetch.site_mapper._crawl_fallback_with_robots", new=AsyncMock(return_value=crawl_entries)
            ) as mock_crawl,
        ):
            await SiteMapper.map_site("example.com", max_urls=7)

        # Verify max_urls=7 was passed to the fallback
        call_kwargs = mock_crawl.call_args
        assert call_kwargs[0][1] == 7 or call_kwargs[1].get("max_urls") == 7


# ---------------------------------------------------------------------------
# SiteMapEntry.to_dict
# ---------------------------------------------------------------------------


class TestSiteMapEntry:
    def test_to_dict_structure(self) -> None:
        entry = SiteMapEntry("https://example.com/page", "My Page", 2)
        d = entry.to_dict()
        assert d == {"url": "https://example.com/page", "title": "My Page", "depth": 2}

    def test_to_dict_null_title(self) -> None:
        entry = SiteMapEntry("https://example.com/", None, 0)
        d = entry.to_dict()
        assert d["title"] is None
