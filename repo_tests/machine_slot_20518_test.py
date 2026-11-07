# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20518: heavy local work queues for a machine-wide slot, and the gate can record a pass."""

from __future__ import annotations

import fcntl
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_ROOT = repo_root()
_HOOK = (_ROOT / "tools/git-hooks/pre-push").read_text(encoding="utf-8")
_ENV_DROP = ("CI", "AUTOBOT_MACHINE_SLOT_HELD")


def _env(slots: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _ENV_DROP}
    env.update(AUTOBOT_MACHINE_SLOT_DIR=str(slots), AUTOBOT_MACHINE_SLOTS="1", AUTOBOT_MACHINE_SLOT_POLL="0.1")
    return env


def _bash_waiter(slots: Path) -> subprocess.Popen:
    fn = re.search(r"^machine_slot_wait\(\) \{\n(?:.*\n)*?\}$", _HOOK, re.MULTILINE).group(0)
    script = f'log() {{ echo "$*"; }}; warn() {{ echo "$*"; }}\n{fn}\nmachine_slot_wait; echo GOT\n'
    return subprocess.Popen(["bash", "-c", script], env=_env(slots), stdout=subprocess.PIPE, text=True)


def _python_waiter(slots: Path) -> subprocess.Popen:
    code = "from repo_tests.machine_slot import acquire; acquire(); print('GOT')"
    return subprocess.Popen([sys.executable, "-c", code], env=_env(slots), cwd=_ROOT, stdout=subprocess.PIPE, text=True)


@pytest.mark.parametrize("start", [_bash_waiter, _python_waiter], ids=["hook", "python"])
def test_over_the_limit_queues_until_a_slot_frees(start, tmp_path: Path) -> None:
    held = os.open(tmp_path / "slot-1", os.O_CREAT | os.O_WRONLY, 0o600)
    fcntl.flock(held, fcntl.LOCK_EX)
    waiter = start(tmp_path)
    try:
        time.sleep(1.5)
        assert waiter.poll() is None, "it ran over the limit instead of queueing"
    finally:
        os.close(held)
    out, _ = waiter.communicate(timeout=30)
    assert "GOT" in out and waiter.returncode == 0


@pytest.mark.parametrize("start", [_bash_waiter, _python_waiter], ids=["hook", "python"])
def test_contrast_a_free_slot_does_not_wait(start, tmp_path: Path) -> None:
    out, _ = start(tmp_path).communicate(timeout=30)
    assert "GOT" in out


def test_one_slot_per_push_taken_before_any_stage_and_the_cache_rechecked() -> None:
    assert re.search(r"^stage_begin\(\) \{\n  machine_slot_wait\n", _HOOK, re.MULTILINE)
    assert _HOOK.count("machine_slot_wait\n") == 1
    stages = set(re.findall(r'stage_begin "([^"]+)"', _HOOK))
    assert stages and set(re.findall(r'! stage_cached "([^"]+)"', _HOOK)) == stages


def test_a_queued_push_prints_while_it_waits_and_names_the_holder(tmp_path: Path) -> None:
    (tmp_path / "slot-1").write_text("4242 pre-push issue-9-x\n", encoding="utf-8")
    held = os.open(tmp_path / "slot-1", os.O_WRONLY)
    fcntl.flock(held, fcntl.LOCK_EX)
    env = {**_env(tmp_path), "AUTOBOT_MACHINE_SLOT_REPORT": "1"}
    fn = re.search(r"^machine_slot_wait\(\) \{\n(?:.*\n)*?\}$", _HOOK, re.MULTILINE).group(0)
    script = f'log() {{ echo "$*"; }}; warn() {{ echo "$*"; }}\n{fn}\nmachine_slot_wait; echo GOT\n'
    waiter = subprocess.Popen(["bash", "-c", script], env=env, stdout=subprocess.PIPE, text=True)
    time.sleep(1.5)
    os.close(held)
    out, _ = waiter.communicate(timeout=30)
    assert "queued" in out and "4242 pre-push issue-9-x" in out and "GOT" in out
    assert "pre-push" in (tmp_path / "slot-1").read_text(encoding="utf-8")


def test_the_hook_and_python_build_the_same_default_path(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in _ENV_DROP + ("AUTOBOT_MACHINE_SLOT_DIR",)}
    env.update(XDG_RUNTIME_DIR=str(tmp_path), PATH=os.environ["PATH"])
    code = "from repo_tests.machine_slot import _slot_paths; print(_slot_paths()[0].parent)"
    python = subprocess.run(
        [sys.executable, "-c", code], env=env, cwd=_ROOT, capture_output=True, text=True, check=True
    )
    fn = re.search(r"^machine_slot_wait\(\) \{\n(?:.*\n)*?\}$", _HOOK, re.MULTILINE).group(0)
    bash = subprocess.run(
        ["bash", "-c", f'log() {{ :; }}; warn() {{ :; }}\n{fn}\nmachine_slot_wait; ls -d "$XDG_RUNTIME_DIR"/*'],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert bash.stdout.strip() == python.stdout.strip()


def test_the_cache_key_follows_the_base() -> None:
    assert re.search(r'fast_key=\$\(stage_key "fast guards[^\n]*rev-parse -q --verify origin/main', _HOOK)


def test_the_floor_check_imports_with_the_paths_pytest_uses() -> None:
    """Without these paths 14 guard modules failed to import and no pass was ever recorded."""
    sys.path.insert(0, str(_ROOT / "scripts"))
    import repin_reach_floors  # noqa: PLC0415

    roots = repin_reach_floors.import_roots()
    assert (_ROOT / "libs/autobot-sdk-python/autobot_sdk").is_dir() and "libs/autobot-sdk-python" in roots
    assert (_ROOT / "autobot-backend/config").is_dir() and "autobot-backend" in roots
    assert "sys.path[1:1]" in (_ROOT / "scripts/repin_reach_floors.py").read_text(encoding="utf-8")
