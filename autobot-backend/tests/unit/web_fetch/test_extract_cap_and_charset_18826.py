# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The HTML extractor's input cap, and one charset-aware body decoder for every fetcher (#18826)."""

import codecs
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from media.document import html_extraction
from media.document.html_extraction import _capped, extract_html
from media.link.pipeline import LinkPipeline
from web_fetch.content_types import decode_body
from web_fetch.fetcher import _fetch_bs4

_LATIN1_CAFE = "café".encode("latin-1")


class TestInputCap:
    def test_over_cap_input_is_truncated_and_the_parser_never_sees_the_tail(self, monkeypatch) -> None:
        head = "<p>LEADING content</p><p>"
        html = head + "filler " * 50 + "</p><p>TAIL-MARKER</p>"
        seen = []
        real = html_extraction.BeautifulSoup

        def _spy(markup, *args, **kwargs):
            seen.append(markup)
            return real(markup, *args, **kwargs)

        monkeypatch.setattr(html_extraction, "HTML_EXTRACT_MAX_BYTES", len(head) + 10)
        monkeypatch.setattr(html_extraction, "BeautifulSoup", _spy)
        document = extract_html(html)
        assert seen == [head + "filler fil"]
        assert document.text.startswith("LEADING content") and "TAIL-MARKER" not in document.text

    def test_under_cap_input_is_parsed_whole(self, monkeypatch) -> None:
        html = "<p>one</p><p>two</p>"
        monkeypatch.setattr(html_extraction, "HTML_EXTRACT_MAX_BYTES", len(html))
        assert _capped(html, len(html)) is html
        assert extract_html(html).text == "one\n\ntwo"

    def test_a_character_split_by_the_byte_cut_is_dropped_not_replaced(self) -> None:
        assert _capped("<p>" + "é" * 10 + "</p>", 8) == "<p>éé"

    def test_a_tag_left_open_by_the_cut_is_dropped(self) -> None:
        assert _capped("<p>abc</p><span class='x'>tail</span>", 15) == "<p>abc</p>"

    def test_the_cap_is_registered_with_its_default(self) -> None:
        from autobot_shared.env_registry import REGISTRY

        spec = REGISTRY["AUTOBOT_HTML_EXTRACT_MAX_BYTES"]
        assert spec.default == 10 * 1024 * 1024 and spec.range == (64 * 1024, 256 * 1024 * 1024)


class TestDecodeBody:
    def test_header_charset_is_honoured(self) -> None:
        assert decode_body(_LATIN1_CAFE, "text/html; charset=iso-8859-1") == "café"
        assert decode_body(_LATIN1_CAFE, 'text/plain; Charset="ISO-8859-1"') == "café"

    def test_missing_charset_falls_back_to_utf8(self) -> None:
        assert decode_body("café".encode("utf-8"), "text/html") == "café"
        assert decode_body("café".encode("utf-8"), None) == "café"
        assert decode_body(_LATIN1_CAFE, "text/html") == "caf�"

    def test_meta_charset_is_sniffed_when_the_header_has_none(self) -> None:
        body = b'<html><head><meta charset="windows-1252"></head><body>' + _LATIN1_CAFE
        equiv = b'<meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1">' + _LATIN1_CAFE
        assert decode_body(body, "text/html").endswith("café")
        assert decode_body(equiv, None).endswith("café")

    def test_header_charset_outranks_meta_and_meta_is_ignored_for_non_html(self) -> None:
        body = '<meta charset="iso-8859-1">café'.encode("utf-8")
        assert decode_body(body, "text/html; charset=utf-8").endswith("café")
        assert decode_body(body, "text/plain").endswith("café")

    def test_a_bom_outranks_the_declared_charset(self) -> None:
        assert decode_body(codecs.BOM_UTF8 + "café".encode("utf-8"), "text/html; charset=iso-8859-1") == "café"

    @pytest.mark.parametrize("label", ["no-such-charset", "utf-7", "base64"])
    def test_unknown_refused_or_non_text_charset_decodes_as_utf8_and_logs(self, label) -> None:
        with patch("web_fetch.content_types.logger") as logger:
            assert decode_body("café +ADw-".encode("utf-8"), f"text/html; charset={label}") == "café +ADw-"
        assert logger.warning.called


def _response(body: bytes, content_type: str):
    async def _chunks(_size):
        yield body

    response = MagicMock()
    response.status, response.url = 200, "https://example.org/page"
    response.headers = {"Content-Type": content_type}
    response.content.iter_chunked = MagicMock(side_effect=_chunks)
    return response


def _pinned(response):
    @asynccontextmanager
    async def _fake(method, url, **kwargs):
        yield response

    return _fake


class TestEveryFetcherDecodesThroughIt:
    @pytest.mark.asyncio
    async def test_web_fetcher_bs4_body_honours_the_charset(self) -> None:
        response = _response(_LATIN1_CAFE, "text/html; charset=iso-8859-1")
        with (
            patch("web_fetch.fetcher._is_public_url", AsyncMock(return_value=True)),
            patch("autobot_shared.security.ssrf_guard.pinned_request_with_redirects", _pinned(response)),
        ):
            body, status, _content_type = await _fetch_bs4("https://example.org/page", 5.0)
        assert (body, status) == ("café", 200)

    @pytest.mark.asyncio
    async def test_link_pipeline_body_honours_the_charset(self) -> None:
        pipe = LinkPipeline()
        response = _response(_LATIN1_CAFE, "text/plain; charset=iso-8859-1")
        with (
            patch("media.link.pipeline._AIOHTTP_AVAILABLE", True),
            patch("media.link.pipeline._BS4_AVAILABLE", True),
            patch("autobot_shared.security.ssrf_guard.pinned_request_with_redirects", _pinned(response)),
            patch.object(pipe, "_is_public_url_async", new=AsyncMock(return_value=False)),
            patch.object(pipe, "_parse_body", return_value={"ok": True}) as parse,
        ):
            await pipe._fetch_and_parse("https://example.org/page", {})
        assert parse.call_args.args[0] == "café"


