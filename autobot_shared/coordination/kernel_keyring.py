# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Linux kernel USER keyring (``@u``) through raw ``add_key`` / ``keyctl`` syscalls (#18811).

The issue-claims CLI keeps its credential here and nowhere else: never a file, never an
environment value. ``keyctl(1)`` and the Python ``keyring`` package are not installed and must
not be, so this calls ``libc.syscall`` through ``ctypes``.

* Key type ``"user"``, keyring ``KEY_SPEC_USER_KEYRING`` (``-4``): per-uid, readable only by
  processes of the same user, held in kernel memory, gone on reboot.
* ``add_key`` replaces the payload of an existing key with the same description, so a re-login
  overwrites rather than duplicates.
* The key's permissions are then set explicitly (``KEYCTL_SETPERM``) to :data:`CREDENTIAL_KEY_PERM`
  rather than left to the kernel default: the possessor may view, read, write, search and set
  attributes; the owning uid without possession may only view and read; group and other get
  nothing. A failure to set them unlinks the key and raises, so a key with default permissions is not kept.
* The syscall function is injectable: tests pass a fake and never touch a real keyring.
"""

from __future__ import annotations

import ctypes
import errno
import os
import platform
import sys
from typing import Any, Callable

KEY_SPEC_USER_KEYRING = -4
KEY_TYPE_USER = b"user"
KEYCTL_SETPERM, KEYCTL_UNLINK, KEYCTL_SEARCH, KEYCTL_READ = 5, 9, 10, 11

# Permission bits from the kernel's ``include/uapi/linux/keyctl.h`` (``key_perm_t``).
KEY_POS_VIEW, KEY_POS_READ, KEY_POS_WRITE = 0x01000000, 0x02000000, 0x04000000
KEY_POS_SEARCH, KEY_POS_SETATTR = 0x08000000, 0x20000000
KEY_USR_VIEW, KEY_USR_READ = 0x00010000, 0x00020000

#: Possessor view/read/write/search/setattr, user view/read, group and other none (``0x2f030000``).
CREDENTIAL_KEY_PERM = (
    KEY_POS_VIEW | KEY_POS_READ | KEY_POS_WRITE | KEY_POS_SEARCH | KEY_POS_SETATTR | KEY_USR_VIEW | KEY_USR_READ
)

#: ``(add_key, keyctl)`` syscall numbers per machine; anything else is "unavailable".
SYSCALL_NUMBERS = {"x86_64": (248, 250), "amd64": (248, 250), "aarch64": (217, 219), "arm64": (217, 219)}

#: "No such key" in all three of its forms: absent, expired, revoked.
_MISSING = {errno.ENOKEY, errno.EKEYEXPIRED, errno.EKEYREVOKED}

#: ``syscall(number, *args) -> (result, errno)``; args are ints, bytes, a buffer or ``None``.
SyscallFn = Callable[..., tuple[int, int]]


class KeyringUnavailable(OSError):
    """The kernel keyring cannot be used here (not Linux, unknown arch, or the syscall is blocked)."""


class KeyNotFound(LookupError):
    """No live key with this description in the user keyring."""


def _ctypes_arg(value: Any) -> Any:
    """Variadic ``syscall`` needs every integer as a full ``long``, every string as a pointer."""
    if isinstance(value, int):
        return ctypes.c_long(value)
    if value is None:
        return ctypes.c_void_p(None)
    return value


def libc_syscall() -> SyscallFn:
    """The real ``libc.syscall``, returning ``(result, errno)``."""
    fn = ctypes.CDLL(None, use_errno=True).syscall
    fn.restype = ctypes.c_long

    def call(number: int, *args: Any) -> tuple[int, int]:
        ctypes.set_errno(0)
        result = fn(ctypes.c_long(number), *(_ctypes_arg(a) for a in args))
        return int(result), ctypes.get_errno()

    return call


class KernelKeyring:
    """``add`` / ``read`` / ``unlink`` a ``user`` key in ``@u`` by description."""

    def __init__(self, syscall: SyscallFn | None = None, machine: str | None = None) -> None:
        self._syscall = syscall
        self._numbers = SYSCALL_NUMBERS.get((machine or platform.machine()).lower())

    def _call(self, which: int, *args: Any) -> int:
        if self._numbers is None or (self._syscall is None and not sys.platform.startswith("linux")):
            raise KeyringUnavailable(errno.ENOSYS, "the Linux kernel keyring is not available on this system")
        syscall = self._syscall or libc_syscall()
        result, err = syscall(self._numbers[which], *args)
        if result >= 0:
            return result
        if err in _MISSING:
            raise KeyNotFound("no such key in the user keyring")
        raise KeyringUnavailable(err, os.strerror(err) if err else "keyring syscall failed")

    def add(self, description: str, payload: bytes) -> int:
        """Store *payload* under *description* in ``@u`` with :data:`CREDENTIAL_KEY_PERM`; returns the serial.

        A refused ``KEYCTL_SETPERM`` unlinks the key it was meant to restrict, then raises.
        """
        serial = self._call(0, KEY_TYPE_USER, description.encode("utf-8"), payload, len(payload), KEY_SPEC_USER_KEYRING)
        try:
            self._call(1, KEYCTL_SETPERM, serial, CREDENTIAL_KEY_PERM)
        except (KeyringUnavailable, KeyNotFound):
            # An unlink failure here propagates too, chained to the SETPERM failure; neither is dropped.
            self._call(1, KEYCTL_UNLINK, serial, KEY_SPEC_USER_KEYRING)
            raise
        return serial

    def _search(self, description: str) -> int:
        return self._call(1, KEYCTL_SEARCH, KEY_SPEC_USER_KEYRING, KEY_TYPE_USER, description.encode("utf-8"), 0)

    def read(self, description: str) -> bytes:
        """The payload stored under *description*; raises :class:`KeyNotFound` when there is none."""
        serial = self._search(description)
        size = self._call(1, KEYCTL_READ, serial, None, 0)
        buffer = ctypes.create_string_buffer(max(size, 1))
        length = self._call(1, KEYCTL_READ, serial, buffer, size)
        return buffer.raw[: min(length, size)]

    def unlink(self, description: str) -> None:
        """Remove the key under *description* from ``@u``; raises :class:`KeyNotFound` when there is none."""
        self._call(1, KEYCTL_UNLINK, self._search(description), KEY_SPEC_USER_KEYRING)
