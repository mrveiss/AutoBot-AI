# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Bridges the RFB handshake (security.vnc_rfb_auth) onto the two real
connections api.vnc_proxy.websocket_proxy manages (#16299): the aiohttp
WebSocket to the real VNC server, and the FastAPI WebSocket to the browser.

Closes the VITE_*_VNC_PASSWORD leak: the backend now answers the real
server's password challenge itself, using a password it reads from the
canonical secrets system (never a local file -- a plaintext env-file read
would be a parallel credential path), and offers the browser security-type
"None" so noVNC never sees or needs a password at all.
"""

from __future__ import annotations

import aiohttp
from fastapi import WebSocket, WebSocketDisconnect

from security.vnc_rfb_auth import VncAuthError, authenticate_as_client, offer_no_auth_as_server
from services.secrets_coordinator import SecretsCoordinator


class _AiohttpWsByteStream:
    """Adapts an aiohttp ClientWebSocketResponse to the ByteReader/ByteWriter
    protocol security.vnc_rfb_auth expects, buffering partial WS messages so
    RFB's byte-oriented handshake can be read message-boundary-agnostic."""

    def __init__(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self._ws = ws
        self._buf = b""

    async def read_exactly(self, n: int) -> bytes:
        while len(self._buf) < n:
            msg = await self._ws.receive()
            if msg.type == aiohttp.WSMsgType.BINARY:
                self._buf += msg.data
            elif msg.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                raise VncAuthError("VNC server closed the connection during the handshake")
            # TEXT frames are not part of the RFB binary handshake; ignored.
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk

    async def write(self, data: bytes) -> None:
        await self._ws.send_bytes(data)

    def leftover(self) -> bytes:
        """Bytes already read off the WebSocket past the handshake boundary
        -- the caller must forward these before starting the plain relay, or
        the start of the framebuffer protocol is silently dropped."""
        return self._buf


class _FastApiWsByteStream:
    """Same adapter, for FastAPI's WebSocket (the browser leg)."""

    def __init__(self, ws: WebSocket) -> None:
        self._ws = ws
        self._buf = b""

    async def read_exactly(self, n: int) -> bytes:
        while len(self._buf) < n:
            try:
                data = await self._ws.receive()
            except WebSocketDisconnect as exc:
                raise VncAuthError("browser disconnected during the handshake") from exc
            if "bytes" in data:
                self._buf += data["bytes"]
            elif data.get("type") == "websocket.disconnect":
                raise VncAuthError("browser disconnected during the handshake")
            # TEXT frames are not part of the RFB binary handshake; ignored.
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk

    async def write(self, data: bytes) -> None:
        await self._ws.send_bytes(data)

    def leftover(self) -> bytes:
        return self._buf


async def get_vnc_password(vnc_type: str) -> bytes:
    """Read this vnc_type's password from the canonical secrets system.

    Fails closed: raises VncAuthError when no secret is registered, never
    falls back to an unauthenticated connection. #16299 review requirement:
    the password itself never appears in the raised message.
    """
    from api.envelope_secrets import get_coordinator  # noqa: PLC0415 -- avoid a router import cycle
    from autobot_shared.secrets_vault import VaultKind, VaultRef  # noqa: PLC0415
    from user_management.database import get_async_session_factory  # noqa: PLC0415

    vault = VaultRef(VaultKind.SYSTEM)
    coordinator: SecretsCoordinator = get_coordinator()
    secret_name = f"vnc-password-{vnc_type}"

    factory = get_async_session_factory()
    async with factory() as session:
        secrets = await coordinator.service_list(session, vault=vault)
        for secret in secrets:
            if secret.name == secret_name:
                return await coordinator.service_read(session, secret_id=secret.id, vault=vault)

    raise VncAuthError(f"no VNC password registered for vnc_type={vnc_type!r} in the secrets vault")


async def authenticate_both_legs(
    vnc_ws: aiohttp.ClientWebSocketResponse, websocket: WebSocket, password: bytes
) -> tuple[bytes, bytes]:
    """Run the RFB handshake on both legs. Returns (vnc_leftover,
    browser_leftover): bytes already consumed off each WebSocket past the
    handshake boundary, which the caller must forward first when the plain
    byte-relay takes over -- losing them would corrupt the start of the
    framebuffer protocol.
    """
    server_stream = _AiohttpWsByteStream(vnc_ws)
    browser_stream = _FastApiWsByteStream(websocket)
    await authenticate_as_client(server_stream, server_stream, password)
    await offer_no_auth_as_server(browser_stream, browser_stream)
    return server_stream.leftover(), browser_stream.leftover()
