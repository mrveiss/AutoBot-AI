# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``remove-role.yml`` refuses a hostile ``role_target_dir`` in a real ``ansible-playbook --check`` run (#22030).

The validation tasks come before every other task, so a refused value fails the run at the first task and nothing
else executes. The run is local, with ``become`` off, against a temporary install root.
"""

from __future__ import annotations

import json
import shutil
import subprocess  # nosec B404 -- runs ansible-playbook on the repo's own playbook
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible not installed")

_PLAYBOOK = Path(__file__).resolve().parents[1] / "ansible" / "playbooks" / "remove-role.yml"
_SHAPE = "role_target_dir must be a relative path of plain segments"
_ESCAPE = "resolves outside"


def _run(tmp_path: Path, role_target_dir: str) -> tuple[int, str]:
    ansible = shutil.which("ansible-playbook")
    extra = {
        "ansible_become": False,
        "role_name": "x",
        "systemd_service": "x",
        "autobot": {"base_dir": str(tmp_path / "root")},
        "role_target_dir": role_target_dir,
    }
    cmd = [str(ansible), "--check", "-i", "localhost,", "-c", "local", str(_PLAYBOOK), "-e", json.dumps(extra)]
    env = {"ANSIBLE_LOG_PATH": str(tmp_path / "a.log"), "PATH": f"{Path(str(ansible)).parent}:/usr/bin:/bin"}
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=180, check=False)  # nosec B603
    return proc.returncode, proc.stdout + proc.stderr


@pytest.mark.parametrize("value", ["", ".", "..", "/", "/etc", "../x", "a/../b", "a/./b", "a//b", "a b", "a;b", "a/"])
def test_a_hostile_directory_fails_the_run_at_the_first_task(tmp_path: Path, value: str) -> None:
    (tmp_path / "root").mkdir()
    code, out = _run(tmp_path, value)
    assert code != 0 and _SHAPE in out, out[-600:]
    assert "Validate required variables" not in out, "a later task ran"


def test_a_symlink_out_of_the_install_root_fails_the_realpath_check(tmp_path: Path) -> None:
    (tmp_path / "root").mkdir()
    (tmp_path / "outside").mkdir()
    (tmp_path / "root" / "link").symlink_to(tmp_path / "outside")
    code, out = _run(tmp_path, "link/x")
    assert code != 0 and _ESCAPE in out and _SHAPE not in out, out[-600:]


def test_the_install_root_itself_cannot_be_reached_through_a_symlink(tmp_path: Path) -> None:
    (tmp_path / "root").mkdir()
    (tmp_path / "root" / "self").symlink_to(tmp_path / "root")
    code, out = _run(tmp_path, "self")
    assert code != 0 and _ESCAPE in out, out[-600:]
