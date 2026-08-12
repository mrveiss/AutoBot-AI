# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Regression tests for #13219 — PTY read loops must not be capped at FD_SETSIZE.

``select.select()`` cannot address a descriptor at or above ``FD_SETSIZE``
(1024 on Linux) no matter how high ``RLIMIT_NOFILE`` is, so once the long-lived
single-process backend crosses 1024 open descriptors every new PTY made the read
loop die with ``ValueError: filedescriptor out of range in select()`` — and the
failure was permanent for the life of the process.

Two layers of coverage:

1. A behavioural test that drives ``SimplePTY._read_loop`` against a PTY whose
   master descriptor is deliberately relocated above the ceiling. It fails on
   the pre-fix code, where the loop raises on the first ``select.select()`` call
   and emits ``close`` instead of the terminal output.
2. Source-level assertions that neither PTY readiness path reintroduces
   ``select.select()``. These fail deterministically against the old code even
   in an environment that cannot allocate a high descriptor.
"""

import ast
import fcntl
import os
import pty
import queue
import resource
import select
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from services.simple_pty import SimplePTY

# FD_SETSIZE on Linux: the ceiling select() cannot see past.
FD_SETSIZE = 1024
_HIGH_FD_BASE = FD_SETSIZE + 176

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_PTY_READINESS_SOURCES = (
    _BACKEND_ROOT / "services" / "simple_pty.py",
    _BACKEND_ROOT / "agents" / "interactive_terminal_agent.py",
)


def _free_fd_at_or_above(start: int) -> int:
    """Return an unused descriptor number at or above ``start``."""
    for candidate in range(start, start + 64):
        try:
            fcntl.fcntl(candidate, fcntl.F_GETFD)
        except OSError:
            return candidate
    raise RuntimeError(f"no free descriptor number in [{start}, {start + 64})")


@contextmanager
def _pty_above_fd_setsize():
    """Yield ``(master_fd, slave_fd)`` with ``master_fd`` >= FD_SETSIZE."""
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    target = _free_fd_at_or_above(_HIGH_FD_BASE)
    raised = False
    if soft <= target:
        if hard != resource.RLIM_INFINITY and hard <= target:
            pytest.skip(f"RLIMIT_NOFILE hard limit {hard} cannot reach descriptor {target}")
        resource.setrlimit(resource.RLIMIT_NOFILE, (target + 1, hard))
        raised = True

    master, slave = pty.openpty()
    try:
        os.dup2(master, target)
        os.close(master)
        yield target, slave
    finally:
        for fd in (target, slave):
            try:
                os.close(fd)
            except OSError:
                pass
        if raised:
            resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))


def _assert_select_cannot_reach(fd: int) -> None:
    """Fail the test unless ``fd`` really is out of ``select()``'s reach."""
    try:
        select.select([fd], [], [], 0)
    except ValueError:
        return
    pytest.fail(f"descriptor {fd} is still within FD_SETSIZE — the test would prove nothing")


def _drain(output_queue: queue.Queue, timeout: float = 5.0):
    """Return the first queued PTY event."""
    return output_queue.get(timeout=timeout)


class TestSimplePtyReadLoopAboveFdSetsize:
    """SimplePTY._read_loop drives a real PTY whose master fd is >= 1024."""

    def test_streams_output_from_a_high_numbered_descriptor(self):
        with _pty_above_fd_setsize() as (master_fd, slave_fd):
            _assert_select_cannot_reach(master_fd)

            session = SimplePTY("fd-setsize-regression")
            session.master_fd = master_fd
            session.running = True
            reader = threading.Thread(target=session._read_loop, daemon=True)
            reader.start()
            try:
                os.write(slave_fd, b"hello-from-high-fd\n")
                event_type, content = _drain(session.output_queue)

                # Pre-fix, select() raised immediately, the loop logged the
                # error, broke, and this first event was ("close", "").
                assert event_type == "output"
                assert "hello-from-high-fd" in content
            finally:
                session.running = False
                reader.join(timeout=5.0)
                assert not reader.is_alive()

    def test_terminates_on_hangup_instead_of_spinning(self):
        with _pty_above_fd_setsize() as (master_fd, slave_fd):
            _assert_select_cannot_reach(master_fd)

            session = SimplePTY("fd-setsize-hangup")
            session.master_fd = master_fd
            session.running = True
            reader = threading.Thread(target=session._read_loop, daemon=True)
            reader.start()
            try:
                os.write(slave_fd, b"final line\n")
                event_type, content = _drain(session.output_queue)
                assert event_type == "output"
                assert "final line" in content

                # Closing the slave leaves the master reporting POLLHUP forever.
                # The loop must read through it (EOF/EIO) and end, not spin.
                os.close(slave_fd)
                reader.join(timeout=5.0)
                assert not reader.is_alive(), "read loop spun on POLLHUP"
                assert _drain(session.output_queue) == ("close", "")
            finally:
                session.running = False

    def test_read_loop_ends_when_the_descriptor_is_closed(self):
        master, slave = pty.openpty()
        os.close(master)
        os.close(slave)

        session = SimplePTY("fd-setsize-closed")
        session.master_fd = master
        session.running = True
        reader = threading.Thread(target=session._read_loop, daemon=True)
        reader.start()
        reader.join(timeout=5.0)

        # POLLNVAL surfaces as OSError(EBADF) — the same error select() raised
        # for a closed descriptor — so the loop still exits rather than looping.
        assert not reader.is_alive()
        assert _drain(session.output_queue) == ("close", "")


class TestNoSelectSelectInPtyReadinessPaths:
    """Neither PTY readiness path may reintroduce the FD_SETSIZE-bound API."""

    @pytest.mark.parametrize("source_path", _PTY_READINESS_SOURCES, ids=lambda p: p.name)
    def test_module_does_not_call_select_select(self, source_path: Path):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        offenders = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "select"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "select"
        ]
        assert not offenders, f"{source_path.name} still calls select.select() at line(s) {offenders}"

    @pytest.mark.parametrize("source_path", _PTY_READINESS_SOURCES, ids=lambda p: p.name)
    def test_module_uses_the_shared_poll_helper(self, source_path: Path):
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "autobot_shared.fd_poll"
            for alias in node.names
        }
        assert "poll_readable" in imported, f"{source_path.name} must use autobot_shared.fd_poll.poll_readable"
