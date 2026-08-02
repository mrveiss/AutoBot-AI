# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""`_fetch_playwright` goes through the canonical browser interface (#13236).

ADR-009 step 2 — the first caller migrated off a directly-named stack.

The migration is only safe if it lands on the *same* stack it called before.
It nearly did not: the worker and the container both satisfy
`EXTRACT + OUT_OF_PROCESS`, and `register_all` registers the worker first, so
under the pre-#13306 contract this caller would have resolved to the worker
and received `get_text` output — plain text where a parser expects HTML, with
nothing raising because text is a valid result.

These pin the properties that make it behaviour-preserving: the container
serves it, the render payload is unchanged, the caller's timeout survives, and
failure still yields `None` rather than propagating.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import browser_backends
from autobot_shared.browser.base import Capability, ContentFormat
from autobot_shared.browser.registry import clear_backends
from browser_backends import ContainerBrowserBackend, InProcessBrowserBackend, WorkerBrowserBackend
from web_fetch.fetcher import _fetch_playwright


@pytest.fixture(autouse=True)
def _registry():
    clear_backends()
    browser_backends._registered = False
    yield
    clear_backends()
    browser_backends._registered = False


def _all_probes_up():
    """Probe reaches real transports; this is about routing, not reachability."""
    return (
        patch.object(ContainerBrowserBackend, "probe", AsyncMock(return_value=True)),
        patch.object(WorkerBrowserBackend, "probe", AsyncMock(return_value=True)),
        patch.object(InProcessBrowserBackend, "probe", AsyncMock(return_value=True)),
    )


@pytest.mark.asyncio
async def test_renders_through_the_container_with_the_payload_it_always_sent():
    """Same stack, same endpoint, same wait — and the timeout survives."""
    service = MagicMock()
    service._post_and_parse = AsyncMock(return_value={"html": "<html>page</html>"})

    p_container, p_worker, p_inproc = _all_probes_up()
    with (
        patch("web_fetch.fetcher._is_public_url", AsyncMock(return_value=True)),
        patch.object(ContainerBrowserBackend, "_service", staticmethod(AsyncMock(return_value=service))),
        p_container,
        p_worker,
        p_inproc,
    ):
        html = await _fetch_playwright("https://example.com/", timeout=7.5)

    assert html == "<html>page</html>"
    endpoint, payload = service._post_and_parse.await_args.args
    assert endpoint == "render"
    assert payload["url"] == "https://example.com/"
    assert payload["wait"] == "networkidle"
    assert payload["timeout"] == 7500, "the caller's timeout must reach the render endpoint"


@pytest.mark.asyncio
async def test_the_worker_is_not_selected_even_though_it_registers_first():
    """The regression #13306 prevents, asserted end to end from this caller."""
    worker_called = AsyncMock()
    service = MagicMock()
    service._post_and_parse = AsyncMock(return_value={"html": "<html/>"})

    p_container, p_worker, p_inproc = _all_probes_up()
    with (
        patch("web_fetch.fetcher._is_public_url", AsyncMock(return_value=True)),
        patch.object(ContainerBrowserBackend, "_service", staticmethod(AsyncMock(return_value=service))),
        patch.object(WorkerBrowserBackend, "extract", worker_called),
        p_container,
        p_worker,
        p_inproc,
    ):
        await _fetch_playwright("https://example.com/", timeout=5.0)

    worker_called.assert_not_awaited()
    service._post_and_parse.assert_awaited_once()


@pytest.mark.asyncio
async def test_a_non_public_url_never_reaches_a_backend():
    """The inline guard is kept as defence in depth alongside the registry's."""
    service = MagicMock()
    service._post_and_parse = AsyncMock()

    with (
        patch("web_fetch.fetcher._is_public_url", AsyncMock(return_value=False)),
        patch.object(ContainerBrowserBackend, "_service", staticmethod(AsyncMock(return_value=service))),
    ):
        result = await _fetch_playwright("http://169.254.169.254/", timeout=5.0)

    assert result is None
    service._post_and_parse.assert_not_awaited()


@pytest.mark.asyncio
async def test_failure_still_returns_none_rather_than_raising():
    """The render cascade depends on this returning None to try the next step."""
    p_container, p_worker, p_inproc = _all_probes_up()
    with (
        patch("web_fetch.fetcher._is_public_url", AsyncMock(return_value=True)),
        patch.object(
            ContainerBrowserBackend, "_service", staticmethod(AsyncMock(side_effect=RuntimeError("container down")))
        ),
        p_container,
        p_worker,
        p_inproc,
    ):
        assert await _fetch_playwright("https://example.com/", timeout=5.0) is None


@pytest.mark.asyncio
async def test_no_capable_backend_returns_none_not_an_exception():
    """Nothing registered at all must degrade, not propagate."""
    with patch("web_fetch.fetcher._is_public_url", AsyncMock(return_value=True)):
        with patch.object(browser_backends, "register_all", lambda **_: None):
            assert await _fetch_playwright("https://example.com/", timeout=5.0) is None


def test_the_requirements_describe_what_this_caller_needs():
    """Documented so a later edit cannot quietly widen them."""
    import inspect

    src = inspect.getsource(_fetch_playwright)

    assert "Capability.EXTRACT_HTML" in src, "a parser needs markup, not text"
    assert "Capability.OUT_OF_PROCESS" in src, "Playwright must stay out of the backend process"
    assert "ContentFormat.HTML" in src
    assert str(Capability.EXTRACT_HTML.value) == "extract_html"
    assert str(ContentFormat.HTML.value) == "html"
