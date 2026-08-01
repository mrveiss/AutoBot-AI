# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The canonical browser interface dispatches and guards (#12651, ADR-009).

The property that justifies this layer existing is the guard: every URL is
validated with the DNS-resolving check *before* any backend sees it, so a
backend cannot forget it and a new backend cannot reintroduce the gap. That
gap is real today — `send_to_browser_vm()` validates nothing and is reachable
from the agent tool path (#13204).

The rest pins dispatch: capabilities select the backend, an unreachable
backend is skipped rather than returned, and the two "nothing available" cases
are distinguishable.
"""

from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.browser.base import (
    ActionRequest,
    BrowserResult,
    Capability,
    ExtractRequest,
    NavigateRequest,
    NoCapableBackendError,
    ScreenshotRequest,
    SessionHandle,
    UnsafeUrlError,
)
from autobot_shared.browser.registry import (
    clear_backends,
    get_browser,
    register_backend,
    registered_backends,
    resolve_backend,
)

_GUARD = "autobot_shared.browser.registry.is_public_url_async"


class FakeBackend:
    """Minimal backend recording what it was asked to do."""

    def __init__(self, name, capabilities, *, reachable=True, probe_raises=False):
        self.name = name
        self.capabilities = frozenset(capabilities)
        self._reachable = reachable
        self._probe_raises = probe_raises
        self.calls: list[str] = []

    async def probe(self) -> bool:
        if self._probe_raises:
            raise RuntimeError("probe exploded")
        return self._reachable

    async def navigate(self, request):
        self.calls.append(f"navigate:{request.url}")
        return BrowserResult(success=True, backend=self.name, url=request.url)

    async def extract(self, request):
        self.calls.append("extract")
        return BrowserResult(success=True, backend=self.name, content="body")

    async def screenshot(self, request):
        self.calls.append(f"screenshot:{request.url}")
        return BrowserResult(success=True, backend=self.name, image_path="/tmp/x.png")

    async def act(self, request):
        self.calls.append(f"act:{request.action}")
        return BrowserResult(success=True, backend=self.name)

    async def release(self, session):
        self.calls.append(f"release:{session.session_id}")


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_backends()
    yield
    clear_backends()


def _allow():
    return patch(_GUARD, AsyncMock(return_value=True))


def _deny():
    return patch(_GUARD, AsyncMock(return_value=False))


# ---------------------------------------------------------------- the guard


@pytest.mark.asyncio
async def test_navigate_to_a_non_public_url_never_reaches_the_backend():
    """The whole reason this layer exists (#13204)."""
    backend = FakeBackend("fake", {Capability.NAVIGATE})
    register_backend(backend)

    with _deny():
        browser = await get_browser(requires={Capability.NAVIGATE})
        with pytest.raises(UnsafeUrlError):
            await browser.navigate(NavigateRequest(url="http://169.254.169.254/latest/meta-data/"))

    assert backend.calls == [], "backend saw a URL the guard rejected"


@pytest.mark.asyncio
async def test_screenshot_url_is_guarded_too():
    """services/playwright_service's screenshot path validates nothing today."""
    backend = FakeBackend("fake", {Capability.SCREENSHOT})
    register_backend(backend)

    with _deny():
        browser = await get_browser(requires={Capability.SCREENSHOT})
        with pytest.raises(UnsafeUrlError):
            await browser.screenshot(ScreenshotRequest(url="http://localhost:6379/"))

    assert backend.calls == []


@pytest.mark.asyncio
async def test_extract_url_is_guarded_for_stateless_backends():
    """#13236: ExtractRequest gained a url, so it needs the same guard.

    A stateless backend has no current page and must be given a URL; that URL
    reaches the network exactly like a navigate URL, so it cannot skip the
    check.
    """
    backend = FakeBackend("fake", {Capability.EXTRACT})
    register_backend(backend)

    with _deny():
        browser = await get_browser(requires={Capability.EXTRACT})
        with pytest.raises(UnsafeUrlError):
            await browser.extract(ExtractRequest(url="http://169.254.169.254/"))

    assert backend.calls == []


@pytest.mark.asyncio
async def test_extract_without_a_url_is_not_blocked():
    """Session-holding backends read their current page — nothing to validate."""
    backend = FakeBackend("fake", {Capability.EXTRACT})
    register_backend(backend)

    with _deny():
        browser = await get_browser(requires={Capability.EXTRACT})
        result = await browser.extract(ExtractRequest(session_id="s1"))

    assert result.success is True


@pytest.mark.asyncio
async def test_locality_narrows_dispatch():
    """#13236: a caller that must stay out-of-process cannot be routed in."""
    in_proc = FakeBackend("in_proc", {Capability.EXTRACT, Capability.IN_PROCESS})
    out_proc = FakeBackend("out_proc", {Capability.EXTRACT, Capability.OUT_OF_PROCESS})
    register_backend(in_proc)
    register_backend(out_proc)

    chosen = await resolve_backend({Capability.EXTRACT, Capability.OUT_OF_PROCESS})

    assert chosen.name == "out_proc", "locality must pin dispatch, not just rank it"


@pytest.mark.asyncio
async def test_empty_url_is_rejected():
    backend = FakeBackend("fake", {Capability.NAVIGATE})
    register_backend(backend)

    with _allow():
        browser = await get_browser(requires={Capability.NAVIGATE})
        with pytest.raises(UnsafeUrlError):
            await browser.navigate(NavigateRequest(url=""))

    assert backend.calls == []


@pytest.mark.asyncio
async def test_public_url_passes_through():
    backend = FakeBackend("fake", {Capability.NAVIGATE})
    register_backend(backend)

    with _allow():
        browser = await get_browser(requires={Capability.NAVIGATE})
        result = await browser.navigate(NavigateRequest(url="https://example.com/"))

    assert result.success is True
    assert result.backend == "fake"
    assert backend.calls == ["navigate:https://example.com/"]


@pytest.mark.asyncio
async def test_screenshot_without_a_url_is_not_blocked():
    """A capture of the *current* page carries no URL to validate."""
    backend = FakeBackend("fake", {Capability.SCREENSHOT})
    register_backend(backend)

    with _deny():
        browser = await get_browser(requires={Capability.SCREENSHOT})
        result = await browser.screenshot(ScreenshotRequest(url=None))

    assert result.success is True


# ---------------------------------------------------------------- dispatch


@pytest.mark.asyncio
async def test_capabilities_select_the_backend_not_registration_order():
    poor = FakeBackend("poor", {Capability.NAVIGATE})
    rich = FakeBackend("rich", {Capability.NAVIGATE, Capability.INTERACT})
    register_backend(poor)
    register_backend(rich)

    chosen = await resolve_backend({Capability.NAVIGATE, Capability.INTERACT})

    assert chosen.name == "rich"


@pytest.mark.asyncio
async def test_first_capable_backend_wins_when_several_match():
    first = FakeBackend("first", {Capability.NAVIGATE})
    second = FakeBackend("second", {Capability.NAVIGATE})
    register_backend(first)
    register_backend(second)

    assert (await resolve_backend({Capability.NAVIGATE})).name == "first"


@pytest.mark.asyncio
async def test_prepend_overrides_preference_order():
    register_backend(FakeBackend("first", {Capability.NAVIGATE}))
    register_backend(FakeBackend("preferred", {Capability.NAVIGATE}), prepend=True)

    assert (await resolve_backend({Capability.NAVIGATE})).name == "preferred"


@pytest.mark.asyncio
async def test_unreachable_backend_is_skipped_for_a_reachable_one():
    down = FakeBackend("down", {Capability.NAVIGATE}, reachable=False)
    up = FakeBackend("up", {Capability.NAVIGATE})
    register_backend(down)
    register_backend(up)

    assert (await resolve_backend({Capability.NAVIGATE})).name == "up"


@pytest.mark.asyncio
async def test_a_backend_whose_probe_raises_is_skipped_not_fatal():
    """A broken probe must not take out the whole cascade."""
    broken = FakeBackend("broken", {Capability.NAVIGATE}, probe_raises=True)
    good = FakeBackend("good", {Capability.NAVIGATE})
    register_backend(broken)
    register_backend(good)

    assert (await resolve_backend({Capability.NAVIGATE})).name == "good"


@pytest.mark.asyncio
async def test_missing_capability_and_all_down_are_distinguishable():
    """'No browser does this' and 'the browser is down' need different responses."""
    with pytest.raises(NoCapableBackendError, match="no registered backend provides"):
        await resolve_backend({Capability.MHTML})

    register_backend(FakeBackend("down", {Capability.MHTML}, reachable=False))
    with pytest.raises(NoCapableBackendError, match="unreachable"):
        await resolve_backend({Capability.MHTML})


# ---------------------------------------------------------------- registry


def test_reregistering_a_name_replaces_rather_than_stacks():
    """A module imported twice must not register duplicates."""
    register_backend(FakeBackend("dup", {Capability.NAVIGATE}))
    register_backend(FakeBackend("dup", {Capability.NAVIGATE, Capability.MHTML}))

    names = [b.name for b in registered_backends()]
    assert names == ["dup"]
    assert Capability.MHTML in registered_backends()[0].capabilities


@pytest.mark.asyncio
async def test_result_names_the_backend_that_served_it():
    """The indirection must stay debuggable."""
    register_backend(FakeBackend("in_process", {Capability.NAVIGATE}))

    with _allow():
        browser = await get_browser(requires={Capability.NAVIGATE})
        result = await browser.navigate(NavigateRequest(url="https://example.com/"))

    assert browser.backend_name == "in_process"
    assert result.backend == "in_process"


@pytest.mark.asyncio
async def test_non_url_operations_reach_the_backend():
    backend = FakeBackend("fake", {Capability.EXTRACT, Capability.INTERACT})
    register_backend(backend)

    browser = await get_browser(requires={Capability.EXTRACT})
    await browser.extract(ExtractRequest(session_id="s1"))
    await browser.act(ActionRequest(action="click", selector="#go"))
    await browser.release(SessionHandle(session_id="s1", backend="fake"))

    assert backend.calls == ["extract", "act:click", "release:s1"]


def test_shared_package_imports_nothing_app_local():
    """autobot_shared must never import a backend-local package (#13201's trap)."""
    import ast
    import pathlib

    pkg = pathlib.Path(__file__).parent
    forbidden = ("user_management", "services.", "api.", "research_browser_manager", "models")

    for path in pkg.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(forbidden), f"{path.name} imports app-local {node.module!r}"
