# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hang guard for CPU-bound test subprocesses that does not read the wall clock (#21862, #21910).

``subprocess.run(timeout=N)`` measures elapsed time, so the same work that takes 36 s on an idle
host exceeds a 180 s budget when ``pytest -n auto`` shares 22 cores with other sessions: the flake
is the budget, not the code. This guard asks the two questions a hang guard actually means:

* *stalled* -- has the process (and its whole process tree) used no CPU at all for
  ``AUTOBOT_TEST_STALL_SECONDS``? A starved-but-runnable process still accrues CPU time, a hung
  one does not.
* *runaway* -- has it used more than ``AUTOBOT_TEST_CPU_BUDGET_SECONDS`` of CPU? CPU time is the
  same on an idle box and at load 30.

Linux ``/proc`` only, like the shell suites these tests drive.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Mapping, Sequence

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

STALL_SECONDS = env_float_clamped("AUTOBOT_TEST_STALL_SECONDS", 120.0, 5.0, 3600.0, positive_finite=True)
CPU_BUDGET_SECONDS = env_float_clamped("AUTOBOT_TEST_CPU_BUDGET_SECONDS", 900.0, 10.0, 7200.0, positive_finite=True)
DRAIN_SECONDS = env_float_clamped("AUTOBOT_TEST_DRAIN_SECONDS", 10.0, 1.0, 300.0, positive_finite=True)
_POLL_SECONDS = 1.0
_CLOCK_TICKS = os.sysconf("SC_CLK_TCK")
_PROC = Path("/proc")


def _stat_fields(entry: Path) -> list[str] | None:
    """Fields after the comm of one ``/proc/<pid>/stat`` (field 3 onward), None if it vanished."""
    try:
        raw = (entry / "stat").read_text(encoding="utf-8")
    except OSError:
        return None  # exited between the listing and the read
    # comm may itself contain spaces/parens, so split after the LAST ')'.
    return raw.rsplit(")", 1)[1].split()


def _session_members(root_pid: int) -> list[tuple[Path, int]]:
    """``(proc entry, session id)`` of every live process whose session id is *root_pid*."""
    members = []
    for entry in _PROC.glob("[0-9]*"):
        fields = _stat_fields(entry)
        if fields is not None and int(fields[3]) == root_pid:  # field 6: session id
            members.append((entry, root_pid))
    return members


def cpu_seconds(root_pid: int) -> float:
    """CPU of the live process tree of *root_pid* plus everything its members reaped.

    The child runs with ``start_new_session=True``, so every descendant shares session id
    *root_pid*. Two passes, in this order, so a child is never counted twice: first the reaped-CPU
    (``cutime``/``cstime``) of every member, then ``utime``/``stime`` of the members STILL present.
    A child that exits between the passes is already in its parent's first-pass reaped total.
    """
    if not _PROC.is_dir():
        raise RuntimeError("hang guard needs /proc (Linux only); it cannot tell a stall from no data")
    members = _session_members(root_pid)
    ticks = 0
    for entry, sid in members:  # pass 1: reaped children's CPU
        fields = _stat_fields(entry)
        if fields is not None and int(fields[3]) == sid:
            ticks += int(fields[13]) + int(fields[14])  # cutime cstime
    for entry, sid in members:  # pass 2: own CPU of whoever is still alive
        fields = _stat_fields(entry)
        if fields is not None and int(fields[3]) == sid:
            ticks += int(fields[11]) + int(fields[12])  # utime stime
    return ticks / _CLOCK_TICKS


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _close_and_reap(proc: subprocess.Popen) -> None:
    """Close the pipes and reap the direct child, whatever still holds the pipe's other end."""
    for pipe in (proc.stdout, proc.stderr):
        if pipe is not None:
            try:
                pipe.close()
            except OSError:
                pass
    try:
        proc.kill()
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=DRAIN_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"hang guard could not reap pid {proc.pid} within {DRAIN_SECONDS:.0f}s of SIGKILL") from exc


def _kill_and_drain(proc: subprocess.Popen) -> tuple[str, str]:
    """Kill the group and collect its output; a descendant that escaped holding a pipe cannot hang us."""
    _kill_group(proc)
    try:
        return proc.communicate(timeout=DRAIN_SECONDS)
    except subprocess.TimeoutExpired:
        _close_and_reap(proc)
        raise


