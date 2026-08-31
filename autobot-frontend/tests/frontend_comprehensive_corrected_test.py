#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Live-stack checks for the surfaces the AutoBot frontend depends on (#14979).

This module used to be an operational script wearing test names: a class with
``__init__`` (which pytest refuses to collect), methods returning ``TestResult``
objects, a ``run_comprehensive_test_suite`` driver and a ``main()`` that printed
a scorecard. All ten ``test_*`` methods therefore collected zero items and
asserted nothing.

Each method is now a real test that asserts. Every one drives the running stack
over HTTP or WebSocket, so a single module-level autouse fixture skips the
module when the frontend or the backend is absent (#14930) — nothing here is
exercisable without both.

Endpoint paths were corrected against the router registry while converting; the
originals targeted several routes no router has ever served (see the notes on
``CRITICAL_ENDPOINTS``, ``test_terminal_integration``,
``test_desktop_viewer_component`` and ``test_chat_functionality_comprehensive``).

The assertion the connectivity tests make is *routed and healthy*, not
``== 200``: most of these endpoints sit behind ``check_admin_permission`` and
these tests carry no credentials, so 401/403 is the correct answer to an
anonymous probe. A 404 (router not mounted) or a 5xx (handler broken) is what
actually breaks the UI, and that is what fails here.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, AsyncIterator, Iterable

import aiohttp
import pytest
import websockets

from autobot_shared.live_service_probe import require_live_endpoint
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

# Real HTTP and WebSocket traffic against a running stack — never a unit item.
pytestmark = pytest.mark.integration

# SSOT only (#1618): no host, port or URL is spelled out in this file.
FRONTEND_URL = config.frontend_url
BACKEND_URL = config.backend_url

# Module constants rather than literals at the call sites, matching the shape the
# other live-probe suites use (`api/voice_integration_test.py:34`). Deliberately
# not env-var-backed: these are assertion budgets for one test module, not
# deployment configuration, and every AUTOBOT_* name read here would have to be
# carried in the env registry and its generated docs for the life of the file.
REQUEST_TIMEOUT_SECONDS = 15.0
CONNECT_TIMEOUT_SECONDS = 5.0
WEBSOCKET_OPEN_TIMEOUT_SECONDS = 10.0
WEBSOCKET_RECV_TIMEOUT_SECONDS = 5.0
FAST_ENDPOINT_BUDGET_SECONDS = 2.0

# A routed, working endpoint may answer 200 or refuse an anonymous caller.
# These statuses mean the route is missing or the handler failed — the two
# conditions that leave a frontend view blank.
BROKEN_ROUTE_STATUSES = frozenset({404, 405, 500, 501, 502, 503, 504})

# A WebSocket handshake refused for want of credentials still proves the route
# is mounted and the server speaks the protocol.
WEBSOCKET_AUTH_STATUSES = frozenset({401, 403})

# Statuses that count as *clean* rejection of a malformed body. A 500 does not:
# an unparseable payload must never reach a handler that crashes on it.
MALFORMED_REQUEST_STATUSES = frozenset({400, 422})

# Paths corrected against autobot-backend/initialization/router_registry (every
# registry router is mounted at ``/api{prefix}``). The originals
# ``/api/system/status``, ``/api/infrastructure/status`` and
# ``/api/monitoring/services`` are served by no router.
CRITICAL_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("/api/health", "Backend health"),
    ("/api/system/info", "System info"),
    ("/api/knowledge_base/stats/basic", "Knowledge base stats"),
    ("/api/validation-dashboard/status", "Validation dashboard"),
    ("/api/infrastructure/hosts", "Infrastructure hosts"),
    ("/api/settings/", "Settings"),
    ("/api/monitoring/services/health", "Service monitor"),
)

# The endpoints a freshly loaded dashboard fans out to at once.
CONCURRENT_ENDPOINTS: tuple[str, ...] = (
    "/api/health",
    "/api/system/info",
    "/api/knowledge_base/stats/basic",
    "/api/monitoring/services/health",
)

# Endpoints that must answer inside the interactive budget.
FAST_ENDPOINTS: tuple[str, ...] = ("/api/health", "/api/system/info")


@pytest.fixture(autouse=True)
def _require_live_frontend_stack() -> None:
    """Skip when the frontend or the backend is absent (#14930).

    Both are probed because this module drives both directly: the health test
    dials the Vite/dist server, the other nine dial the backend API. A skip
    naming only one would misreport which half of the stack was missing.
    """
    require_live_endpoint(FRONTEND_URL, what="the AutoBot frontend")
    require_live_endpoint(BACKEND_URL, what="the AutoBot backend API")


@pytest.fixture
async def http_session() -> AsyncIterator[aiohttp.ClientSession]:
    """One aiohttp session per test, closed on the way out.

    Replaces the deleted ``__init__``/``__aenter__`` pair, which pytest could
    not collect around.
    """
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS, connect=CONNECT_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        yield session


