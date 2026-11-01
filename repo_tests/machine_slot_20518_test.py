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


def test_the_hook_queues_before_any_stage_timeout_and_rechecks_the_cache() -> None:
    """Each stage: wait, then a pass another push of this tree recorded, then the timed work."""
    stages = re.findall(r"machine_slot_wait\n\s*! stage_cached \"([^\"]+)\"", _HOOK)
    assert sorted(stages) == sorted(set(re.findall(r'stage_begin "([^"]+)"', _HOOK)))


def test_the_floor_check_imports_with_the_paths_pytest_uses() -> None:
    sys.path.insert(0, str(_ROOT / "scripts"))
    import repin_reach_floors  # noqa: PLC0415

    roots = repin_reach_floors.import_roots()
    assert "autobot-backend" in roots and "libs/autobot-sdk-python" in roots
