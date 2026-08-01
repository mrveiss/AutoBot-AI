# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""TDD tests for content_reach._url_guard + inline enforcement in URL-fetching backends (#10932, #11095).

Structure:
  1. ensure_public_url direct unit tests
  2. ensure_robots_allowed direct unit tests
  3. TrafilaturaBackend SSRF block (no underlying fetch)
  4. JinaReaderBackend SSRF block
  5. BrowserBackend SSRF block
  6. RedditJsonBackend url-mode SSRF block
  7. YtDlpCaptionBackend: SSRF on request.url + caption_url
  8. BrowserSearchBackend SSRF on built DDG url
  9. robots: disallowed → BackendError; env=0 → passes; allowed+public → reaches mocked fetch
  10. Real is_public_url_async: 169.254.169.254 blocked
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# 1. ensure_public_url — direct unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_public_url_raises_on_empty():
    """ensure_public_url raises BackendError for an empty string."""
    from content_reach._url_guard import ensure_public_url
    from content_reach.base import BackendError

    with pytest.raises(BackendError, match="blocked"):
        await ensure_public_url("")


@pytest.mark.asyncio
async def test_ensure_public_url_raises_when_not_public(monkeypatch):
    """ensure_public_url raises BackendError when is_public_url_async returns False."""
    import content_reach._url_guard as guard_mod
    from content_reach.base import BackendError

    async def _fake_public(url: str) -> bool:
        return False

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _fake_public)

    with pytest.raises(BackendError, match="blocked"):
        from content_reach._url_guard import ensure_public_url

        await ensure_public_url("http://10.0.0.1/secret")


@pytest.mark.asyncio
async def test_ensure_public_url_passes_for_public(monkeypatch):
    """ensure_public_url does NOT raise when is_public_url_async returns True."""
    import content_reach._url_guard as guard_mod

    async def _fake_public(url: str) -> bool:
        return True

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _fake_public)

    from content_reach._url_guard import ensure_public_url

    # Should not raise
    await ensure_public_url("https://example.com/page")


# ---------------------------------------------------------------------------
# 2. ensure_robots_allowed — direct unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ensure_robots_raises_when_disallowed(monkeypatch):
    """With robots enabled, ensure_robots_allowed raises BackendError when disallowed."""
    import content_reach._url_guard as guard_mod
    from content_reach.base import BackendError

    monkeypatch.setattr(guard_mod, "_RESPECT_ROBOTS", True)

    async def _mock_is_allowed(url: str, ua: str) -> bool:
        return False

    monkeypatch.setattr(guard_mod, "_robots_is_allowed", _mock_is_allowed)

    with pytest.raises(BackendError, match="robots"):
        from content_reach._url_guard import ensure_robots_allowed

        await ensure_robots_allowed("https://example.com/restricted")


@pytest.mark.asyncio
async def test_ensure_robots_noop_when_disabled(monkeypatch):
    """When _RESPECT_ROBOTS=False, ensure_robots_allowed is a no-op (no call to checker)."""
    import content_reach._url_guard as guard_mod

    monkeypatch.setattr(guard_mod, "_RESPECT_ROBOTS", False)

    called = []

    async def _mock_is_allowed(url: str, ua: str) -> bool:
        called.append(url)
        return False

    monkeypatch.setattr(guard_mod, "_robots_is_allowed", _mock_is_allowed)

    from content_reach._url_guard import ensure_robots_allowed

    await ensure_robots_allowed("https://example.com/robots-disallowed")
    assert called == [], "robots checker must not be called when disabled"


@pytest.mark.asyncio
async def test_ensure_robots_passes_when_allowed(monkeypatch):
    """With robots enabled, ensure_robots_allowed does NOT raise when allowed."""
    import content_reach._url_guard as guard_mod

    monkeypatch.setattr(guard_mod, "_RESPECT_ROBOTS", True)

    async def _mock_is_allowed(url: str, ua: str) -> bool:
        return True

    monkeypatch.setattr(guard_mod, "_robots_is_allowed", _mock_is_allowed)

    from content_reach._url_guard import ensure_robots_allowed

    await ensure_robots_allowed("https://example.com/allowed")


@pytest.mark.asyncio
async def test_ensure_robots_failopen_on_checker_error(monkeypatch):
    """Robots checker raising an exception → fail-open (no BackendError)."""
    import content_reach._url_guard as guard_mod

    monkeypatch.setattr(guard_mod, "_RESPECT_ROBOTS", True)

    async def _boom(url: str, ua: str) -> bool:
        raise RuntimeError("network error")

    monkeypatch.setattr(guard_mod, "_robots_is_allowed", _boom)

    from content_reach._url_guard import ensure_robots_allowed

    # Must NOT raise — fail-open
    await ensure_robots_allowed("https://example.com/page")


