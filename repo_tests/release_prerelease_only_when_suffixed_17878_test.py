# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A release is a prerelease only when its version says so (#17878).

Every release was flagged a prerelease, so GitHub's `releases/latest` pointed at a version thousands of
commits old. These run the workflow's real shell from its YAML.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

_WORKFLOW = ".github/workflows/release.yml"


def _steps() -> list[dict]:
    doc = yaml.safe_load((repo_root() / _WORKFLOW).read_text(encoding="utf-8"))
    return [step for job in doc["jobs"].values() for step in job.get("steps", [])]


def _step(step_id: str) -> dict:
    return next(step for step in _steps() if step.get("id") == step_id)


def _is_prerelease(version: str, tmp_path: Path) -> str:
    out = tmp_path / "out"
    env = {"VERSION": version, "GITHUB_OUTPUT": str(out)}
    subprocess.run(["bash", "-c", _step("kind")["run"]], check=True, env=env)
    return out.read_text(encoding="utf-8").strip()


@pytest.mark.parametrize(
    ("version", "flag"),
    [
        ("v0.11.0", "false"),
        ("v1.0.0", "false"),
        ("v1.0.0-rc1", "true"),
        ("v1.0.0-rc.2", "true"),
        ("v1.0.0-beta", "true"),
        ("v1.0.0-beta.3", "true"),
    ],
)
def test_the_flag_follows_the_version(version: str, flag: str, tmp_path: Path) -> None:
    assert _is_prerelease(version, tmp_path) == f"prerelease={flag}"


def test_the_release_takes_the_decided_flag_not_a_constant() -> None:
    release = next(step for step in _steps() if step.get("name") == "Create GitHub Release")
    assert release["with"]["prerelease"] == "${{ steps.kind.outputs.prerelease }}"


def _version_pattern() -> str:
    return re.search(r"=~ (\^v\S+\$) \]\]", _step("check")["run"]).group(1)


@pytest.mark.parametrize(
    ("version", "accepted"),
    [
        ("v1.2.3", True),
        ("v1.2.3-rc1", True),
        ("v1.2.3-beta.2", True),
        ("v1.2.3-alpha", False),
        ("1.2.3", False),
        ("", False),
    ],
)
def test_the_version_gate_lets_a_real_prerelease_through(version: str, accepted: bool) -> None:
    script = f'[[ "$V" =~ {_version_pattern()} ]]'
    done = subprocess.run(["bash", "-c", script], env={"V": version}, check=False)
    assert (done.returncode == 0) is accepted


def test_the_monotonic_guard_survives_a_suffixed_highest_tag() -> None:
    line = next(ln for ln in _step("check")["run"].splitlines() if "PAT" in ln and "NEXT_VERSION=" in ln)
    script = f'IFS=. read -r MAJ MIN PAT <<<"1.0.0-rc1"\n{line}\necho "$NEXT_VERSION"'
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True)
    assert done.stdout.strip() == "v1.0.1"
