# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The three backends conform to the canonical browser contract (#12651).

ADR-009 wraps three stacks rather than collapsing onto one, because each is the
only home of something: MHTML capture and human handoff in-process, stable
element refs and interaction in the worker, restart-survival out-of-process.

These pin the properties that make that safe — every backend satisfies the
Protocol, declares capabilities matching what it can actually do, and refuses
rather than pretends when asked for something it does not have. Transport is
mocked throughout; nothing here starts a browser.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.browser.base import (
    ActionRequest,
    BrowserBackend,
    Capability,
    ExtractRequest,
    NavigateRequest,
    ScreenshotRequest,
    SessionHandle,
)
from browser_backends import (
    ContainerBrowserBackend,
    InProcessBrowserBackend,
    WorkerBrowserBackend,
    register_all,
)

_ALL = [InProcessBrowserBackend, ContainerBrowserBackend, WorkerBrowserBackend]


@pytest.mark.parametrize("cls", _ALL, ids=lambda c: c.name)
def test_satisfies_the_protocol(cls):
    assert isinstance(cls(), BrowserBackend)


@pytest.mark.parametrize("cls", _ALL, ids=lambda c: c.name)
def test_declares_a_name_and_capabilities(cls):
    backend = cls()
    assert isinstance(backend.name, str) and backend.name
    assert backend.capabilities
    assert all(isinstance(c, Capability) for c in backend.capabilities)


def test_capability_claims_match_the_audited_matrix():
    """ADR-009's matrix, pinned. A wrong claim routes work to a stack that cannot do it."""
    in_process = InProcessBrowserBackend()
    worker = WorkerBrowserBackend()
    container = ContainerBrowserBackend()

    # Only in-process captures MHTML and hands off to a human.
    assert Capability.MHTML in in_process.capabilities
    assert Capability.HUMAN_HANDOFF in in_process.capabilities
    assert Capability.MHTML not in worker.capabilities | container.capabilities
    assert Capability.HUMAN_HANDOFF not in worker.capabilities | container.capabilities

    # Only the worker has stable element refs and interaction.
    assert {Capability.ELEMENT_REFS, Capability.INTERACT} <= worker.capabilities
    assert not ({Capability.ELEMENT_REFS, Capability.INTERACT} & in_process.capabilities)
    assert not ({Capability.ELEMENT_REFS, Capability.INTERACT} & container.capabilities)

    # research_browser_manager has no screenshot path — verified in ADR-009.
    assert Capability.SCREENSHOT not in in_process.capabilities
    assert Capability.SCREENSHOT in container.capabilities
    assert Capability.SCREENSHOT in worker.capabilities


def test_locality_is_declared_and_exclusive():
    """#13236: callers pin process locality, so every backend must declare it.

    `web_fetch` uses the container deliberately to keep Playwright out of the
    backend's process. If a backend declared neither — or both — that caller
    could be routed into the process it is avoiding.
    """
    for backend in (InProcessBrowserBackend(), ContainerBrowserBackend(), WorkerBrowserBackend()):
        locality = backend.capabilities & {Capability.IN_PROCESS, Capability.OUT_OF_PROCESS}
        assert len(locality) == 1, f"{backend.name} declares {locality or 'no'} locality"

    assert Capability.IN_PROCESS in InProcessBrowserBackend().capabilities
    assert Capability.OUT_OF_PROCESS in ContainerBrowserBackend().capabilities
    assert Capability.OUT_OF_PROCESS in WorkerBrowserBackend().capabilities


@pytest.mark.asyncio
async def test_container_extract_renders_html():
    """#13236: phase 2 under-declared this stack — it has a `render` endpoint."""
    service = MagicMock()
    service._post_and_parse = AsyncMock(return_value={"html": "<html>ok</html>"})

    with patch.object(ContainerBrowserBackend, "_service", staticmethod(AsyncMock(return_value=service))):
        result = await ContainerBrowserBackend().extract(ExtractRequest(url="https://example.com/"))

    assert result.success is True
    assert result.content == "<html>ok</html>"
    endpoint, payload = service._post_and_parse.await_args.args
    assert endpoint == "render" and payload["url"] == "https://example.com/"


@pytest.mark.asyncio
async def test_in_process_navigate_can_extract_in_one_round_trip():
    """research_url does both; asking twice would navigate twice (#13236)."""
    manager = MagicMock()
    manager.research_url = AsyncMock(
        return_value={
            "success": True,
            "status": "completed",
            "navigation": {"url": "https://example.com/"},
            "content": {"text_content": "hi", "structured_data": {"h1": ["Title"]}},
            "session_id": "s",
        }
    )

    with patch.object(InProcessBrowserBackend, "_manager", staticmethod(lambda: manager)):
        result = await InProcessBrowserBackend().navigate(NavigateRequest(url="https://example.com/", extract=True))

    assert manager.research_url.await_args.kwargs["extract_content"] is True
    assert result.content == "hi"
    assert result.structured == {"h1": ["Title"]}, "structured_data had no home before #13236"


