# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ctypes kernel-keyring wrapper (#18811): the syscalls it makes, and how it fails."""

from __future__ import annotations

import errno
import sys
import uuid

import pytest

from autobot_shared.coordination.kernel_keyring import (
    CREDENTIAL_KEY_PERM,
    KEY_SPEC_USER_KEYRING,
    KEYCTL_READ,
    KEYCTL_SEARCH,
    KEYCTL_SETPERM,
    KEYCTL_UNLINK,
    KernelKeyring,
    KeyNotFound,
    KeyringUnavailable,
    libc_syscall,
)
from tests.coordination._issue_claims_cli_harness import ADD_KEY, KEYCTL, FakeSyscall

DESC = "autobot:issue-claims:https://claims.test:443"


def test_add_is_add_key_of_type_user_into_the_user_keyring():
    fake = FakeSyscall()
    serial = KernelKeyring(syscall=fake, machine="x86_64").add(DESC, b"payload")
    assert fake.calls[0] == (ADD_KEY, (b"user", DESC.encode(), b"payload", 7, -4)) and serial > 0
    assert KEY_SPEC_USER_KEYRING == -4


def test_add_sets_the_permissions_explicitly_with_keyctl_setperm():
    fake = FakeSyscall()
    serial = KernelKeyring(syscall=fake, machine="x86_64").add(DESC, b"payload")
    assert KEYCTL_SETPERM == 5
    # possessor view|read|write|search|setattr = 0x2f000000; user view|read = 0x00030000; group, other 0.
    assert CREDENTIAL_KEY_PERM == 0x2F030000
    assert fake.calls[1] == (KEYCTL, (5, serial, 0x2F030000)) and len(fake.calls) == 2
    assert fake.perms == {serial: 0x2F030000}


@pytest.mark.parametrize("err", [errno.EPERM, errno.EACCES])
def test_a_refused_setperm_unlinks_the_key_and_raises(err):
    fake = FakeSyscall()

    def syscall(number, *args):
        if number == KEYCTL and args[0] == KEYCTL_SETPERM:
            fake.calls.append((number, args))
            return -1, err
        return fake(number, *args)

    with pytest.raises(KeyringUnavailable):
        KernelKeyring(syscall=syscall, machine="x86_64").add(DESC, b"payload")
    assert fake.calls[-1][1][0] == KEYCTL_UNLINK and not fake.keys


def test_read_searches_the_user_keyring_then_reads():
    fake = FakeSyscall()
    ring = KernelKeyring(syscall=fake, machine="x86_64")
    serial = ring.add(DESC, b"payload")
    fake.calls.clear()
    assert ring.read(DESC) == b"payload"
    search, size, read = fake.calls
    assert search == (KEYCTL, (KEYCTL_SEARCH, -4, b"user", DESC.encode(), 0))
    assert size == (KEYCTL, (KEYCTL_READ, serial, None, 0)) and read[1][:1] == (KEYCTL_READ,)


def test_unlink_removes_it_from_the_user_keyring():
    fake = FakeSyscall()
    ring = KernelKeyring(syscall=fake, machine="x86_64")
    serial = ring.add(DESC, b"payload")
    ring.unlink(DESC)
    assert fake.calls[-1] == (KEYCTL, (KEYCTL_UNLINK, serial, -4)) and not fake.keys


def test_aarch64_uses_its_own_syscall_numbers():
    fake = FakeSyscall()
    calls = []
    KernelKeyring(syscall=lambda n, *a: calls.append(n) or (1, 0), machine="aarch64").add(DESC, b"x")
    assert calls == [217, 219] and fake.calls == []


@pytest.mark.parametrize("err", [errno.ENOKEY, errno.EKEYEXPIRED, errno.EKEYREVOKED])
def test_a_missing_expired_or_revoked_key_is_key_not_found(err):
    with pytest.raises(KeyNotFound):
        KernelKeyring(syscall=lambda n, *a: (-1, err), machine="x86_64").read(DESC)


@pytest.mark.parametrize("err", [errno.EPERM, errno.ENOSYS, errno.EACCES])
def test_a_blocked_syscall_is_keyring_unavailable(err):
    with pytest.raises(KeyringUnavailable):
        KernelKeyring(syscall=lambda n, *a: (-1, err), machine="x86_64").read(DESC)


def test_an_unknown_architecture_is_keyring_unavailable():
    with pytest.raises(KeyringUnavailable):
        KernelKeyring(syscall=lambda n, *a: (1, 0), machine="sparc64").add(DESC, b"x")


def _real_keyring_usable() -> bool:
    """A full add/unlink round trip: a sandbox can allow the read lookup yet deny add (EACCES)."""
    if not sys.platform.startswith("linux"):
        return False
    ring, desc = KernelKeyring(), f"autobot:probe:{uuid.uuid4()}"
    try:
        ring.add(desc, b"probe")
        ring.unlink(desc)
    except (KeyringUnavailable, KeyNotFound, OSError):
        return False
    return True


@pytest.mark.skipif(not _real_keyring_usable(), reason="the kernel keyring syscalls are unavailable here")
def test_the_real_user_keyring_round_trips():
    ring, desc = KernelKeyring(syscall=libc_syscall()), f"autobot:test:{uuid.uuid4()}"
    ring.add(desc, b"round-trip")
    try:
        assert ring.read(desc) == b"round-trip"
    finally:
        ring.unlink(desc)
    with pytest.raises(KeyNotFound):
        ring.read(desc)
