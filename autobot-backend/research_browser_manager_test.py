# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hostile-path tests for research_browser_manager's DNS-rebind mitigation (#13018).

Playwright performs its own DNS resolution inside page.goto(); an earlier SSRF
check by a caller (e.g. content_reach.ensure_public_url) can be stale by the
time Playwright actually connects. ``ResearchBrowserSession.navigate_to`` now
re-validates immediately before page.goto as a compensating control (narrows,
does not close, the TOCTOU window — see the module docstring in
research_browser_manager.py).

The DNS-mocking technique (patching ``autobot_shared.url_safety.socket.getaddrinfo``)
mirrors ``api/tests/test_provider_auth_ssrf.py`` / PR #13020's
``tests/content_reach/test_http_pinned_get.py`` — it exercises the REAL
``is_public_url_async`` guard rather than mocking the guard away.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from research_browser_manager import ResearchBrowserManager, ResearchBrowserSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_with_page() -> ResearchBrowserSession:
    """Build a session with a mock Playwright page (no real browser)."""
    session = ResearchBrowserSession(session_id="s1", conversation_id="c1")
    session.page = MagicMock()
    session.page.goto = AsyncMock()
    session.page.title = AsyncMock(return_value="Title")
    session.page.content = AsyncMock(return_value="<html></html>")
    session.page.evaluate = AsyncMock(return_value=None)
    return session


def _dns(ip: str):
    """Return a patch context targeting the real getaddrinfo used by is_public_url_async."""
    fake_infos = [(2, 1, 6, "", (ip, 0))]
    return patch("autobot_shared.url_safety.socket.getaddrinfo", return_value=fake_infos)


# ---------------------------------------------------------------------------
# navigate_to — blocked cases: page.goto must NEVER be called
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_navigate_to_blocks_private_ip_no_goto_call():
    session = _make_session_with_page()
    with _dns("10.0.0.5"):
        result = await session.navigate_to("https://internal.example/")
    assert result["success"] is False
    assert result["blocked_by_guard"] is True
    session.page.goto.assert_not_called()


@pytest.mark.asyncio
async def test_navigate_to_blocks_loopback_no_goto_call():
    session = _make_session_with_page()
    with _dns("127.0.0.1"):
        result = await session.navigate_to("https://loopback.example/")
    assert result["success"] is False
    assert result["blocked_by_guard"] is True
    session.page.goto.assert_not_called()


@pytest.mark.asyncio
async def test_navigate_to_blocks_link_local_metadata_no_goto_call():
    """169.254.169.254 — cloud-metadata endpoint must be blocked."""
    session = _make_session_with_page()
    with _dns("169.254.169.254"):
        result = await session.navigate_to("https://metadata.example/")
    assert result["success"] is False
    assert result["blocked_by_guard"] is True
    session.page.goto.assert_not_called()


@pytest.mark.asyncio
async def test_navigate_to_blocks_dns_rebind_between_earlier_check_and_navigate():
    """A URL that passed an earlier (public) check but rebinds to a private
    address by the time navigate_to runs is still rejected — this is the
    exact vector #13018 documents: navigate_to re-checks independently of
    whatever the caller checked earlier."""
    session = _make_session_with_page()
    # Simulate: caller's earlier ensure_public_url check saw a public IP...
    with _dns("93.184.216.34"):
        from autobot_shared.url_safety import is_public_url_async

        assert await is_public_url_async("https://rebind.example/") is True
    # ...but by navigate_to time, DNS has rebound to a private address.
    with _dns("10.1.2.3"):
        result = await session.navigate_to("https://rebind.example/")
    assert result["success"] is False
    assert result["blocked_by_guard"] is True
    session.page.goto.assert_not_called()


# ---------------------------------------------------------------------------
# navigate_to — success case: a genuinely public address navigates normally
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_navigate_to_allows_public_ip_and_calls_goto():
    session = _make_session_with_page()
    with _dns("93.184.216.34"):
        result = await session.navigate_to("https://example.com/", wait_for_load=False)
    assert result["success"] is True
    assert "blocked_by_guard" not in result
    session.page.goto.assert_awaited_once()


# ---------------------------------------------------------------------------
# research_url() — a guard rejection must NOT fall through to the unguarded
# MHTML fallback (that fallback does its own raw page.goto with no re-check).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_research_url_returns_blocked_result_without_mhtml_fallback(monkeypatch):
    manager = ResearchBrowserManager()
    session = _make_session_with_page()

    async def _fake_get_or_create_session(conversation_id: str):
        return session

    monkeypatch.setattr(manager, "_get_or_create_session", _fake_get_or_create_session)

    fallback_mock = AsyncMock(side_effect=AssertionError("MHTML fallback must not run for a guard rejection"))
    monkeypatch.setattr(manager, "_try_mhtml_fallback", fallback_mock)

    with _dns("10.0.0.9"):
        result = await manager.research_url("c1", "https://internal.example/")

    assert result["success"] is False
    assert result["blocked_by_guard"] is True
    fallback_mock.assert_not_called()


@pytest.mark.asyncio
async def test_research_url_still_falls_back_on_natural_navigation_failure(monkeypatch):
    """Regression guard: a non-guard navigation failure must still reach the
    existing MHTML fallback path (#13018's gating must not swallow it)."""
    manager = ResearchBrowserManager()
    session = _make_session_with_page()
    session.page.goto = AsyncMock(side_effect=RuntimeError("net::ERR_CONNECTION_RESET"))

    async def _fake_get_or_create_session(conversation_id: str):
        return session

    monkeypatch.setattr(manager, "_get_or_create_session", _fake_get_or_create_session)

    fallback_mock = AsyncMock(return_value={"success": True, "status": "mhtml_fallback"})
    monkeypatch.setattr(manager, "_try_mhtml_fallback", fallback_mock)

    with _dns("93.184.216.34"):
        result = await manager.research_url("c1", "https://example.com/")

    fallback_mock.assert_awaited_once()
    assert result == {"success": True, "status": "mhtml_fallback"}
