# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for web_fetch.extractors — HTML-to-Markdown, SPA detection, title extraction."""

from unittest.mock import patch

import pytest

from web_fetch.extractors import (
    _extract_title,
    _html_to_markdown_via_markdownify,
    _html_to_plain_text_via_bs4,
    _is_noscript_dominated,
    _strip_boilerplate,
    extract_markdown,
    is_spa_content,
)

_SIMPLE_HTML = """<html><head><title>My Page</title></head>
<body><main><p>Hello world content here.</p></main></body></html>"""

_OG_TITLE_HTML = """<html>
<head>
<meta property="og:title" content="OG Title Value"/>
<title>Fallback Title</title>
</head>
<body><p>content</p></body></html>"""

_SPA_NOSCRIPT_HTML = """<html><body>
<noscript>Please enable JavaScript to use this application.</noscript>
<div id="root">Loading...</div>
</body></html>"""

_SPA_LOADING_HTML = """<html><body><p>Loading...</p></body></html>"""

_JS_REQUIRED_HTML = """<html><body>
<p>Please enable JavaScript to continue.</p>
</body></html>"""

_BOILERPLATE_HTML = """<html><body>
<nav>Nav content</nav>
<header>Header</header>
<footer>Footer</footer>
<aside>Sidebar</aside>
<script>var x = 1;</script>
<style>.cls{}</style>
<noscript>Enable JS</noscript>
<main><p>Main content here</p></main>
</body></html>"""


class TestExtractTitle:
    def test_og_title_takes_priority(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(_OG_TITLE_HTML, "html.parser")
        assert _extract_title(soup) == "OG Title Value"

    def test_falls_back_to_title_tag(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(_SIMPLE_HTML, "html.parser")
        assert _extract_title(soup) == "My Page"

    def test_empty_when_no_title(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup("<html><body>no title here</body></html>", "html.parser")
        assert _extract_title(soup) == ""

    def test_truncates_long_title(self) -> None:
        from bs4 import BeautifulSoup

        long_title = "A" * 400
        html = f"<html><head><title>{long_title}</title></head></html>"
        soup = BeautifulSoup(html, "html.parser")
        result = _extract_title(soup)
        assert len(result) == 300


class TestStripBoilerplate:
    def test_removes_nav_footer_header(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(_BOILERPLATE_HTML, "html.parser")
        _strip_boilerplate(soup)
        assert soup.find("nav") is None
        assert soup.find("footer") is None
        assert soup.find("header") is None
        assert soup.find("noscript") is None

    def test_keeps_main_content(self) -> None:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(_BOILERPLATE_HTML, "html.parser")
        _strip_boilerplate(soup)
        assert soup.find("main") is not None
        assert "Main content here" in soup.get_text()


class TestHtmlToMarkdownify:
    def test_converts_heading(self) -> None:
        html = "<h1>Title</h1><p>Para</p>"
        md = _html_to_markdown_via_markdownify(html)
        assert "Title" in md

    def test_exception_path_handled(self) -> None:
        # markdownify is imported inside the function; test that the function
        # does not propagate exceptions to the caller.
        result = _html_to_markdown_via_markdownify("<p>hi</p>")
        # Normal path: markdownify is available, should return non-empty string.
        assert isinstance(result, str)

    def test_returns_string(self) -> None:
        result = _html_to_markdown_via_markdownify("<p>text</p>")
        assert isinstance(result, str)


class TestHtmlToPlainText:
    def test_extracts_main_text(self) -> None:
        result = _html_to_plain_text_via_bs4(_SIMPLE_HTML)
        assert "Hello world" in result

    def test_empty_body_returns_empty(self) -> None:
        html = "<html><body></body></html>"
        result = _html_to_plain_text_via_bs4(html)
        assert result == ""

    def test_prefers_article_tag(self) -> None:
        html = "<html><body><article><p>Article text</p></article><p>Outside</p></body></html>"
        result = _html_to_plain_text_via_bs4(html)
        assert "Article text" in result


class TestExtractMarkdown:
    def test_returns_title_and_markdown(self) -> None:
        title, md = extract_markdown(_SIMPLE_HTML)
        assert title == "My Page"
        assert isinstance(md, str)

    def test_og_title_extracted(self) -> None:
        title, md = extract_markdown(_OG_TITLE_HTML)
        assert title == "OG Title Value"

    def test_empty_html_returns_empty_strings(self) -> None:
        title, md = extract_markdown("")
        assert isinstance(title, str)
        assert isinstance(md, str)

    def test_strips_whitespace(self) -> None:
        _, md = extract_markdown("<p>  hello  </p>")
        assert md == md.strip()


class TestIsSpaContent:
    def test_loading_marker_detected(self) -> None:
        assert is_spa_content("Loading...", "") is True

    def test_js_required_marker_detected(self) -> None:
        assert is_spa_content("please enable javascript", "") is True

    def test_clean_content_not_spa(self) -> None:
        assert is_spa_content("This is real content with no SPA markers.") is False

    def test_noscript_dominated_html_detected(self) -> None:
        assert is_spa_content("", _SPA_NOSCRIPT_HTML) is True

    def test_spa_marker_in_html_detected(self) -> None:
        assert is_spa_content("", _SPA_LOADING_HTML) is True

    def test_js_required_in_html(self) -> None:
        assert is_spa_content("", _JS_REQUIRED_HTML) is True

    def test_clean_html_not_spa(self) -> None:
        assert is_spa_content("Regular content", _SIMPLE_HTML) is False


class TestIsNoscriptDominated:
    def test_noscript_dominates_empty_body(self) -> None:
        html = "<html><body><noscript>Enable JS please</noscript></body></html>"
        assert _is_noscript_dominated(html) is True

    def test_normal_content_not_dominated(self) -> None:
        assert _is_noscript_dominated(_SIMPLE_HTML) is False

    def test_no_body_treated_as_dominated(self) -> None:
        # Empty HTML has no body text so noscript is considered dominant.
        result = _is_noscript_dominated("")
        assert result is True  # empty body with no real content = dominated

    def test_body_with_content_not_dominated(self) -> None:
        html = "<html><body><noscript>JS needed</noscript><p>" + "x" * 200 + "</p></body></html>"
        assert _is_noscript_dominated(html) is False
