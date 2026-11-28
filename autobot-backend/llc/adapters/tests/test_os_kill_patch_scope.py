# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: no test here patches ``os.kill`` interpreter-wide (GH#16920).

``patch("os.kill", ...)`` intercepts every PID in the process, so under xdist a
sibling test's real reap lands inside the window. Every fake must be built by
``conftest.scoped_os_kill``, which routes foreign PIDs to the real ``os.kill``.
"""

from __future__ import annotations

import os
import pathlib
import re
import signal
import subprocess
import sys

import pytest

from .conftest import scoped_os_kill

_TESTS_DIR = pathlib.Path(__file__).parent
_EXEMPT = frozenset({"conftest.py", pathlib.Path(__file__).name})
_RAW_PATCH = re.compile(r"""(?:setattr|patch(?:\.object)?)\(\s*(?:["'][\w.]*os\.kill["']|os\s*,\s*["']kill["'])""")


def _offenders(sources: dict[str, str]) -> list[str]:
    return sorted(name for name, text in sources.items() if _RAW_PATCH.search(text))


def test_no_raw_os_kill_patch_in_directory() -> None:
    sources = {p.name: p.read_text(encoding="utf-8") for p in _TESTS_DIR.glob("*.py") if p.name not in _EXEMPT}
    assert _offenders(sources) == []


def test_detector_flags_raw_patch_forms() -> None:
    """Contrast: the detector does fire on both raw spellings, and not on the helper."""
    assert _offenders({"a.py": 'with patch("os.kill", side_effect=X):'}) == ["a.py"]
    assert _offenders({"b.py": 'with patch.object(os, "kill") as k:'}) == ["b.py"]
    assert _offenders({"c.py": "with scoped_os_kill(42) as k:"}) == []


def test_detector_flags_monkeypatch_and_module_path_forms() -> None:
    assert _offenders({"d.py": 'monkeypatch.setattr(os, "kill", fake)'}) == ["d.py"]
    assert _offenders({"e.py": 'monkeypatch.setattr("os.kill", fake)'}) == ["e.py"]
    assert _offenders({"f.py": 'with patch("llc.adapters.subprocess_support.os.kill") as k:'}) == ["f.py"]
    assert _offenders({"g.py": "monkeypatch.setattr(os, 'kill', fake)"}) == ["g.py"]


def test_scoped_fake_refuses_fabricated_foreign_pid_signal() -> None:
    with scoped_os_kill(1234):
        with pytest.raises(AssertionError, match="4194311"):
            os.kill(2**22 + 7, signal.SIGKILL)


@pytest.mark.parametrize("pid", [0, -1, -4242, 1])
def test_scoped_fake_refuses_pid_le_one_with_signal(pid: int) -> None:
    with scoped_os_kill(1234):
        with pytest.raises(AssertionError, match="refused"):
            os.kill(pid, signal.SIGTERM)


def test_scoped_fake_passes_signal_zero_to_foreign_pid() -> None:
    with scoped_os_kill(1234):
        os.kill(os.getpid(), 0)  # real probe of a live foreign pid: no raise, no assertion
        with pytest.raises(ProcessLookupError):
            os.kill(2**22 + 7, 0)  # real os.kill answered, not the guard


def test_scoped_fake_records_only_its_own_pid_and_passes_others_through() -> None:
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        with scoped_os_kill(2**22 + 7, side_effect=ProcessLookupError) as mock_kill:
            os.kill(child.pid, 0)  # foreign: real os.kill, child is alive so no raise
            os.kill(child.pid, signal.SIGKILL)  # foreign: really reaps the child
            try:
                os.kill(2**22 + 7, 0)
            except ProcessLookupError:
                pass
        assert [c.args for c in mock_kill.call_args_list] == [(2**22 + 7, 0)]
        assert child.wait(timeout=10) == -signal.SIGKILL
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
