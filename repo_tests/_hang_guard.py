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

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Mapping, Sequence

from autobot_shared.env_utils import env_float_clamped

STALL_SECONDS = env_float_clamped("AUTOBOT_TEST_STALL_SECONDS", 120.0, 5.0, 3600.0, positive_finite=True)
CPU_BUDGET_SECONDS = env_float_clamped("AUTOBOT_TEST_CPU_BUDGET_SECONDS", 900.0, 10.0, 7200.0, positive_finite=True)
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


def cpu_seconds(root_pid: int) -> float:
    """CPU of the live process tree of *root_pid* plus everything its members reaped.

    The child runs with ``start_new_session=True``, so every descendant shares session id
    *root_pid*. ``cutime``/``cstime`` count only REAPED children, so live descendants are summed
    by their own ``utime``/``stime``.
    """
    if not _PROC.is_dir():
        raise RuntimeError("hang guard needs /proc (Linux only); it cannot tell a stall from no data")
    ticks = 0
    for entry in _PROC.glob("[0-9]*"):
        fields = _stat_fields(entry)
        if fields is None or int(fields[3]) != root_pid:  # field 6: session id
            continue
        ticks += sum(int(fields[i]) for i in (11, 12, 13, 14))  # utime stime cutime cstime
    return ticks / _CLOCK_TICKS


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _sample_cpu(proc: subprocess.Popen) -> float:
    try:
        return cpu_seconds(proc.pid)
    except RuntimeError:
        _kill_group(proc)  # no /proc: never leave the child running unobserved
        proc.communicate()  # reap it and close its pipes before re-raising
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
    state = (0.0, started, 0.0)  # last_cpu, last_progress, peak_cpu
    while True:
        try:
            out, err = proc.communicate(timeout=_POLL_SECONDS)
            return subprocess.CompletedProcess(argv, proc.returncode, out, err)
        except subprocess.TimeoutExpired:
            pass
        now = time.monotonic()
        state, reason = _poll(proc, state, now)
        if reason:
            _kill_group(proc)
            out, err = proc.communicate()
            raise subprocess.TimeoutExpired(list(argv), now - started, output=f"{reason}\n{out}", stderr=err)
