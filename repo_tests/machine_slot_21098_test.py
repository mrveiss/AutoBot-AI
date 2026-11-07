# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#21098: the pre-push machine queue defaults to 2 slots and waits while the 1-minute load is high."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from repo_tests._paths import repo_root

_ROOT = repo_root()
_HOOK = (_ROOT / "tools/git-hooks/pre-push").read_text(encoding="utf-8")
_FN = re.search(r"^machine_slot_wait\(\) \{\n(?:.*\n)*?\}$", _HOOK, re.MULTILINE).group(0)
_DROP = ("CI", "AUTOBOT_MACHINE_SLOT_HELD", "AUTOBOT_MACHINE_SLOTS", "AUTOBOT_MACHINE_SLOT_MAX_LOAD")


def _env(slots: Path, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _DROP}
    env.update(AUTOBOT_MACHINE_SLOT_DIR=str(slots), AUTOBOT_MACHINE_SLOT_POLL="0.1", **extra)
    return env


def _wait(env: dict, tail: str = "echo GOT") -> subprocess.Popen:
    script = f'log() {{ echo "$*"; }}; warn() {{ echo "$*"; }}\n{_FN}\nmachine_slot_wait; {tail}\n'
    return subprocess.Popen(["bash", "-c", script], env=env, stdout=subprocess.PIPE, text=True)


def _fake_load(path: Path, value: str) -> Path:
    path.write_text(f"{value} 1.00 1.00 1/100 1234\n", encoding="utf-8")
    return path


def test_the_default_is_two_slots(tmp_path: Path) -> None:
    # Two pushes hold a slot each (a third would be a third slot); the third must queue.
    held = [_wait(_env(tmp_path), "sleep 4; echo GOT") for _ in range(2)]
    time.sleep(1.0)
    third = _wait(_env(tmp_path))
    try:
        time.sleep(1.5)
        assert third.poll() is None, "a third push ran: the default is more than 2 slots"
    finally:
        for p in held:
            p.communicate(timeout=30)
    out, _ = third.communicate(timeout=30)
    assert "GOT" in out
    assert not (tmp_path / "slot-3").exists(), "the hook tried a third slot"


def test_the_default_is_declared_once_per_side() -> None:
    from repo_tests.machine_slot import _slot_paths

    assert ":-2}" in _FN and ":-4}" not in _FN
    env = {k: v for k, v in os.environ.items() if k != "AUTOBOT_MACHINE_SLOTS"}
    code = "from repo_tests.machine_slot import _slot_paths; print(len(_slot_paths()))"
    out = subprocess.run(
        [sys.executable, "-c", code], env={**env, "PYTHONPATH": str(_ROOT)}, cwd=_ROOT, capture_output=True, text=True
    )
    assert out.stdout.strip() == "2", out.stderr
    assert callable(_slot_paths)


def test_high_load_waits_and_reports_then_proceeds_when_it_falls(tmp_path: Path) -> None:
    load = _fake_load(tmp_path / "loadavg", "20.50")
    env = _env(tmp_path, AUTOBOT_MACHINE_SLOT_LOADAVG=str(load), AUTOBOT_MACHINE_SLOT_REPORT="1")
    waiter = _wait(env)
    time.sleep(1.5)
    assert waiter.poll() is None, "it ran while the load was at or above the ceiling"
    _fake_load(load, "3.00")
    out, _ = waiter.communicate(timeout=30)
    assert "load 20.50 is at or above 14" in out and "AUTOBOT_MACHINE_SLOT_MAX_LOAD" in out
    assert "queued" in out and "GOT" in out


def test_the_ceiling_is_configurable_and_equal_load_waits(tmp_path: Path) -> None:
    load = _fake_load(tmp_path / "loadavg", "5.00")
    env = _env(tmp_path, AUTOBOT_MACHINE_SLOT_LOADAVG=str(load), AUTOBOT_MACHINE_SLOT_MAX_LOAD="5")
    waiter = _wait(env)
    try:
        time.sleep(1.0)
        assert waiter.poll() is None, "a load equal to the ceiling must wait"
    finally:
        waiter.kill()
        waiter.communicate()


def test_low_load_and_an_unreadable_source_do_not_wait(tmp_path: Path) -> None:
    low = _fake_load(tmp_path / "loadavg", "0.10")
    out, _ = _wait(_env(tmp_path, AUTOBOT_MACHINE_SLOT_LOADAVG=str(low))).communicate(timeout=30)
    assert "GOT" in out and "at or above" not in out
    gone = _env(tmp_path, AUTOBOT_MACHINE_SLOT_LOADAVG=str(tmp_path / "missing"))
    out, _ = _wait(gone).communicate(timeout=30)
    assert "GOT" in out
