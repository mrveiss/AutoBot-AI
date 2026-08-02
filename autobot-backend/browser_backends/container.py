# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Playwright-container backend (#12651, ADR-009).

Wraps ``services/playwright_service.py`` — the stack ``web_fetch`` uses for its
JS-render fallback, deliberately out-of-process so Playwright does not run
inside the backend. It is stateless and survives a backend restart, which the
in-process stack does not.

**This stack validates no URLs of its own** — one half of #13204. Behind the
canonical interface the registry's DNS-resolving guard runs before anything
reaches it, so routing a caller through here closes that gap for this path.
"""

from __future__ import annotations

import logging

from autobot_shared.browser.base import (
    ActionRequest,
    BrowserResult,
    Capability,
    ExtractRequest,
    NavigateRequest,
    ScreenshotRequest,
    SessionHandle,
)

logger = logging.getLogger(__name__)

BACKEND_NAME = "container"


class ContainerBrowserBackend:
    """``PlaywrightService`` behind the canonical contract."""

    name = BACKEND_NAME
    capabilities = frozenset(
        {
            Capability.SCREENSHOT,
            # #13236: the container also exposes a `render` endpoint, which
            # `web_fetch/fetcher.py::_fetch_playwright` already uses for its
            # JS-render fallback. Phase 2 wrapped only `capture_screenshot`
            # and under-declared this stack.
            Capability.EXTRACT_HTML,
            Capability.OUT_OF_PROCESS,
        }
    )

    @staticmethod
    async def _service():
        """Import lazily so a process that never renders pays nothing."""
        from services.playwright_service import get_playwright_service

        return await get_playwright_service()

    async def probe(self) -> bool:
        """Healthy only when the container answers its health check."""
        try:
            service = await self._service()
            return await service.is_ready()
        except Exception as exc:
            logger.debug("container browser backend unavailable: %s", exc)
            return False

    async def navigate(self, request: NavigateRequest) -> BrowserResult:
        """Not supported — this stack exposes no bare navigate endpoint."""
        return BrowserResult(
            success=False,
            backend=BACKEND_NAME,
            error="container backend does not support navigate",
        )

    async def extract(self, request: ExtractRequest) -> BrowserResult:
        """Render *url* and return its **HTML**.

        Stateless: the URL is required because this backend holds no current
        page. The registry has already validated it (#13236).
        """
        if not request.url:
            return BrowserResult(
                success=False,
                backend=BACKEND_NAME,
                error="container backend needs an explicit url (it holds no session)",
            )

        service = await self._service()
        raw = await service._post_and_parse(
            "render",
            {"url": request.url, "wait": "networkidle"},
        )
        html = raw.get("html") or raw.get("content")
        if request.max_chars is not None and html:
            html = html[: request.max_chars]

        return BrowserResult(
            success=bool(html),
            backend=BACKEND_NAME,
            url=request.url,
            content=html,
            error=None if html else raw.get("error", "render returned no content"),
        )

    async def screenshot(self, request: ScreenshotRequest) -> BrowserResult:
        """Capture *url*. The registry has already validated it."""
        if not request.url:
            return BrowserResult(
                success=False,
                backend=BACKEND_NAME,
                error="container backend needs an explicit url (it holds no session)",
            )

        service = await self._service()
        raw = await service.capture_screenshot(
            url=request.url,
            full_page=request.full_page,
        )
        return BrowserResult(
            success=bool(raw.get("success")),
            backend=BACKEND_NAME,
            url=request.url,
            image_path=raw.get("screenshot") or raw.get("screenshot_path"),
            error=raw.get("error"),
            details={k: v for k, v in raw.items() if k not in {"success", "error"}},
        )

    async def act(self, request: ActionRequest) -> BrowserResult:
        """Not supported — no element refs or interaction on this stack."""
        return BrowserResult(
            success=False,
            backend=BACKEND_NAME,
            error="container backend does not support interaction",
        )

    async def release(self, session: SessionHandle) -> None:
        """No-op — the container holds no per-caller session."""
        return None