# ---------------------------------------------------------------------------
# 3. TrafilaturaBackend — SSRF block (no underlying HTTP call)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trafilatura_ssrf_block_no_fetch(monkeypatch):
    """TrafilaturaBackend.fetch raises BackendError on private URL and never calls client.get."""
    from unittest.mock import AsyncMock

    import content_reach._url_guard as guard_mod
    from content_reach.base import BackendError, ContentRequest
    from content_reach.sources.web_page import TrafilaturaBackend

    async def _fake_public(url: str) -> bool:
        return False

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _fake_public)

    mock_client = AsyncMock()
    backend = TrafilaturaBackend(client=mock_client)
    request = ContentRequest(url="http://127.0.0.1/admin")

    with pytest.raises(BackendError):
        await backend.fetch(request)

    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_trafilatura_ssrf_block_real_link_local():
    """TrafilaturaBackend.fetch raises BackendError for 169.254.169.254 (real util)."""
    from unittest.mock import AsyncMock

    from content_reach.base import BackendError, ContentRequest
    from content_reach.sources.web_page import TrafilaturaBackend

    mock_client = AsyncMock()
    backend = TrafilaturaBackend(client=mock_client)
    request = ContentRequest(url="http://169.254.169.254/latest/meta-data/")

    with pytest.raises(BackendError):
        await backend.fetch(request)

    mock_client.get.assert_not_called()


# ---------------------------------------------------------------------------
# 4. JinaReaderBackend — SSRF block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_jina_reader_ssrf_block_no_fetch(monkeypatch):
    """JinaReaderBackend.fetch raises BackendError on private URL and never calls client.get."""
    from unittest.mock import AsyncMock

    import content_reach._url_guard as guard_mod
    from content_reach.base import BackendError, ContentRequest
    from content_reach.sources.web_page import JinaReaderBackend

    async def _fake_public(url: str) -> bool:
        return False

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _fake_public)

    mock_client = AsyncMock()
    backend = JinaReaderBackend(client=mock_client)
    request = ContentRequest(url="http://10.0.0.1/secret")

    with pytest.raises(BackendError):
        await backend.fetch(request)

    mock_client.get.assert_not_called()


# ---------------------------------------------------------------------------
# 5. BrowserBackend — SSRF block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browser_backend_ssrf_block_no_manager_call(monkeypatch):
    """BrowserBackend.fetch raises BackendError on private URL and never calls manager."""
    import content_reach._url_guard as guard_mod
    import content_reach.backends.browser as browser_mod
    from content_reach.backends.browser import BrowserBackend
    from content_reach.base import BackendError, ContentRequest
    from source_attribution import SourceType

    async def _fake_public(url: str) -> bool:
        return False

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _fake_public)

    manager_calls = []

    class _StubManager:
        async def research_url(self, cid, url, extract_content=True):
            manager_calls.append(url)
            return {"success": True, "content": {"text_content": "x", "structured_data": {}}}

    monkeypatch.setattr(browser_mod, "_get_manager", lambda: _StubManager())

    backend = BrowserBackend(source_type=SourceType.WEB_PAGE)
    request = ContentRequest(url="http://192.168.1.1/internal")

    with pytest.raises(BackendError):
        await backend.fetch(request)

    assert manager_calls == [], "manager.research_url must not be called on SSRF block"


# ---------------------------------------------------------------------------
# 6. RedditJsonBackend — url-mode SSRF block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reddit_url_mode_ssrf_block_no_fetch(monkeypatch):
    """RedditJsonBackend url-mode raises BackendError on private URL and never calls client.get."""
    from unittest.mock import AsyncMock

    import content_reach._url_guard as guard_mod
    from content_reach.base import BackendError, ContentRequest
    from content_reach.sources.reddit import RedditJsonBackend

    async def _fake_public(url: str) -> bool:
        return False

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _fake_public)

    mock_client = AsyncMock()
    backend = RedditJsonBackend(client=mock_client)
    # Genuine reddit.com host so the url-mode branch is taken; the SSRF guard
    # (_is_public_url_async stubbed False) must then block before any fetch.
    request = ContentRequest(url="https://www.reddit.com/r/test")

    with pytest.raises(BackendError):
        await backend.fetch(request)

    mock_client.get.assert_not_called()


