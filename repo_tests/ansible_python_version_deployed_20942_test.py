# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20942: .python-version must be deployed to the install root.

autobot_shared/python_floor.py reads ``<install root>/.python-version``; without a
task that copies it there every startup logs "unreadable" and uses the fallback.
"""

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_ANSIBLE = _ROOT / "autobot-slm-backend" / "ansible"
_SOURCES = (
    _ANSIBLE / "roles" / "_shared" / "tasks" / "stage_shared_manifests.yml",
    _ANSIBLE / "playbooks" / "update-all-nodes.yml",
)


def _tasks(node) -> list[dict]:
    out: list[dict] = []
    if isinstance(node, list):
        for item in node:
            if isinstance(item, dict):
                out.append(item)
                for key in ("block", "rescue", "always", "tasks"):
                    out.extend(_tasks(item.get(key)))
    return out


def deploys_python_version(path: Path) -> bool:
    """True if a copy task in ``path`` lands ``.python-version`` at base_dir root."""
    for task in _tasks(yaml.safe_load(path.read_text(encoding="utf-8"))):
        copy = task.get("ansible.builtin.copy") or task.get("copy")
        if isinstance(copy, dict) and str(copy.get("src", "")).endswith("/.python-version"):
            return str(copy.get("dest", "")) == "{{ autobot.base_dir }}/.python-version"
    return False


def test_source_file_exists():
    assert (_ROOT / ".python-version").is_file()


def test_every_deploy_path_stages_python_version():
    for path in _SOURCES:
        assert deploys_python_version(path), f"{path.name} does not deploy .python-version (#20942)"


def test_control_detector_rejects_a_file_without_the_task(tmp_path):
    other = tmp_path / "x.yml"
    other.write_text(
        "- ansible.builtin.copy:\n    src: a/constraints/shared.txt\n    dest: '{{ autobot.base_dir }}/c'\n",
        encoding="utf-8",
    )
    assert not deploys_python_version(other)
