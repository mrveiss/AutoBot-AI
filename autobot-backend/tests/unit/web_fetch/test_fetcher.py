# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for web_fetch.fetcher — render mode selection, SPA detection, fallback chain."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web_fetch.fetcher import (
    WebFetcher,
    _circuit_is_open,
    _domain_circuit,
    _fetch_bs4,
    _record_domain_failure,
    _record_domain_success,
)
from web_fetch.types import (
    ERR_CIRCUIT_OPEN,
    ERR_ROBOTS_BLOCKED,
    ERR_SSRF_BLOCKED,
    RenderMode,
)

_STATIC_HTML = """<html><head><title>Hello World</title></head>
<body><main>
<h1>Hello World</h1>
<p>This is a detailed article about some static content with enough words to
exceed the five hundred character threshold that the system uses to determine
whether the page is sufficiently rendered for indexing purposes. Let us add
more text to make absolutely sure we have enough content here for the tests
to pass reliably without any flakiness or brittle assertions on character count.
Additional text to pad the content some more so we clear five hundred chars.</p>
</main></body></html>"""

_SPA_HTML = """<html><body>
<noscript>Please enable JavaScript to use this application.</noscript>
<div id="app">Loading...</div>
</body></html>"""

_JINA_RESPONSE = """Title: Hello World
URL Source: https://example.com

# Hello World

This is a detailed article about some static content with enough words to
exceed the five hundred character threshold that the system uses to determine
whether the page is sufficiently rendered for indexing purposes. Let us add
more text to make absolutely sure we have enough content here for the tests
to pass reliably without any brittle assertions on character count. More words
here to ensure we hit the limit comfortably without any guessing.
"""


def _make_redis(cache_store=None):
    """Build async Redis mock backed by an in-memory dict."""
    store = {} if cache_store is None else cache_store
    redis = AsyncMock()

    async def mock_get(key):
        val = store.get(key)
        return val.encode("utf-8") if isinstance(val, str) else val

    async def mock_setex(key, ttl, value):
        store[key] = value if isinstance(value, str) else value.decode("utf-8")

    redis.get = mock_get
    redis.setex = mock_setex
    return redis, store


class TestSSRFGuard:
    @pytest.mark.asyncio
    async def test_private_ip_rejected(self) -> None:
        with patch("web_fetch.fetcher._is_public_url", return_value=False):
            result = await WebFetcher.fetch("http://127.0.0.1/page")
        assert result.success is False
        assert result.error_code == ERR_SSRF_BLOCKED

    @pytest.mark.asyncio
    async def test_link_local_rejected(self) -> None:
        with patch("web_fetch.fetcher._is_public_url", return_value=False):
            result = await WebFetcher.fetch("http://169.254.169.254/latest/meta-data/")
        assert result.success is False
        assert result.error_code == ERR_SSRF_BLOCKED

    @pytest.mark.asyncio
    async def test_private_class_a_rejected(self) -> None:
        with patch("web_fetch.fetcher._is_public_url", return_value=False):
            result = await WebFetcher.fetch("http://10.0.0.1/page")
        assert result.success is False
        assert result.error_code == ERR_SSRF_BLOCKED


