# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#21098: the pre-push machine queue defaults to 2 slots and waits while the 1-minute load is high.

Every script here points ``AUTOBOT_MACHINE_SLOT_LOADAVG`` at a fixture: a test that read the real load
average would wait whenever the host is busy. Waits are bounded polls on the slot files, not sleeps.
"""

from __future__ import annotations

import os
import select
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from repo_tests._machine_slot_hook import fake_load, hook_functions
from repo_tests._paths import repo_root

_ROOT = repo_root()
_DROP = ("CI", "AUTOBOT_MACHINE_SLOT_HELD", "AUTOBOT_MACHINE_SLOTS", "AUTOBOT_MACHINE_SLOT_MAX_LOAD")
_PAUSE = 0.05
_LIMIT = 20.0


def _env(slots: Path, load: Path, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _DROP}
    env.update(AUTOBOT_MACHINE_SLOT_DIR=str(slots), AUTOBOT_MACHINE_SLOT_POLL="0.05", **extra)
    env["AUTOBOT_MACHINE_SLOT_LOADAVG"] = str(load)
    return env


def _wait(env: dict, tail: str = "echo GOT") -> subprocess.Popen:
    script = f'log() {{ echo "$*"; }}; warn() {{ echo "WARN $*"; }}\n{hook_functions()}\nmachine_slot_wait; {tail}\n'
    return subprocess.Popen(["bash", "-c", script], env=env, stdout=subprocess.PIPE, text=True)


def _until(what: str, done: Callable[[], bool]) -> None:
    deadline = time.monotonic() + _LIMIT
    while not done():
        assert time.monotonic() < deadline, f"timed out after {_LIMIT}s waiting for: {what}"
        time.sleep(_PAUSE)


def _holder_named(slot: Path) -> bool:
    return slot.exists() and "pre-push" in slot.read_text(encoding="utf-8")


def test_the_default_is_two_slots(tmp_path: Path) -> None:
    load = fake_load(tmp_path / "loadavg")
    release = tmp_path / "release"
    tail = f'until [ -e "{release}" ]; do sleep 0.05; done; echo GOT'
    held = [_wait(_env(tmp_path, load), tail) for _ in range(2)]
    third = None
    try:
        _until("both slots held", lambda: all(_holder_named(tmp_path / f"slot-{i}") for i in (1, 2)))
        third = _wait(_env(tmp_path, load))
        first = _first_line(third)
        assert first.startswith("queued"), f"a third push did not queue (default above 2 slots): {first!r}"
        assert third.poll() is None
        assert not (tmp_path / "slot-3").exists(), "the hook tried a third slot"
    finally:
        release.write_text("", encoding="utf-8")
        for p in held:
            p.communicate(timeout=_LIMIT)
    assert third is not None and "GOT" in third.communicate(timeout=_LIMIT)[0]


def _first_line(proc: subprocess.Popen) -> str:
    ready, _, _ = select.select([proc.stdout], [], [], _LIMIT)
    assert ready, f"no output within {_LIMIT}s"
    return proc.stdout.readline()


def test_the_python_side_defaults_to_two_too(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k != "AUTOBOT_MACHINE_SLOTS"}
    env.update(AUTOBOT_MACHINE_SLOT_DIR=str(tmp_path), PYTHONPATH=str(_ROOT))
    code = "from repo_tests.machine_slot import _slot_paths; print(len(_slot_paths()))"
    out = subprocess.run([sys.executable, "-c", code], env=env, cwd=_ROOT, capture_output=True, text=True)
    assert out.stdout.strip() == "2", out.stderr


def test_high_load_waits_and_reports_then_proceeds_when_it_falls(tmp_path: Path) -> None:
    load = fake_load(tmp_path / "loadavg", "20.50")
    waiter = _wait(_env(tmp_path, load, AUTOBOT_MACHINE_SLOT_REPORT="1"))
    try:
        time.sleep(0.5)
        assert waiter.poll() is None, "it ran while the load was at or above the ceiling"
        assert not list(tmp_path.glob("slot-*")), "it took a slot while the load was high"
    finally:
        fake_load(load, "3.00")
    out, _ = waiter.communicate(timeout=_LIMIT)
    assert "load 20.50 is at or above 14" in out and "AUTOBOT_MACHINE_SLOT_MAX_LOAD" in out
    assert "queued" in out and "GOT" in out


def test_the_ceiling_is_configurable_and_equal_load_waits(tmp_path: Path) -> None:
    load = fake_load(tmp_path / "loadavg", "5.00")
    waiter = _wait(_env(tmp_path, load, AUTOBOT_MACHINE_SLOT_MAX_LOAD="5"))
    try:
        time.sleep(0.5)
        assert waiter.poll() is None, "a load equal to the ceiling must wait"
    finally:
        waiter.kill()
        waiter.communicate()


def test_low_load_does_not_wait(tmp_path: Path) -> None:
    out, _ = _wait(_env(tmp_path, fake_load(tmp_path / "loadavg"))).communicate(timeout=_LIMIT)
    assert "GOT" in out and "at or above" not in out and "WARN" not in out


def test_an_unreadable_load_source_warns_once_and_never_blocks(tmp_path: Path) -> None:
    gone = tmp_path / "missing"
    out, _ = _wait(_env(tmp_path, gone), "machine_slot_load_high; machine_slot_load_high; echo GOT").communicate(
        timeout=_LIMIT
    )
    assert "GOT" in out
    assert out.count("WARN the load average is unreadable") == 1, out
