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


class ContentFormat(str, Enum):
    """What shape extracted content comes back in (#13236).

    `EXTRACT` used to mean "return the page's text/markup", which conflated
    three different things the real callers need and the three stacks
    produce:

    - `web_fetch/_fetch_playwright` needs **HTML**; it feeds a parser.
    - `content_reach` needs **text plus structured** data.
    - `tool_handler`'s search fallback needs **text**.

    Under one capability, a caller asking for `EXTRACT` could be routed to a
    backend that returns text where it needed markup — a silent regression,
    not an error. Format is now explicit and routable.
    """

    #: Human-readable page text, markup stripped.
    TEXT = "text"
    #: Raw HTML markup.
    HTML = "html"
    #: Parsed structure (headings, links, metadata) alongside text.
    STRUCTURED = "structured"


class Capability(str, Enum):
    """What a backend can do. Callers request these; backends declare them.

    ``(str, Enum)`` rather than ``StrEnum``: it is the shape
    ``autobot_shared.status_enums.AgentLifecycleStatus`` already uses, and it
    keeps the module importable on Python 3.10 as well as the 3.14 that
    ``autobot_shared/pyproject.toml`` targets.
    """

    #: Point the browser at a URL and report the resulting page state.
    NAVIGATE = "navigate"
    #: Return page text, markup stripped.
    EXTRACT_TEXT = "extract_text"
    #: Return raw HTML markup.
    EXTRACT_HTML = "extract_html"
    #: Return parsed structure (headings, links, metadata) alongside text.
    EXTRACT_STRUCTURED = "extract_structured"
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

    # --- Locality (#13236) -------------------------------------------------
    # Callers are not always indifferent to *where* a browser runs, and the
    # first two real migrations proved it: `web_fetch` uses the container
    # deliberately so Playwright does NOT run in the backend's own process,
    # and routing it in-process would defeat the reason that fallback exists.
    # Declaring locality as a capability keeps callers declarative — they say
    # what they need, not which module to call.

    #: Runs inside the calling process. Fast, but shares its memory and dies
    #: with it.
    IN_PROCESS = "in_process"
    #: Runs outside the calling process. Survives a backend restart and keeps
    #: browser memory out of it.
    OUT_OF_PROCESS = "out_of_process"


class BrowserError(Exception):
    """Base for every error raised through the canonical browser interface."""


class NoCapableBackendError(BrowserError):
    """No registered backend both declares the capabilities and is reachable."""


class UnsupportedFormatError(BrowserError):
    """The resolved backend cannot produce the requested content format.

    Raised rather than returning the wrong shape, which is what a single
    `EXTRACT` capability allowed (#13236).
    """


class UnsafeUrlError(BrowserError):
    """The URL failed the DNS-resolving public-address guard.

    Raised by the registry *before* any backend sees the request, so a backend
    cannot forget the check — the gap #13204 records for
    ``send_to_browser_vm`` and ``services/playwright_service``.
    """


#: Which capability a backend must declare to serve each content format.
FORMAT_CAPABILITY: dict[ContentFormat, Capability] = {
    ContentFormat.TEXT: Capability.EXTRACT_TEXT,
    ContentFormat.HTML: Capability.EXTRACT_HTML,
    ContentFormat.STRUCTURED: Capability.EXTRACT_STRUCTURED,
}


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
    #: Extract content as part of navigating. Some stacks do both in one
    #: round trip (`research_url(extract_content=True)`), so asking for it
    #: here avoids a second navigation (#13236).
    extract: bool = False


@dataclass(frozen=True)
class ExtractRequest:
    """Read content from the current page of *session_id*."""

    #: Required by stateless backends, which hold no current page. Validated
    #: by the registry exactly like a navigate URL (#13236).
    url: str | None = None
    session_id: str | None = None
    selector: str | None = None
    max_chars: int | None = None
    #: What shape to return. The registry refuses a backend that does not
    #: declare the matching capability, so a caller cannot silently receive
    #: text where it asked for markup (#13236).
    format: ContentFormat = ContentFormat.TEXT


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
    #: Structured extraction (headings, links, metadata) where the backend
    #: produces it. `content_reach` maps this onto `ContentResult.structured`,
    #: and it had no home in this result until #13236.
    structured: dict[str, Any] = field(default_factory=dict)
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
