# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""`capture_screenshot` validates its URL before reaching the container (#13204).

Every other browser/fetch entry point (`content_reach`, `web_fetch`,
`send_to_browser_vm`) runs a caller-supplied URL through the DNS-resolving
public-address guard first. `capture_screenshot` did not — a private or
link-local `url` reached the Playwright container's `/test-frontend` endpoint
unchecked. This pins that a non-public URL is rejected before any HTTP call,
and that a public one still reaches the container exactly as before.
"""

from unittest.mock import AsyncMock, patch

import pytest

from services.playwright_service import PlaywrightService


class _FakeResponse:
    def __init__(self, status: int, payload: dict):
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        return ""


class _FakePostCM:
    def __init__(self, response: _FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc_info):
        return False


@pytest.mark.asyncio
async def test_non_public_url_is_rejected_before_any_http_call():
    service = PlaywrightService()

    with (
        patch("services.playwright_service.is_public_url_async", AsyncMock(return_value=False)),
        patch.object(service, "is_ready", AsyncMock(return_value=True)) as is_ready,
    ):
        result = await service.capture_screenshot(url="http://169.254.169.254/latest/meta-data/")

    assert result == {
        "success": False,
        "error": "URL is not a public address",
        "url": "http://169.254.169.254/latest/meta-data/",
    }
    is_ready.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_url_still_reaches_the_container():
    service = PlaywrightService()

    async def _fake_post(*args, **kwargs):
        return _FakePostCM(_FakeResponse(200, {"has_screenshot": True, "screenshot_size": 42}))

    with (
        patch("services.playwright_service.is_public_url_async", AsyncMock(return_value=True)),
        patch.object(service, "is_ready", AsyncMock(return_value=True)),
        patch.object(service.http_client, "post", _fake_post),
    ):
        result = await service.capture_screenshot(url="https://example.com")

    assert result["success"] is True
    assert result["size"] == 42
