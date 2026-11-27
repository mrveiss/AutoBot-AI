# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The stylelint gate is whole-tree and blocking (#17567); changed-file lists skip deletions (#17571).

#17571: ``git diff --name-only`` reports a DELETED file's path, and a per-file tool handed that
list answers ``NoFilesFoundError`` (stylelint exits 123) *before* linting any file that exists.
``stylelint-tokens.yml`` hit it and ``continue-on-error`` hid it as an ordinary red badge.

#17567 removed the cause for that workflow: the gate no longer lints "the files this PR
changed", it lints each project's whole tree and blocks. A tree has no deleted paths, and a
gate that cannot fail is not a gate, so the first three tests pin the properties that make it
one. ``import-hermeticity-sweep.yml`` still feeds a changed-file list to a per-file tool, so it
keeps the ``--diff-filter=d`` guard.
"""

from __future__ import annotations

import pytest
import yaml
from repo_tests._paths import repo_root

_WORKFLOWS = repo_root() / ".github" / "workflows"
_STYLELINT = _WORKFLOWS / "stylelint-tokens.yml"

# Whole-tree lint scopes the gate must keep: project directory, glob handed to stylelint.
_TREES = (
    ("autobot-frontend", 'npx stylelint "src/**/*.{vue,css}"'),
    ("autobot-slm-frontend", 'npx stylelint "src/**/*.{vue,css}"'),
)


def _jobs() -> dict:
    return yaml.safe_load(_STYLELINT.read_text(encoding="utf-8"))["jobs"]


def _runs() -> list[tuple[str, str]]:
    """(working-directory, script) of every step that runs a command."""
    return [(s.get("working-directory", ""), s["run"]) for job in _jobs().values() for s in job["steps"] if "run" in s]


def test_the_gate_blocks() -> None:
    """No job or step may be non-blocking: red must mean the PR cannot merge."""
    text = _STYLELINT.read_text(encoding="utf-8")
    assert "continue-on-error" not in text
    assert "stylelint-changed" not in text


@pytest.mark.parametrize(("directory", "command"), _TREES)
def test_each_app_is_linted_whole_tree(directory: str, command: str) -> None:
    """A step in the app's own directory lints its whole `src` tree, not a changed-file list."""
    assert any(wd == directory and command in script for wd, script in _runs())


def test_the_kit_is_linted_whole_tree_without_its_token_source() -> None:
    """`libs/autobot-ui` is listed from git, so a deleted path cannot appear, and contract.css is excluded."""
    scripts = [script for _, script in _runs() if "libs/autobot-ui" in script]
    assert scripts, "no step lints libs/autobot-ui"
    script = scripts[0]
    assert "ls-files" in script
    assert ":!libs/autobot-ui/src/tokens/contract.css" in script
    assert "--config ../libs/autobot-ui/.stylelintrc.json" in script


def test_no_stylelint_step_reads_a_diff() -> None:
    """The gate's population is the tree; a `git diff` list would reintroduce the diff-scoped gate."""
    assert not [script for _, script in _runs() if "git diff" in script]


def test_import_hermeticity_sweep_still_skips_deletions() -> None:
    """The remaining workflow that hands `git diff --name-only` to a per-file tool must filter deletions."""
    text = (_WORKFLOWS / "import-hermeticity-sweep.yml").read_text(encoding="utf-8")
    uses = [ln.strip() for ln in text.splitlines() if "diff --name-only" in ln]
    assert uses, "import-hermeticity-sweep.yml no longer runs `git diff --name-only`; re-derive the population"
    assert all("--diff-filter=d" in ln for ln in uses), uses