class TestFetchBS4SSRFPinning:
    """Hostile-path tests for ``_fetch_bs4``'s pinned-redirect fetch (#13019).

    Mocks real DNS at ``autobot_shared.url_safety.socket.getaddrinfo`` — never
    the guard itself — mirroring ``api/tests/test_provider_auth_ssrf.py`` /
    ``tests/content_reach/test_http_pinned_get.py``. ``_is_public_url`` is
    NOT mocked in these tests so the real pre-check + real pinned connect
    both run, proving the fix holds end-to-end.
    """

    @pytest.mark.asyncio
    async def test_blocks_private_ip_literal_no_network_call(self) -> None:
        with patch("aiohttp.ClientSession") as mock_session_cls:
            html, status = await _fetch_bs4("http://10.0.0.5/secret", timeout=5.0)
        assert (html, status) == (None, None)
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocks_link_local_metadata_no_network_call(self) -> None:
        with patch("aiohttp.ClientSession") as mock_session_cls:
            html, status = await _fetch_bs4("http://169.254.169.254/latest/meta-data/", timeout=5.0)
        assert (html, status) == (None, None)
        mock_session_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocks_dns_rebind_public_at_precheck_private_at_connect(self) -> None:
        """A hostname that is public at the ``_is_public_url`` pre-check but
        resolves to a private address by the time the pinned connect happens
        must still be refused — the classic validate-then-forget TOCTOU.
        """
        public_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
        private_infos = [(2, 1, 6, "", ("10.0.0.9", 0))]

        with (
            patch(
                "autobot_shared.url_safety.socket.getaddrinfo",
                side_effect=[public_infos, private_infos],
            ),
            patch("aiohttp.ClientSession") as mock_session_cls,
        ):
            html, status = await _fetch_bs4("https://rebind.example.com/page", timeout=5.0)

        assert (html, status) == (None, None)
        mock_session_cls.assert_not_called()

    @staticmethod
    def _fake_getaddrinfo_for(public_hosts: dict):
        """Real DNS pass-through except for hostnames explicitly mapped to a
        canned answer — so literal-IP redirect targets (e.g. ``10.0.0.5``,
        which needs NO DNS at all) are resolved for real, not via a blanket
        mock that would misreport them as public.
        """
        import socket as _socket

        real_getaddrinfo = _socket.getaddrinfo

        def _fake(host, *args, **kwargs):
            if host in public_hosts:
                return public_hosts[host]
            return real_getaddrinfo(host, *args, **kwargs)

        return _fake

    @pytest.mark.asyncio
    async def test_redirect_to_internal_rejected_outright(self) -> None:
        """A public site that 302s to a private address is rejected, not followed."""
        fake_dns = self._fake_getaddrinfo_for({"open-redirect.example.com": [(2, 1, 6, "", ("93.184.216.34", 0))]})

        redirect_resp = MagicMock()
        redirect_resp.status = 302
        redirect_resp.headers = {"Location": "http://10.0.0.5/internal"}
        redirect_resp.release = AsyncMock(return_value=None)
        responses = [redirect_resp]

        class _FakeSession:
            def __init__(self, *a, **kw):
                pass

            async def request(self, method, url, **kwargs):
                return responses.pop(0)

            async def close(self):
                pass

        with (
            patch("autobot_shared.url_safety.socket.getaddrinfo", side_effect=fake_dns),
            patch("aiohttp.ClientSession", _FakeSession),
        ):
            html, status = await _fetch_bs4("https://open-redirect.example.com/go", timeout=5.0)

        assert (html, status) == (None, None)
        # Only the first (legitimate) hop connected; hop 2 was blocked pre-connect.
        assert responses == []

    @pytest.mark.asyncio
    async def test_genuinely_public_url_succeeds(self) -> None:
        """A real public host fetches successfully through the pinned path."""
        fake_dns = self._fake_getaddrinfo_for({"real.example.com": [(2, 1, 6, "", ("93.184.216.34", 0))]})

        ok_resp = MagicMock()
        ok_resp.status = 200

        async def _iter_chunked(_size):
            yield b"<html><body>hi</body></html>"

        ok_resp.content.iter_chunked = MagicMock(side_effect=lambda n: _iter_chunked(n))

        class _FakeSession:
            def __init__(self, *a, **kw):
                pass

            async def request(self, method, url, **kwargs):
                return ok_resp

            async def close(self):
                pass

        with (
            patch("autobot_shared.url_safety.socket.getaddrinfo", side_effect=fake_dns),
            patch("aiohttp.ClientSession", _FakeSession),
        ):
            html, status = await _fetch_bs4("https://real.example.com/page", timeout=5.0)

        assert status == 200
        assert "hi" in html


class TestCircuitBreaker:
    def setup_method(self):
        # Clean circuit state before each test
        _domain_circuit.clear()

    def test_circuit_closed_initially(self) -> None:
        assert _circuit_is_open("example.com") is False

    def test_circuit_opens_after_threshold(self) -> None:
        for _ in range(3):
            _record_domain_failure("flaky.com")
        assert _circuit_is_open("flaky.com") is True

    def test_circuit_clears_on_success(self) -> None:
        _record_domain_failure("flaky.com")
        _record_domain_success("flaky.com")
        # Two failures remain would not open circuit — success cleared them
        _record_domain_failure("flaky.com")
        _record_domain_failure("flaky.com")
        assert _circuit_is_open("flaky.com") is False

    @pytest.mark.asyncio
    async def test_open_circuit_returns_error(self) -> None:
        _domain_circuit["blocked.com"] = {
            "failures": [],
            "cooldown_until": time.monotonic() + 60.0,
        }
        with patch("web_fetch.fetcher._is_public_url", return_value=True):
            result = await WebFetcher.fetch("https://blocked.com/page")
        assert result.success is False
        assert result.error_code == ERR_CIRCUIT_OPEN
        assert result.retryable is True


