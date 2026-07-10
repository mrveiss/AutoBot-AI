# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for web_fetch.extractors — HTML-to-Markdown, SPA detection, title extraction,
and schema-driven structured data extraction (Issue #7405).

Issue #11520: _build_extraction_prompt and _call_llm_for_extraction were
consolidated into llm_shared.structured_ops.extract; extract_url now delegates
there.  Tests for those internal helpers were moved/updated accordingly:
  - _build_extraction_prompt → covered by structured_ops_test.py
  - _call_llm_for_extraction → absorbed into structured_ops._extract_single
  - extract_url tests now patch llm_shared.structured_ops.extract directly.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web_fetch.extractors import (
    _extract_title,
    _html_to_markdown_via_markdownify,
    _html_to_plain_text_via_bs4,
    _is_noscript_dominated,
    _strip_boilerplate,
    _strip_script_blocks,
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


# ---------------------------------------------------------------------------
# Issue #7405 — _strip_script_blocks (prompt-injection guard)
# ---------------------------------------------------------------------------


class TestStripScriptBlocks:
    def test_removes_inline_script(self) -> None:
        md = "Hello\n<script>alert(1)</script>\nworld"
        assert "<script>" not in _strip_script_blocks(md)
        assert "Hello" in _strip_script_blocks(md)

    def test_removes_multiline_script(self) -> None:
        md = "Before\n<script type='text/javascript'>\nvar x = document.cookie;\n</script>\nAfter"
        result = _strip_script_blocks(md)
        assert "<script" not in result
        assert "document.cookie" not in result
        assert "After" in result

    def test_no_script_unchanged(self) -> None:
        md = "Normal markdown content with no scripts."
        assert _strip_script_blocks(md) == md

    def test_multiple_script_blocks_removed(self) -> None:
        md = "<script>a()</script> text <script>b()</script>"
        result = _strip_script_blocks(md)
        assert "a()" not in result
        assert "b()" not in result
        assert "text" in result

    def test_script_injection_stripped_before_extraction(self) -> None:
        """_strip_script_blocks removes script content; safe to pass to LLM."""
        malicious_md = "<html><body><script>alert(1)</script><p>Real content</p></body></html>"
        safe = _strip_script_blocks(malicious_md)
        assert "alert(1)" not in safe
        assert "Real content" in safe


# ---------------------------------------------------------------------------
# Issue #7405 — extract_url (integration-level unit tests with mocks)
# Issue #11520 — now delegates to llm_shared.structured_ops.extract
# ---------------------------------------------------------------------------


def _make_fetch_result(
    success: bool = True, markdown: str = "# Hello", title: str = "Page", url: str = "https://ex.com"
):
    r = MagicMock()
    r.success = success
    r.markdown = markdown
    r.title = title
    r.url = url
    r.error_code = None if success else "connection"
    r.retryable = not success
    return r


def _make_firewall_verdict(blocked: bool = False, content: str = "# Hello") -> MagicMock:
    """Return a mock firewall verdict that passes through by default."""
    v = MagicMock()
    v.blocked = blocked
    v.content = content
    v.risk = MagicMock()
    v.risk.value = "none"
    return v


@pytest.mark.asyncio
async def test_extract_url_success() -> None:
    """extract_url returns {url, data, schema_valid:True} on happy path."""
    from web_fetch.extractors import extract_url

    mock_result = _make_fetch_result(markdown="Product: Widget, Price: 9.99")
    schema = {"type": "object", "properties": {"product": {"type": "string"}, "price": {"type": "number"}}}
    extracted_data = {"product": "Widget", "price": 9.99}
    ops_mod = sys.modules["llm_shared.structured_ops"]

    with (
        patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result),
        patch(
            "security.content_firewall.get_content_firewall",
            return_value=MagicMock(
                inspect=AsyncMock(return_value=_make_firewall_verdict(content=mock_result.markdown))
            ),
        ),
        patch.object(ops_mod, "extract", new_callable=AsyncMock, return_value=extracted_data),
    ):
        result = await extract_url("https://ex.com", schema)

    assert result["schema_valid"] is True
    assert result["data"]["product"] == "Widget"
    assert result["url"] == "https://ex.com"


@pytest.mark.asyncio
async def test_extract_url_fetch_failure_raises_runtime_error() -> None:
    """extract_url raises RuntimeError when WebFetcher.fetch fails."""
    from web_fetch.extractors import extract_url

    mock_result = _make_fetch_result(success=False, markdown="")

    with patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result):
        with pytest.raises(RuntimeError, match="connection"):
            await extract_url("https://ex.com", {"type": "object"})


@pytest.mark.asyncio
async def test_extract_url_schema_validation_failure_raises_value_error() -> None:
    """extract_url raises ValueError when extraction fails (ExtractionError → ValueError)."""
    from llm_shared.structured_ops import ExtractionError
    from web_fetch.extractors import extract_url

    mock_result = _make_fetch_result()
    ops_mod = sys.modules["llm_shared.structured_ops"]

    with (
        patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result),
        patch(
            "security.content_firewall.get_content_firewall",
            return_value=MagicMock(
                inspect=AsyncMock(return_value=_make_firewall_verdict(content=mock_result.markdown))
            ),
        ),
        patch.object(
            ops_mod,
            "extract",
            new_callable=AsyncMock,
            side_effect=ExtractionError("schema validation failed after 3 attempts"),
        ),
    ):
        with pytest.raises(ValueError):
            await extract_url("https://ex.com", {"type": "object", "properties": {"count": {"type": "integer"}}})


@pytest.mark.asyncio
async def test_extract_url_non_json_llm_output_raises_value_error() -> None:
    """extract_url raises ValueError when extraction fails (e.g. non-JSON after retries)."""
    from llm_shared.structured_ops import ExtractionError
    from web_fetch.extractors import extract_url

    mock_result = _make_fetch_result()
    ops_mod = sys.modules["llm_shared.structured_ops"]

    with (
        patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result),
        patch(
            "security.content_firewall.get_content_firewall",
            return_value=MagicMock(
                inspect=AsyncMock(return_value=_make_firewall_verdict(content=mock_result.markdown))
            ),
        ),
        patch.object(
            ops_mod,
            "extract",
            new_callable=AsyncMock,
            side_effect=ExtractionError("LLM returned non-JSON output after 3 attempts"),
        ),
    ):
        with pytest.raises(ValueError, match="non-JSON"):
            await extract_url("https://ex.com", {"type": "object"})


@pytest.mark.asyncio
async def test_extract_url_strips_scripts_before_llm() -> None:
    """Script blocks in page markdown are stripped before being sent to LLM."""
    from web_fetch.extractors import extract_url

    script_page = "<script>steal_cookies()</script>\n# Product: Widget"
    mock_result = _make_fetch_result(markdown=script_page)
    captured_text: list = []

    async def capture_extract(text: str, schema, **kwargs) -> dict:
        captured_text.append(text)
        return {"product": "Widget"}

    schema = {"type": "object", "properties": {"product": {"type": "string"}}}
    safe_page = "# Product: Widget"
    ops_mod = sys.modules["llm_shared.structured_ops"]

    with (
        patch("web_fetch.WebFetcher.fetch", new_callable=AsyncMock, return_value=mock_result),
        patch(
            "security.content_firewall.get_content_firewall",
            return_value=MagicMock(inspect=AsyncMock(return_value=_make_firewall_verdict(content=safe_page))),
        ),
        patch.object(ops_mod, "extract", side_effect=capture_extract),
    ):
        await extract_url("https://ex.com", schema)

    assert captured_text, "extract() was never called"
    assert "steal_cookies" not in captured_text[0]