def test_the_title_cap_is_the_named_constant(monkeypatch):
    """The title cap is HTML_TITLE_MAX_CHARS (env AUTOBOT_HTML_TITLE_MAX_CHARS), not a literal (#18826)."""
    from media.document import html_extraction

    monkeypatch.setattr(html_extraction, "HTML_TITLE_MAX_CHARS", 10)
    doc = html_extraction.extract_html("<html><head><title>" + "T" * 50 + "</title></head><body><p>x</p></body></html>")
    assert doc.info["title"] == "T" * 10


def test_link_schemes_are_a_fixed_allowlist():
    """Only http/https/mailto targets survive; the list is deliberately not configurable."""
    from media.document.html_extraction import LINK_SCHEMES

    assert LINK_SCHEMES == frozenset({"http", "https", "mailto"})
    assert not {"javascript", "data", "file", "vbscript"} & LINK_SCHEMES


# --- review round on #18869: ReDoS, BOM order, the cap through a real caller -------------------


def test_an_unterminated_style_comment_parses_in_linear_time():
    """A ``/\\*.*?\\*/`` regex took ~48s on this (CodeRabbit/review on #18869); the scan is linear."""
    import time

    from media.document import inline_style

    started = time.monotonic()
    inline_style._split_declarations("/*a" * 40000)  # 120 KB, no closing */
    assert time.monotonic() - started < 1.0


def test_the_css_length_parse_is_linear_on_a_long_non_length():
    """``\\d+\\.?\\d*`` split one digit run two ways; the unambiguous ``_LENGTH`` rejects at once (#18869)."""
    import time

    from media.document import inline_style

    started = time.monotonic()
    assert inline_style._length("1" * 100000 + "!") is None  # "!" is no unit, so the match must fail
    assert time.monotonic() - started < 1.0
    assert inline_style._length("1.5em") == (1.5, "em")


def test_the_charset_parameter_parse_is_linear_on_padded_whitespace():
    """Adjacent ``\\s*["']?\\s*`` made ``charset=`` + n spaces + ``;`` quadratic (#18869); one ``\\s*`` suffices."""
    import time

    from web_fetch.content_types import _CHARSET_PARAM, _META_CHARSET

    started = time.monotonic()
    assert _CHARSET_PARAM.search("text/html; charset=" + " " * 50000 + ";") is None
    assert _META_CHARSET.search(b"<meta charset=" + b" " * 50000 + b">") is None
    assert time.monotonic() - started < 1.0
    assert _CHARSET_PARAM.search('text/html; charset= "UTF-8"').group(1) == "UTF-8"


def test_an_oversized_style_attribute_fails_closed(monkeypatch):
    """Padding can't push display:none past a truncation point: an over-cap style hides its element."""
    from media.document import inline_style

    monkeypatch.setattr(inline_style, "STYLE_MAX_CHARS", 256)
    assert inline_style.hidden_by_style("color:red;" + " " * 300 + "display:none") is True
    assert inline_style.hidden_by_style("color:red") is False


def test_the_html_sniff_is_linear_on_hostile_comments():
    """The old (<!--.*?-->\\s*)* sniff backtracked catastrophically; the linear scan returns at once."""
    import time

    from web_fetch.content_types import _looks_like_html, _sniff

    started = time.monotonic()
    for body in ("<!---->" * 3000 + "x", "<!-- a --> " * 3000 + "x", "<!--" + "-->" * 3000 + "x", "<!--" * 5000):
        _sniff(body)
    assert time.monotonic() - started < 1.0
    assert _looks_like_html("  <!-- c --> <HTML lang=en>") and not _looks_like_html("<!-- open")
    assert not _looks_like_html("<htmlx>")


def test_a_utf32_bom_is_not_misread_as_utf16():
    import codecs

    from web_fetch.content_types import decode_body

    assert decode_body(codecs.BOM_UTF32_LE + "café".encode("utf-32-le"), None) == "café"
    assert decode_body(codecs.BOM_UTF16_LE + "café".encode("utf-16-le"), None) == "café"


@pytest.mark.asyncio
async def test_the_cap_applies_through_chat_extract_content(monkeypatch):
    """A caller of extract_page (chat's extract_content) gets the capped extraction, not the full page."""
    from unittest.mock import AsyncMock

    from chat_workflow.tool_handler import ToolHandlerMixin
    from media.document import html_extraction

    monkeypatch.setattr(html_extraction, "HTML_EXTRACT_MAX_BYTES", 64 * 1024)
    page = "<html><body><p>LEADING-PART</p>" + "<p>filler text here</p>" * 6000 + "<p>TAIL-PART</p></body></html>"
    mixin = ToolHandlerMixin.__new__(ToolHandlerMixin)
    mixin._capture_live_page_snapshot = AsyncMock(return_value=(page, "https://example.com/p"))
    seen = {}

    async def _answer(text, url, goal):
        seen["text"] = text
        return "ok"

    mixin._answer_goal_from_markdown = _answer
    assert await mixin._exec_extract_content({"goal": "g"}, session_id="s") == "ok"
    assert "LEADING-PART" in seen["text"] and "TAIL-PART" not in seen["text"]
