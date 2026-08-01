# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Node browser-worker backend (#12651, ADR-009).

Wraps ``api/browser_mcp.send_to_browser_vm`` — the live, per-conversation
browser a user can watch and take over. It is the only stack with stable
indexed element refs and real interaction (click / fill / select), and the only
one holding a ``BrowserContext`` per chat ``session_id`` (#11539).

**This is the path #13204 is really about.** ``send_to_browser_vm`` performs no
URL validation at all, and it is reachable from the agent tool path via
``chat_workflow/tool_handler._web_search_via_browser_vm``. ``is_url_allowed``
in ``api/browser_mcp.py`` guards only the ``POST /mcp/navigate`` HTTP endpoint,
and is a regex over the URL string that cannot see where a hostname resolves.
Reaching this stack through the canonical interface puts the DNS-resolving
guard in front of it.
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

BACKEND_NAME = "worker"


class WorkerBrowserBackend:
    """The Node browser worker behind the canonical contract."""

    name = BACKEND_NAME
    capabilities = frozenset(
        {
            Capability.NAVIGATE,
            Capability.EXTRACT,
            Capability.SCREENSHOT,
            Capability.INTERACT,
            Capability.ELEMENT_REFS,
            Capability.PERSISTENT_SESSION,
        }
    )

    @staticmethod
    async def _send(action: str, params: dict, session_id: str | None):
        """Import lazily — ``api.browser_mcp`` pulls FastAPI routing in."""
        from api.browser_mcp import DEFAULT_BROWSER_SESSION_ID, send_to_browser_vm

        return await send_to_browser_vm(action, params, session_id=session_id or DEFAULT_BROWSER_SESSION_ID)

    async def probe(self) -> bool:
        """Reachable when the transport imports and the worker answers."""
        try:
            result = await self._send("observe_state", {}, None)
            return bool(result)
        except Exception as exc:
            logger.debug("worker browser backend unavailable: %s", exc)
            return False

    async def navigate(self, request: NavigateRequest) -> BrowserResult:
        """Navigate the session's context. The registry has validated the URL."""
        raw = await self._send("navigate", {"url": request.url}, request.session_id)
        return self._to_result(raw, request.session_id, url=request.url)

    async def extract(self, request: ExtractRequest) -> BrowserResult:
        """Read text from *selector*, defaulting to the whole body."""
        raw = await self._send(
            "get_text",
            {"selector": request.selector or "body"},
            request.session_id,
        )
        inner = raw.get("result", raw) if isinstance(raw, dict) else {}
        text = inner.get("text", "") if isinstance(inner, dict) else ""
        if request.max_chars is not None and text:
            text = text[: request.max_chars]

        return self._to_result(raw, request.session_id, content=text)

    async def screenshot(self, request: ScreenshotRequest) -> BrowserResult:
        """Capture the session's current page."""
        params: dict = {"full_page": request.full_page}
        if request.url:
            params["url"] = request.url
        raw = await self._send("screenshot", params, request.session_id)
        inner = raw.get("result", raw) if isinstance(raw, dict) else {}
        image = inner.get("path") or inner.get("screenshot") if isinstance(inner, dict) else None
        return self._to_result(raw, request.session_id, url=request.url, image_path=image)

    async def act(self, request: ActionRequest) -> BrowserResult:
        """Click / fill / select, by selector or stable element ref."""
        params: dict = dict(request.params)
        if request.selector:
            params["selector"] = request.selector
        if request.element_ref:
            params["ref"] = request.element_ref
        if request.value is not None:
            params["value"] = request.value

        raw = await self._send(request.action, params, request.session_id)
        return self._to_result(raw, request.session_id)

    async def release(self, session: SessionHandle) -> None:
        """Ask the worker to drop this conversation's context."""
        try:
            await self._send("close_session", {}, session.session_id)
        except Exception as exc:
            logger.warning("worker: releasing session %s failed: %s", session.session_id, exc)

    @staticmethod
    def _to_result(
        raw,
        session_id: str | None,
        *,
        url: str | None = None,
        content: str | None = None,
        image_path: str | None = None,
    ) -> BrowserResult:
        """Map the worker's envelope onto the canonical result."""
        payload = raw if isinstance(raw, dict) else {}
        inner = payload.get("result") if isinstance(payload.get("result"), dict) else {}

        return BrowserResult(
            success=bool(payload.get("success", True)) and "error" not in payload,
            backend=BACKEND_NAME,
            url=url or inner.get("url") or payload.get("url"),
            title=inner.get("title") or payload.get("title"),
            content=content,
            image_path=image_path,
            session=SessionHandle(session_id=session_id, backend=BACKEND_NAME) if session_id else None,
            error=payload.get("error"),
            details={k: v for k, v in payload.items() if k not in {"success", "error", "result"}},
        )
