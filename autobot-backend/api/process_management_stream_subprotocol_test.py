# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``stream_process_logs`` echoes the client's ``bearer`` subprotocol (#16374).

Round 1 of #16374 put the SLM session JWT in the stream URL's query string
(``?slm_ws_token=``), which nginx's access log and the browser's history both
persist. Round 2 moves it to the ``Sec-WebSocket-Protocol`` subprotocol list
instead (``new WebSocket(url, ['bearer', token])``); nginx's dedicated stream
location gates the handshake on it and strips it before proxying, so this
endpoint only ever sees the literal ``bearer`` offer.

RFC 6455 4.2.2 requires a server that accepts a handshake carrying
subprotocols to choose and echo one of them, or the browser fails the
handshake outright — so ``websocket.accept()`` must pass ``subprotocol=
"bearer"`` whenever the client offered it, mirroring the convention already
used by ``autobot-slm-backend/api/websocket.py``'s ``ConnectionManager.connect``
(see ``autobot-slm-backend/tests/test_websocket_connection_manager_12515.py``).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import api.process_management as process_management
from api.process_management import set_process_adapter_service, stream_process_logs


def _fake_ws(protocols: str = "") -> AsyncMock:
    """A fake WebSocket exposing the sync ``headers`` the endpoint reads."""
    ws = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    ws.close = AsyncMock()
    ws.headers = MagicMock()
    ws.headers.get = MagicMock(
        side_effect=lambda key, default="": protocols if key == "sec-websocket-protocol" else default
    )
    return ws


@pytest.fixture(autouse=True)
def _process_service_stub():
    """Register a service whose ``get_process_status`` ends the stream at once.

    ``None`` makes the loop send one "not found" message and ``break``
    immediately, so these tests exercise only the accept()-time subprotocol
    logic, not the tailing loop. The module-level singleton is restored after
    each test so it cannot leak into unrelated tests.
    """
    original = process_management._process_svc
    svc = MagicMock()
    svc.get_process_status = AsyncMock(return_value=None)
    set_process_adapter_service(svc)
    yield svc
    process_management._process_svc = original


async def test_accepts_with_bearer_subprotocol_when_offered():
    ws = _fake_ws(protocols="bearer, sometoken")
    with patch.object(process_management, "enforce_ws_origin", new=AsyncMock(return_value=True)):
        await stream_process_logs(ws, "p1")
    assert ws.accept.call_args.kwargs.get("subprotocol") == "bearer"


async def test_accepts_with_no_subprotocol_when_none_offered():
    ws = _fake_ws(protocols="")
    with patch.object(process_management, "enforce_ws_origin", new=AsyncMock(return_value=True)):
        await stream_process_logs(ws, "p1")
    assert ws.accept.call_args.kwargs.get("subprotocol") is None