class TestRenderModeAuto:
    @pytest.mark.asyncio
    async def test_jina_success_returns_markdown(self) -> None:
        # Jina returns enough content — should short-circuit before BS4.
        with (
            patch("web_fetch.fetcher._is_public_url", return_value=True),
            patch("web_fetch.fetcher._fetch_jina", return_value=_JINA_RESPONSE),
            patch("web_fetch.fetcher._parse_jina_markdown", return_value=("Hello World", _JINA_RESPONSE)),
            patch("web_fetch.fetcher._fetch_bs4", side_effect=AssertionError("should not be called")),
        ):
            result = await WebFetcher.fetch("https://example.com")

        assert result.success is True
        assert "Hello World" in result.markdown
        assert result.source == "jina"
        assert result.render_mode == RenderMode.AUTO

    @pytest.mark.asyncio
    async def test_jina_failure_falls_back_to_bs4(self) -> None:
        with (
            patch("web_fetch.fetcher._is_public_url", return_value=True),
            patch("web_fetch.fetcher._fetch_jina", return_value=None),
            patch("web_fetch.fetcher._fetch_bs4", return_value=(_STATIC_HTML, 200)),
        ):
            result = await WebFetcher.fetch("https://example.com")

        assert result.success is True
        assert result.source == "bs4"

    @pytest.mark.asyncio
    async def test_spa_triggers_playwright_fallback(self) -> None:
        playwright_html = _STATIC_HTML  # playwright returns rendered static content

        with (
            patch("web_fetch.fetcher._is_public_url", return_value=True),
            patch("web_fetch.fetcher._fetch_jina", return_value=None),
            patch("web_fetch.fetcher._fetch_bs4", return_value=(_SPA_HTML, 200)),
            patch("web_fetch.fetcher._fetch_playwright", return_value=playwright_html),
        ):
            result = await WebFetcher.fetch("https://spa.example.com")

        assert result.success is True
        assert result.source == "playwright"


class TestRenderModeFast:
    @pytest.mark.asyncio
    async def test_fast_mode_uses_jina(self) -> None:
        with (
            patch("web_fetch.fetcher._is_public_url", return_value=True),
            patch("web_fetch.fetcher._fetch_jina", return_value=_JINA_RESPONSE),
            patch("web_fetch.fetcher._parse_jina_markdown", return_value=("Hello World", _JINA_RESPONSE)),
            patch("web_fetch.fetcher._fetch_bs4", side_effect=AssertionError("should not be called")),
        ):
            result = await WebFetcher.fetch("https://example.com", render=RenderMode.FAST)

        assert result.success is True
        assert result.source == "jina"
        assert result.render_mode == RenderMode.FAST

    @pytest.mark.asyncio
    async def test_fast_mode_never_uses_playwright(self) -> None:
        playwright_called = False

        async def track_playwright(url, timeout):
            nonlocal playwright_called
            playwright_called = True
            return None

        with (
            patch("web_fetch.fetcher._is_public_url", return_value=True),
            patch("web_fetch.fetcher._fetch_jina", return_value=None),
            patch("web_fetch.fetcher._fetch_bs4", return_value=(_SPA_HTML, 200)),
            patch("web_fetch.fetcher._fetch_playwright", side_effect=track_playwright),
        ):
            await WebFetcher.fetch("https://example.com", render=RenderMode.FAST)

        assert playwright_called is False


class TestRenderModePlaywright:
    @pytest.mark.asyncio
    async def test_playwright_mode_skips_fast_path(self) -> None:
        jina_called = False

        async def track_jina(url, timeout):
            nonlocal jina_called
            jina_called = True
            return None

        with (
            patch("web_fetch.fetcher._is_public_url", return_value=True),
            patch("web_fetch.fetcher._fetch_jina", side_effect=track_jina),
            patch("web_fetch.fetcher._fetch_playwright", return_value=_STATIC_HTML),
        ):
            result = await WebFetcher.fetch("https://example.com", render=RenderMode.PLAYWRIGHT)

        assert jina_called is False
        assert result.source == "playwright"

    @pytest.mark.asyncio
    async def test_playwright_mode_on_success(self) -> None:
        with (
            patch("web_fetch.fetcher._is_public_url", return_value=True),
            patch("web_fetch.fetcher._fetch_playwright", return_value=_STATIC_HTML),
        ):
            result = await WebFetcher.fetch("https://example.com", render=RenderMode.PLAYWRIGHT)

        assert result.success is True
        assert result.render_mode == RenderMode.PLAYWRIGHT


class TestRobotsIntegration:
    @pytest.mark.asyncio
    async def test_robots_blocked_returns_error(self) -> None:
        robots = AsyncMock()
        robots.is_allowed = AsyncMock(return_value=False)

        with patch("web_fetch.fetcher._is_public_url", return_value=True):
            result = await WebFetcher.fetch("https://example.com/private", robots_cache=robots)

        assert result.success is False
        assert result.error_code == ERR_ROBOTS_BLOCKED


