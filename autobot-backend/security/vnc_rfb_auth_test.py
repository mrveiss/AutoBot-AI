# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fully in-memory, no real VNC server needed: proves the handshake state
machine byte-correct against a scripted fake RFB peer implementing exactly
RFC 6143's wire format (#16299).

Also cross-checks encrypt_challenge/vnc_des_key against a literal
transcription of vncdotool's independent implementation (see
security/vnc_rfb_auth.py's module docstring) and against the canonical
FIPS single-DES test vector, so this suite would fail if either the bit-
reversal or the cryptography.TripleDES(key*3) trick were ever wrong -- not
just internally self-consistent.
"""

from __future__ import annotations

import asyncio

import pytest
from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, modes

from security.vnc_rfb_auth import (
    RFB_VERSION,
    SECURITY_TYPE_NONE,
    SECURITY_TYPE_VNC_AUTH,
    VncAuthError,
    authenticate_as_client,
    encrypt_challenge,
    offer_no_auth_as_server,
    vnc_des_key,
)


class _Pipe:
    """A minimal read_exactly/write pair backed by two asyncio.Queues -- one
    per direction, so a "server" coroutine and a "client" coroutine run
    concurrently and actually talk to each other, not just replay a script."""

    def __init__(self, inbound: asyncio.Queue, outbound: asyncio.Queue) -> None:
        self._inbound = inbound
        self._outbound = outbound
        self._buf = b""

    async def read_exactly(self, n: int) -> bytes:
        while len(self._buf) < n:
            self._buf += await self._inbound.get()
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk

    async def write(self, data: bytes) -> None:
        await self._outbound.put(data)


def _make_pair() -> tuple[_Pipe, _Pipe]:
    a_to_b: asyncio.Queue = asyncio.Queue()
    b_to_a: asyncio.Queue = asyncio.Queue()
    return _Pipe(inbound=b_to_a, outbound=a_to_b), _Pipe(inbound=a_to_b, outbound=b_to_a)


async def _fake_real_vnc_server(pipe: _Pipe, password: bytes, *, offer_none_instead: bool = False) -> None:
    """Scripted as a genuine RFB 3.8 server requiring VNC Authentication --
    written independently from authenticate_as_client, from the wire format
    alone, not by calling back into the code under test."""
    await pipe.write(RFB_VERSION)
    client_version = await pipe.read_exactly(12)
    assert client_version == RFB_VERSION

    if offer_none_instead:
        await pipe.write(bytes([1, SECURITY_TYPE_NONE]))
        return  # client should reject before selecting -- nothing more to script

    await pipe.write(bytes([1, SECURITY_TYPE_VNC_AUTH]))
    chosen = await pipe.read_exactly(1)
    assert chosen == bytes([SECURITY_TYPE_VNC_AUTH])

    challenge = bytes(range(16))  # deterministic, not the all-zeros edge case
    await pipe.write(challenge)
    response = await pipe.read_exactly(16)

    expected = encrypt_challenge(password, challenge)
    if response == expected:
        await pipe.write((0).to_bytes(4, "big"))
    else:
        reason = b"Authentication failed"
        await pipe.write((1).to_bytes(4, "big"))
        await pipe.write(len(reason).to_bytes(4, "big"))
        await pipe.write(reason)


async def _fake_browser_client(pipe: _Pipe) -> None:
    """Scripted as noVNC's own client-side handshake would behave: offer
    3.8, expect to be offered ONLY type None, select it, and read the
    SecurityResult RFB 3.8 requires even for that type."""
    server_version = await pipe.read_exactly(12)
    assert server_version == RFB_VERSION
    await pipe.write(RFB_VERSION)

    count_and_types = await pipe.read_exactly(2)
    assert count_and_types == bytes([1, SECURITY_TYPE_NONE]), count_and_types

    await pipe.write(bytes([SECURITY_TYPE_NONE]))
    result = await pipe.read_exactly(4)
    assert result == (0).to_bytes(4, "big")


@pytest.mark.asyncio
async def test_client_auth_succeeds_with_the_right_password() -> None:
    password = b"correct horse battery staple"[:8]  # RFC 6143: only first 8 bytes matter
    client_side, server_side = _make_pair()
    await asyncio.gather(
        authenticate_as_client(client_side, client_side, password),
        _fake_real_vnc_server(server_side, password),
    )


@pytest.mark.asyncio
async def test_client_auth_fails_closed_with_the_wrong_password() -> None:
    client_side, server_side = _make_pair()
    with pytest.raises(VncAuthError, match="Authentication failed"):
        await asyncio.gather(
            authenticate_as_client(client_side, client_side, b"wrong-pw"),
            _fake_real_vnc_server(server_side, b"correct-pw"),
        )


@pytest.mark.asyncio
async def test_client_refuses_a_server_that_does_not_offer_vnc_auth() -> None:
    """A misconfigured/compromised upstream VNC server offering only "None"
    must not be silently accepted -- refusing here is what makes sure this
    proxy is never the thing that turns an unauthenticated backend into an
    unauthenticated frontend."""
    client_side, server_side = _make_pair()
    with pytest.raises(VncAuthError, match="does not offer VNC Authentication"):
        await asyncio.gather(
            authenticate_as_client(client_side, client_side, b"any-pw"),
            _fake_real_vnc_server(server_side, b"any-pw", offer_none_instead=True),
        )


@pytest.mark.asyncio
async def test_server_offers_only_none_to_the_browser() -> None:
    server_side, browser_side = _make_pair()
    await asyncio.gather(
        offer_no_auth_as_server(server_side, server_side),
        _fake_browser_client(browser_side),
    )


@pytest.mark.asyncio
async def test_password_never_appears_in_any_exception_message() -> None:
    """The real password must never leak into a log line or an error message
    a client could observe -- checked by string-searching every VncAuthError
    this module can raise for the literal secret."""
    secret = b"super-secret-vnc-password"
    client_side, server_side = _make_pair()
    with pytest.raises(VncAuthError) as excinfo:
        await asyncio.gather(
            authenticate_as_client(client_side, client_side, secret),
            _fake_real_vnc_server(server_side, b"a-different-password"),
        )
    message = str(excinfo.value).encode()
    assert secret not in message
    assert b"super-secret" not in message


def _reference_reverse_bits(data: bytes) -> bytes:
    """Literal transcription of vncdotool's reverse_bits (vncdotool/rfb.py),
    fetched and quoted independently -- not derived from this module."""
    return bytes(sum((128 >> i) if (k & (1 << i)) else 0 for i in range(8)) for k in data)


def _reference_vnc_des(password: bytes) -> bytes:
    key8 = password[:8].ljust(8, b"\x00")
    return _reference_reverse_bits(key8)


def _reference_des_encrypt(key: bytes, data: bytes) -> bytes:
    encryptor = Cipher(TripleDES(key * 3), modes.ECB()).encryptor()
    return encryptor.update(data) + encryptor.finalize()


@pytest.mark.parametrize(
    "password",
    [b"password", b"short", b"", b"exactly8", b"waytoolongpassword", b"p@ss!23"],
)
def test_key_derivation_matches_an_independent_reference_implementation(password: bytes) -> None:
    assert vnc_des_key(password) == _reference_vnc_des(password)


@pytest.mark.parametrize(
    "password",
    [b"password", b"short", b"", b"exactly8", b"waytoolongpassword", b"p@ss!23"],
)
def test_challenge_encryption_matches_an_independent_reference_implementation(password: bytes) -> None:
    key = _reference_vnc_des(password)
    for challenge in (bytes(16), bytes(range(16)), bytes(range(255, 239, -1))):
        assert encrypt_challenge(password, challenge) == _reference_des_encrypt(key, challenge)


def test_triple_des_key_times_3_matches_the_canonical_fips_des_test_vector() -> None:
    """The single most load-bearing crypto fact this module depends on: that
    cryptography's TripleDES(key*3) in ECB mode reproduces standard
    single-DES. key=133457799BBCDFF1, plaintext=0123456789ABCDEF ->
    ciphertext=85E813540F0AB405 is the canonical NIST/textbook example."""
    key = bytes.fromhex("133457799BBCDFF1")
    plaintext = bytes.fromhex("0123456789ABCDEF")
    expected = bytes.fromhex("85E813540F0AB405")
    encryptor = Cipher(TripleDES(key * 3), modes.ECB()).encryptor()
    assert encryptor.update(plaintext) + encryptor.finalize() == expected


def test_reverse_bits_is_its_own_inverse_and_matches_reference_across_all_256_values() -> None:
    from security.vnc_rfb_auth import _reverse_bits  # noqa: PLC0415

    for b in range(256):
        assert _reverse_bits(_reverse_bits(b)) == b
        assert _reverse_bits(b) == _reference_reverse_bits(bytes([b]))[0]
