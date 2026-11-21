# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""WebFetcher dispatches on Content-Type: only HTML reaches the HTML extractor (#18826).

Every network edge is stubbed and the paths that must not run raise, so a fall-through
fails loudly instead of fetching the real internet (#17746).
"""

from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from web_fetch.content_types import BodyKind, classify_body
from web_fetch.fetcher import WebFetcher
from web_fetch.profile import IngestProfile, extract_page
from web_fetch.types import ERR_UNSUPPORTED_CONTENT_TYPE, RenderMode

_URL = "https://example.com/resource"
_HTML = "<html><head><title>T</title></head><body><nav>MENU</nav><main><h1>Head</h1><p>Body.</p></main></body></html>"


@contextmanager
def _served(body, content_type, extractor_allowed=True):
    """Serve *body* with *content_type* on the direct path; Jina misses, Playwright must not run."""
    guard = {} if extractor_allowed else {"side_effect": AssertionError("HTML extractor reached for a non-HTML body")}
    with (
        patch("web_fetch.fetcher._is_public_url", AsyncMock(return_value=True)),
        patch("web_fetch.fetcher.get_cached_result", AsyncMock(return_value=None)),
        patch("web_fetch.fetcher.set_cached_result", AsyncMock()),
        patch("web_fetch.fetcher._fetch_jina", AsyncMock(return_value=None)),
        patch("web_fetch.fetcher._fetch_bs4", AsyncMock(return_value=(body, 200, content_type))),
        patch.object(WebFetcher, "_run_playwright", AsyncMock(side_effect=AssertionError("Playwright reached"))),
        patch("web_fetch.content_types.extract_page", wraps=extract_page, **guard),
    ):
        yield


@pytest.mark.parametrize(
    ("content_type", "body", "kind"),
    [
        ("text/html; charset=utf-8", "", BodyKind.HTML),
        ("application/xhtml+xml", "", BodyKind.HTML),
        ("text/plain", "<p>x</p>", BodyKind.TEXT),
        ("text/markdown", "# x", BodyKind.TEXT),
        ("application/json", "{}", BodyKind.JSON),
        ("application/ld+json", "{}", BodyKind.JSON),
        ("application/octet-stream", "abc", BodyKind.UNSUPPORTED),
        ("application/pdf", "%PDF-1.7", BodyKind.UNSUPPORTED),
        ("image/png", "�PNG", BodyKind.UNSUPPORTED),
        ("text/css", "a{}", BodyKind.UNSUPPORTED),
        (None, "<!DOCTYPE html><html><body>x</body></html>", BodyKind.HTML),
        ("", "  <!-- c --><html><body>x</body></html>", BodyKind.HTML),
        (None, "plain words, and a <b>tag</b> later", BodyKind.TEXT),
        (None, "\x00\x01binary", BodyKind.UNSUPPORTED),
        (None, "�" * 20 + "abc", BodyKind.UNSUPPORTED),
    ],
)
def test_classify(content_type, body, kind):
    assert classify_body(content_type, body) is kind


@pytest.mark.asyncio
@pytest.mark.parametrize("render", [RenderMode.FAST, RenderMode.AUTO])
async def test_plain_text_is_stored_as_text_never_html_parsed(render):
    body = "Line one   \r\n\r\n\r\n\r\n<p>not markup</p>\r\n"
    with _served(body, "text/plain; charset=utf-8", extractor_allowed=False):
        result = await WebFetcher.fetch(_URL, render=render)
    assert result.success and result.source == "bs4"
    assert result.markdown == "Line one\n\n<p>not markup</p>"
    assert result.title == ""


@pytest.mark.asyncio
async def test_json_passes_through_pretty_printed():
    with _served('{"name": "x", "items": [1, 2]}', "application/json", extractor_allowed=False):
        result = await WebFetcher.fetch(_URL, render=RenderMode.FAST)
    assert result.success
    assert result.markdown == '{\n  "name": "x",\n  "items": [\n    1,\n    2\n  ]\n}'


@pytest.mark.asyncio
async def test_json_that_does_not_parse_passes_through_as_text():
    with _served("{not json", "application/json", extractor_allowed=False):
        result = await WebFetcher.fetch(_URL, render=RenderMode.FAST)
    assert result.success and result.markdown == "{not json"


@pytest.mark.asyncio
@pytest.mark.parametrize("render", [RenderMode.FAST, RenderMode.AUTO])
@pytest.mark.parametrize("content_type", ["application/octet-stream", "application/pdf", "image/png"])
async def test_binary_body_fails_with_the_error_code_and_no_text(render, content_type):
    with _served("\x00\x01\x02�� binary", content_type, extractor_allowed=False):
        result = await WebFetcher.fetch(_URL, render=render)
    assert result.success is False
    assert result.error_code == ERR_UNSUPPORTED_CONTENT_TYPE
    assert result.markdown == "" and result.status_code == 200 and result.retryable is False


@pytest.mark.asyncio
async def test_refused_bodies_never_trip_the_domain_circuit():
    from web_fetch.fetcher import _domain_circuit

    _domain_circuit.pop("example.com", None)
    for _ in range(10):
        with _served("\x00 binary", "application/octet-stream", extractor_allowed=False):
            result = await WebFetcher.fetch(_URL, render=RenderMode.FAST)
        assert result.error_code == ERR_UNSUPPORTED_CONTENT_TYPE
    assert not _domain_circuit.get("example.com", {}).get("failures")


@pytest.mark.asyncio
async def test_undeclared_binary_is_refused_and_undeclared_html_is_extracted():
    with _served("\x00\x01 raw bytes", None, extractor_allowed=False):
        refused = await WebFetcher.fetch(_URL, render=RenderMode.FAST)
    assert refused.error_code == ERR_UNSUPPORTED_CONTENT_TYPE
    with _served(_HTML, None):
        page = await WebFetcher.fetch(_URL, render=RenderMode.FAST)
    assert page.markdown == "Head\n\nBody."


@pytest.mark.asyncio
async def test_html_is_unchanged_it_goes_through_the_one_extractor():
    with _served(_HTML, "text/html; charset=utf-8"):
        result = await WebFetcher.fetch(_URL, render=RenderMode.FAST)
    expected = extract_page(_HTML, IngestProfile.DOCUMENT, base_url=_URL)
    assert result.success and result.markdown == expected.text == "Head\n\nBody."
    assert result.title == "T"


@pytest.mark.asyncio
async def test_crawler_refuses_a_binary_page_with_a_specific_reason():
    from knowledge.connectors.models import ConnectorConfig
    from knowledge.connectors.web_crawler import WebCrawlerConnector, _no_content_reason

    connector = WebCrawlerConnector(
        ConnectorConfig(connector_id="c", connector_type="web_crawler", name="c", config={"urls": [_URL]})
    )
    with patch.object(WebFetcher, "fetch_raw_page", AsyncMock(return_value=("\x00\x01PK binary", 200, None))):
        result, raw_html = await connector._fetch_page_with_html(WebFetcher(), _URL)
    assert result.success is False and result.error_code == ERR_UNSUPPORTED_CONTENT_TYPE and raw_html == ""
    assert _no_content_reason(result).startswith("skipped: not an HTML, text or JSON page")


class TestLinkIngestDispatch:
    """Link ingest (media/link/pipeline.py) dispatches the same way, keeping its result shape."""

    _SHAPE = {"type", "url", "title", "description", "content", "word_count", "links", "open_graph"}

    def _parse(self, body, content_type):
        from media.link.pipeline import LinkPipeline

        pipe = LinkPipeline()
        with patch.object(pipe, "_parse_html", side_effect=AssertionError("HTML-parsed a non-HTML body")):
            return pipe._parse_body(body, _URL, content_type, {"k": "v"})

    def test_text_body_is_stored_as_text_with_no_links(self):
        result = self._parse("See https://example.com/x for details   \r\n\r\n\r\nnext   ", "text/plain")
        assert self._SHAPE <= set(result) and result["content_type"] == "text/plain"
        assert result["content"] == "See https://example.com/x for details\n\nnext"
        assert result["links"] == [] and result["open_graph"] == {} and result["metadata"] == {"k": "v"}

    def test_json_body_passes_through(self):
        result = self._parse('{"a": [1]}', "application/json; charset=utf-8")
        assert result["content"] == '{\n  "a": [\n    1\n  ]\n}' and result["links"] == []

    @pytest.mark.parametrize("content_type", ["application/octet-stream", "application/pdf", None])
    def test_binary_body_is_refused_with_no_text(self, content_type):
        result = self._parse("\x00\x01�� binary", content_type)
        assert result["processing_status"] == "error" and result["content"] == "" and result["links"] == []
        assert "unsupported content type" in result["error"]

    def test_html_body_still_goes_to_parse_html(self):
        from media.link.pipeline import LinkPipeline

        result = LinkPipeline()._parse_body(_HTML, _URL, "text/html", {})
        assert result["content"] == "Head\n\nBody." and result["title"] == "T"
