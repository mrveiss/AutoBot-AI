# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Auth-reject handshake convention for ``api/websockets.py`` (#12366).

Standardizes ``/ws-test``, ``/ws``, and ``/ws/npu-workers`` on
accept-then-close (matching ``live_events.py``'s convention) instead of the
old close-before-accept form (#2818), so an auth-rejected socket gets a real
WS close frame (code 4001 + reason) rather than an HTTP 403 indistinguishable
from a missing route (root cause of the #12340 misdiagnosis).

Same pure-import + starlette ``TestClient`` pattern as
``test_websocket_auth_smoke.py`` — no real server, Redis, or network needed.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

_BACKEND = Path(__file__).resolve().parent.parent
for _p in (str(_BACKEND), str(_BACKEND.parent / "autobot_shared")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _repair_stubbed_packages() -> None:
    """Mirror the backend root-conftest repair (#11791) — earlier-collected
    test modules may stub ``services``/``api``/``events`` in sys.modules,
    breaking the late import of ``api.websockets`` below."""
    for pkg in ("services", "api", "events"):
        mod = sys.modules.get(pkg)
        if mod is not None and not mod.__dict__.get("__path__"):
            mod.__path__ = [str(_BACKEND / pkg)]


@contextmanager
def _websockets_client(*, verify_fn):
    """Yield a TestClient with the ``api.websockets`` router and controlled auth."""

    async def _fake_authenticate_websocket(websocket) -> dict | None:
        return verify_fn(websocket.query_params.get("token"))

    _repair_stubbed_packages()
    # api/websockets.py imports authenticate_websocket at module scope (unlike
    # live_events.py's deferred import), so the patch target is the bound name
    # in api.websockets, not auth_middleware itself.
    with patch("api.websockets.authenticate_websocket", new=_fake_authenticate_websocket):
        from api.websockets import router as websockets_router

        app = FastAPI()
        app.include_router(websockets_router)
        yield TestClient(app, raise_server_exceptions=False)


def _verify_valid(token: str | None) -> dict | None:
    return {"user_id": "u-smoke", "username": "smoketest"} if token == "smoke" else None


def _verify_none(token: str | None) -> None:
    return None


@pytest.mark.parametrize("path", ["/ws-test", "/ws", "/ws/npu-workers"])
def test_unauthenticated_ws_accepted_then_closed_4001(path: str) -> None:
    """No/invalid bearer -> connection accepted then closed with 4001 + reason,
    NOT a close-before-accept HTTP 403 (#12366)."""
    with _websockets_client(verify_fn=_verify_none) as client:
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(path) as ws:
                ws.receive_text()
    assert exc_info.value.code == 4001


@pytest.mark.parametrize("path", ["/ws-test", "/ws/npu-workers"])
def test_authenticated_ws_proceeds(path: str) -> None:
    """A valid bearer accepts the connection and does not close with 4001."""
    with (
        _websockets_client(verify_fn=_verify_valid) as client,
        patch("api.websockets.get_event_bus", return_value=AsyncMock()),
    ):
        with client.websocket_connect(f"{path}?token=smoke") as ws:
            frame = ws.receive_json()
        assert frame["type"] in ("connected", "connection_established", "initial_workers")
