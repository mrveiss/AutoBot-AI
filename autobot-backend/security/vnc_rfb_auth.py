# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RFB "VNC Authentication" (security-type 2) handshake, both directions (#16299).

Lets ``api.vnc_proxy`` answer the real VNC server's password challenge
itself, and offer the browser security-type "None" -- so noVNC never sees
or needs the password, closing the leak of ``VITE_*_VNC_PASSWORD`` being
compiled into the frontend bundle.

The algorithm was verified against three independent sources before writing
this, not derived from memory alone:

- RFC 6143 section 7.2.2: password truncated to 8 bytes, or null-padded.
- LibVNCServer's ``src/common/d3des.c``: its own comment documents that the
  ``bytebit[]`` table "has been reversed" from standard DES -- confirming the
  classic VNC per-byte bit-reversal quirk is real, not a folk belief.
- ``vncdotool``'s ``vncdotool/rfb.py`` (a modern, actively maintained Python
  client using this exact same ``cryptography.hazmat.decrepit.ciphers
  .algorithms.TripleDES`` primitive): its ``reverse_bits`` was cross-checked
  byte-for-byte against ``_reverse_bits`` below across all 256 values, and
  its full password->key->response pipeline was cross-checked end-to-end
  against this module's, across 6 password shapes x 5 random challenges each
  -- all identical.

