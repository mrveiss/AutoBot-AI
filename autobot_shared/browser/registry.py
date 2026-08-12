# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Backend registration, capability dispatch, and the URL guard (#12651).

Two jobs, and the second is the one that matters:

1. **Dispatch.** Callers ask for capabilities; this picks the first registered
   backend that declares them all and answers `probe()`. That replaces the
   hand-rolled cascades each caller carries today — the one in
   `chat_workflow/tool_handler.py` has already been debugged once for
   re-issuing a call to a stack it had just found unavailable (#7478).

2. **The guard, enforced once.** Every URL entering the interface is checked
   with `autobot_shared.url_safety.is_public_url_async` — the DNS-*resolving*
   check — **before** any backend sees it. A backend therefore cannot forget
   it, and adding a backend cannot reintroduce the gap.

   That gap is real and recorded as **#13204**: `send_to_browser_vm()` performs
   no URL validation at all and is reachable from the agent tool path, while
   `services/playwright_service.py` validates nothing either. `is_url_allowed`
   in `api/browser_mcp.py` guards exactly one HTTP endpoint and is a regex over
   the URL string, so it cannot see where a hostname resolves.

**Backends register from the app that owns their transport.** `autobot_shared`
holds the contract and this registry; it never imports `research_browser_manager`,
`services.playwright_service` or `api.browser_mcp`. Importing an app-local
package from shared code is the inverted dependency #13201 had to design around
for `organization_service`, and this avoids it by construction.
"""

from __future__ import annotations

import logging

from autobot_shared.browser.base import (
    FORMAT_CAPABILITY,
    ActionRequest,
    BrowserBackend,
    BrowserResult,
    Capability,
    ExtractRequest,
    NavigateRequest,
    NoCapableBackendError,
    ScreenshotRequest,
    SessionHandle,
    UnsafeUrlError,
    UnsupportedFormatError,
)
from autobot_shared.url_safety import is_public_url_async

logger = logging.getLogger(__name__)

#: Registered backends, in preference order — first match wins.
_BACKENDS: list[BrowserBackend] = []


def register_backend(backend: BrowserBackend, *, prepend: bool = False) -> None:
    """Register *backend*. Later registrations rank lower unless *prepend*.

    Re-registering a backend with the same ``name`` replaces the earlier one,
    so a module that is imported twice cannot silently stack duplicates.
    """
    global _BACKENDS
    _BACKENDS = [b for b in _BACKENDS if b.name != backend.name]
    if prepend:
        _BACKENDS.insert(0, backend)
    else:
        _BACKENDS.append(backend)
    logger.info(
        "browser: registered backend %r with capabilities %s",
        backend.name,
        sorted(c.value for c in backend.capabilities),
    )


def registered_backends() -> tuple[BrowserBackend, ...]:
    """Snapshot of registered backends, in preference order."""
    return tuple(_BACKENDS)


def clear_backends() -> None:
    """Drop all registrations. For tests."""
    _BACKENDS.clear()


async def _guard_url(url: str | None) -> None:
    """Reject a URL that is empty or does not resolve to a public address."""
    if url is None:
        return
    if not url or not await is_public_url_async(url):
        logger.warning("browser: refusing non-public URL %r", url)
        raise UnsafeUrlError(f"URL is not a public address: {url!r}")


async def resolve_backend(requires: set[Capability]) -> BrowserBackend:
    """Return the first registered backend with *requires* that probes OK.

    Raises:
        NoCapableBackendError: nothing registered declares the capabilities, or
            everything that does is currently unreachable. The message names
            which of the two it was, because "no browser available" and "the
            browser you wanted is down" need different responses.
    """
    needed = frozenset(requires)
    candidates = [b for b in _BACKENDS if needed <= b.capabilities]
    if not candidates:
        raise NoCapableBackendError(
            f"no registered backend provides {sorted(c.value for c in needed)}; "
            f"registered: {[b.name for b in _BACKENDS] or 'none'}"
        )

    for backend in candidates:
        try:
            if await backend.probe():
                return backend
        except Exception as exc:
            logger.warning("browser: backend %r probe raised: %s", backend.name, exc)

    raise NoCapableBackendError(
        f"every backend providing {sorted(c.value for c in needed)} is unreachable: " f"{[b.name for b in candidates]}"
    )


class Browser:
    """Capability-scoped facade over one resolved backend.

    Obtained from :func:`get_browser`. Each entry point validates any URL it
    carries before dispatching, so the guard cannot be bypassed by reaching a
    backend directly through this object.
    """

    def __init__(self, backend: BrowserBackend) -> None:
        self._backend = backend

    @property
    def backend_name(self) -> str:
        """Which stack actually serves this browser — keeps dispatch debuggable."""
        return self._backend.name

    async def navigate(self, request: NavigateRequest) -> BrowserResult:
        """Navigate, after validating the target URL."""
        await _guard_url(request.url)
        return await self._backend.navigate(request)

    async def extract(self, request: ExtractRequest) -> BrowserResult:
        """Read content in the requested format.

        Two checks before dispatch:

        - the URL is guarded when the request carries one, because stateless
          backends need an explicit URL and it reaches the network exactly
          like a navigate URL;
        - the resolved backend must declare the capability for
          ``request.format``. Requiring a capability at ``get_browser`` time
          and naming a format here are two statements that can disagree; this
          ties them together so a caller cannot receive text where it asked
          for markup (#13236).
        """
        await _guard_url(request.url)

        needed = FORMAT_CAPABILITY[request.format]
        if needed not in self._backend.capabilities:
            raise UnsupportedFormatError(
                f"backend {self._backend.name!r} cannot produce "
                f"{request.format.value!r} (needs {needed.value!r}); "
                f"require it in get_browser() so dispatch picks a backend that can"
            )

        return await self._backend.extract(request)

    async def screenshot(self, request: ScreenshotRequest) -> BrowserResult:
        """Capture a page image, after validating any explicit URL."""
        await _guard_url(request.url)
        return await self._backend.screenshot(request)

    async def act(self, request: ActionRequest) -> BrowserResult:
        """Perform an interaction on the current page."""
        return await self._backend.act(request)

    async def release(self, session: SessionHandle) -> None:
        """Release a persistent session."""
        await self._backend.release(session)


async def get_browser(
    *,
    requires: set[Capability],
    session_id: str | None = None,
) -> Browser:
    """Return a browser able to do *requires*.

    Args:
        requires: Capabilities the caller needs. Ask for the minimum — a
            narrower set matches more backends.
        session_id: Reserved for session-affinity routing; accepted now so
            callers written against this signature keep working when
            per-session pinning lands.
    """
    backend = await resolve_backend(requires)
    logger.debug(
        "browser: resolved %s for %s",
        backend.name,
        sorted(c.value for c in requires),
    )
    return Browser(backend)
