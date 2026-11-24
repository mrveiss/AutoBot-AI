# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for autobot_shared.fd_poll (#13219).

The point of the module is that it keeps working for descriptors at or above
``FD_SETSIZE`` (1024), where ``select.select()`` raises
``ValueError: filedescriptor out of range in select()``. Every readiness test
below is therefore also asserted against ``select.select()`` on the same
descriptor, so the suite proves the ceiling is really gone instead of merely
exercising a low descriptor where ``select()`` would have worked anyway.
"""

import errno
import os
import pty
import select
import time

import pytest

from autobot_shared.fd_poll import poll_readable, seconds_to_poll_timeout_ms
from autobot_shared.fd_testing import FD_SETSIZE, pty_above_fd_setsize

# First descriptor number we try to relocate a PTY to; comfortably past the ceiling.
_HIGH_FD_BASE = FD_SETSIZE + 76


def _select_rejects(fd: int) -> bool:
    """True when ``select.select()`` cannot handle ``fd`` (the bug being fixed)."""
    try:
        select.select([fd], [], [], 0)
    except ValueError:
        return True
    return False


class TestSecondsToPollTimeoutMs:
    """The seconds -> milliseconds translation the call sites depend on."""

    def test_translates_the_pty_read_loop_interval(self):
        # The PTY read loop waited select.select(..., 0.01) == 10 ms.
        assert seconds_to_poll_timeout_ms(0.01) == 10

    def test_zero_stays_a_non_blocking_poll(self):
        # select.select(..., 0) is a non-blocking probe; poll(0) is the same.
        assert seconds_to_poll_timeout_ms(0) == 0

    def test_sub_millisecond_budget_never_collapses_to_zero(self):
        # Rounding 0.0001 s down to 0 ms would turn a wait into a busy-spin.
        assert seconds_to_poll_timeout_ms(0.0001) == 1

    @pytest.mark.parametrize(
        ("seconds", "expected_ms"),
        [(0.02, 20), (0.1, 100), (0.5, 500), (1.0, 1000), (30, 30000)],
    )
    def test_common_timeouts(self, seconds, expected_ms):
        assert seconds_to_poll_timeout_ms(seconds) == expected_ms


class TestPollReadableAboveFdSetsize:
    """The regression: readiness checks must survive descriptors >= 1024."""

    def test_reports_pending_data_where_select_raises(self):
        with pty_above_fd_setsize(_HIGH_FD_BASE) as (master_fd, slave_fd):
            assert master_fd >= FD_SETSIZE
            # Guard against a vacuous pass: select() must genuinely fail here.
            assert _select_rejects(master_fd), "descriptor is below FD_SETSIZE — test proves nothing"

            os.write(slave_fd, b"hello-from-high-fd\n")
            assert poll_readable(master_fd, 0) is True
            assert b"hello-from-high-fd" in os.read(master_fd, 4096)

    def test_reports_idle_descriptor_as_not_ready(self):
        with pty_above_fd_setsize(_HIGH_FD_BASE) as (master_fd, _slave_fd):
            assert _select_rejects(master_fd)
            assert poll_readable(master_fd, 0) is False

    def test_honours_the_millisecond_timeout(self):
        with pty_above_fd_setsize(_HIGH_FD_BASE) as (master_fd, _slave_fd):
            started = time.monotonic()
            assert poll_readable(master_fd, 50) is False
            elapsed = time.monotonic() - started
            # Waited roughly the requested 50 ms: not an instant spin, and not
            # the 50 *seconds* a seconds/milliseconds mix-up would produce.
            assert 0.02 <= elapsed < 5.0


class TestPollReadableEventMask:
    """POLLHUP / POLLERR / POLLNVAL handling — events poll() reports unasked."""

    def test_hangup_is_ready_so_the_reader_terminates(self):
        with pty_above_fd_setsize(_HIGH_FD_BASE) as (master_fd, slave_fd):
            os.write(slave_fd, b"line one\n")
            os.close(slave_fd)

            # A read loop must drain the buffer and then end, never spin on the
            # hangup. Two iterations suffice: one data read, one EIO.
            collected = []
            ended = False
            for _ in range(50):
                if not poll_readable(master_fd, 10):
                    continue
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError as exc:
                    assert exc.errno == errno.EIO
                    ended = True
                    break
                if not chunk:
                    ended = True
                    break
                collected.append(chunk)

            assert ended, "read loop spun on POLLHUP instead of terminating"
            assert b"line one" in b"".join(collected)

    def test_closed_descriptor_raises_ebadf_like_select(self):
        master, slave = pty.openpty()
        os.close(master)
        os.close(slave)

        with pytest.raises(OSError) as excinfo:
            poll_readable(master, 0)
        assert excinfo.value.errno == errno.EBADF

        # select() reports the same errno for a closed descriptor, so callers
        # that already handle OSError keep behaving identically.
        with pytest.raises(OSError) as select_excinfo:
            select.select([master], [], [], 0)
        assert select_excinfo.value.errno == errno.EBADF


class TestPollReadableLowFdParity:
    """Behaviour below the ceiling is unchanged from select()."""

    def test_matches_select_for_a_low_descriptor(self):
        master, slave = pty.openpty()
        try:
            if master >= FD_SETSIZE:
                pytest.skip("process already holds >= FD_SETSIZE descriptors; select() parity is untestable")
            assert poll_readable(master, 0) is False
            assert not select.select([master], [], [], 0)[0]

            os.write(slave, b"x\n")
            assert poll_readable(master, 10) is True
            assert select.select([master], [], [], 0.01)[0] == [master]
        finally:
            os.close(master)
            os.close(slave)