class TestDispatchAndCacheWrite:
    @pytest.mark.asyncio
    async def test_successful_result_written_to_cache(self) -> None:
        """Verify _cache is called after a successful fetch."""
        redis, store = _make_redis()

        with (
            patch("web_fetch.fetcher._is_public_url", return_value=True),
            patch("web_fetch.fetcher._fetch_jina", return_value=None),
            patch("web_fetch.fetcher._fetch_bs4", return_value=(_STATIC_HTML, 200)),
        ):
            result = await WebFetcher.fetch(
                "https://example.com/cached-path",
                render=RenderMode.AUTO,
                redis_client=redis,
            )

        assert result.success is True
        assert len(store) > 0  # something written to cache

    @pytest.mark.asyncio
    async def test_failed_result_not_cached(self) -> None:
        """SSRF-blocked results must not be cached."""
        redis, store = _make_redis()

        with patch("web_fetch.fetcher._is_public_url", return_value=False):
            result = await WebFetcher.fetch(
                "http://10.0.0.1/private",
                redis_client=redis,
            )

        assert result.success is False
        assert len(store) == 0


class TestCacheIntegration:
    @pytest.mark.asyncio
    async def test_cache_hit_skips_fetch(self) -> None:
        import json

        cached_payload = {
            "url": "https://example.com",
            "success": True,
            "markdown": "cached content",
            "title": "Cached",
            "render_mode": "auto",
            "source": "jina",
            "error_code": None,
            "retryable": False,
            "status_code": 200,
        }
        redis, store = _make_redis()
        from web_fetch.cache import _content_cache_key

        key = _content_cache_key("https://example.com", "auto")
        store[key] = json.dumps(cached_payload)

        jina_called = False

        async def track_jina(url, timeout):
            nonlocal jina_called
            jina_called = True
            return None

        with patch("web_fetch.fetcher._fetch_jina", side_effect=track_jina):
            result = await WebFetcher.fetch("https://example.com", redis_client=redis)

        assert jina_called is False
        assert result.markdown == "cached content"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_cache_populated_after_fetch(self) -> None:
        redis, store = _make_redis()

        with (
            patch("web_fetch.fetcher._is_public_url", return_value=True),
            patch("web_fetch.fetcher._fetch_jina", return_value=_JINA_RESPONSE),
        ):
            result = await WebFetcher.fetch("https://example.com", redis_client=redis)

        assert result.success is True
        # Verify something was stored in the cache store
        assert len(store) > 0


# ---------------------------------------------------------------------------
# WebFetcher.fetch_raw_html — public API (#7476)
# ---------------------------------------------------------------------------


class TestFetchRawHtml:
    """Contract tests for ``WebFetcher.fetch_raw_html`` — the public alias
    for ``_fetch_bs4`` introduced in #7476 to replace private-import usage
    in ``site_mapper.py`` and ``knowledge/connectors/web_crawler.py``."""

    @pytest.mark.asyncio
    async def test_returns_html_and_status_tuple(self) -> None:
        with patch(
            "web_fetch.fetcher._fetch_bs4",
            return_value=("<html><body>ok</body></html>", 200),
        ):
            html, status = await WebFetcher.fetch_raw_html("https://example.com")

        assert html == "<html><body>ok</body></html>"
        assert status == 200

    @pytest.mark.asyncio
    async def test_returns_none_tuple_on_error(self) -> None:
        with patch("web_fetch.fetcher._fetch_bs4", return_value=(None, None)):
            html, status = await WebFetcher.fetch_raw_html("https://example.com")

        assert html is None
        assert status is None

    @pytest.mark.asyncio
    async def test_threads_timeout_through(self) -> None:
        captured = {}

        async def _capture(url, timeout):
            captured["url"] = url
            captured["timeout"] = timeout
            return ("<html/>", 200)

        with patch("web_fetch.fetcher._fetch_bs4", side_effect=_capture):
            await WebFetcher.fetch_raw_html("https://example.com", timeout=7.5)

        assert captured == {"url": "https://example.com", "timeout": 7.5}

    @pytest.mark.asyncio
    async def test_default_timeout_is_30s(self) -> None:
        captured = {}

        async def _capture(url, timeout):
            captured["timeout"] = timeout
            return ("<html/>", 200)

        with patch("web_fetch.fetcher._fetch_bs4", side_effect=_capture):
            await WebFetcher.fetch_raw_html("https://example.com")

        assert captured["timeout"] == 30.0