# ---------------------------------------------------------------------------
# 7. YtDlpCaptionBackend — SSRF on request.url + caption_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_yt_dlp_ssrf_block_request_url_no_extract(monkeypatch):
    """YtDlpCaptionBackend.fetch raises BackendError on private request.url; extract_info not called."""
    import content_reach._url_guard as guard_mod
    import content_reach.sources.youtube as yt_mod
    from content_reach.base import BackendError, ContentRequest
    from content_reach.sources.youtube import YtDlpCaptionBackend

    async def _fake_public(url: str) -> bool:
        return False

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _fake_public)

    extract_calls = []

    def _mock_extract(url: str) -> dict:
        extract_calls.append(url)
        return {}

    monkeypatch.setattr(yt_mod, "_ytdlp_extract_info", _mock_extract)

    from unittest.mock import AsyncMock

    mock_client = AsyncMock()
    backend = YtDlpCaptionBackend(client=mock_client)
    request = ContentRequest(url="http://127.0.0.1/video")

    with pytest.raises(BackendError):
        await backend.fetch(request)

    assert extract_calls == [], "_ytdlp_extract_info must not be called on SSRF block"
    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_yt_dlp_ssrf_block_caption_url_no_http(monkeypatch):
    """YtDlpCaptionBackend raises BackendError if caption track URL is private; no HTTP call."""
    from unittest.mock import AsyncMock

    import content_reach._url_guard as guard_mod
    import content_reach.sources.youtube as yt_mod
    from content_reach.base import BackendError, ContentRequest
    from content_reach.sources.youtube import YtDlpCaptionBackend

    # request.url is public, caption url is private
    public_urls = {"https://youtube.com/watch?v=abc": True}

    async def _selective_public(url: str) -> bool:
        return public_urls.get(url, False)

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _selective_public)

    def _mock_extract(url: str) -> dict:
        return {
            "subtitles": {"en": [{"ext": "vtt", "url": "http://10.0.0.1/captions.vtt"}]},
            "automatic_captions": {},
        }

    monkeypatch.setattr(yt_mod, "_ytdlp_extract_info", _mock_extract)

    mock_client = AsyncMock()
    backend = YtDlpCaptionBackend(client=mock_client)
    request = ContentRequest(url="https://youtube.com/watch?v=abc")

    with pytest.raises(BackendError):
        await backend.fetch(request)

    mock_client.get.assert_not_called()


# ---------------------------------------------------------------------------
# 8. BrowserSearchBackend — SSRF on built DDG URL
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_browser_search_ssrf_block_ddg_url(monkeypatch):
    """BrowserSearchBackend raises BackendError when SSRF guard blocks the DDG URL."""
    import content_reach._url_guard as guard_mod
    import content_reach.backends.browser as browser_mod
    from content_reach.backends.browser import BrowserSearchBackend
    from content_reach.base import BackendError, ContentRequest
    from source_attribution import SourceType

    async def _fake_public(url: str) -> bool:
        return False

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _fake_public)

    manager_calls = []

    class _StubManager:
        async def research_url(self, cid, url, extract_content=True):
            manager_calls.append(url)
            return {"success": True, "content": {"text_content": "x", "structured_data": {}}}

    monkeypatch.setattr(browser_mod, "_get_manager", lambda: _StubManager())

    backend = BrowserSearchBackend(source_type=SourceType.WEB_SEARCH)
    request = ContentRequest(query="test query")

    with pytest.raises(BackendError):
        await backend.fetch(request)

    assert manager_calls == []


# ---------------------------------------------------------------------------
# 9. robots end-to-end: TrafilaturaBackend
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trafilatura_robots_block_default(monkeypatch):
    """With default env (robots respected), disallowed URL → BackendError; client.get not called."""
    from unittest.mock import AsyncMock

    import content_reach._url_guard as guard_mod
    from content_reach.base import BackendError, ContentRequest
    from content_reach.sources.web_page import TrafilaturaBackend

    # SSRF passes, robots blocks
    async def _always_public(url: str) -> bool:
        return True

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _always_public)
    monkeypatch.setattr(guard_mod, "_RESPECT_ROBOTS", True)

    async def _disallowed(url: str, ua: str) -> bool:
        return False

    monkeypatch.setattr(guard_mod, "_robots_is_allowed", _disallowed)

    mock_client = AsyncMock()
    backend = TrafilaturaBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/restricted")

    with pytest.raises(BackendError):
        await backend.fetch(request)

    mock_client.get.assert_not_called()


