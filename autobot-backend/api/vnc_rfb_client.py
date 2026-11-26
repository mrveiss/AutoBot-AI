# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Minimal RFB client: input events and one framebuffer grab against a VNC server (#22145).

The chat Desktop controls act on the host the user is shown, so they speak the
VNC protocol to that host's own endpoint instead of driving a local X display.
The VncAuth handshake is ``security.vnc_rfb_auth.authenticate_as_client``; this
module owns only what follows it: ClientInit/ServerInit, pointer, key and
clipboard messages, and a Raw-encoded framebuffer read for screenshots.
"""

from __future__ import annotations

import asyncio
import io
import struct
from dataclasses import dataclass

from autobot_shared.env_utils import env_int, env_int_clamped
from security.vnc_rfb_auth import VncAuthError, authenticate_as_client

VNC_CONNECT_TIMEOUT_S = env_int("AUTOBOT_VNC_CLIENT_CONNECT_TIMEOUT_S", 10)
VNC_FRAME_TIMEOUT_S = env_int("AUTOBOT_VNC_CLIENT_FRAME_TIMEOUT_S", 15)
VNC_MAX_FRAMEBUFFER_BYTES = env_int("AUTOBOT_VNC_CLIENT_MAX_FRAMEBUFFER_BYTES", 64 * 1024 * 1024)
# Desktop name and server cut text cap.
VNC_MAX_TEXT_BYTES = env_int_clamped("AUTOBOT_VNC_CLIENT_MAX_TEXT_BYTES", 1024 * 1024, min_v=1024, max_v=67108864)

# VNC_MAX_FRAMEBUFFER_BYTES caps each buffer in that buffer's OWN unit: the RGB canvas we keep
# (3 bytes per pixel) and the raw bytes one update carries on the wire (4 bytes per pixel, 32bpp).
_RGB_BYTES_PER_PIXEL = 3
_WIRE_BYTES_PER_PIXEL = 4

_MSG_SET_PIXEL_FORMAT = 0
_MSG_SET_ENCODINGS = 2
_MSG_FRAMEBUFFER_REQUEST = 3
_MSG_KEY_EVENT = 4
_MSG_POINTER_EVENT = 5
_MSG_CLIENT_CUT_TEXT = 6
_ENCODING_RAW = 0
# 32bpp, depth 24, little-endian, true colour, 8 bits per channel, R<<16 G<<8 B.
_PIXEL_FORMAT = struct.pack("!BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 16, 8, 0)


class VncProtocolError(Exception):
    """The server broke the RFB protocol or the framebuffer exceeded the cap."""


class _Stream:
    """Adapts asyncio streams to the ByteReader/ByteWriter shape the handshake expects."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader, self.writer = reader, writer

    async def read_exactly(self, n: int) -> bytes:
        try:
            return await self.reader.readexactly(n)
        except asyncio.IncompleteReadError as exc:
            raise VncProtocolError("VNC server closed the connection") from exc

    async def write(self, data: bytes) -> None:
        self.writer.write(data)
        await self.writer.drain()


@dataclass
class VncFrame:
    width: int
    height: int
    rgb: bytes  # tightly packed 3 bytes per pixel


