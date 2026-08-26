# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every lint-tool version is pinned twice; this keeps the two copies equal (#15134).

``.github/workflows/code-quality.yml`` installs exact versions and says they
"match .pre-commit-config.yaml". Nothing checked that. The two files can drift,
and the drift is invisible in the worst direction: the local hook passes on one
version while the required CI context runs another, so a developer's green run
means less than it reads.

The mypy pin is the one this issue arrived through. ``mypy autobot_shared/`` is
a **required** context, and moving it is a deliberate act -- but a bump landing
in only one of the two files is not a decision, it is an accident. This makes
that accident fail with the two versions named.

The set of stub packages installed alongside mypy is checked the same way: a
type checker with different stubs is a different type checker, so the hook and
the gate must be handed the same ones.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CODE_QUALITY = REPO_ROOT / ".github" / "workflows" / "code-quality.yml"
PRE_COMMIT = REPO_ROOT / ".pre-commit-config.yaml"

#: pre-commit repo slug -> the distribution name the CI workflow pip-installs.
#: Only tools pinned in both places belong here; anything else is not a parity
#: claim and must not be invented into one.
TOOL_BY_PRE_COMMIT_REPO = {
    "psf/black": "black",
    "pycqa/isort": "isort",
    "pycqa/flake8": "flake8",
    "pycqa/autoflake": "autoflake",
    "pre-commit/mirrors-mypy": "mypy",
    "pycqa/bandit": "bandit",
}

#: A pip requirement pinned to an exact version, extras tolerated:
#: ``black==26.3.1``, ``'bandit[toml]==1.9.4'``, ``mypy==1.16.0 \``.
_PINNED = re.compile(r"([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?==([0-9][A-Za-z0-9.]*)")


def _ci_pins() -> dict[str, str]:
    """Exact versions ``code-quality.yml`` pip-installs, keyed by distribution."""
    text = CODE_QUALITY.read_text(encoding="utf-8")
    return {name.lower(): version for name, version in _PINNED.findall(text)}


def _pre_commit_pins() -> dict[str, str]:
    """Exact versions ``.pre-commit-config.yaml`` pins, keyed by distribution."""
    config = yaml.safe_load(PRE_COMMIT.read_text(encoding="utf-8"))
    pins: dict[str, str] = {}
    for repo in config.get("repos", []):
        url = str(repo.get("repo", ""))
        slug = "/".join(url.rstrip("/").split("/")[-2:]).lower()
        tool = TOOL_BY_PRE_COMMIT_REPO.get(slug)
        if tool is not None:
            pins[tool] = str(repo.get("rev", "")).lstrip("v")
    return pins


def _pre_commit_mypy_stub_sets() -> list[set[str]]:
    """``additional_dependencies`` of each mypy hook, one set per hook."""
    config = yaml.safe_load(PRE_COMMIT.read_text(encoding="utf-8"))
    out: list[set[str]] = []
    for repo in config.get("repos", []):
        if "mirrors-mypy" not in str(repo.get("repo", "")):
            continue
        for hook in repo.get("hooks", []):
            if hook.get("id") == "mypy":
                out.append({str(dep).strip().lower() for dep in hook.get("additional_dependencies", [])})
    return out


def _ci_mypy_stub_set() -> set[str]:
    """Packages installed next to mypy in the workflow's mypy install step.

    Read from the continued ``pip install`` block the ``mypy==`` line opens, so
    the unrelated formatter pins in the step above are not swept in.
    """
    lines = CODE_QUALITY.read_text(encoding="utf-8").splitlines()
    start = next((i for i, line in enumerate(lines) if "mypy==" in line), None)
    if start is None:
        return set()
    collected: set[str] = set()
    continued = lines[start].rstrip().endswith("\\")
    for line in lines[start + 1 :]:
        if not continued:
            break
        candidate = line.strip().rstrip("\\").strip()
        continued = line.rstrip().endswith("\\")
        if candidate:
            collected.add(candidate.lower())
    return collected


CI_PINS = _ci_pins()
PRE_COMMIT_PINS = _pre_commit_pins()
SHARED_TOOLS = sorted(set(CI_PINS) & set(PRE_COMMIT_PINS))


def test_the_sweep_found_tools_to_compare():
    """An empty enumeration would make every parametrised case below vacuous.

    Both files are checked in, so finding nothing means the parsing broke, not
    that the repo stopped pinning anything.
    """
    assert CI_PINS, f"no pinned versions parsed from {CODE_QUALITY.name}"
    assert PRE_COMMIT_PINS, f"no pinned revs parsed from {PRE_COMMIT.name}"
    assert SHARED_TOOLS, "no tool is pinned in both files -- the parity claim cannot be checked"


def test_mypy_is_among_the_tools_compared():
    """The required type gate is the pin this test exists for; never let it drop out."""
    assert (
        "mypy" in SHARED_TOOLS
    ), f"mypy is not pinned in both files: CI={CI_PINS.get('mypy')}, hook={PRE_COMMIT_PINS.get('mypy')}"


@pytest.mark.parametrize("tool", SHARED_TOOLS)
def test_ci_and_pre_commit_pin_the_same_version(tool):
    """The local hook and the CI gate must run the same checker."""
    assert CI_PINS[tool] == PRE_COMMIT_PINS[tool], (
        f"{tool} is pinned to {CI_PINS[tool]} in {CODE_QUALITY.name} but "
        f"{PRE_COMMIT_PINS[tool]} in {PRE_COMMIT.name}. Bump both, or neither."
    )


def test_every_mypy_hook_gets_the_stubs_ci_installs():
    """Different stubs make a different checker, whatever the version says."""
    hook_sets = _pre_commit_mypy_stub_sets()
    ci_stubs = _ci_mypy_stub_set()

    assert hook_sets, "no mypy hook found in .pre-commit-config.yaml"
    assert ci_stubs, "no stub packages parsed from the workflow's mypy install step"

    for index, hook_stubs in enumerate(hook_sets):
        assert hook_stubs == ci_stubs, (
            f"mypy hook #{index} installs {sorted(hook_stubs)} while "
            f"{CODE_QUALITY.name} installs {sorted(ci_stubs)}"
        )
