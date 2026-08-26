# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Route-level capability scoping for paired-device credentials (#14964).

Drives the real ``/ws/{session_id}``, ``/ws/ssh/{host_id}`` and
``/{vnc_type}/websockify`` routes through ``starlette.testclient.TestClient``,
so route matching and dependency resolution are part of what is under test.
A handler-direct call cannot see a routing failure, and a 404 makes a refusal
assertion pass for the wrong reason -- so every refusal case here is paired
with a case that gets *through* the same gate on the same path, which is the
non-vacuity witness a "not 404" assertion is for a WebSocket route.

What is deliberately NOT claimed here: that a paired device can reach these
sockets in production today. It cannot -- ``_resolve_ws_user`` resolves user,
session and service credentials only, and a device JWT presented at these
routes was refused as merely "unauthenticated" before this change. What
changed is that the refusal is now a *capability decision* with its own reason,
taken against the credential's own grant set, instead of an accident of the
credential being unrecognised. The device credential is injected at
``_resolve_ws_device_credential`` -- the JWT validation seam -- so the gate,
the predicate and the routes are all real and only the credential's arrival is
staged.
"""

import logging
import uuid
from contextlib import contextmanager, suppress
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient
from starlette.websockets import WebSocket, WebSocketDisconnect

from api.terminal import router as terminal_router
from api.terminal import session_manager
from api.vnc_proxy import router as vnc_router
from autobot_shared.auth.device_capabilities import (
    NO_CAPABILITIES_JSON,
    DeviceCapability,
    serialise_device_permissions,
)
from models.mobile_device import MobileDevice
from services.terminal_session_store import SessionConfigStore

_WS_LOGGER = "api.ws_security"
_DEVICE_ID = "7f6a5b4c-3d2e-4f10-9a8b-0c1d2e3f4a5b"
_DEVICE_USERNAME = f"device:{_DEVICE_ID}"

_original_accept = WebSocket.accept


async def _spy_accept(self, *args, **kwargs):
    """Real function, not a Mock, so ``self`` binds the normal descriptor way."""
    _spy_accept.calls.append(self)
    return await _original_accept(self, *args, **kwargs)


_spy_accept.calls = []


@contextmanager
def _accept_spy():
    _spy_accept.calls = []
    with patch.object(WebSocket, "accept", new=_spy_accept):
        yield _spy_accept.calls


def _device_row(*, permissions: str, is_approved: bool = True, revoked_at=None) -> MobileDevice:
    """A ``MobileDevice`` in a chosen capability state, built without a database.

    The row is the real model object, so ``permissions``/``is_approved``/
    ``revoked_at`` are read by the production predicate exactly as they would
    be off a live query.
    """
    return MobileDevice(
        id=uuid.UUID(_DEVICE_ID),
        user_id="alice",
        device_name="alice-phone",
        platform="ios",
        permissions=permissions,
        is_approved=is_approved,
        revoked_at=revoked_at,
    )


#: The state migration 20260824_084 leaves every row that predates it in.
def _backfilled_row() -> MobileDevice:
    return _device_row(permissions=NO_CAPABILITIES_JSON, is_approved=False)


@contextmanager
def _device_credential(device: "MobileDevice | None"):
    """Present a paired-device credential and no user credential.

    ``_resolve_ws_user`` is forced to ``None`` because every user/session/
    service source must be closed off for "this caller is a device"; the
    conftest's ``auth_middleware`` stub otherwise fabricates a truthy user for
    anything left unpatched, and the test would pass through the wrong branch.
    """
    device_user = {
        "username": _DEVICE_USERNAME,
        "user_id": "alice",
        "role": "device",
        "device_id": _DEVICE_ID,
        "scope": "read",
        "auth_method": "device_jwt",
    }
    with (
        patch("api.ws_security._resolve_ws_user", new=AsyncMock(return_value=None)),
        patch("api.ws_security._resolve_ws_device_credential", new=AsyncMock(return_value=device_user)),
        patch("services.device_capabilities._load_device", new=AsyncMock(return_value=device)),
    ):
        yield


@contextmanager
def _no_credential_at_all():
    with (
        patch("api.ws_security._resolve_ws_user", new=AsyncMock(return_value=None)),
        patch("api.ws_security._resolve_ws_device_credential", new=AsyncMock(return_value=None)),
    ):
        yield


@pytest.fixture
def terminal_client():
    app = FastAPI()
    app.include_router(terminal_router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def vnc_client():
    app = FastAPI()
    app.include_router(vnc_router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _fake_session_store(monkeypatch):
    """Back ``session_manager`` with fakeredis; the real store fails closed."""
    fake_client = fakeredis.FakeRedis(server=fakeredis.FakeServer())
    monkeypatch.setattr(session_manager, "session_configs", SessionConfigStore(redis_client=fake_client))


@pytest.fixture
def device_owned_session():
    """A terminal session owned by the device credential itself.

    Ownership is checked against ``username`` (``_lookup_terminal_session``),
    so a device that clears the capability gate still has to own the session.
    Handing it one is what makes the granted case reach ``accept()`` and
    therefore what makes the denied cases non-vacuous.
    """
    session_id = str(uuid.uuid4())
    session_manager.session_configs[session_id] = {
        "session_id": session_id,
        "owner": _DEVICE_USERNAME,
        "security_level": "standard",
    }
    yield session_id
    session_manager.session_configs.pop(session_id, None)


class TestTerminalWebsocketCapabilityGate:
    def test_a_backfilled_credential_is_refused_the_terminal(self, terminal_client, device_owned_session, caplog):
        """AC: a credential that predates the capability column exercises nothing.

        This is the backfill assertion at route level. Flip migration
        20260824_084's default from ``'[]'`` to a grant and this goes red.
        """
        with (
            _device_credential(_backfilled_row()),
            caplog.at_level(logging.WARNING, logger=_WS_LOGGER),
            _accept_spy() as calls,
        ):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with terminal_client.websocket_connect(f"/ws/{device_owned_session}"):
                    pass

        assert exc_info.value.code == 1008
        assert len(calls) == 0, "refused before accept() -- no shell may exist for a denied credential"
        assert any("reason=not_approved:terminal" in r.getMessage() for r in caplog.records)

    def test_an_approved_credential_without_the_terminal_capability_is_refused(
        self, terminal_client, device_owned_session, caplog
    ):
        """Approval alone is not a capability: the grant set still has to name it."""
        approved_but_desktop_only = _device_row(
            permissions=serialise_device_permissions([DeviceCapability.DESKTOP_VIEW])
        )
        with (
            _device_credential(approved_but_desktop_only),
            caplog.at_level(logging.WARNING, logger=_WS_LOGGER),
            _accept_spy() as calls,
        ):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with terminal_client.websocket_connect(f"/ws/{device_owned_session}"):
                    pass

        assert exc_info.value.code == 1008
        assert len(calls) == 0
        assert any("reason=missing_capability:terminal" in r.getMessage() for r in caplog.records)

    def test_a_revoked_credential_is_refused_a_capability_it_holds(
        self, terminal_client, device_owned_session, caplog
    ):
        """AC: revocation takes effect on a new handshake, without deleting the row."""
        revoked = _device_row(
            permissions=serialise_device_permissions([DeviceCapability.TERMINAL]),
            revoked_at="2026-08-24T00:00:00+00:00",
        )
        with (
            _device_credential(revoked),
            caplog.at_level(logging.WARNING, logger=_WS_LOGGER),
            _accept_spy() as calls,
        ):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with terminal_client.websocket_connect(f"/ws/{device_owned_session}"):
                    pass

        assert exc_info.value.code == 1008
        assert len(calls) == 0

    def test_a_granted_credential_reaches_accept(self, terminal_client, device_owned_session):
        """Non-vacuity witness for every refusal above.

        Same route, same client, same session: the only difference is the
        credential's grant set. Without this, a 404, a routing change or a
        fail-closed session store would make the refusals pass for the wrong
        reason.
        """
        fake_terminal = MagicMock()
        fake_terminal.cleanup = AsyncMock()
        granted = _device_row(permissions=serialise_device_permissions([DeviceCapability.TERMINAL]))

        with (
            _device_credential(granted),
            patch("api.terminal._init_terminal_handler", new=AsyncMock(return_value=fake_terminal)),
            patch("api.terminal._run_terminal_message_loop", new=AsyncMock()),
            _accept_spy() as calls,
        ):
            with terminal_client.websocket_connect(f"/ws/{device_owned_session}"):
                pass

        assert len(calls) == 1

    def test_a_missing_credential_and_a_denied_credential_are_distinguishable(
        self, terminal_client, device_owned_session, caplog
    ):
        """Both close 1008. A log that cannot tell them apart is not a log.

        The vacuous version of this test asserts only that both are refused.
        This one asserts the two refusals carry different, mutually exclusive
        reasons -- an operator has to be able to tell "nobody authenticated"
        from "a known device lacks a capability".
        """
        with _no_credential_at_all(), caplog.at_level(logging.WARNING, logger=_WS_LOGGER):
            with pytest.raises(WebSocketDisconnect) as no_credential:
                with terminal_client.websocket_connect(f"/ws/{device_owned_session}"):
                    pass
            anonymous_messages = [r.getMessage() for r in caplog.records]

        caplog.clear()
        with _device_credential(_backfilled_row()), caplog.at_level(logging.WARNING, logger=_WS_LOGGER):
            with pytest.raises(WebSocketDisconnect) as denied_device:
                with terminal_client.websocket_connect(f"/ws/{device_owned_session}"):
                    pass
            device_messages = [r.getMessage() for r in caplog.records]

        assert no_credential.value.code == denied_device.value.code == 1008
        assert any("Rejected unauthenticated WebSocket handshake" in m for m in anonymous_messages)
        assert not any("Rejected device credential" in m for m in anonymous_messages)
        assert any("Rejected device credential" in m for m in device_messages)
        assert not any("Rejected unauthenticated WebSocket handshake" in m for m in device_messages)

    def test_no_refusal_message_carries_credential_material(
        self, terminal_client, device_owned_session, caplog
    ):
        """A refusal names the device, never the secret that identified it.

        The telltale is planted in the encrypted-token column, which is the
        one field on this record that is credential material.
        """
        telltale = "TELLTALE-DEVICE-SECRET-14964"  # noqa: S105 - test marker, not a credential
        device = _backfilled_row()
        device._device_token_encrypted = telltale

        with _device_credential(device), caplog.at_level(logging.DEBUG):
            with pytest.raises(WebSocketDisconnect):
                with terminal_client.websocket_connect(f"/ws/{device_owned_session}"):
                    pass

        rendered = "\n".join(r.getMessage() for r in caplog.records)
        assert telltale not in rendered
        assert _DEVICE_ID in rendered, "the refusal must still name which device it refused"


class TestSshTerminalWebsocketCapabilityGate:
    def test_a_backfilled_credential_is_refused_before_the_admin_gate(self, terminal_client, caplog):
        """The capability gate runs first and names itself.

        A device credential carries ``role="device"`` and would fail the admin
        check anyway; the point is that it fails for a stated reason rather
        than falling into a check that was never about devices.
        """
        with (
            _device_credential(_backfilled_row()),
            caplog.at_level(logging.WARNING),
            _accept_spy() as calls,
        ):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with terminal_client.websocket_connect("/ws/ssh/some-host"):
                    pass

        messages = [r.getMessage() for r in caplog.records]
        assert exc_info.value.code == 1008
        assert len(calls) == 0
        assert any("Rejected device credential" in m for m in messages)
        assert not any("is not an admin" in m for m in messages)


class TestVncWebsocketCapabilityGate:
    """The raw RFB proxy requires BOTH desktop capabilities.

    ``_forward_client_to_vnc`` forwards the client's KeyEvent/PointerEvent
    frames verbatim, so this socket grants input as inseparably as it grants
    view. A credential holding only ``desktop:view`` must therefore be refused
    -- granting it would be a view-only grant that is not view-only.
    """

    def test_a_backfilled_credential_is_refused_the_desktop(self, vnc_client, caplog):
        with (
            _device_credential(_backfilled_row()),
            caplog.at_level(logging.WARNING, logger=_WS_LOGGER),
            _accept_spy() as calls,
        ):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with vnc_client.websocket_connect("/desktop/websockify"):
                    pass

        assert exc_info.value.code == 1008
        assert len(calls) == 0, "no RFB frame may be forwarded for a denied credential"
        rendered = "\n".join(r.getMessage() for r in caplog.records)
        assert "desktop:input" in rendered and "desktop:view" in rendered

    def test_view_alone_does_not_open_the_input_carrying_socket(self, vnc_client, caplog):
        view_only = _device_row(permissions=serialise_device_permissions([DeviceCapability.DESKTOP_VIEW]))
        with (
            _device_credential(view_only),
            caplog.at_level(logging.WARNING, logger=_WS_LOGGER),
            _accept_spy() as calls,
        ):
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with vnc_client.websocket_connect("/desktop/websockify"):
                    pass

        rendered = "\n".join(r.getMessage() for r in caplog.records)
        assert exc_info.value.code == 1008
        assert len(calls) == 0
        assert "reason=missing_capability:desktop:input" in rendered

    def test_both_desktop_capabilities_reach_accept(self, vnc_client):
        """Non-vacuity witness: the route is live and the gate is the only thing refusing."""
        granted = _device_row(
            permissions=serialise_device_permissions(
                [DeviceCapability.DESKTOP_VIEW, DeviceCapability.DESKTOP_INPUT]
            )
        )
        with (
            _device_credential(granted),
            patch("api.vnc_proxy.record_observation", new=AsyncMock()),
            patch("api.vnc_proxy.get_http_client", side_effect=RuntimeError("stop after the capability gate")),
            _accept_spy() as calls,
        ):
            with suppress(Exception):
                with vnc_client.websocket_connect("/desktop/websockify"):
                    pass

        assert len(calls) == 1


class TestGateWiringMistakesDeny:
    """Handler-level, not route-level, because the mistake is at a call site.

    An enforcement point that names no capability cannot be produced by a
    request; it is produced by wiring the gate wrong. The only safe reading of
    "must hold nothing in particular" on a full-control surface is that the
    credential holds nothing.
    """

    @pytest.mark.asyncio
    async def test_a_gate_invoked_with_no_required_capability_refuses(self, caplog):
        from api.ws_security import enforce_ws_remote_control_auth

        websocket = MagicMock()
        websocket.headers = {}
        websocket.query_params = {}
        websocket.close = AsyncMock()

        with (
            _device_credential(
                _device_row(permissions=serialise_device_permissions(list(DeviceCapability)))
            ),
            caplog.at_level(logging.ERROR, logger=_WS_LOGGER),
        ):
            user = await enforce_ws_remote_control_auth(websocket)

        assert user is None, "a gate that requires nothing must not admit a full-control credential"
        websocket.close.assert_awaited_once()
        assert websocket.close.await_args.kwargs.get("code") == 1008
        assert any("no required capability" in r.getMessage() for r in caplog.records)