@pytest.mark.asyncio
async def test_unsupported_operations_refuse_rather_than_raise():
    """The registry never routes these, but they must not explode if reached."""
    result = await InProcessBrowserBackend().screenshot(ScreenshotRequest(url="https://example.com"))
    assert result.success is False and "screenshot" in result.error

    result = await ContainerBrowserBackend().act(ActionRequest(action="click"))
    assert result.success is False and "interaction" in result.error

    result = await ContainerBrowserBackend().navigate(NavigateRequest(url="https://example.com"))
    assert result.success is False


@pytest.mark.asyncio
async def test_in_process_maps_research_url_onto_the_contract():
    manager = MagicMock()
    manager.research_url = AsyncMock(
        return_value={
            "success": True,
            "status": "completed",
            "navigation": {"url": "https://example.com/", "title": "Example"},
            "content": {"text_content": "hello", "mhtml_backup": "/tmp/p.mhtml"},
            "session_id": "sess-1",
            "browser_url": "/browser/sess-1",
        }
    )

    with patch.object(InProcessBrowserBackend, "_manager", staticmethod(lambda: manager)):
        result = await InProcessBrowserBackend().navigate(NavigateRequest(url="https://example.com/"))

    assert result.success is True
    assert result.backend == "in_process"
    assert result.title == "Example"
    assert result.session == SessionHandle(session_id="sess-1", backend="in_process")
    assert result.details["mhtml_backup"] == "/tmp/p.mhtml"


@pytest.mark.asyncio
async def test_in_process_surfaces_interaction_required():
    """Human handoff is this stack's reason to exist — it must not be flattened."""
    manager = MagicMock()
    manager.research_url = AsyncMock(
        return_value={
            "success": True,
            "status": "interaction_required",
            "message": "captcha",
            "session_id": "sess-2",
            "actions": ["wait", "manual_intervention"],
        }
    )

    with patch.object(InProcessBrowserBackend, "_manager", staticmethod(lambda: manager)):
        result = await InProcessBrowserBackend().navigate(NavigateRequest(url="https://example.com/"))

    assert result.interaction_required is True
    assert result.details["actions"] == ["wait", "manual_intervention"]


@pytest.mark.asyncio
async def test_worker_navigate_threads_the_session_id():
    """#11539: every call is routed to that conversation's BrowserContext."""
    sent = {}

    async def fake_send(action, params, session_id):
        sent.update(action=action, params=params, session_id=session_id)
        return {"success": True, "result": {"url": "https://example.com/", "title": "Example"}}

    with patch.object(WorkerBrowserBackend, "_send", staticmethod(fake_send)):
        result = await WorkerBrowserBackend().navigate(NavigateRequest(url="https://example.com/", session_id="conv-9"))

    assert sent == {
        "action": "navigate",
        "params": {"url": "https://example.com/"},
        "session_id": "conv-9",
    }
    assert result.success is True and result.backend == "worker"


@pytest.mark.asyncio
async def test_worker_extract_unwraps_the_envelope_and_truncates():
    async def fake_send(action, params, session_id):
        return {"success": True, "result": {"text": "abcdefghij"}}

    with patch.object(WorkerBrowserBackend, "_send", staticmethod(fake_send)):
        result = await WorkerBrowserBackend().extract(ExtractRequest(session_id="c", max_chars=4))

    assert result.content == "abcd"


@pytest.mark.asyncio
async def test_container_screenshot_requires_an_explicit_url():
    """It is stateless — there is no 'current page' to capture."""
    result = await ContainerBrowserBackend().screenshot(ScreenshotRequest(url=None))

    assert result.success is False
    assert "url" in result.error


@pytest.mark.asyncio
async def test_probe_failures_are_reported_not_raised():
    """resolve_backend() relies on probe() returning False, never exploding."""
    with patch.object(
        InProcessBrowserBackend, "_manager", staticmethod(MagicMock(side_effect=RuntimeError("no playwright")))
    ):
        assert await InProcessBrowserBackend().probe() is False

    with patch.object(ContainerBrowserBackend, "_service", staticmethod(AsyncMock(side_effect=RuntimeError("down")))):
        assert await ContainerBrowserBackend().probe() is False

    with patch.object(WorkerBrowserBackend, "_send", staticmethod(AsyncMock(side_effect=RuntimeError("down")))):
        assert await WorkerBrowserBackend().probe() is False


def test_register_all_is_idempotent():
    from autobot_shared.browser.registry import clear_backends, registered_backends

    clear_backends()
    register_all(force=True)
    first = [b.name for b in registered_backends()]
    register_all(force=True)
    second = [b.name for b in registered_backends()]

    assert first == second == ["in_process", "worker", "container"]
    clear_backends()
