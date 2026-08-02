# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""In-process Playwright backend (#12651, ADR-009).

Wraps ``research_browser_manager`` — the stack that owns interactive research
sessions. It is the only one of the three with MHTML capture, "interaction
required" detection and human handoff, which is why ADR-009 wraps the stacks
rather than collapsing onto one.

The wrapper adapts shapes only. It adds no behaviour and removes none: the
manager's own DNS-rebind re-check (#13018) still runs inside ``navigate_to``,
underneath the registry's guard.
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

BACKEND_NAME = "in_process"


class InProcessBrowserBackend:
    """``research_browser_manager`` behind the canonical contract."""

    name = BACKEND_NAME
    capabilities = frozenset(
        {
            Capability.NAVIGATE,
            Capability.EXTRACT_TEXT,
            Capability.EXTRACT_STRUCTURED,
            Capability.MHTML,
            Capability.HUMAN_HANDOFF,
            Capability.PERSISTENT_SESSION,
            Capability.IN_PROCESS,
        }
    )

    @staticmethod
    def _manager():
        """Import lazily — Playwright is heavy and not every process needs it."""
        from research_browser_manager import get_research_browser_manager

        return get_research_browser_manager()

    async def probe(self) -> bool:
        """Reachable whenever the manager module imports."""
        try:
            self._manager()
            return True
        except Exception as exc:
            logger.debug("in_process browser backend unavailable: %s", exc)
            return False

    async def navigate(self, request: NavigateRequest) -> BrowserResult:
        """Navigate via ``research_url``, preserving its interaction handoff."""
        manager = self._manager()
        conversation_id = request.session_id or "canonical-browser"
        raw = await manager.research_url(
            conversation_id,
            request.url,
            extract_content=request.extract,
        )
        return self._to_result(raw, requested_url=request.url)

    async def extract(self, request: ExtractRequest) -> BrowserResult:
        """Extract content, which for this stack means a research round-trip."""
        manager = self._manager()
        conversation_id = request.session_id or "canonical-browser"
        session = manager.get_session_by_conversation(conversation_id)
        if session is None:
            return BrowserResult(
                success=False,
                backend=BACKEND_NAME,
                error=f"no in-process session for {conversation_id!r}",
            )

        raw = await session.extract_content()
        content = raw.get("text_content")
        if request.max_chars is not None and content:
            content = content[: request.max_chars]

        return BrowserResult(
            success=bool(raw.get("success")),
            backend=BACKEND_NAME,
            url=raw.get("url"),
            title=raw.get("title"),
            content=content,
            structured=raw.get("structured_data") or {},
            error=raw.get("error"),
            details={k: v for k, v in raw.items() if k not in {"success", "url", "title", "text_content", "error"}},
        )

    async def screenshot(self, request: ScreenshotRequest) -> BrowserResult:
        """Not supported — this stack has no screenshot path.

        Unreachable through the registry, which never routes SCREENSHOT here
        because the capability is not declared. Present so the object still
        satisfies the Protocol.
        """
        return BrowserResult(
            success=False,
            backend=BACKEND_NAME,
            error="in_process backend does not support screenshots",
        )

    async def act(self, request: ActionRequest) -> BrowserResult:
        """Not supported — no element refs or interaction on this stack."""
        return BrowserResult(
            success=False,
            backend=BACKEND_NAME,
            error="in_process backend does not support interaction",
        )

    async def release(self, session: SessionHandle) -> None:
        """Close the underlying research session."""
        manager = self._manager()
        existing = manager.get_session_by_conversation(session.session_id)
        if existing is not None:
            await manager.cleanup_session(existing.session_id)

    @staticmethod
    def _to_result(raw: dict, *, requested_url: str) -> BrowserResult:
        """Map ``research_url``'s dict onto the canonical result."""
        session_id = raw.get("session_id")
        navigation = raw.get("navigation") or {}
        content = raw.get("content") or {}

        return BrowserResult(
            success=bool(raw.get("success")),
            backend=BACKEND_NAME,
            url=navigation.get("url") or content.get("url") or requested_url,
            title=navigation.get("title") or content.get("title"),
            content=content.get("text_content"),
            structured=content.get("structured_data") or {},
            session=SessionHandle(session_id=session_id, backend=BACKEND_NAME) if session_id else None,
            interaction_required=raw.get("status") == "interaction_required",
            error=raw.get("error"),
            details={
                "status": raw.get("status"),
                "browser_url": raw.get("browser_url"),
                "actions": raw.get("actions"),
                "mhtml_backup": content.get("mhtml_backup"),
                "blocked_by_guard": navigation.get("blocked_by_guard"),
            },
        )
