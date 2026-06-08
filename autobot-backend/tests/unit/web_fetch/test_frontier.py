# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for web_fetch.frontier — dedup, depth, same-origin, max_pages."""

from web_fetch.frontier import Frontier, _same_origin, _url_key, extract_links


class TestUrlKey:
    def test_strips_trailing_slash(self) -> None:
        k1 = _url_key("https://example.com/path/")
        k2 = _url_key("https://example.com/path")
        assert k1 == k2

    def test_differs_by_path(self) -> None:
        assert _url_key("https://example.com/a") != _url_key("https://example.com/b")

    def test_same_url_same_key(self) -> None:
        assert _url_key("https://example.com/page") == _url_key("https://example.com/page")


class TestSameOrigin:
    def test_same_scheme_and_host(self) -> None:
        assert _same_origin("https://a.com/page", "https://a.com/other") is True

    def test_different_host(self) -> None:
        assert _same_origin("https://b.com/page", "https://a.com/other") is False

    def test_different_scheme(self) -> None:
        assert _same_origin("http://a.com/page", "https://a.com/other") is False


class TestExtractLinks:
    _HTML = """<html><body>
        <a href="/about">About</a>
        <a href="https://other.com/page">External</a>
        <a href="#anchor">Skip</a>
        <a href="javascript:void(0)">JS</a>
        <a href="mailto:a@b.com">Mail</a>
        <a href="/contact">Contact</a>
    </body></html>"""

    def test_resolves_relative_links(self) -> None:
        links = extract_links(self._HTML, "https://example.com")
        assert "https://example.com/about" in links

    def test_includes_external_when_no_filter(self) -> None:
        links = extract_links(self._HTML, "https://example.com", same_origin_only=False)
        assert "https://other.com/page" in links

    def test_excludes_external_with_filter(self) -> None:
        links = extract_links(self._HTML, "https://example.com", same_origin_only=True)
        assert all("other.com" not in url for url in links)

    def test_skips_anchors_and_js(self) -> None:
        links = extract_links(self._HTML, "https://example.com")
        assert all("#anchor" not in url for url in links)
        assert all("javascript" not in url for url in links)

    def test_skips_mailto(self) -> None:
        links = extract_links(self._HTML, "https://example.com")
        assert not any("mailto" in url for url in links)

    def test_deduplicates(self) -> None:
        html = '<a href="/p">1</a><a href="/p">2</a>'
        links = extract_links(html, "https://example.com")
        assert links.count("https://example.com/p") == 1


class TestFrontier:
    def test_seed_is_first(self) -> None:
        f = Frontier("https://example.com", max_pages=5)
        item = f.next()
        assert item is not None
        url, depth = item
        assert url == "https://example.com"
        assert depth == 0

    def test_returns_none_when_empty(self) -> None:
        f = Frontier("https://example.com", max_pages=1)
        f.next()  # consume seed
        assert f.next() is None

    def test_max_pages_respected(self) -> None:
        f = Frontier("https://example.com", max_pages=2)
        f.next()  # seed
        f.add_links(["https://example.com/a", "https://example.com/b"], depth=1)
        urls = []
        while (item := f.next()) is not None:
            urls.append(item[0])
        assert len(urls) == 1  # max_pages=2 means 1 remaining after seed

    def test_dedup_prevents_revisit(self) -> None:
        f = Frontier("https://example.com", max_pages=10)
        f.next()  # consume seed
        f.add_links(["https://example.com/page"], depth=1)
        f.add_links(["https://example.com/page"], depth=1)  # duplicate
        item1 = f.next()
        item2 = f.next()
        assert item1 is not None
        assert item2 is None  # only one unique page

    def test_depth_limit(self) -> None:
        f = Frontier("https://example.com", max_pages=100, max_depth=1)
        f.next()  # seed at depth 0
        f.add_links(["https://example.com/a"], depth=1)
        f.add_links(["https://example.com/b"], depth=2)  # beyond max_depth
        item = f.next()
        assert item is not None
        assert item[0] == "https://example.com/a"
        assert f.next() is None  # /b was rejected

    def test_same_origin_filter(self) -> None:
        f = Frontier("https://example.com", max_pages=10, same_origin=True)
        f.next()  # seed
        f.add_links(["https://other.com/page", "https://example.com/about"], depth=1)
        item = f.next()
        assert item is not None
        assert "example.com" in item[0]
        assert f.next() is None  # other.com was filtered

    def test_exhausted(self) -> None:
        f = Frontier("https://example.com", max_pages=1)
        assert not f.exhausted()
        f.next()
        assert f.exhausted()

    def test_pages_emitted_counter(self) -> None:
        f = Frontier("https://example.com", max_pages=5)
        assert f.pages_emitted == 0
        f.next()
        assert f.pages_emitted == 1

    def test_visited_count(self) -> None:
        f = Frontier("https://example.com", max_pages=10)
        assert f.visited_count == 1  # seed counted
        f.add_links(["https://example.com/a"], depth=1)
        assert f.visited_count == 2
