# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Visual-browser proxy (`api/playwright.py`) session isolation (#11539).

BLOCKER follow-up: `api/playwright.py` proxies `/navigate`, `/reload`,
`/back`, `/forward`, `/status`, `/screenshot` (worker-screenshot), and
`/interact` straight through to the browser-worker's per-session-context
endpoints (see autobot-browser-worker/playwright-server.js and
test_browser_mcp_session_isolation.py), but originally sent no session_id at
all — every visual-browser action landed in the worker's shared "default"
bucket regardless of which conversation/user was driving it. These tests
prove every one of those proxy endpoints now puts the caller's session_id on
the wire (or the explicit default bucket when none is supplied), and that
two different conversations produce two distinct outbound session_id values.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from api.browser_mcp import DEFAULT_BROWSER_SESSION_ID
from api.playwright import (
    get_worker_status,
    go_back,
    go_forward,
    interact_with_page,
    navigate_to_url,
    reload_page,
    take_worker_screenshot,
)
from api.schemas_code import (
    PlaywrightInteractRequest,
    PlaywrightNavigateRequest,
    PlaywrightReloadRequest,
    PlaywrightSessionRequest,
)
from tests.unit.api._fake_http_client import fake_http_client


@pytest.mark.asyncio
async def test_navigate_threads_session_id():
    calls: list = []
    with patch("api.playwright.get_http_client", return_value=fake_http_client(calls, {"url": "https://github.com"})):
        await navigate_to_url(PlaywrightNavigateRequest(url="https://github.com", session_id="conversation-A"))

    assert calls[0]["url"].endswith("/navigate")
    assert calls[0]["payload"]["session_id"] == "conversation-A"


@pytest.mark.asyncio
async def test_navigate_defaults_session_id_when_omitted():
    calls: list = []
    with patch("api.playwright.get_http_client", return_value=fake_http_client(calls, {"url": "https://github.com"})):
        await navigate_to_url(PlaywrightNavigateRequest(url="https://github.com"))

    assert calls[0]["payload"]["session_id"] == DEFAULT_BROWSER_SESSION_ID


@pytest.mark.asyncio
async def test_reload_threads_session_id():
    calls: list = []
    with patch("api.playwright.get_http_client", return_value=fake_http_client(calls)):
        await reload_page(PlaywrightReloadRequest(session_id="conversation-A"))

    assert calls[0]["url"].endswith("/reload")
    assert calls[0]["payload"]["session_id"] == "conversation-A"


@pytest.mark.asyncio
async def test_back_and_forward_thread_session_id():
    calls: list = []
    with patch("api.playwright.get_http_client", return_value=fake_http_client(calls)):
        await go_back(PlaywrightSessionRequest(session_id="conversation-A"))
        await go_forward(PlaywrightSessionRequest(session_id="conversation-B"))

    assert calls[0]["url"].endswith("/back")
    assert calls[0]["payload"]["session_id"] == "conversation-A"
    assert calls[1]["url"].endswith("/forward")
    assert calls[1]["payload"]["session_id"] == "conversation-B"


@pytest.mark.asyncio
async def test_back_defaults_session_id_with_no_body():
    """PopoutChromiumBrowser.vue / VisualBrowserPanel.vue historically posted
    no body at all to /back — must still resolve to the default bucket, not
    crash or send session_id=None literally."""
    calls: list = []
    with patch("api.playwright.get_http_client", return_value=fake_http_client(calls)):
        await go_back(None)

    assert calls[0]["payload"]["session_id"] == DEFAULT_BROWSER_SESSION_ID


@pytest.mark.asyncio
async def test_worker_status_sends_session_id_as_query_param():
    calls: list = []
    with patch("api.playwright.get_http_client", return_value=fake_http_client(calls, {"status": "connected"})):
        await get_worker_status(session_id="conversation-A")

    assert calls[0]["url"].endswith("/status")
    assert calls[0]["payload"] == {"session_id": "conversation-A"}


@pytest.mark.asyncio
async def test_worker_screenshot_threads_session_id():
    calls: list = []
    with patch("api.playwright.get_http_client", return_value=fake_http_client(calls)):
        await take_worker_screenshot(PlaywrightSessionRequest(session_id="conversation-A"))

    assert calls[0]["url"].endswith("/screenshot")
    assert calls[0]["payload"]["session_id"] == "conversation-A"


@pytest.mark.asyncio
async def test_interact_threads_session_id():
    calls: list = []
    with patch("api.playwright.get_http_client", return_value=fake_http_client(calls)):
        await interact_with_page(
            PlaywrightInteractRequest(action="click", x=1, y=2, session_id="conversation-A")
        )

    assert calls[0]["url"].endswith("/click")
    assert calls[0]["payload"]["session_id"] == "conversation-A"


@pytest.mark.asyncio
async def test_two_conversations_get_distinct_session_ids_on_visual_browser_navigate():
    """SECURITY (#11539): the actual regression the blocker flagged — two
    conversations driving the visual-browser panel must never share a
    session_id on the wire to the worker's /navigate endpoint."""
    calls: list = []
    with patch("api.playwright.get_http_client", return_value=fake_http_client(calls, {"url": "https://github.com"})):
        await navigate_to_url(PlaywrightNavigateRequest(url="https://github.com/a", session_id="conversation-A"))
        await navigate_to_url(PlaywrightNavigateRequest(url="https://github.com/b", session_id="conversation-B"))

    session_ids = [c["payload"]["session_id"] for c in calls]
    assert session_ids == ["conversation-A", "conversation-B"]
    assert session_ids[0] != session_ids[1]
