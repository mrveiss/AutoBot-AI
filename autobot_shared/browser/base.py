# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical browser contract — capabilities, requests, results (#12651).

AutoBot drives a browser through three separate stacks, and a single web-search
tool call already fans out across all of them (see ADR-009):

- in-process Python Playwright (`research_browser_manager.py`)
- a Playwright container (`services/playwright_service.py`)
- the Node browser worker (`api/browser_mcp.py` -> `autobot-browser-worker/`)

None is redundant: MHTML capture and human handoff exist only in-process,
stable element refs and interaction only in the worker, restart-survival only
out-of-process. So this module does not replace them — it gives callers one
contract to state *what* they need, and lets the registry decide *where* it
runs.

**Capabilities, not stack names.** A caller asking for `NAVIGATE | EXTRACT`
gets whichever backend can serve that and is currently up. Nothing outside a
backend implementation should name a stack.

This module is deliberately dependency-free beyond `autobot_shared`: the
backend implementations live in the app that owns their transport and register
themselves (see `registry.py`), so `autobot_shared` never imports a
backend-local package. That is the same inverted-dependency trap #13201 hit
with `organization_service`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class Capability(str, Enum):
    """What a backend can do. Callers request these; backends declare them.

    ``(str, Enum)`` rather than ``StrEnum``: it is the shape
    ``autobot_shared.status_enums.AgentLifecycleStatus`` already uses, and it
    keeps the module importable on Python 3.10 as well as the 3.14 that
    ``autobot_shared/pyproject.toml`` targets.
    """

    #: Point the browser at a URL and report the resulting page state.
    NAVIGATE = "navigate"
    #: Return the page's text/markup content.
    EXTRACT = "extract"
    #: Capture a page image.
    SCREENSHOT = "screenshot"
    #: Click / fill / select. Requires ELEMENT_REFS in practice.
    INTERACT = "interact"
    #: Stable indexed element references that survive a re-render.
    ELEMENT_REFS = "element_refs"
    #: Capture the page as MHTML.
    MHTML = "mhtml"
    #: Detect "interaction required" and hand control to a human.
    HUMAN_HANDOFF = "human_handoff"
    #: A browser context that outlives a single call, keyed by session.
    PERSISTENT_SESSION = "persistent_session"


class BrowserError(Exception):
    """Base for every error raised through the canonical browser interface."""


class NoCapableBackendError(BrowserError):
    """No registered backend both declares the capabilities and is reachable."""


class UnsafeUrlError(BrowserError):
    """The URL failed the DNS-resolving public-address guard.

    Raised by the registry *before* any backend sees the request, so a backend
    cannot forget the check — the gap #13204 records for
    ``send_to_browser_vm`` and ``services/playwright_service``.
    """


@dataclass(frozen=True)
class SessionHandle:
    """Identifies a browser context that outlives a single call."""

    session_id: str
    backend: str


@dataclass(frozen=True)
class NavigateRequest:
    """Go to *url*, optionally within an existing session."""

    url: str
    session_id: str | None = None
    wait_for_load: bool = True
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class ExtractRequest:
    """Read content from the current page of *session_id*."""

    session_id: str | None = None
    selector: str | None = None
    max_chars: int | None = None


@dataclass(frozen=True)
class ScreenshotRequest:
    """Capture *url* (or the current page when *url* is None)."""

    url: str | None = None
    session_id: str | None = None
    full_page: bool = True
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class ActionRequest:
    """Perform an interaction — click, fill, select — on the current page."""

    action: str
    session_id: str | None = None
    selector: str | None = None
    element_ref: str | None = None
    value: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserResult:
    """Common shape for every backend response.

    ``backend`` names the stack that actually served the call. It is carried on
    every result specifically so the indirection this interface introduces
    stays debuggable — a caller can always see where its request ran.
    """

    success: bool
    backend: str
    url: str | None = None
    title: str | None = None
    content: str | None = None
    image_path: str | None = None
    session: SessionHandle | None = None
    interaction_required: bool = False
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class BrowserBackend(Protocol):
    """One execution stack behind the canonical interface.

    A backend implements only the methods matching the capabilities it
    declares; the registry never routes a call to a backend that did not
    declare the corresponding capability, so unimplemented methods are
    unreachable rather than raising.
    """

    name: str
    capabilities: frozenset[Capability]

    async def probe(self) -> bool:
        """True if this backend is currently usable."""
        ...

    async def navigate(self, request: NavigateRequest) -> BrowserResult:
        """Navigate to a URL. The registry has already validated it."""
        ...

    async def extract(self, request: ExtractRequest) -> BrowserResult:
        """Return page content."""
        ...

    async def screenshot(self, request: ScreenshotRequest) -> BrowserResult:
        """Capture a page image."""
        ...

    async def act(self, request: ActionRequest) -> BrowserResult:
        """Perform an interaction on the current page."""
        ...

    async def release(self, session: SessionHandle) -> None:
        """Release a persistent session's resources."""
        ...
