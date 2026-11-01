# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19805: on a GPU host the torch install replaces a CPU build, using the task's real pip flags."""

from __future__ import annotations

import base64
import hashlib
import os
import subprocess
import venv
import zipfile
from pathlib import Path

import yaml
from repo_tests._paths import repo_root

_ROLE = "autobot-slm-backend/ansible/roles/backend"
_GROUP_VARS = "autobot-slm-backend/ansible/inventory/group_vars/all.yml"
_TASK = "Backend | Install CUDA torch requirements"


def _pip_task() -> dict:
    tasks = yaml.safe_load((repo_root() / _ROLE / "tasks/main.yml").read_text(encoding="utf-8"))
    found = [t for t in _walk(tasks) if str(t.get("name", "")).startswith(_TASK)]
    assert len(found) == 1
    return found[0]["ansible.builtin.pip"]


def _walk(tasks: list[dict]):
    for task in tasks:
        yield task
        for key in ("block", "rescue", "always"):
            yield from _walk(task.get(key) or [])


def _wheel(where: Path, version: str) -> None:
    info = f"torch-{version}.dist-info"
    files = {
        f"{info}/METADATA": f"Metadata-Version: 2.1\nName: torch\nVersion: {version}\n",
        f"{info}/WHEEL": "Wheel-Version: 1.0\nGenerator: t\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
    }
    record = [
        f"{n},sha256={base64.urlsafe_b64encode(hashlib.sha256(c.encode()).digest()).rstrip(b'=').decode()},{len(c)}"
        for n, c in files.items()
    ]
    with zipfile.ZipFile(where / f"torch-{version}-py3-none-any.whl", "w") as whl:
        for name, content in files.items():
            whl.writestr(name, content)
        whl.writestr(f"{info}/RECORD", "\n".join([*record, f"{info}/RECORD,,"]) + "\n")


def _installed_after(tmp_path: Path, flags: list[str], installed: str, offered: str) -> str:
    """Install ``installed``, then ask pip for the same pin, with ``offered`` on the index."""
    env_dir = tmp_path / "venv"
    venv.create(env_dir, with_pip=True)
    py = env_dir / "bin/python"
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _wheel(first, installed)
    _wheel(second, offered)
    env = {k: v for k, v in os.environ.items() if not k.startswith("PIP_")}
    base = [str(py), "-m", "pip", "install", "-q", "--no-index", "--disable-pip-version-check"]
    subprocess.run([*base, "--find-links", str(first), "torch==2.14.1"], check=True, env=env)
    subprocess.run([*base, *flags, "--find-links", str(second), "torch==2.14.1"], check=True, env=env)
    show = [str(py), "-c", "import importlib.metadata as m; print(m.version('torch'))"]
    return subprocess.run(show, check=True, capture_output=True, text=True, env=env).stdout.strip()


def _task_flags() -> list[str]:
    """The task's flags, minus --index-url: the test's local directory stands in for the index."""
    return _pip_task()["extra_args"].split(" --index-url ")[0].split()


def test_the_task_pins_the_index_from_the_role_default() -> None:
    assert _pip_task()["extra_args"] == "--upgrade --index-url {{ backend_torch_cuda_index_url }}"
    group_vars = yaml.safe_load((repo_root() / _GROUP_VARS).read_text(encoding="utf-8"))
    assert "https://download.pytorch.org/whl/cu130" in group_vars["backend_torch_cuda_index_url"]


def test_a_cpu_build_is_replaced(tmp_path: Path) -> None:
    assert _installed_after(tmp_path, _task_flags(), "2.14.1+cpu", "2.14.1+cu130") == "2.14.1+cu130"


def test_contrast_without_the_flags_pip_keeps_the_cpu_build(tmp_path: Path) -> None:
    assert _installed_after(tmp_path, [], "2.14.1+cpu", "2.14.1+cu130") == "2.14.1+cpu"


def test_a_cuda_build_already_installed_is_left_alone(tmp_path: Path) -> None:
    assert _installed_after(tmp_path, _task_flags(), "2.14.1+cu130", "2.14.1+cu130") == "2.14.1+cu130"
