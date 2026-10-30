# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""GPU detection finds nvidia-smi on PATH and in WSL2's own directory (#19731).

Under WSL2 the binary is in /usr/lib/wsl/lib, not on the PATH of the account Ansible runs as, so a
host with a GPU read as having none and every GPU-only model was skipped. This runs the shipped task
with real ansible-playbook, for each place the binary can be and for no binary at all.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest
import yaml
from repo_tests._paths import repo_root

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_TASK = _ANSIBLE / "roles" / "_shared" / "tasks" / "detect_nvidia_gpu.yml"
_PLAYBOOK = shutil.which("ansible-playbook")
_needs_ansible = pytest.mark.skipif(_PLAYBOOK is None, reason="ansible-playbook is not installed")


def _fake_smi(directory) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    smi = directory / "nvidia-smi"
    smi.write_text('#!/bin/sh\necho "Fake GPU"\n', encoding="utf-8")
    smi.chmod(0o755)


def _probe(tmp_path, on_path: bool, in_extra: bool) -> dict:
    path_dir, extra_dir = tmp_path / "bin", tmp_path / "wsl"
    if on_path:
        _fake_smi(path_dir)
    if in_extra:
        _fake_smi(extra_dir)
    play = [
        {
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "tasks": [
                {"ansible.builtin.include_tasks": str(_TASK)},
                {
                    "ansible.builtin.debug": {
                        "msg": "PROBE={{ {'rc': nvidia_smi_probe.rc, 'out': nvidia_smi_probe.stdout} | to_json }}"
                    }
                },
            ],
        }
    ]
    file = tmp_path / "play.yml"
    file.write_text(yaml.safe_dump(play), encoding="utf-8")
    env = {**os.environ, "PATH": f"{path_dir}:/usr/bin:/bin", "ANSIBLE_STDOUT_CALLBACK": "default"}
    args = [_PLAYBOOK, "-i", "localhost,", str(file), "-e", json.dumps({"nvidia_smi_extra_path": str(extra_dir)})]
    done = subprocess.run(args, capture_output=True, text=True, timeout=120, cwd=tmp_path, env=env, check=False)
    assert done.returncode == 0, done.stdout[-1500:]
    line = next(line for line in done.stdout.splitlines() if "PROBE=" in line)
    return {"gpu": '\\"rc\\": 0' in line and "Fake GPU" in line, "line": line}


@_needs_ansible
@pytest.mark.parametrize(
    ("on_path", "in_extra", "expected"),
    [(True, False, True), (False, True, True), (False, False, False)],
    ids=["bare-metal", "wsl2-lib-path", "absent"],
)
def test_each_location(tmp_path, on_path: bool, in_extra: bool, expected: bool) -> None:
    result = _probe(tmp_path, on_path, in_extra)
    assert result["gpu"] is expected, result["line"]


def test_no_role_runs_a_bare_nvidia_smi_of_its_own() -> None:
    found = []
    for path in sorted((_ANSIBLE / "roles").rglob("*.yml")):
        if path != _TASK and "nvidia-smi --query" in path.read_text(encoding="utf-8"):
            found.append(path.name)
    assert not found, found
