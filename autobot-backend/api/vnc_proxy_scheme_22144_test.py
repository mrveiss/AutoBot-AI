# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#22144: websockify is --ssl-only, so scheme and timeouts are derived, not literal."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from api import infrastructure as infra
from api import vnc_proxy


def test_upstream_endpoints_use_the_ssl_only_scheme():
    assert all(url.startswith("https://") for url in vnc_proxy.VNC_ENDPOINTS.values())


@pytest.mark.parametrize(
    ("endpoint", "ws"),
    [("https://h:6080", "wss://h:6080/websockify"), ("http://h:6080", "ws://h:6080/websockify")],
)
def test_websocket_scheme_follows_the_endpoint_scheme(endpoint, ws):
    assert vnc_proxy._websockify_url(endpoint) == ws


def test_timeouts_are_env_backed_constants():
    assert vnc_proxy.VNC_STATUS_PROBE_TIMEOUT_S > 0 and vnc_proxy.VNC_OBSERVATION_TIMEOUT_S > 0


@pytest.mark.asyncio
async def test_control_lock_refuses_a_non_secrets_host_id(monkeypatch):
    from api.schemas_system import DesktopControlAcquireRequest

    monkeypatch.setattr(infra, "_load_secrets_hosts", lambda: [])
    with patch("api.vnc_proxy.acquire_human_control") as acquire:
        with pytest.raises(HTTPException) as exc:
            await vnc_proxy.acquire_desktop_control(
                "desktop", DesktopControlAcquireRequest(session_id="fleet-node-7"), current_user={"username": "a"}
            )
    assert exc.value.status_code == 404
    acquire.assert_not_called()


@pytest.mark.asyncio
async def test_unknown_vnc_type_is_refused_for_every_proxy_route():
    """Only the desktop VM and the browser VM are proxied; any other type is 404 (owner 2026-11-24)."""
    with pytest.raises(HTTPException) as exc:
        await vnc_proxy.get_vnc_client("fleet-node-7", current_user={})
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException):
        await vnc_proxy.proxy_vnc_assets("fleet-node-7", "app.js", current_user={})
    with pytest.raises(HTTPException):
        await vnc_proxy.get_vnc_status("fleet-node-7", current_user={})


def _proxy_client():
    from fastapi import FastAPI
    from starlette.testclient import TestClient

    app = FastAPI()
    app.include_router(vnc_proxy.router, prefix="/vnc-proxy")
    return TestClient(app)


def test_unknown_vnc_type_the_client_receives_1003_and_the_reason():
    """Accepted first, then closed: a close before accept would reach a real client only as a 403."""
    from unittest.mock import AsyncMock

    from starlette.websockets import WebSocketDisconnect

    with (
        patch("api.vnc_proxy.enforce_ws_origin", new=AsyncMock(return_value=True)),
        patch("api.vnc_proxy.enforce_ws_desktop_auth", new=AsyncMock(return_value={"username": "a"})),
    ):
        with _proxy_client() as client:
            with client.websocket_connect("/vnc-proxy/fleet-node-7/websockify") as ws:
                with pytest.raises(WebSocketDisconnect) as closed:
                    ws.receive_bytes()
    assert closed.value.code == 1003
    assert closed.value.reason == "Unknown VNC type: fleet-node-7"


def test_origin_and_auth_refusals_stay_before_accept():
    """A refusal by the origin or auth gate is a handshake rejection, never an accepted socket."""
    from unittest.mock import AsyncMock

    from starlette.websockets import WebSocketDisconnect

    async def refuse(websocket):  # what enforce_ws_desktop_auth does for an unauthenticated caller
        await websocket.close(code=1008)

    with (
        patch("api.vnc_proxy.enforce_ws_origin", new=AsyncMock(return_value=True)),
        patch("api.vnc_proxy.enforce_ws_desktop_auth", new=refuse),
    ):
        with _proxy_client() as client:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/vnc-proxy/fleet-node-7/websockify"):
                    pass


def test_the_desktop_vm_is_a_registry_type_with_no_static_main_machine_entry():
    assert set(vnc_proxy.VNC_ENDPOINTS) == {"browser"}
    assert vnc_proxy.REGISTRY_VNC_TYPES == {"desktop"}
    assert vnc_proxy._known_type("desktop") and vnc_proxy._known_type("browser")
    assert not vnc_proxy._known_type("fleet-node-7")
