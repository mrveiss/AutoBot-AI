# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Single-descriptor readiness polling without the ``select()`` FD_SETSIZE ceiling.

``select.select()`` is bound by the C library's ``FD_SETSIZE`` constant (1024 on
Linux) regardless of ``RLIMIT_NOFILE``, and CPython raises
``ValueError: filedescriptor out of range in select()`` for any descriptor at or
above it. A long-lived single-process backend crosses 1024 open descriptors in
normal operation (sockets, connection pools, HTTP clients, PTYs), after which
every newly created descriptor lands above the ceiling and the failure is
permanent for the life of the process (#13219).

``select.poll()`` has no such ceiling and — unlike ``select.epoll()`` — consumes
no descriptor of its own, which matters precisely in the situation where
descriptors are already plentiful.

POSIX only: ``select.poll`` is unavailable on Windows, as is the ``pty`` module
this helper exists to serve.
"""

import errno
import select

# POLLIN (data to read) and POLLPRI (out-of-band data) are the conditions we ask
# for. POLLHUP, POLLERR and POLLNVAL are reported by poll() whether requested or
# not, so they are deliberately absent from the requested mask.
_READ_EVENTS = select.POLLIN | select.POLLPRI


def poll_readable(fd: int, timeout_ms: int) -> bool:
    """Return True when ``fd`` is ready for an ``os.read()`` call.

    Behavioural drop-in for ``bool(select.select([fd], [], [], t)[0])``, with the
    timeout expressed in **milliseconds** (as ``select.poll().poll()`` requires)
    rather than seconds: ``0`` polls without blocking, a positive value waits at
    most that many milliseconds, a negative value blocks indefinitely.

    Hangup (``POLLHUP``) and error (``POLLERR``) count as ready, mirroring how
    ``select()`` reports an at-EOF descriptor as readable. The caller's existing
    ``os.read()`` therefore still observes EOF or ``EIO`` and terminates its loop
    instead of spinning on an undrained hangup.

    Args:
        fd: Open file descriptor to test for readability.
        timeout_ms: Wait budget in milliseconds (0 = non-blocking poll).

    Returns:
        True if a read should be attempted, False if the timeout expired first.

    Raises:
        OSError: ``EBADF`` when the descriptor is not open (``POLLNVAL``), which
            is what ``select.select()`` raises for a closed descriptor.
    """
    poller = select.poll()
    poller.register(fd, _READ_EVENTS)
    events = poller.poll(timeout_ms)
    if not events:
        return False

    _, revents = events[0]
    if revents & select.POLLNVAL:
        raise OSError(errno.EBADF, f"Bad file descriptor: {fd}")
    return True


def seconds_to_poll_timeout_ms(timeout_seconds: float) -> int:
    """Convert a ``select()``-style seconds timeout to ``poll()`` milliseconds.

    Rounds up so a sub-millisecond budget never collapses to 0 (a busy-spin);
    an exact 0 stays 0 (a non-blocking poll, as ``select()`` treats it).

    Args:
        timeout_seconds: Non-negative timeout in seconds.

    Returns:
        Equivalent timeout in whole milliseconds.
    """
    if timeout_seconds <= 0:
        return 0
    return max(1, int(timeout_seconds * 1000 + 0.5))