@pytest.mark.asyncio
async def test_trafilatura_robots_disabled_env_passes(monkeypatch):
    """When _RESPECT_ROBOTS=False, disallowed URL proceeds to fetch."""
    from unittest.mock import AsyncMock, MagicMock

    import content_reach._url_guard as guard_mod
    import content_reach.sources.web_page as wp_mod
    from content_reach.base import ContentRequest
    from content_reach.sources.web_page import TrafilaturaBackend

    async def _always_public(url: str) -> bool:
        return True

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _always_public)
    monkeypatch.setattr(guard_mod, "_RESPECT_ROBOTS", False)

    monkeypatch.setattr(wp_mod, "_trafilatura_extract", lambda html: "extracted text")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body>content</body></html>"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    backend = TrafilaturaBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/page")

    result = await backend.fetch(request)
    assert result.success is True
    mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_trafilatura_public_allowed_url_reaches_fetch(monkeypatch):
    """Public + robots-allowed URL passes both guards and reaches client.get."""
    from unittest.mock import AsyncMock, MagicMock

    import content_reach._url_guard as guard_mod
    import content_reach.sources.web_page as wp_mod
    from content_reach.base import ContentRequest
    from content_reach.sources.web_page import TrafilaturaBackend

    async def _always_public(url: str) -> bool:
        return True

    monkeypatch.setattr(guard_mod, "_is_public_url_async", _always_public)
    monkeypatch.setattr(guard_mod, "_RESPECT_ROBOTS", True)

    async def _allowed(url: str, ua: str) -> bool:
        return True

    monkeypatch.setattr(guard_mod, "_robots_is_allowed", _allowed)
    monkeypatch.setattr(wp_mod, "_trafilatura_extract", lambda html: "article body")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<html><body>content</body></html>"

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    backend = TrafilaturaBackend(client=mock_client)
    request = ContentRequest(url="https://example.com/article")

    result = await backend.fetch(request)
    assert result.success is True
    mock_client.get.assert_called_once()


# ---------------------------------------------------------------------------
# 10. Real util: 169.254.169.254 is blocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_real_util_blocks_link_local():
    """Using the real is_public_url_async: 169.254.169.254 is blocked (returns False)."""
    from autobot_shared.url_safety import is_public_url_async

    result = await is_public_url_async("http://169.254.169.254/latest/meta-data/")
    assert result is False


# ---------------------------------------------------------------------------
# 11. robots cache bound (#11078)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_robots_cache_cleared_when_max_reached(monkeypatch):
    """Cache is cleared when it reaches _ROBOTS_CACHE_MAX before adding a new entry."""
    import content_reach._url_guard as guard_mod

    # Patch _ROBOTS_CACHE_MAX to a small value for the test.
    monkeypatch.setattr(guard_mod, "_ROBOTS_CACHE_MAX", 3)

    # Reset the cache state.
    guard_mod._robots_cache.clear()

    # Pre-populate with 3 entries (at the limit).
    import urllib.robotparser

    for i in range(3):
        guard_mod._robots_cache[f"http://example{i}.com"] = urllib.robotparser.RobotFileParser()

    assert len(guard_mod._robots_cache) == 3

    # Mock fetch to return empty text.
    async def _empty_fetch(domain: str) -> str:
        return ""

    monkeypatch.setattr(guard_mod, "_fetch_robots_text", _empty_fetch)

    # Adding a 4th entry should trigger a clear and then add the new entry.
    await guard_mod._get_robots_parser("http://new-domain.com")

    # After clear + add new, cache should contain exactly 1 entry.
    assert len(guard_mod._robots_cache) == 1
    assert "http://new-domain.com" in guard_mod._robots_cache


@pytest.mark.asyncio
async def test_robots_cache_under_max_not_cleared(monkeypatch):
    """Cache is NOT cleared when it is below _ROBOTS_CACHE_MAX."""
    import content_reach._url_guard as guard_mod

    monkeypatch.setattr(guard_mod, "_ROBOTS_CACHE_MAX", 10)
    guard_mod._robots_cache.clear()

    import urllib.robotparser

    for i in range(5):
        guard_mod._robots_cache[f"http://domain{i}.com"] = urllib.robotparser.RobotFileParser()

    async def _empty_fetch(domain: str) -> str:
        return ""

    monkeypatch.setattr(guard_mod, "_fetch_robots_text", _empty_fetch)

    await guard_mod._get_robots_parser("http://another.com")

    # 5 existing + 1 new = 6
    assert len(guard_mod._robots_cache) == 6


