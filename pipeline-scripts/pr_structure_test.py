# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20516: controls for the PR milestone and phase check."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pr_structure  # noqa: E402

M1 = "M1 - Seamless install and consistent docs"
_SCRIPT = Path(__file__).resolve().parent / "pr_structure.py"


def _pull(milestone=M1, labels=("phase:M1.4",), ref="issue-1-x", association="OWNER", kind="User") -> dict:
    return {
        "head": {"ref": ref},
        "author_association": association,
        "user": {"type": kind},
        "milestone": {"title": milestone} if milestone else None,
        "labels": [{"name": name} for name in labels],
    }


def test_a_correct_pr_passes() -> None:
    assert pr_structure.check(_pull()) == []


@pytest.mark.parametrize(
    ("pull", "count"),
    [
        (_pull(milestone=None, labels=()), 2),
        (_pull(milestone=None), 2),
        (_pull(labels=()), 1),
        (_pull(labels=("phase:M2.1",)), 1),
        (_pull(milestone="Backlog"), 2),
    ],
    ids=["neither", "phase-only", "milestone-only", "mismatched-pair", "not-a-goal-milestone"],
)
def test_each_wrong_shape_is_caught(pull: dict, count: int) -> None:
    assert len(pr_structure.check(pull)) == count


@pytest.mark.parametrize(
    "pull",
    [
        _pull(milestone=None, labels=(), ref="train-2026-11-01-88a"),
        _pull(milestone=None, labels=(), association="NONE"),
        _pull(milestone=None, labels=(), association="CONTRIBUTOR"),
        _pull(milestone=None, labels=(), kind="Bot"),
    ],
    ids=["train", "outside", "past-contributor", "bot"],
)
def test_exclusions_ask_nothing(pull: dict) -> None:
    assert pr_structure.check(pull) == []


def test_contrast_a_branch_merely_containing_train_is_still_checked() -> None:
    assert pr_structure.check(_pull(milestone=None, labels=(), ref="issue-1-train-x"))


def _run(tmp_path: Path, pull: dict) -> subprocess.CompletedProcess:
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": pull}), encoding="utf-8")
    env = {**os.environ, "GITHUB_EVENT_PATH": str(event), "GITHUB_TOKEN": "", "GITHUB_REPOSITORY": "o/r"}
    return subprocess.run([sys.executable, str(_SCRIPT)], capture_output=True, text=True, check=False, env=env)


def test_the_script_fails_a_bad_pr_and_passes_a_good_one(tmp_path: Path) -> None:
    bad = _run(tmp_path, _pull(milestone=None, labels=()))
    assert bad.returncode == 1 and "::error::" in bad.stdout
    assert _run(tmp_path, _pull()).returncode == 0


def test_the_workflow_runs_on_every_event_that_changes_the_answer() -> None:
    path = Path(__file__).resolve().parents[1] / ".github/workflows/pr-structure.yml"
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    types = document[True]["pull_request"]["types"]
    assert {"opened", "labeled", "unlabeled", "milestoned", "demilestoned"} <= set(types)
    assert document["permissions"] == {"contents": "read"}


def test_a_pin_lowering_head_opened_with_a_personal_token_is_not_asked() -> None:
    assert pr_structure.check(_pull(milestone=None, labels=(), ref="automation/duplication-pins")) == []


def test_contrast_a_branch_merely_naming_automation_is_still_checked() -> None:
    assert pr_structure.check(_pull(milestone=None, labels=(), ref="issue-1-automation/x"))


def test_the_workflows_sparse_checkout_is_enough_to_run_the_script(tmp_path: Path) -> None:
    """Importing the rules loads the upsert action, and the exclusions need autobot_shared."""
    root = Path(__file__).resolve().parent.parent
    workflow = yaml.safe_load((root / ".github/workflows/pr-structure.yml").read_text(encoding="utf-8"))
    checkout = next(s for s in workflow["jobs"]["pr-structure"]["steps"] if "checkout" in s.get("uses", ""))
    for listed in checkout["with"]["sparse-checkout"].split():
        shutil.copytree(root / listed, tmp_path / listed, ignore=shutil.ignore_patterns("__pycache__"))
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": _pull()}), encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-S", str(tmp_path / "pipeline-scripts/pr_structure.py")],
        capture_output=True,
        text=True,
        check=False,
        env={"GITHUB_EVENT_PATH": str(event)},
    )
    assert done.returncode == 0, done.stderr