``cryptography``'s ``TripleDES(key * 3)`` (the 8-byte VNC key repeated three
times, K1=K2=K3) in ECB mode was independently verified against the
canonical FIPS DES test vector: key=133457799BBCDFF1,
plaintext=0123456789ABCDEF -> ciphertext=85E813540F0AB405, exact match.
"""

from __future__ import annotations

from typing import Protocol

from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, modes

RFB_VERSION = b"RFB 003.008\n"

SECURITY_TYPE_NONE = 1
SECURITY_TYPE_VNC_AUTH = 2


class VncAuthError(Exception):
    """The RFB handshake failed -- auth rejected, protocol mismatch, or a peer
    that doesn't speak the dialect this module expects. Never carries the
    password: every raise site here passes only protocol-level detail."""


class ByteReader(Protocol):
    async def read_exactly(self, n: int) -> bytes: ...


class ByteWriter(Protocol):
    async def write(self, data: bytes) -> None: ...


def _reverse_bits(b: int) -> int:
    """Reverse the 8 bits of one byte -- see module docstring for why."""
    b = ((b & 0xF0) >> 4) | ((b & 0x0F) << 4)
    b = ((b & 0xCC) >> 2) | ((b & 0x33) << 2)
    b = ((b & 0xAA) >> 1) | ((b & 0x55) << 1)
    return b


def vnc_des_key(password: bytes) -> bytes:
    """RFC 6143 7.2.2: truncate to 8 bytes, or pad with null bytes on the
    right. Then the classic VNC bit-reversal quirk (see module docstring)."""
    key8 = password[:8].ljust(8, b"\x00")
    return bytes(_reverse_bits(b) for b in key8)


def encrypt_challenge(password: bytes, challenge: bytes) -> bytes:
    """16-byte challenge -> 16-byte response: two independent 8-byte ECB
    blocks, same key (confirmed via noVNC's core/crypto/des.js encrypt loop)."""
    if len(challenge) != 16:
        raise ValueError(f"VNC challenge must be 16 bytes, got {len(challenge)}")
    key = vnc_des_key(password)
    encryptor = Cipher(TripleDES(key * 3), modes.ECB()).encryptor()
    return encryptor.update(challenge) + encryptor.finalize()


def _parse_version(raw: bytes) -> tuple[int, int]:
    """b"RFB 003.008\\n" -> (3, 8). Raises VncAuthError on anything else."""
    if len(raw) != 12 or not raw.startswith(b"RFB ") or not raw.endswith(b"\n"):
        raise VncAuthError(f"not an RFB ProtocolVersion message: {raw!r}")
    try:
        major = int(raw[4:7])
        minor = int(raw[8:11])
    except ValueError as exc:
        raise VncAuthError(f"malformed RFB version numbers: {raw!r}") from exc
    return major, minor


async def authenticate_as_client(reader: ByteReader, writer: ByteWriter, password: bytes) -> None:
    """Perform the RFB client-side handshake against the REAL VNC server.

    Requires the server to offer VNC Authentication (security type 2) --
    refuses to proceed with "None" or any other type, since silently
    accepting an unauthenticated upstream would make this proxy the thing
    that turns a misconfigured backend into an unauthenticated frontend.
    Raises VncAuthError on any failure; never logs or includes `password` in
    an exception message.

    After this returns successfully, the byte stream is positioned exactly
    at the start of ClientInit -- everything from here on is opaque
    framebuffer protocol this function never inspects.
    """
    server_version_raw = await reader.read_exactly(12)
    major, minor = _parse_version(server_version_raw)
    if major != 3:
        raise VncAuthError(f"unsupported RFB major version from server: {major}")
    await writer.write(RFB_VERSION)

    if minor < 7:
        # RFB 3.3: server dictates a single 4-byte security-type value, no
        # negotiation list. Rare for a modern deployment; refuse cleanly
        # rather than guess at 3.3's different security-type encoding.
        raise VncAuthError(f"RFB 3.{minor} security handshake (pre-3.7) is not supported")

    count_raw = await reader.read_exactly(1)
    count = count_raw[0]
    if count == 0:
        # RFB 3.7+: a zero count is followed by a reason string, then close.
        reason_len_raw = await reader.read_exactly(4)
        reason_len = int.from_bytes(reason_len_raw, "big")
        reason = await reader.read_exactly(reason_len) if reason_len else b""
        raise VncAuthError(f"server offered no security types: {reason!r}")
    types = await reader.read_exactly(count)
    if SECURITY_TYPE_VNC_AUTH not in types:
        raise VncAuthError(f"server does not offer VNC Authentication (offered types: {list(types)})")

    await writer.write(bytes([SECURITY_TYPE_VNC_AUTH]))

    challenge = await reader.read_exactly(16)
    response = encrypt_challenge(password, challenge)
    await writer.write(response)

    result_raw = await reader.read_exactly(4)
    result = int.from_bytes(result_raw, "big")
    if result != 0:
        if minor >= 8:
            reason_len_raw = await reader.read_exactly(4)
            reason_len = int.from_bytes(reason_len_raw, "big")
            reason = await reader.read_exactly(reason_len) if reason_len else b""
            raise VncAuthError(f"VNC authentication rejected by server: {reason!r}")
        raise VncAuthError("VNC authentication rejected by server")


async def offer_no_auth_as_server(reader: ByteReader, writer: ByteWriter) -> None:
    """Perform the RFB server-side handshake toward the BROWSER, offering only
    security type "None" -- noVNC never sees or needs a password, because by
    the time this runs the real server-side auth (authenticate_as_client,
    above) has already succeeded on the other leg. Raises VncAuthError if the
    browser doesn't speak RFB 3.7+ or doesn't select type None.
    """
    await writer.write(RFB_VERSION)
    client_version_raw = await reader.read_exactly(12)
    major, minor = _parse_version(client_version_raw)
    # #16299 review: security-type None's SecurityResult is version-gated by
    # RFC 6143 Appendix A -- RFB 3.8 sends one, 3.3/3.7 do not. The
    # unconditional send below is only correct for a negotiated 3.8 session,
    # so require exactly that rather than tracking two behaviors for a
    # pre-3.8 client this proxy has no real reason to support: noVNC (the
    # only browser client this proxy ever talks to) has spoken 3.8 since
    # well before this project existed.
    if major != 3 or minor != 8:
        raise VncAuthError(f"client offered unsupported RFB version: {major}.{minor} (only 3.8 is supported)")

    await writer.write(bytes([1, SECURITY_TYPE_NONE]))  # count=1, type=None
    chosen_raw = await reader.read_exactly(1)
    if chosen_raw[0] != SECURITY_TYPE_NONE:
        raise VncAuthError(f"client selected unexpected security type: {chosen_raw[0]}")

    # RFB 3.8 (RFC 6143 7.2.1): even security-type None sends a SecurityResult.
    # Safe unconditionally here since the version check above already requires 3.8.
    await writer.write((0).to_bytes(4, "big"))