def _websocket_url(path: str) -> str:
    """Return the ws(s):// form of ``BACKEND_URL`` with *path* appended."""
    scheme, _, remainder = BACKEND_URL.partition("://")
    ws_scheme = "wss" if scheme.lower() == "https" else "ws"
    return f"{ws_scheme}://{remainder.rstrip('/')}{path}"


async def _probe_endpoints(session: aiohttp.ClientSession, endpoints: Iterable[tuple[str, str]]) -> list[str]:
    """Return one description per endpoint that is unrouted or erroring."""
    broken: list[str] = []
    for path, name in endpoints:
        async with session.get(f"{BACKEND_URL}{path}") as response:
            if response.status in BROKEN_ROUTE_STATUSES:
                broken.append(f"{name} ({path}) -> HTTP {response.status}")
    return broken


async def _json_body(response: aiohttp.ClientResponse, path: str) -> Any:
    """Parse *response* as JSON, naming *path* when the body is not JSON."""
    body = await response.text()
    try:
        return json.loads(body)
    except ValueError as exc:
        raise AssertionError(f"GET {path} returned HTTP 200 but the body is not JSON: {exc}") from exc


async def _assert_probe_reply(socket: Any, url: str) -> None:
    """Assert that any frame the server volunteers is a JSON object.

    Silence is allowed: none of these routes is required to answer an
    unsolicited ping, and the completed handshake is the assertion that matters.
    """
    try:
        raw = await asyncio.wait_for(socket.recv(), timeout=WEBSOCKET_RECV_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return

    payload = json.loads(raw)
    assert isinstance(
        payload, dict
    ), f"websocket {url} replied with a JSON {type(payload).__name__}, expected an object"


async def _assert_websocket_route_served(url: str, probe: dict[str, Any] | None = None) -> None:
    """Assert the backend serves a WebSocket route at *url*.

    An open handshake is the strongest result; a 401/403 rejection still proves
    the route is mounted, and these tests carry no credentials. A 404 means the
    router is not mounted, and every transport error propagates untouched.
    """
    try:
        async with websockets.connect(url, open_timeout=WEBSOCKET_OPEN_TIMEOUT_SECONDS) as socket:
            state = socket.state.name
            assert state == "OPEN", f"websocket {url} completed its handshake but the connection is {state}"
            if probe is not None:
                await socket.send(json.dumps(probe))
                await _assert_probe_reply(socket, url)
    except websockets.exceptions.InvalidStatus as exc:
        status = exc.response.status_code
        assert status in WEBSOCKET_AUTH_STATUSES, (
            f"websocket {url} was refused with HTTP {status}; expected an open handshake "
            f"or an authentication rejection {sorted(WEBSOCKET_AUTH_STATUSES)}"
        )
        logger.info("websocket %s is mounted but refused an anonymous handshake with HTTP %s", url, status)


class TestFrontendSurface:
    """The frontend page and the backend surfaces its views call."""

    async def test_frontend_health_and_accessibility(self, http_session: aiohttp.ClientSession) -> None:
        """The frontend serves an index page that mounts the AutoBot Vue app."""
        async with http_session.get(f"{FRONTEND_URL}/") as response:
            assert response.status == 200, f"frontend {FRONTEND_URL}/ returned HTTP {response.status}, expected 200"
            content = await response.text()

        assert "AutoBot" in content, (
            f"frontend index from {FRONTEND_URL}/ never mentions 'AutoBot' " f"({len(content)} bytes served)"
        )
        assert (
            'id="app"' in content
        ), f'frontend index from {FRONTEND_URL}/ has no id="app" mount point for the Vue application'

    async def test_api_connectivity_from_frontend(self, http_session: aiohttp.ClientSession) -> None:
        """Every backend endpoint the shell calls on load is mounted and healthy."""
        broken = await _probe_endpoints(http_session, CRITICAL_ENDPOINTS)
        assert not broken, "backend endpoints the frontend calls on load are unrouted or erroring: " + "; ".join(broken)

    async def test_websocket_connections(self, http_session: aiohttp.ClientSession) -> None:
        """The realtime WebSocket the UI subscribes to is served.

        The original dialled ``/api/websocket/chat`` and fell back to ``/ws``;
        neither is registered. ``api.websockets`` mounts ``/ws`` at the ``/api``
        prefix, so the served route is ``/api/ws``.
        """
        await _assert_websocket_route_served(
            _websocket_url("/api/ws"),
            probe={"type": "ping", "data": "connectivity_test"},
        )

    async def test_core_ui_components(self, http_session: aiohttp.ClientSession) -> None:
        """The three APIs behind the chat, monitor and knowledge views answer."""
        broken = await _probe_endpoints(
            http_session,
            (
                ("/api/chat/chats", "Chat interface"),
                ("/api/monitoring/services/health", "System monitor"),
                ("/api/knowledge_base/categories", "Knowledge base browser"),
            ),
        )
        assert not broken, "APIs behind core UI components are unrouted or erroring: " + "; ".join(broken)

    async def test_terminal_integration(self, http_session: aiohttp.ClientSession) -> None:
        """The terminal session WebSocket is served.

        ``api/terminal.py`` registers no HTTP route at all — the integration is
        WebSocket-only — so the original GET of ``/api/terminal/status`` could
        only ever 404, which it then reported as a pass.
        """
        session_id = f"frontend-surface-{uuid.uuid4().hex}"
        await _assert_websocket_route_served(_websocket_url(f"/api/terminal/ws/{session_id}"))

    async def test_desktop_viewer_component(self, http_session: aiohttp.ClientSession) -> None:
        """The VNC status endpoint behind the desktop viewer answers.

        There is no ``/api/desktop`` router; the desktop viewer is served by
        ``api.vnc_manager``, mounted at ``/api/vnc``.
        """
        broken = await _probe_endpoints(http_session, (("/api/vnc/status", "Desktop viewer (VNC)"),))
        assert not broken, "the desktop viewer's VNC status endpoint is unrouted or erroring: " + "; ".join(broken)

    async def test_knowledge_base_interface(self, http_session: aiohttp.ClientSession) -> None:
        """Stats, categories and search all answer for the knowledge base view."""
        broken = await _probe_endpoints(
            http_session,
            (
                ("/api/knowledge_base/stats/basic", "KB stats"),
                ("/api/knowledge_base/categories", "KB categories"),
            ),
        )
        search_path = "/api/knowledge_base/search"
        async with http_session.post(
            f"{BACKEND_URL}{search_path}", json={"query": "AutoBot configuration"}
        ) as response:
            if response.status in BROKEN_ROUTE_STATUSES:
                broken.append(f"KB search ({search_path}) -> HTTP {response.status}")
            elif response.status == 200:
                payload = await _json_body(response, search_path)
                assert isinstance(payload, dict) and "results" in payload, (
                    f"POST {search_path} returned HTTP 200 without a 'results' key; " f"got {type(payload).__name__}"
                )

        assert not broken, "knowledge base endpoints are unrouted or erroring: " + "; ".join(broken)

    async def test_chat_functionality_comprehensive(self, http_session: aiohttp.ClientSession) -> None:
        """The chat list and chat health endpoints answer.

        Chat *creation* is not asserted: the original posted to
        ``/api/chat/chats/new``, which no router serves, and the message route
        it used (``/api/chat/chats/{id}/message``) is really
        ``/api/chats/{id}/message`` and needs an existing chat id.
        """
        broken = await _probe_endpoints(
            http_session,
            (("/api/chat/chats", "Chat list"), ("/api/chat/health", "Chat health")),
        )
        assert not broken, "chat endpoints are unrouted or erroring: " + "; ".join(broken)

    async def test_performance_and_responsiveness(self, http_session: aiohttp.ClientSession) -> None:
        """A dashboard-sized fan-out succeeds, and hot endpoints stay inside budget."""
        requests = [http_session.get(f"{BACKEND_URL}{path}") for path in CONCURRENT_ENDPOINTS]
        responses = await asyncio.gather(*requests, return_exceptions=True)

        failures: list[str] = []
        for path, result in zip(CONCURRENT_ENDPOINTS, responses):
            if isinstance(result, BaseException):
                failures.append(f"{path} -> {type(result).__name__}: {result}")
                continue
            if result.status in BROKEN_ROUTE_STATUSES:
                failures.append(f"{path} -> HTTP {result.status}")
            result.close()

        assert (
            not failures
        ), f"a concurrent fan-out of {len(CONCURRENT_ENDPOINTS)} dashboard endpoints failed: " + "; ".join(failures)
        await self._assert_response_time_budget(http_session)

    async def test_error_handling_and_edge_cases(self, http_session: aiohttp.ClientSession) -> None:
        """Unknown routes 404 and malformed bodies are rejected, not crashed on."""
        unknown_path = "/api/nonexistent/endpoint"
        async with http_session.get(f"{BACKEND_URL}{unknown_path}") as response:
            assert response.status == 404, f"GET {unknown_path} returned HTTP {response.status}, expected 404"

        search_path = "/api/knowledge_base/search"
        async with http_session.post(
            f"{BACKEND_URL}{search_path}",
            data="invalid json data",
            headers={"Content-Type": "application/json"},
        ) as response:
            assert response.status in MALFORMED_REQUEST_STATUSES, (
                f"POST {search_path} with an unparseable body returned HTTP {response.status}; "
                f"expected a clean rejection {sorted(MALFORMED_REQUEST_STATUSES)}"
            )

    async def _assert_response_time_budget(self, session: aiohttp.ClientSession) -> None:
        """Assert each hot endpoint answers within FAST_ENDPOINT_BUDGET_SECONDS."""
        loop = asyncio.get_running_loop()
        slow: list[str] = []
        for path in FAST_ENDPOINTS:
            started = loop.time()
            async with session.get(f"{BACKEND_URL}{path}") as response:
                await response.read()
            elapsed = loop.time() - started
            if elapsed >= FAST_ENDPOINT_BUDGET_SECONDS:
                slow.append(f"{path} -> {elapsed:.3f}s")

        assert not slow, f"endpoints exceeded the {FAST_ENDPOINT_BUDGET_SECONDS:.1f}s interactive budget: " + "; ".join(
            slow
        )
