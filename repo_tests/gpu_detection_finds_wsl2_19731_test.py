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


_GPU = '#!/bin/sh\necho "Fake GPU"\n'
#: WSL2 can ship the binary on a host with no GPU; a stub like this must read as no GPU.
_NO_GPU_STUB = '#!/bin/sh\necho "NVIDIA-SMI has failed because it could not communicate with the driver" >&2\nexit 9\n'


def _fake_smi(directory, body: str = _GPU) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    smi = directory / "nvidia-smi"
    smi.write_text(body, encoding="utf-8")
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


@_needs_ansible
def test_a_wsl2_stub_with_no_gpu_reads_as_none(tmp_path) -> None:
    _fake_smi(tmp_path / "wsl", _NO_GPU_STUB)
    assert _probe(tmp_path, on_path=False, in_extra=False)["gpu"] is False


@pytest.mark.parametrize("role", ["llm", "backend"])
def test_both_roles_use_the_shared_probe(role: str) -> None:
    source = (_ANSIBLE / "roles" / role / "tasks" / "main.yml").read_text(encoding="utf-8")
    source = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert "_shared/tasks/detect_nvidia_gpu.yml" in source
    assert "nvidia-smi --query" not in source, f"{role} has a bare probe of its own again"
