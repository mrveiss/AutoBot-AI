# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every enforcing step of the pre-commit gate judges the committed tree, not one a fixer rewrote (#21535).

`pre-commit run` in ``_gate-precommit.yml`` runs fixer hooks (``insert-license``, black, isort, autoflake and the
whitespace fixers) that rewrite files in the CI checkout. The run only warns, so the rewritten tree stayed in
place and the SPDX header step after it read files the hook had just headed: three header-less files reached
``main`` under a green check.

The invariant, read structurally off the job's steps: a step that runs ``pre-commit run`` is followed at once by a
step that restores the tracked tree to ``HEAD``. Adjacency, not "somewhere later", so no enforcing step can sit in
the gap. What this does not prove is that the restore works on a runner: that is the first CI run, where the
header step must read the committed text.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
import yaml
from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_lines

_ROOT = repo_root()
_WORKFLOW = _ROOT / ".github" / "workflows" / "_gate-precommit.yml"
_CONFIG = _ROOT / ".pre-commit-config.yaml"
_JOB = "precommit-config"
_FIXER_HOOK = "insert-license"
_SPDX_STEP = "Enforce SPDX"
_RUNS_PRECOMMIT = re.compile(r"\bpre-commit run\b")
_RESTORES = re.compile(r"\bgit restore\b(?=.*--source=HEAD)(?=.*--staged)(?=.*--worktree)")


def _code(step: dict[str, Any]) -> str:
    """The step's script without its comment lines, so prose naming a command is not the command."""
    return "\n".join(line.text for line in code_lines(str(step.get("run", "")), name="step.sh"))


def runs_precommit(step: dict[str, Any]) -> bool:
    return bool(_RUNS_PRECOMMIT.search(_code(step)))


def restores_tree(step: dict[str, Any]) -> bool:
    return bool(_RESTORES.search(_code(step)))


def unrestored(steps: list[dict[str, Any]]) -> list[str]:
    """Names of steps that run pre-commit and are not directly followed by a restore."""
    return [
        str(step.get("name"))
        for index, step in enumerate(steps)
        if runs_precommit(step) and not (index + 1 < len(steps) and restores_tree(steps[index + 1]))
    ]


@pytest.fixture(scope="module")
def steps() -> list[dict[str, Any]]:
    return yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"][_JOB]["steps"]


def test_the_scan_is_not_vacuous(steps) -> None:
    assert sum(runs_precommit(step) for step in steps) >= 2, "the sweep and the gating run both invoke pre-commit"
    assert any(restores_tree(step) for step in steps)
    assert any(_SPDX_STEP in str(step.get("name")) for step in steps), "the enforcing step this protects exists"


def test_the_fixer_hook_the_gate_runs_still_exists() -> None:
    """If the hook leaves the config this guard's premise is gone and should be revisited, not silently pass."""
    config = yaml.safe_load(_CONFIG.read_text(encoding="utf-8"))
    ids = {hook["id"] for repo in config["repos"] for hook in repo["hooks"]}
    assert _FIXER_HOOK in ids


def test_every_pre_commit_step_is_followed_by_a_restore_of_the_tree(steps) -> None:
    assert unrestored(steps) == []


def test_the_header_step_runs_after_a_restore(steps) -> None:
    names = [str(step.get("name")) for step in steps]
    spdx = next(i for i, name in enumerate(names) if _SPDX_STEP in name)
    assert any(restores_tree(step) for step in steps[:spdx])
    last_precommit = max(i for i, step in enumerate(steps) if runs_precommit(step))
    assert last_precommit < spdx and restores_tree(steps[last_precommit + 1])


def _step(name: str, run: str) -> dict[str, Any]:
    return {"name": name, "run": run}


def test_contrast_a_restore_right_after_is_accepted() -> None:
    steps = [_step("a", "pre-commit run --all-files"), _step("b", "git restore --source=HEAD --staged --worktree -- .")]
    assert unrestored(steps) == []


def test_contrast_a_step_between_the_run_and_the_restore_is_refused() -> None:
    steps = [
        _step("run", "pre-commit run --all-files"),
        _step("enforce", "python3 tools/lint/check_spdx_header.py --all"),
        _step("restore", "git restore --source=HEAD --staged --worktree -- ."),
    ]
    assert unrestored(steps) == ["run"]


def test_contrast_no_restore_at_all_and_a_partial_restore_are_refused() -> None:
    assert unrestored([_step("run", "pre-commit run --from-ref a --to-ref b")]) == ["run"]
    partial = [_step("run", "pre-commit run -a"), _step("r", "git restore -- .")]
    assert unrestored(partial) == ["run"]


def test_contrast_a_comment_naming_the_commands_is_not_the_commands() -> None:
    commented = _step("note", "# pre-commit run is described here\necho done")
    assert not runs_precommit(commented)
    assert not restores_tree(_step("r", "# git restore --source=HEAD --staged --worktree"))
