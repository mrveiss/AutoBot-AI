# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The issue-claims CLI over a mock HTTP transport and a fake kernel keyring (#18811).

The keyring is the real ``KernelKeyring`` over an in-memory fake ``syscall``, so every test also
runs the wrapper's argument marshalling; no real keyring is touched. File writes are trapped:
``no_file_writes`` fails the test on any ``open`` for writing.
"""

from __future__ import annotations

import builtins
import ctypes
import errno
import io
import os
from types import SimpleNamespace

import httpx
import pytest

from autobot_shared.coordination import issue_claims_api
from autobot_shared.coordination.kernel_keyring import (
    KEY_SPEC_USER_KEYRING,
    KEY_TYPE_USER,
    KEYCTL_READ,
    KEYCTL_SEARCH,
    KEYCTL_SETPERM,
    KEYCTL_UNLINK,
    KernelKeyring,
)
from autobot_shared.egress_allowlist import reset_internal_origin_state

URL = "https://claims.test:8443"  # noqa: hardcoded -- a test fixture URL, never dialled
CREDENTIAL = "5b7c1f3e-0000-4000-8000-00000000abcd.verifier-SECRET-0123456789abcdef"
ADD_KEY, KEYCTL = 248, 250


class FakeSyscall:
    """``add_key`` / ``keyctl`` over a dict; records every call as ``(number, args)``."""

    def __init__(self) -> None:
        self.keys: dict[bytes, tuple[int, bytes]] = {}
        self.perms: dict[int, int] = {}
        self.calls: list[tuple[int, tuple]] = []
        self._serial = 100

    def __call__(self, number: int, *args):
        self.calls.append((number, args))
        if number == ADD_KEY:
            return self._add(*args)
        return self._keyctl(*args)

    def _add(self, key_type, description, payload, length, keyring):
        assert (key_type, keyring, length) == (KEY_TYPE_USER, KEY_SPEC_USER_KEYRING, len(payload))
        self._serial += 1
        self.keys[description] = (self._serial, bytes(payload))
        return self._serial, 0

    def _by_serial(self, serial):
        return next(((d, p) for d, (s, p) in self.keys.items() if s == serial), (None, None))

    def _keyctl(self, op, *args):
        if op == KEYCTL_SEARCH:
            found = self.keys.get(args[2])
            return (found[0], 0) if found else (-1, errno.ENOKEY)
        description, payload = self._by_serial(args[0])
        if description is None:
            return -1, errno.ENOKEY
        if op == KEYCTL_SETPERM:
            self.perms[args[0]] = args[1]
            return 0, 0
        if op == KEYCTL_READ:
            if args[1] is not None:
                ctypes.memmove(args[1], payload, min(args[2], len(payload)))
            return len(payload), 0
        assert op == KEYCTL_UNLINK and args[1] == KEY_SPEC_USER_KEYRING
        del self.keys[description]
        return 0, 0


@pytest.fixture
def no_file_writes(monkeypatch):
    """Fail on any ``open`` for writing, by any of the three doors a write can take."""
    attempts: list = []
    real_open, real_io_open, real_os_open = builtins.open, io.open, os.open

    def _guard(opener, write_check):
        def _open(file, *args, **kwargs):
            if write_check(args, kwargs):
                attempts.append(file)
                raise AssertionError(f"file opened for writing: {file!r}")
            return opener(file, *args, **kwargs)

        return _open

    def _text_write(args, kwargs):
        mode = args[0] if args else kwargs.get("mode", "r")
        return any(c in str(mode) for c in "wax+")

    def _os_write(args, kwargs):
        flags = args[0] if args else kwargs.get("flags", os.O_RDONLY)
        return bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND))

    monkeypatch.setattr(builtins, "open", _guard(real_open, _text_write))
    monkeypatch.setattr(io, "open", _guard(real_io_open, _text_write))
    monkeypatch.setattr(os, "open", _guard(real_os_open, _os_write))
    return attempts


@pytest.fixture
def cli(monkeypatch):
    """``state.handler`` answers requests; ``seen`` holds them; ``sys`` is the fake keyring syscall."""
    monkeypatch.setenv(issue_claims_api.API_URL_ENV, URL)
    fake = FakeSyscall()
    monkeypatch.setattr(issue_claims_api, "keyring", lambda: KernelKeyring(syscall=fake, machine="x86_64"))
    state = SimpleNamespace(handler=lambda req: httpx.Response(200, json={"held": False}), seen=[], sys=fake)

    def _client(headers: dict) -> httpx.AsyncClient:
        def handler(req: httpx.Request) -> httpx.Response:
            state.seen.append(req)
            return state.handler(req)

        return httpx.AsyncClient(headers=headers, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(issue_claims_api, "client", _client)
    yield state
    reset_internal_origin_state()


def store(state, credential: str = CREDENTIAL, url: str = URL) -> None:
    """Put *credential* in the fake keyring the way ``login`` would."""
    KernelKeyring(syscall=state.sys, machine="x86_64").add(
        issue_claims_api.keyring_description(url), credential.encode("utf-8")
    )