# ---------------------------------------------------------------------------
# 12. robots fetch-error log level is WARNING (#11078)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_robots_fetch_error_logs_at_warning(monkeypatch, caplog):
    """_fetch_robots_text logs at WARNING (not DEBUG) on a natural network failure.

    Real DNS is mocked (not the guard) per the ``config_declared_provider_test.py``
    pattern: the domain resolves to a public IP so ``pinned_connector`` succeeds,
    then the aiohttp session itself raises — this is a benign network failure,
    distinct from a guard rejection (see test_robots_fetch_blocked_by_ssrf_guard_*).
    """
    import logging

    import aiohttp

    import content_reach._url_guard as guard_mod

    class _FailSession:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        def get(self, *a, **kw):
            return _FailResp()

    class _FailResp:
        async def __aenter__(self):
            raise aiohttp.ClientError("blocked")

        async def __aexit__(self, *a):
            pass

    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(aiohttp, "ClientSession", _FailSession)

    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos),
        caplog.at_level(logging.WARNING, logger="content_reach._url_guard"),
    ):
        text = await guard_mod._fetch_robots_text("http://example.com")

    assert text == ""
    assert any("robots.txt fetch failed" in r.message for r in caplog.records if r.levelno == logging.WARNING)


# ---------------------------------------------------------------------------
# 13. robots.txt fetch is SSRF-guarded (#13017) — hostile cases, real DNS mocked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_robots_fetch_blocked_by_ssrf_guard_dns_rebind(caplog):
    """A domain that resolves to a private address must be blocked, and logged distinctly."""
    import logging

    import content_reach._url_guard as guard_mod

    fake_infos = [(2, 1, 6, "", ("10.0.0.9", 0))]
    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos),
        caplog.at_level(logging.WARNING, logger="content_reach._url_guard"),
    ):
        text = await guard_mod._fetch_robots_text("http://rebind.example.com")

    assert text == ""
    assert any(
        "blocked by SSRF guard" in r.message for r in caplog.records if r.levelno == logging.WARNING
    ), "a guard rejection must be logged distinctly from a natural fetch failure"


@pytest.mark.asyncio
async def test_robots_fetch_blocked_by_ssrf_guard_loopback():
    """A domain resolving to loopback must be blocked."""
    import content_reach._url_guard as guard_mod

    fake_infos = [(2, 1, 6, "", ("127.0.0.1", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        text = await guard_mod._fetch_robots_text("http://sneaky.example.com")
    assert text == ""


@pytest.mark.asyncio
async def test_robots_fetch_blocked_by_ssrf_guard_metadata():
    """A domain resolving to the cloud metadata address must be blocked."""
    import content_reach._url_guard as guard_mod

    fake_infos = [(2, 1, 6, "", ("169.254.169.254", 0))]
    with patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos):
        text = await guard_mod._fetch_robots_text("http://sneaky2.example.com")
    assert text == ""


@pytest.mark.asyncio
async def test_robots_fetch_rejects_redirect_to_internal_address(monkeypatch, caplog):
    """A public domain answering robots.txt with a 302 to an internal address must NOT be followed.

    This is the exact vector in defect 1 of #13017: allow_redirects must be
    False, and any 3xx must be rejected outright rather than followed.
    """
    import logging

    import aiohttp

    import content_reach._url_guard as guard_mod

    class _RedirectResp:
        status = 302

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _RedirectSession:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def get(self, url, *, allow_redirects, **kw):
            assert allow_redirects is False, "robots.txt fetch must never follow redirects"
            return _RedirectResp()

    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
    monkeypatch.setattr(aiohttp, "ClientSession", _RedirectSession)

    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos),
        caplog.at_level(logging.WARNING, logger="content_reach._url_guard"),
    ):
        text = await guard_mod._fetch_robots_text("http://public-domain.example.com")

    assert text == ""
    assert any(
        "redirect" in r.message and "rejected" in r.message for r in caplog.records if r.levelno == logging.WARNING
    )


@pytest.mark.asyncio
async def test_robots_fetch_pins_connector_for_public_domain():
    """A genuinely public domain resolves, is pinned, and its robots.txt is returned on 200."""
    import content_reach._url_guard as guard_mod

    class _OkResp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def text(self, encoding="utf-8", errors="replace"):
            return "User-agent: *\nDisallow: /admin"

    class _OkSession:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def get(self, url, *, allow_redirects, **kw):
            assert allow_redirects is False
            return _OkResp()

    fake_infos = [(2, 1, 6, "", ("93.184.216.34", 0))]
    with (
        patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos),
        patch("aiohttp.ClientSession", _OkSession),
    ):
        text = await guard_mod._fetch_robots_text("https://real.example.com")

    assert "Disallow: /admin" in text
