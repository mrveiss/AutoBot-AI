# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""scripts/check-frontend-deps-current.sh judges node_modules by content (#22135)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

SCRIPT = repo_root() / "scripts" / "check-frontend-deps-current.sh"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def _workspace(tmp_path: Path, installed: dict[str, str | None]) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "package.json").write_text(json.dumps({"dependencies": {n: "^1" for n in installed}}), encoding="utf-8")
    locked = {f"node_modules/{n}": {"version": "2.0.0"} for n in installed}
    (ws / "package-lock.json").write_text(json.dumps({"packages": locked}), encoding="utf-8")
    for name, version in installed.items():
        if version is not None:
            pkg_dir = ws / "node_modules" / name
            pkg_dir.mkdir(parents=True)
            (pkg_dir / "package.json").write_text(json.dumps({"version": version}), encoding="utf-8")
    return ws


def _run(ws: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(SCRIPT), str(ws)], capture_output=True, text=True, check=False)


def test_matching_install_passes(tmp_path):
    assert _run(_workspace(tmp_path, {"a": "2.0.0"})).returncode == 0


def test_absent_package_fails_and_names_it(tmp_path):
    result = _run(_workspace(tmp_path, {"a": "2.0.0", "reka-ui": None}))
    assert result.returncode == 1
    assert "reka-ui: installed (absent)" in result.stdout
    # The fix command comes before the package list so a head-truncated report still carries it.
    assert result.stdout.index("npm --prefix") < result.stdout.index("reka-ui")


def test_older_version_than_lockfile_fails(tmp_path):
    result = _run(_workspace(tmp_path, {"a": "1.0.0"}))
    assert result.returncode == 1
    assert "a: installed 1.0.0, lockfile 2.0.0" in result.stdout
