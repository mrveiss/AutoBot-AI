# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#22145: chat Desktop controls act on the selected /secrets host, never a fixed display.

Covers: the host id resolves only from /secrets (fleet and unknown ids refused),
the control reaches that host's own VNC address/port/password, the screenshot
path returns a PNG from that host, and the E7 rule (no default user/capabilities).
"""

import base64
import struct
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api import infrastructure as infra
from api.infrastructure_host_rules import missing_host_fields, refuse_incomplete_host
from api.schemas_system import MouseClickRequest
from api.vnc_host_actions import keysym_for, run_on_host
from api.vnc_host_target import DESKTOP_VM_HOST_ID, VncTarget, resolve_host_id, resolve_vnc_target
from api.vnc_manager import vnc_mouse_click, vnc_screenshot
from api.vnc_rfb_client import VncFrame, VncRfbSession, frame_to_png
from services.slm_vnc_registry import DesktopVmEndpoint

SECRETS_HOST = {
    "id": "h-secret",
    "name": "box",
    "host": "vnc.example.test",
    "ssh_port": 22,
    "vnc_port": 5905,
    "username": "alice",
    "capabilities": ["ssh", "vnc"],
}
FLEET_NODE_ID = "fleet-node-7"


@pytest.fixture
def secrets_hosts(monkeypatch):
    """The one secrets loader terminal_ssh also uses; a fleet node is NOT in it."""
    monkeypatch.setattr(infra, "_load_secrets_hosts", lambda: [dict(SECRETS_HOST)])


@pytest.fixture
def password(monkeypatch):
    async def _pw(host_id):
        return b"pw-" + host_id.encode()

    monkeypatch.setattr("api.vnc_host_target._vnc_password_for", _pw)


class TestResolveOnlyFromSecrets:
    @pytest.mark.asyncio
    async def test_secrets_host_resolves_to_its_own_endpoint_and_credentials(self, secrets_hosts, password):
        target = await resolve_vnc_target("h-secret")
        assert target == VncTarget("h-secret", "vnc.example.test", 5905, b"pw-h-secret")

    @pytest.mark.parametrize("bad_id", [FLEET_NODE_ID, "", "localhost", "default"])
    @pytest.mark.asyncio
    async def test_fleet_or_unknown_id_is_refused(self, secrets_hosts, password, bad_id):
        with pytest.raises(HTTPException) as exc:
            await resolve_vnc_target(bad_id)
        assert exc.value.status_code == 404 and exc.value.detail["code"] == "host_not_found"

    def test_host_without_vnc_capability_is_refused(self, monkeypatch, password):
        host = {**SECRETS_HOST, "capabilities": ["ssh"]}
        monkeypatch.setattr(infra, "_load_secrets_hosts", lambda: [host])
        with pytest.raises(HTTPException) as exc:
            resolve_host_id("h-secret")
        assert exc.value.status_code == 422

    def test_host_without_username_is_refused_with_a_clear_message(self, monkeypatch, password):
        host = {**SECRETS_HOST, "username": ""}
        monkeypatch.setattr(infra, "_load_secrets_hosts", lambda: [host])
        with pytest.raises(HTTPException) as exc:
            resolve_host_id("h-secret")
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "host_fields_missing" and "username" in exc.value.detail["message"]


class _FakeSession:
    """Records what a control sends; stands in for the RFB connection."""

    instances: list = []

    def __init__(self, host, port, password):
        self.args = (host, port, password)
        self.width, self.height = 100, 80
        self.events: list = []
        _FakeSession.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def pointer(self, x, y, buttons):
        self.events.append(("pointer", x, y, buttons))

    async def key(self, keysym, down):
        self.events.append(("key", keysym, down))

    async def cut_text(self, text):
        self.events.append(("cut", text))

    async def grab_frame(self):
        return VncFrame(2, 1, bytes([255, 0, 0, 0, 255, 0]))


@pytest.fixture
def fake_session(secrets_hosts, password):
    _FakeSession.instances = []
    with patch("api.vnc_host_actions.VncRfbSession", _FakeSession):
        yield _FakeSession


class TestControlsActOnTheSelectedHost:
    @pytest.mark.asyncio
    async def test_click_connects_to_the_secrets_host_with_its_password(self, fake_session):
        with patch("api.vnc_manager.is_actuation_muted", new=AsyncMock(return_value=False)):
            result = await vnc_mouse_click(
                MouseClickRequest(host_id="h-secret", x=3, y=4), admin_check=True, current_user={"username": "alice"}
            )
        assert result["status"] == "success"
        (session,) = fake_session.instances
        assert session.args == ("vnc.example.test", 5905, b"pw-h-secret")
        assert ("pointer", 3, 4, 1) in session.events

    @pytest.mark.asyncio
    async def test_fleet_node_id_never_opens_a_connection(self, fake_session):
        with patch("api.vnc_manager.is_actuation_muted", new=AsyncMock(return_value=False)):
            with pytest.raises(HTTPException) as exc:
                await vnc_mouse_click(
                    MouseClickRequest(host_id=FLEET_NODE_ID, x=1, y=1),
                    admin_check=True,
                    current_user={"username": "alice"},
                )
        assert exc.value.status_code == 404
        assert fake_session.instances == []

    def test_host_id_is_required_on_the_request(self):
        with pytest.raises(ValueError):
            MouseClickRequest(x=1, y=1)

    @pytest.mark.asyncio
    async def test_key_chord_presses_then_releases_in_reverse(self, fake_session):
        await run_on_host("h-secret", "key", key="ctrl+alt+Delete")
        keys = [e for e in fake_session.instances[0].events if e[0] == "key"]
        assert [k[2] for k in keys] == [True, True, True, False, False, False]
        assert keys[0][1] == keysym_for("ctrl") and keys[2][1] == keysym_for("Delete")

    @pytest.mark.asyncio
    async def test_clipboard_text_goes_to_the_host(self, fake_session):
        await run_on_host("h-secret", "clipboard", content="hello")
        assert ("cut", "hello") in fake_session.instances[0].events

    @pytest.mark.asyncio
    async def test_unreachable_host_reports_an_error_result(self, secrets_hosts, password):
        class Boom(_FakeSession):
            async def __aenter__(self):
                raise ConnectionRefusedError()

        with patch("api.vnc_host_actions.VncRfbSession", Boom):
            result = await run_on_host("h-secret", "click", x=1, y=1, button="left")
        assert result["status"] == "error"


class TestScreenshotPath:
    @pytest.mark.asyncio
    async def test_screenshot_returns_a_png_from_the_selected_host(self, fake_session):
        result = await vnc_screenshot(host_id="h-secret", admin_check=True)
        assert result["status"] == "success"
        assert base64.b64decode(result["image_data"])[:8] == b"\x89PNG\r\n\x1a\n"
        assert fake_session.instances[0].args[0] == "vnc.example.test"

    @pytest.mark.asyncio
    async def test_screenshot_of_a_fleet_node_is_refused(self, fake_session):
        with pytest.raises(HTTPException) as exc:
            await vnc_screenshot(host_id=FLEET_NODE_ID, admin_check=True)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_failure_is_an_error_result_not_operation_failed(self, secrets_hosts, password):
        """Missing capture tools used to surface as the generic 'Operation failed' (#22145)."""

        class Boom(_FakeSession):
            async def grab_frame(self):
                raise OSError("down")

        with patch("api.vnc_host_actions.VncRfbSession", Boom):
            result = await vnc_screenshot(host_id="h-secret", admin_check=True)
        assert result["status"] == "error" and result["message"] != "Operation failed"
        assert result["image_data"] == ""

    def test_frame_to_png_round_trips_pixels(self):
        from io import BytesIO

        from PIL import Image

        png = frame_to_png(VncFrame(2, 1, bytes([255, 0, 0, 0, 255, 0])))
        assert list(Image.open(BytesIO(png)).getdata()) == [(255, 0, 0), (0, 255, 0)]


class TestRfbRawRectDecoding:
    @pytest.mark.asyncio
    async def test_raw_bgrx_rect_becomes_rgb(self):
        session = VncRfbSession("h", 1, b"pw")
        session.width, session.height = 2, 1
        payload = struct.pack("!HHHHi", 0, 0, 2, 1, 0) + bytes([0, 0, 255, 0, 0, 255, 0, 0])  # B,G,R,X per pixel
        buf = bytearray(payload)

        class Stream:
            async def read_exactly(self, n):
                chunk = bytes(buf[:n])
                del buf[:n]
                return chunk

        session._stream = Stream()
        canvas = bytearray(6)
        await session._read_rect(canvas)
        assert bytes(canvas) == bytes([255, 0, 0, 0, 255, 0])


class TestE7NoDefaultUserOrCapabilities:
    def test_loader_does_not_invent_root_or_ssh(self, monkeypatch):
        import api.secrets as secrets_module

        monkeypatch.setattr(
            secrets_module.secrets_manager,
            "list_secrets",
            lambda *a, **k: [{"id": "s", "type": "infrastructure_host", "name": "n", "metadata": {"host": "h"}}],
        )
        (host,) = infra._load_secrets_hosts()
        assert host["username"] == "" and host["capabilities"] == []

    def test_incomplete_host_is_rejected_naming_the_fields(self):
        with pytest.raises(HTTPException) as exc:
            refuse_incomplete_host("infrastructure_host", {"host": "h"})
        assert exc.value.status_code == 422
        assert exc.value.detail["fields"] == ["username", "capabilities"]

    def test_complete_host_and_other_secret_types_pass(self):
        refuse_incomplete_host("infrastructure_host", {"username": "u", "capabilities": ["ssh"]})
        refuse_incomplete_host("api_key", {})
        assert missing_host_fields({"username": "u", "capabilities": ["vnc"]}) == []


class TestTerminalSshSharesTheResolver:
    @pytest.mark.asyncio
    async def test_resolve_ssh_host_id_uses_the_same_lookup(self, secrets_hosts):
        from api.terminal_ssh import resolve_ssh_host_id

        assert await resolve_ssh_host_id("h-secret") is True
        assert await resolve_ssh_host_id(FLEET_NODE_ID) is False


class TestVncPasswordLookup:
    @pytest.mark.asyncio
    async def test_only_a_password_secret_linked_to_the_host_counts(self, monkeypatch):
        import api.secrets as secrets_module
        from api.vnc_host_target import VNC_COMPANION_HOST_KEY, _vnc_password_for

        entries = [
            {"id": "a", "type": "api_key", "metadata": {VNC_COMPANION_HOST_KEY: "h1"}},
            {"id": "b", "type": "password", "metadata": {VNC_COMPANION_HOST_KEY: "other"}},
            {"id": "c", "type": "password", "metadata": {VNC_COMPANION_HOST_KEY: "h1"}},
        ]
        mgr = secrets_module.secrets_manager
        monkeypatch.setattr(mgr, "list_secrets", lambda *a, **k: entries)
        monkeypatch.setattr(mgr, "get_secret", lambda sid, *a, **k: {"value": f"pw-{sid}"})
        assert await _vnc_password_for("h1") == b"pw-c"

    @pytest.mark.asyncio
    async def test_missing_password_is_a_stable_error_code(self, monkeypatch):
        import api.secrets as secrets_module
        from api.vnc_host_target import VNC_AUTH_MISSING, _vnc_password_for

        monkeypatch.setattr(secrets_module.secrets_manager, "list_secrets", lambda *a, **k: [])
        with pytest.raises(HTTPException) as exc:
            await _vnc_password_for("h1")
        assert exc.value.status_code == 422 and exc.value.detail["code"] == VNC_AUTH_MISSING

    @pytest.mark.asyncio
    async def test_the_store_is_read_off_the_event_loop(self, monkeypatch):
        from api import vnc_host_target

        calls = []

        async def fake_to_thread(fn, *args):
            calls.append(fn)
            return b"x"

        monkeypatch.setattr(vnc_host_target.asyncio, "to_thread", fake_to_thread)
        await vnc_host_target._vnc_password_for("h1")
        assert calls == [vnc_host_target._read_vnc_password]


class TestHostileRfbServer:
    """A server that lies about sizes must be refused, not obeyed (#22191 review)."""

    def _session(self, payload: bytes, width=4, height=4):
        session = VncRfbSession("h", 1, b"pw")
        session.width, session.height = width, height
        buf = bytearray(payload)

        class Stream:
            async def read_exactly(self, n):
                chunk = bytes(buf[:n])
                del buf[:n]
                return chunk

            async def write(self, data):
                return None

        session._stream = Stream()
        return session

    @pytest.mark.asyncio
    async def test_rect_outside_the_screen_is_refused(self):
        from api.vnc_rfb_client import VncProtocolError

        session = self._session(struct.pack("!HHHHi", 3, 0, 2, 1, 0) + bytes(8))
        with pytest.raises(VncProtocolError, match="outside"):
            await session._read_rect(bytearray(4 * 4 * 3))

    @pytest.mark.asyncio
    async def test_total_bytes_per_update_are_capped(self, monkeypatch):
        from api import vnc_rfb_client
        from api.vnc_rfb_client import VncProtocolError

        monkeypatch.setattr(vnc_rfb_client, "VNC_MAX_FRAMEBUFFER_BYTES", 16)
        session = self._session(struct.pack("!HHHHi", 0, 0, 2, 2, 0) + bytes(16))
        with pytest.raises(VncProtocolError, match="cap"):
            await session._read_rect(bytearray(4 * 4 * 3), [8])

    @pytest.mark.asyncio
    async def test_oversize_canvas_is_refused_at_handshake(self, monkeypatch):
        from api import vnc_rfb_client
        from api.vnc_rfb_client import VncProtocolError

        monkeypatch.setattr(vnc_rfb_client, "VNC_MAX_FRAMEBUFFER_BYTES", 100)
        monkeypatch.setattr(vnc_rfb_client, "authenticate_as_client", AsyncMock())
        init = struct.pack("!HH", 65535, 65535) + bytes(16) + struct.pack("!I", 0)
        session = self._session(init)
        with pytest.raises(VncProtocolError, match="screen"):
            await session._handshake()

    @pytest.mark.asyncio
    async def test_oversize_desktop_name_is_refused(self, monkeypatch):
        from api import vnc_rfb_client
        from api.vnc_rfb_client import VncProtocolError

        monkeypatch.setattr(vnc_rfb_client, "authenticate_as_client", AsyncMock())
        init = struct.pack("!HH", 2, 2) + bytes(16) + struct.pack("!I", 2**31)
        session = self._session(init)
        with pytest.raises(VncProtocolError, match="name"):
            await session._handshake()

    @pytest.mark.asyncio
    async def test_oversize_server_cut_text_is_refused(self):
        from api.vnc_rfb_client import VncProtocolError

        session = self._session(struct.pack("!xxxI", 2**31))
        with pytest.raises(VncProtocolError, match="cut text"):
            await session._skip_server_message(3)


class TestRequestBounds:
    def test_coordinates_beyond_the_wire_range_are_a_422_not_a_500(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            MouseClickRequest(host_id="h", x=70000, y=1)


REGISTRY_NODE = DesktopVmEndpoint(
    node_id="n-desk", credential_id="c-desk", host="desk.example.test", web_port=6090, rfb_port=5907
)


@pytest.fixture
def registry_node(monkeypatch):
    """A fake SLM registry holding one VNC desktop node with its own password."""

    async def endpoint(**_):
        return REGISTRY_NODE

    async def password(ep):
        assert ep is REGISTRY_NODE
        return b"node-own-pw"

    monkeypatch.setattr("api.vnc_host_target.desktop_vnc_endpoint", endpoint)
    monkeypatch.setattr("api.vnc_host_target.desktop_vnc_password", password)


@pytest.fixture
def empty_registry(monkeypatch):
    async def endpoint(**_):
        return None

    monkeypatch.setattr("api.vnc_host_target.desktop_vnc_endpoint", endpoint)


class TestDesktopVmEntry:
    """Owner 2026-11-24: the desktop VM is a fleet node running VNC, resolved from the SLM registry."""

    @pytest.mark.asyncio
    async def test_desktop_vm_resolves_from_the_registry_with_that_nodes_password(self, registry_node, secrets_hosts):
        target = await resolve_vnc_target(DESKTOP_VM_HOST_ID)
        assert target == VncTarget(DESKTOP_VM_HOST_ID, "desk.example.test", 5907, b"node-own-pw")

    @pytest.mark.asyncio
    async def test_no_registered_node_means_no_fallback_a_stable_code(self, empty_registry, secrets_hosts):
        """One solid VNC desktop (owner 2026-11-24): no registered node, no main-machine guess."""
        with pytest.raises(HTTPException) as exc:
            await resolve_vnc_target(DESKTOP_VM_HOST_ID)
        assert exc.value.status_code == 404 and exc.value.detail["code"] == "desktop_vm_unavailable"

    @pytest.mark.asyncio
    async def test_a_control_with_no_desktop_node_is_refused_before_any_connection(self, empty_registry, fake_session):
        with pytest.raises(HTTPException) as exc:
            await run_on_host(DESKTOP_VM_HOST_ID, "click", x=1, y=1, button="left")
        assert exc.value.detail["code"] == "desktop_vm_unavailable"
        assert fake_session.instances == []

    @pytest.mark.asyncio
    async def test_the_endpoint_route_returns_none_without_a_node(self, empty_registry):
        from api import vnc_proxy

        assert await vnc_proxy.get_desktop_vm_endpoint(current_user={}) is None

    def test_desktop_vm_and_secrets_host_are_allowed_other_fleet_node_refused(self, secrets_hosts, password):
        assert resolve_host_id(DESKTOP_VM_HOST_ID) == DESKTOP_VM_HOST_ID
        assert resolve_host_id("h-secret") == "h-secret"
        with pytest.raises(HTTPException) as exc:
            resolve_host_id(FLEET_NODE_ID)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_registry_node_without_a_password_is_the_stable_code(self, monkeypatch, secrets_hosts):
        async def endpoint(**_):
            return REGISTRY_NODE

        async def no_password(ep):
            return None

        monkeypatch.setattr("api.vnc_host_target.desktop_vnc_endpoint", endpoint)
        monkeypatch.setattr("api.vnc_host_target.desktop_vnc_password", no_password)
        with pytest.raises(HTTPException) as exc:
            await resolve_vnc_target(DESKTOP_VM_HOST_ID)
        assert exc.value.status_code == 422 and exc.value.detail["code"] == "vnc_credential_missing"

    @pytest.mark.asyncio
    async def test_unreadable_registry_is_a_503_not_a_silent_fallback(self, monkeypatch, secrets_hosts):
        from services.slm_vnc_registry import SlmRegistryUnavailable

        async def down(**_):
            raise SlmRegistryUnavailable("down")

        monkeypatch.setattr("api.vnc_host_target.desktop_vnc_endpoint", down)
        with pytest.raises(HTTPException) as exc:
            await resolve_vnc_target(DESKTOP_VM_HOST_ID)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_a_control_on_the_desktop_vm_connects_to_the_registry_node(self, registry_node, fake_session):
        result = await run_on_host(DESKTOP_VM_HOST_ID, "click", x=1, y=1, button="left")
        assert result["status"] == "success"
        assert fake_session.instances[0].args == ("desk.example.test", 5907, b"node-own-pw")

    @pytest.mark.asyncio
    async def test_page_proxy_and_controls_hit_the_same_machine(self, registry_node, secrets_hosts):
        """The endpoint route the page reads, the proxy upstream and the controls all name one node."""
        from api import vnc_proxy

        route = await vnc_proxy.get_desktop_vm_endpoint(current_user={})
        upstream = await vnc_proxy._upstream_endpoint("desktop")
        target = await resolve_vnc_target(DESKTOP_VM_HOST_ID)
        assert route == {"host": "desk.example.test", "port": 6090}
        assert upstream == f"{vnc_proxy.VNC_UPSTREAM_SCHEME}://desk.example.test:6090"
        assert target.address == route["host"]

    @pytest.mark.asyncio
    async def test_the_proxy_answers_with_the_registry_nodes_password(self, registry_node):
        from api import vnc_proxy

        assert await vnc_proxy._proxy_password("desktop") == b"node-own-pw"


class TestWebsocketRefusals:
    """The desktop VM's refusals close the websocket with 1011 and the stable code, before and after accept."""

    def _ws(self):
        from unittest.mock import MagicMock

        ws = MagicMock()
        ws.close = AsyncMock()
        return ws

    def _client_app(self):
        """A real ASGI app serving the proxy's websocket route, driven by Starlette's TestClient."""
        from fastapi import FastAPI

        from api import vnc_proxy

        app = FastAPI()
        app.include_router(vnc_proxy.router, prefix="/vnc-proxy")
        return app

    def test_no_desktop_node_the_client_receives_1011_and_the_code(self, empty_registry):
        """A real client sees the close code and the stable reason, not a bare handshake rejection."""
        from starlette.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        with (
            patch("api.vnc_proxy.enforce_ws_origin", new=AsyncMock(return_value=True)),
            patch("api.vnc_proxy.enforce_ws_desktop_auth", new=AsyncMock(return_value={"username": "a"})),
        ):
            with TestClient(self._client_app()) as client:
                with client.websocket_connect("/vnc-proxy/desktop/websockify") as ws:
                    with pytest.raises(WebSocketDisconnect) as closed:
                        ws.receive_bytes()
        assert closed.value.code == 1011
        assert closed.value.reason == "desktop_vm_unavailable"

    def test_unreadable_registry_the_client_receives_1011_and_the_code(self, monkeypatch):
        from starlette.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect

        from services.slm_vnc_registry import SlmRegistryUnavailable

        async def down(**_):
            raise SlmRegistryUnavailable("down")

        monkeypatch.setattr("api.vnc_host_target.desktop_vnc_endpoint", down)
        with (
            patch("api.vnc_proxy.enforce_ws_origin", new=AsyncMock(return_value=True)),
            patch("api.vnc_proxy.enforce_ws_desktop_auth", new=AsyncMock(return_value={"username": "a"})),
        ):
            with TestClient(self._client_app()) as client:
                with client.websocket_connect("/vnc-proxy/desktop/websockify") as ws:
                    with pytest.raises(WebSocketDisconnect) as closed:
                        ws.receive_bytes()
        assert closed.value.code == 1011 and closed.value.reason == "slm_registry_unavailable"

    @pytest.mark.asyncio
    async def test_a_password_refusal_after_accept_closes_1011_with_the_code(self, registry_node, monkeypatch):
        from api import vnc_proxy

        async def no_password(ep):
            return None

        monkeypatch.setattr("api.vnc_host_target.desktop_vnc_password", no_password)
        ws = self._ws()

        class FakeWs:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return None

        class FakeSession:
            def ws_connect(self, url):
                return FakeWs()

        class FakeClient:
            def tracked_session(self):
                return FakeCtx()

        class FakeCtx:
            async def __aenter__(self):
                return FakeSession()

            async def __aexit__(self, *a):
                return None

        with (
            patch("api.vnc_proxy.enforce_ws_origin", new=AsyncMock(return_value=True)),
            patch("api.vnc_proxy.enforce_ws_desktop_auth", new=AsyncMock(return_value={"username": "a"})),
            patch("api.vnc_proxy.accept_websocket", new=AsyncMock()),
            patch("api.vnc_proxy.record_observation", new=AsyncMock()),
            patch("api.vnc_proxy.assert_egress_policy", new=AsyncMock()),
            patch("api.vnc_proxy.get_http_client", return_value=FakeClient()),
        ):
            await vnc_proxy.websocket_proxy(ws, "desktop")
        ws.close.assert_awaited_once_with(code=1011, reason="vnc_credential_missing")
