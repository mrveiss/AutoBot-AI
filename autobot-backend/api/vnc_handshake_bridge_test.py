# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for api.vnc_handshake_bridge (#16299).

get_vnc_password must fail closed -- a missing secret refuses the
connection, never falls back to no auth. The WS-byte-stream adapters are
exercised against fake WebSocket doubles that emit messages across
artificial boundaries, proving read_exactly correctly reassembles a
multi-message handshake and that leftover() surfaces exactly the bytes
past the boundary, not silently dropping them.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from api.vnc_handshake_bridge import (
    _AiohttpWsByteStream,
    _FastApiWsByteStream,
    authenticate_both_legs,
    get_vnc_password,
)
from security.vnc_rfb_auth import (
    RFB_VERSION,
    SECURITY_TYPE_NONE,
    SECURITY_TYPE_VNC_AUTH,
    VncAuthError,
    encrypt_challenge,
)


class _FakeSecret:
    def __init__(self, name: str, id_: str) -> None:
        self.name = name
        self.id = id_


def _mock_session_factory():
    """A get_async_session_factory() double whose `async with factory() as
    session` yields a MagicMock session -- session itself is never touched
    by service_list/service_read once the coordinator is mocked."""
    session = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


@pytest.mark.asyncio
async def test_get_vnc_password_fails_closed_when_no_secret_is_registered():
    """#16299 review requirement: a missing secret must refuse the
    connection, never silently proceed as if no password were needed."""
    with (
        patch("api.envelope_secrets.get_coordinator") as mock_get_coordinator,
        patch("user_management.database.get_async_session_factory", new=_mock_session_factory()),
    ):
        mock_get_coordinator.return_value.service_list = AsyncMock(return_value=[])
        with pytest.raises(VncAuthError, match="no VNC password registered"):
            await get_vnc_password("desktop")


@pytest.mark.asyncio
async def test_get_vnc_password_returns_the_matching_secret_plaintext():
    with (
        patch("api.envelope_secrets.get_coordinator") as mock_get_coordinator,
        patch("user_management.database.get_async_session_factory", new=_mock_session_factory()),
    ):
        coordinator = mock_get_coordinator.return_value
        coordinator.service_list = AsyncMock(
            return_value=[_FakeSecret("vnc-password-browser", "id-1"), _FakeSecret("vnc-password-desktop", "id-2")]
        )
        coordinator.service_read = AsyncMock(return_value=b"the-real-password")

        result = await get_vnc_password("desktop")

    assert result == b"the-real-password"
    read_kwargs = coordinator.service_read.await_args.kwargs
    assert read_kwargs["secret_id"] == "id-2", "must read the desktop-named secret, not the first one found"


@pytest.mark.asyncio
async def test_get_vnc_password_error_never_contains_a_secret_value():
    """Even the failure path must not leak anything secret-shaped -- there is
    no value to leak here (nothing was ever read), but pin the message
    shape so a future refactor can't accidentally start interpolating one."""
    with (
        patch("api.envelope_secrets.get_coordinator") as mock_get_coordinator,
        patch("user_management.database.get_async_session_factory", new=_mock_session_factory()),
    ):
        mock_get_coordinator.return_value.service_list = AsyncMock(return_value=[])
        with pytest.raises(VncAuthError) as excinfo:
            await get_vnc_password("browser")

    assert str(excinfo.value) == "no VNC password registered for vnc_type='browser' in the secrets vault"


def _aiohttp_msg(data: bytes) -> SimpleNamespace:
    return SimpleNamespace(type=aiohttp.WSMsgType.BINARY, data=data)


@pytest.mark.asyncio
async def test_aiohttp_stream_reassembles_reads_split_across_messages():
    """read_exactly(16) must work even when the 16 bytes arrive as three
    separate WS frames (5, 5, 7 bytes -- one byte past the boundary) -- RFB
    message boundaries don't align with WS frame boundaries."""
    ws = MagicMock()
    ws.receive = AsyncMock(side_effect=[_aiohttp_msg(b"12345"), _aiohttp_msg(b"67890"), _aiohttp_msg(b"ABCDEFG")])
    stream = _AiohttpWsByteStream(ws)

    result = await stream.read_exactly(16)

    assert result == b"1234567890ABCDEF"
    assert stream.leftover() == b"G", "the 16th byte's frame carried one extra byte that must not be lost"


@pytest.mark.asyncio
async def test_aiohttp_stream_raises_on_server_close_mid_handshake():
    ws = MagicMock()
    ws.receive = AsyncMock(return_value=SimpleNamespace(type=aiohttp.WSMsgType.CLOSED, data=None))
    stream = _AiohttpWsByteStream(ws)

    with pytest.raises(VncAuthError, match="closed the connection"):
        await stream.read_exactly(16)


@pytest.mark.asyncio
async def test_fastapi_stream_reassembles_reads_split_across_messages():
    ws = MagicMock()
    ws.receive = AsyncMock(side_effect=[{"bytes": b"RFB 003."}, {"bytes": b"008\nEXTRA"}])
    stream = _FastApiWsByteStream(ws)

    result = await stream.read_exactly(12)

    assert result == RFB_VERSION
    assert stream.leftover() == b"EXTRA"


@pytest.mark.asyncio
async def test_authenticate_both_legs_runs_the_full_handshake_and_surfaces_leftovers():
    """End-to-end through the real adapters and the real handshake functions
    -- fake WebSocket doubles scripted as a genuine RFB 3.8 server and a
    genuine noVNC-shaped browser client, each with one extra byte of
    framebuffer-protocol data tacked onto their last handshake message."""
    password = b"topsecret"
    challenge = bytes(range(16))
    response = encrypt_challenge(password, challenge)

    vnc_ws = MagicMock()
    vnc_ws.receive = AsyncMock(
        side_effect=[
            _aiohttp_msg(RFB_VERSION),
            _aiohttp_msg(bytes([1, SECURITY_TYPE_VNC_AUTH])),
            _aiohttp_msg(challenge),
            _aiohttp_msg((0).to_bytes(4, "big") + b"X"),  # +1 leftover byte
        ]
    )
    vnc_ws.send_bytes = AsyncMock()

    browser_ws = MagicMock()
    browser_ws.receive = AsyncMock(
        side_effect=[
            {"bytes": RFB_VERSION},
            {"bytes": bytes([SECURITY_TYPE_NONE]) + b"Y"},  # +1 leftover byte
        ]
    )
    browser_ws.send_bytes = AsyncMock()

    vnc_leftover, browser_leftover = await authenticate_both_legs(vnc_ws, browser_ws, password)

    assert vnc_leftover == b"X"
    assert browser_leftover == b"Y"
    sent_to_vnc = [call.args[0] for call in vnc_ws.send_bytes.await_args_list]
    assert sent_to_vnc == [RFB_VERSION, bytes([SECURITY_TYPE_VNC_AUTH]), response]
    sent_to_browser = [call.args[0] for call in browser_ws.send_bytes.await_args_list]
    assert sent_to_browser == [RFB_VERSION, bytes([1, SECURITY_TYPE_NONE]), (0).to_bytes(4, "big")]
