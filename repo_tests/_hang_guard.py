# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hang guard for CPU-bound test subprocesses that does not read the wall clock (#21862, #21910).

``subprocess.run(timeout=N)`` measures elapsed time, so the same work that takes 36 s on an idle
host exceeds a 180 s budget when ``pytest -n auto`` shares 22 cores with other sessions: the flake
is the budget, not the code. This guard asks the two questions a hang guard actually means:

* *stalled* -- has the process (and the children it has reaped) used no CPU at all for
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

from autobot_shared.env_utils import env_float

STALL_SECONDS = env_float("AUTOBOT_TEST_STALL_SECONDS", 120.0)
CPU_BUDGET_SECONDS = env_float("AUTOBOT_TEST_CPU_BUDGET_SECONDS", 900.0)
_POLL_SECONDS = 1.0
_CLOCK_TICKS = os.sysconf("SC_CLK_TCK")


def cpu_seconds(pid: int) -> float | None:
    """User+system CPU of *pid* plus its reaped children, or None when it is gone."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    # Fields after the parenthesised comm (which may itself contain spaces/parens).
    fields = raw.rsplit(")", 1)[1].split()
    utime, stime, cutime, cstime = (int(fields[i]) for i in (11, 12, 13, 14))
    return (utime + stime + cutime + cstime) / _CLOCK_TICKS


def _kill_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _verdict(used: float, idle_for: float) -> str | None:
    if used > CPU_BUDGET_SECONDS:
        return f"used {used:.0f}s CPU, over the {CPU_BUDGET_SECONDS:.0f}s budget"
    if idle_for > STALL_SECONDS:
        return f"made no CPU progress for {idle_for:.0f}s (stall limit {STALL_SECONDS:.0f}s)"
    return None


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
    started = last_progress = time.monotonic()
    last_cpu = 0.0
    while True:
        try:
            out, err = proc.communicate(timeout=_POLL_SECONDS)
            return subprocess.CompletedProcess(argv, proc.returncode, out, err)
        except subprocess.TimeoutExpired:
            pass
        used = cpu_seconds(proc.pid)
        now = time.monotonic()
        if used is not None and used > last_cpu:
            last_cpu, last_progress = used, now
        reason = _verdict(last_cpu, now - last_progress)
        if reason:
            _kill_group(proc)
            out, err = proc.communicate()
            raise subprocess.TimeoutExpired(list(argv), now - started, output=f"{reason}\n{out}", stderr=err)
