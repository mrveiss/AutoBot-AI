# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20517: installing the frontend must not rewrite its lockfile, which then reads as drift."""

from __future__ import annotations

import json
import re

from repo_tests._paths import repo_root

_ANSIBLE = "autobot-slm-backend/ansible"
_INSTALL = re.compile(r"cmd:\s*(npm (?:install|i|ci)\b.*)")


def _frontend_installs(path: str) -> list[str]:
    """Every npm install command in the file that runs in the autobot-frontend directory."""
    lines = (repo_root() / path).read_text(encoding="utf-8").splitlines()
    return [
        match.group(1).strip()
        for number, line in enumerate(lines)
        if (match := _INSTALL.search(line)) and lines[number + 1].rstrip().endswith('/autobot-frontend"')
    ]


def test_the_role_installs_the_way_the_updater_does() -> None:
    role = _frontend_installs(f"{_ANSIBLE}/roles/frontend/tasks/main.yml")
    updater = _frontend_installs(f"{_ANSIBLE}/playbooks/update-all-nodes.yml")
    assert role == ["npm ci --ignore-scripts"]
    assert updater == role  # control: the matcher does read the updater's install


def test_the_matcher_sees_the_command_that_rewrote_the_lockfile() -> None:
    assert _INSTALL.search("    cmd: npm install --legacy-peer-deps")
    assert _INSTALL.search("    cmd: npm install esbuild --legacy-peer-deps")


def test_esbuild_still_arrives_from_the_lockfile() -> None:
    """The role's separate esbuild install went away because npm ci already brings it."""
    frontend = repo_root() / "autobot-frontend"
    declared = json.loads((frontend / "package.json").read_text(encoding="utf-8"))
    assert "esbuild" in {**declared.get("dependencies", {}), **declared.get("devDependencies", {})}
    lock = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8"))
    assert "node_modules/esbuild" in lock["packages"]
