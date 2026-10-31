# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20191: a workflow installs requirements-ci.txt through one action, which frees disk first."""

import re
from pathlib import Path

import pytest
import yaml
from repo_tests._reach import declare

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
ACTION = REPO_ROOT / ".github" / "actions" / "install-ci-requirements" / "action.yml"
_OWN_INSTALL = re.compile(r"pip install\b[^\n]*-r requirements-ci\.txt|requirements-file:\s*requirements-ci\.txt")
_CALLERS = {
    "api-wiring.yml",
    "ci.yml",
    "co-located-smoke.yml",
    "company-os-contract.yml",
    "company-os-workflow-e2e.yml",
    "import-hermeticity-sweep.yml",
    "marker-tests.yml",
    "security.yml",
    "startup-import-smoke.yml",
    "trajectory-eval.yml",
    "verify-generated-types.yml",
}


WORKFLOW_REACH = declare(
    "ci-requirements-one-install-workflows",
    discover=lambda root: sorted((root / ".github" / "workflows").glob("*.y*ml")),
    what="workflow files searched for their own requirements-ci.txt install",
    roots=(".github/workflows",),
    floor=65,  # mid-window; repinned by scripts/repin_reach_floors.py
    growth=10,
)


def _workflows() -> dict[str, str]:
    return {path.name: path.read_text("utf-8") for path in WORKFLOW_REACH.examined(REPO_ROOT)}


def test_no_workflow_installs_the_file_itself() -> None:
    own = sorted(name for name, text in _workflows().items() if _OWN_INSTALL.search(text))
    assert not own, f"use ./.github/actions/install-ci-requirements: {own}"


def test_every_known_caller_uses_the_action() -> None:
    using = {name for name, text in _workflows().items() if "./.github/actions/install-ci-requirements" in text}
    assert using == _CALLERS


def test_the_action_frees_disk_before_installing_and_swallows_nothing() -> None:
    steps = yaml.safe_load(ACTION.read_text("utf-8"))["runs"]["steps"]
    assert steps[0]["uses"] == "./.github/actions/free-disk-space"
    assert "requirements-ci.txt" in steps[1]["run"]
    assert "|| true" not in steps[1]["run"]


@pytest.mark.parametrize(
    ("source", "flagged"),
    [
        ("python -m pip install -r requirements-ci.txt --prefer-binary || true", True),
        ("python -m pip install -c constraints/shared.txt -r requirements-ci.txt", True),
        ("requirements-file: requirements-ci.txt", True),
        ("# requirements-ci.txt, not autobot-backend/requirements.txt", False),
        ("python -m pip install -r autobot-slm-backend/requirements.txt", False),
    ],
)
def test_the_detector_has_both_sides(source: str, flagged: bool) -> None:
    assert bool(_OWN_INSTALL.search(source)) is flagged