def _sample_cpu(proc: subprocess.Popen) -> float:
    try:
        return cpu_seconds(proc.pid)
    except RuntimeError:
        with contextlib.suppress(subprocess.TimeoutExpired):
            _kill_and_drain(proc)  # no /proc: never leave the child running unobserved
        raise


def _verdict(used: float, idle_for: float) -> str | None:
    if used > CPU_BUDGET_SECONDS:
        return f"used {used:.0f}s CPU, over the {CPU_BUDGET_SECONDS:.0f}s budget"
    if idle_for > STALL_SECONDS:
        return f"made no CPU progress for {idle_for:.0f}s (stall limit {STALL_SECONDS:.0f}s)"
    return None


def _poll(proc: subprocess.Popen, state: tuple[float, float, float], now: float):
    """Sample CPU once; return the updated (last_cpu, last_progress, peak_cpu) and a kill reason or None."""
    last_cpu, last_progress, peak_cpu = state
    used = _sample_cpu(proc)
    if used != last_cpu:  # the total can drop (setsid escape, reaped orphan): still a change
        last_cpu, last_progress = used, now
    peak_cpu = max(peak_cpu, used)
    return (last_cpu, last_progress, peak_cpu), _verdict(peak_cpu, now - last_progress)


def run_guarded(
    argv: Sequence[str],
    *,
    cwd: str | os.PathLike[str],
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run *argv* capturing text output; kill it only if it stalls or runs away on CPU."""
    proc = subprocess.Popen(  # noqa: S603 - caller-fixed argv
        list(argv),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=None if env is None else dict(env),
        start_new_session=True,
    )
    started = time.monotonic()
    try:
        done = _monitor(proc, argv, started)
        if isinstance(done, subprocess.CompletedProcess):
            return done
        _raise_killed(proc, argv, done, started)
    except subprocess.TimeoutExpired:
        raise  # already killed, drained and reaped
    except BaseException as original:  # incl. KeyboardInterrupt: never leave the group running or the pipes open
        _cleanup_keeping(original, proc)
        raise


def _cleanup_keeping(original: BaseException, proc: subprocess.Popen) -> None:
    """Kill and reap *proc*; a cleanup failure is logged and noted on *original*, never replaces it."""
    try:
        _kill_group(proc)
        _close_and_reap(proc)
    except Exception as cleanup_error:  # noqa: BLE001 - must not mask the original exception
        logger.error("hang guard cleanup failed for pid %s: %r", proc.pid, cleanup_error)
        original.add_note(f"hang guard cleanup also failed: {cleanup_error!r}")


def _monitor(proc: subprocess.Popen, argv: Sequence[str], started: float):
    """Poll until the process ends (a CompletedProcess) or must be killed (the reason string)."""
    state = (0.0, started, 0.0)  # last_cpu, last_progress, peak_cpu
    while True:
        try:
            out, err = proc.communicate(timeout=_POLL_SECONDS)
            return subprocess.CompletedProcess(argv, proc.returncode, out, err)
        except subprocess.TimeoutExpired:
            pass
        state, reason = _poll(proc, state, time.monotonic())
        if reason:
            return reason


def _as_text(data: str | bytes | None) -> str:
    """TimeoutExpired from ``communicate`` carries bytes or None even for a text-mode Popen."""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""


def _raise_killed(proc: subprocess.Popen, argv: Sequence[str], reason: str, started: float) -> None:
    elapsed = time.monotonic() - started
    try:
        out, err = _kill_and_drain(proc)
    except subprocess.TimeoutExpired as exc:
        note = f"{reason}\n(a descendant outside the process group kept the pipes open; output is partial)"
        partial = _as_text(exc.output)
        if partial:
            note = f"{note}\n{partial}"
        raise subprocess.TimeoutExpired(list(argv), elapsed, output=note, stderr=_as_text(exc.stderr)) from exc
    raise subprocess.TimeoutExpired(list(argv), elapsed, output=f"{reason}\n{out}", stderr=err)