class VncRfbSession:
    """One authenticated RFB connection; use as ``async with``."""

    def __init__(self, host: str, port: int, password: bytes) -> None:
        self._host, self._port, self._password = host, port, password
        self._stream: _Stream | None = None
        self.width = 0
        self.height = 0

    async def __aenter__(self) -> "VncRfbSession":
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port), timeout=VNC_CONNECT_TIMEOUT_S
        )
        self._stream = _Stream(reader, writer)
        try:
            await asyncio.wait_for(self._handshake(), timeout=VNC_CONNECT_TIMEOUT_S)
        except BaseException:
            writer.close()
            raise
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._stream:
            self._stream.writer.close()
            try:
                await self._stream.writer.wait_closed()
            except OSError:
                pass

    async def _handshake(self) -> None:
        s = self._stream
        await authenticate_as_client(s, s, self._password, max_reason_bytes=VNC_MAX_TEXT_BYTES)
        await s.write(b"\x01")  # ClientInit: shared
        self.width, self.height = struct.unpack("!HH", await s.read_exactly(4))
        await s.read_exactly(16)  # server pixel format, superseded below
        if self.width * self.height * _RGB_BYTES_PER_PIXEL > VNC_MAX_FRAMEBUFFER_BYTES:
            raise VncProtocolError("server advertises a screen larger than the configured size cap")
        name_len = struct.unpack("!I", await s.read_exactly(4))[0]
        if name_len > VNC_MAX_TEXT_BYTES:
            raise VncProtocolError("server desktop name exceeds the configured size cap")
        await s.read_exactly(name_len)
        await s.write(struct.pack("!Bxxx", _MSG_SET_PIXEL_FORMAT) + _PIXEL_FORMAT)
        await s.write(struct.pack("!BxHi", _MSG_SET_ENCODINGS, 1, _ENCODING_RAW))

    async def _send(self, data: bytes) -> None:
        await self._stream.write(data)

    async def pointer(self, x: int, y: int, buttons: int) -> None:
        await self._send(struct.pack("!BBHH", _MSG_POINTER_EVENT, buttons, x, y))

    async def key(self, keysym: int, down: bool) -> None:
        await self._send(struct.pack("!BBxxI", _MSG_KEY_EVENT, 1 if down else 0, keysym))

    async def cut_text(self, text: str) -> None:
        data = text.encode("latin-1", errors="replace")
        await self._send(struct.pack("!Bxxx", _MSG_CLIENT_CUT_TEXT) + struct.pack("!I", len(data)) + data)

    async def grab_frame(self) -> VncFrame:
        """Request the full framebuffer and read it (Raw encoding only)."""
        await self._send(struct.pack("!BBHHHH", _MSG_FRAMEBUFFER_REQUEST, 0, 0, 0, self.width, self.height))
        return await asyncio.wait_for(self._read_update(), timeout=VNC_FRAME_TIMEOUT_S)

    async def _skip_server_message(self, kind: int) -> None:
        s = self._stream
        if kind == 1:  # SetColourMap
            _, count = struct.unpack("!xHH", await s.read_exactly(5))
            await s.read_exactly(6 * count)
        elif kind == 3:  # ServerCutText
            length = struct.unpack("!xxxI", await s.read_exactly(7))[0]
            if length > VNC_MAX_TEXT_BYTES:
                raise VncProtocolError("server cut text exceeds the configured size cap")
            await s.read_exactly(length)
        elif kind != 2:  # Bell carries no body
            raise VncProtocolError(f"unexpected server message type {kind}")

    async def _read_update(self) -> VncFrame:
        s = self._stream
        canvas = bytearray(self.width * self.height * _RGB_BYTES_PER_PIXEL)
        while True:
            kind = (await s.read_exactly(1))[0]
            if kind != 0:
                await self._skip_server_message(kind)
                continue
            count = struct.unpack("!xH", await s.read_exactly(3))[0]
            budget = [VNC_MAX_FRAMEBUFFER_BYTES]  # bytes one update may still carry
            for _ in range(count):
                await self._read_rect(canvas, budget)
            return VncFrame(self.width, self.height, bytes(canvas))

    async def _read_rect(self, canvas: bytearray, budget: list | None = None) -> None:
        s = self._stream
        x, y, w, h, enc = struct.unpack("!HHHHi", await s.read_exactly(12))
        if enc != _ENCODING_RAW:
            raise VncProtocolError(f"server sent unsupported encoding {enc}")
        if x + w > self.width or y + h > self.height:
            raise VncProtocolError("server sent a rectangle outside the screen")
        left = budget if budget is not None else [VNC_MAX_FRAMEBUFFER_BYTES]
        left[0] -= w * h * _WIRE_BYTES_PER_PIXEL
        if left[0] < 0:
            raise VncProtocolError("framebuffer exceeds the configured size cap")
        raw = await s.read_exactly(w * h * _WIRE_BYTES_PER_PIXEL)
        for row in range(h):
            line = raw[row * w * _WIRE_BYTES_PER_PIXEL : (row + 1) * w * _WIRE_BYTES_PER_PIXEL]
            start = ((y + row) * self.width + x) * 3
            # little-endian 32bpp is B, G, R, pad -> R, G, B
            canvas[start : start + w * 3 : 3] = line[2::4]
            canvas[start + 1 : start + w * 3 : 3] = line[1::4]
            canvas[start + 2 : start + w * 3 : 3] = line[0::4]


def frame_to_png(frame: VncFrame) -> bytes:
    """Encode a grabbed frame as PNG."""
    from PIL import Image

    out = io.BytesIO()
    Image.frombytes("RGB", (frame.width, frame.height), frame.rgb).save(out, format="PNG")
    return out.getvalue()


__all__ = ["VncAuthError", "VncFrame", "VncProtocolError", "VncRfbSession", "frame_to_png"]
