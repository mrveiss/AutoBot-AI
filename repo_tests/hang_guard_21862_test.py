# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The hang guard kills a stalled or runaway process and spares a slow one (#21862, #21910)."""

from __future__ import annotations

import subprocess
import sys

import pytest
from repo_tests import _hang_guard
from repo_tests._paths import repo_root


def test_a_slow_but_progressing_process_is_not_killed() -> None:
    done = _hang_guard.run_guarded([sys.executable, "-c", "print('ok')"], cwd=repo_root())
    assert done.returncode == 0 and done.stdout.strip() == "ok"


def test_a_process_using_no_cpu_is_killed_as_stalled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hang_guard, "STALL_SECONDS", 2.0)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        _hang_guard.run_guarded([sys.executable, "-c", "import time; time.sleep(60)"], cwd=repo_root())
    assert "no CPU progress" in str(caught.value.output)


def test_a_cpu_runaway_is_killed_on_its_cpu_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_hang_guard, "CPU_BUDGET_SECONDS", 1.0)
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        _hang_guard.run_guarded([sys.executable, "-c", "while True: pass"], cwd=repo_root())
    assert "over the" in str(caught.value.output)
