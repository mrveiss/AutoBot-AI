#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for scripts/check_script_exec_bits.py (#13355).

The checker's whole value is that it fires only on a real mismatch. Its first
draft matched any backtick-wrapped path and reported six prose mentions —
``see `scripts/format.sh` for the wrapper`` and similar. A checker that is
wrong on correct work gets ignored, so the discrimination between *naming* a
script and *running* one is what these tests pin.

Run: python3 -m pytest scripts/check_script_exec_bits_test.py
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent / "check_script_exec_bits.py"
_spec = importlib.util.spec_from_file_location("check_script_exec_bits", _MODULE_PATH)
checker = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(checker)  # type: ignore[union-attr]


# --------------------------------------------------------------- invocations


@pytest.mark.parametrize(
    "line",
    [
        "scripts/start-services.sh start",
        "  scripts/start-services.sh restart backend",
        "$ scripts/cleanup-worktrees.sh --dry-run",
        "Bulk: `scripts/cleanup-worktrees.sh --dry-run` then something",
        './scripts/gh-pr-update-body.sh $PR "body"',
        "scripts/start-services.sh",
    ],
)
def test_recognises_an_invocation(line):
    hits = {m.group(1) for m in checker._INVOCATION_WITH_ARGS.finditer(line)}
    alone = checker._INVOCATION_ALONE.match(line)
    if alone:
        hits.add(alone.group(1))
    assert hits, f"should be read as running a script: {line!r}"


# ------------------------------------------------------------ mere mentions


@pytest.mark.parametrize(
    "line",
    [
        "- **`scripts/cleanup-worktrees.sh`** prunes stale worktrees and branches",
        "`scripts/format.sh` wrapper + make targets; Python 3.14 settings pinned",
        "- `scripts/setup_daily_health_check.sh` - Configures daily cron job",
        "Safety guards (shared in `scripts/lib/branch-guards.sh`, tested by ...)",
        "A convenience wrapper is available at `scripts/gh-pr-update-body.sh`:",
    ],
)
def test_ignores_a_bare_mention(line):
    """Naming a file is not running it — this is what the first draft got wrong."""
    hits = {m.group(1) for m in checker._INVOCATION_WITH_ARGS.finditer(line)}
    alone = checker._INVOCATION_ALONE.match(line)
    if alone:
        hits.add(alone.group(1))
    assert not hits, f"should NOT be read as running a script: {line!r}"


# ------------------------------------------------------ interpreter-prefixed


@pytest.mark.parametrize(
    "line",
    [
        "bash scripts/format.sh --check",
        "bash scripts/lib/branch-guards_test.sh",
        "sh scripts/format.sh path/to/file.py",
        "source scripts/lib/branch-guards.sh",
        "# shellcheck source=scripts/lib/branch-guards.sh",
    ],
)
def test_ignores_interpreter_prefixed_and_directives(line):
    """A script handed to an interpreter needs no exec bit — 644 is correct there."""
    assert checker._INTERPRETED.search(line) or checker._DIRECTIVE.search(line), line


# ------------------------------------------------------------- end to end


# Neutralise the ambient git config (#13668). Without this the fixture inherits
# whatever the developer or runner has set globally — `commit.gpgsign = true`
# alone made every test here fail — and `core.hooksPath` / `init.templateDir`
# could reach into the throwaway repo.
_GIT_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}


def _init_repo(root: Path) -> None:
    """A throwaway git repo — the checker reads modes from the index, not the FS."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=_GIT_ENV)


def _stage_all(root: Path) -> None:
    """Stage only. ``git ls-files`` reads the index, so committing adds nothing
    but failure modes (signing, hooks, identity) the checker does not care about."""
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=_GIT_ENV)


def _mark_executable(root: Path, relpath: str) -> None:
    """Set the exec bit *in the index*, independent of the tmpdir filesystem.

    ``chmod`` only works if git detects ``core.fileMode=true`` there; this
    repo's own config has it false, so a runner with TMPDIR on such a
    filesystem would fail for a purely environmental reason — the exact class
    of failure this PR exists to remove. It is also the command the checker's
    own error message tells people to run.
    """
    subprocess.run(["git", "update-index", "--chmod=+x", relpath], cwd=root, check=True, env=_GIT_ENV)


def test_a_documented_invocation_of_a_non_executable_script_is_reported(tmp_path):
    """The defect the checker exists to catch, against a fixture (#13668).

    Built as its own git repo rather than asserting on this one: the live-tree
    form could not distinguish "the checker is broken" from "someone edited an
    unrelated doc", so it failed for reasons that had nothing to do with it.
    """
    _init_repo(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "deploy.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Run it with ./scripts/deploy.sh now\n", encoding="utf-8")
    _stage_all(tmp_path)

    problems = checker.find_disagreements(tmp_path)

    assert len(problems) == 1, problems
    assert "scripts/deploy.sh" in problems[0]


def test_an_executable_script_is_not_reported(tmp_path):
    """Same documented invocation, exec bit set — must be silent."""
    _init_repo(tmp_path)
    (tmp_path / "scripts").mkdir()
    script = tmp_path / "scripts" / "deploy.sh"
    script.write_text("#!/bin/bash\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Run it with ./scripts/deploy.sh now\n", encoding="utf-8")
    _stage_all(tmp_path)
    _mark_executable(tmp_path, "scripts/deploy.sh")

    # Pin the reason: without this the assertion below would also hold if the
    # doc regex simply stopped matching.
    assert checker._is_executable(script, tmp_path)
    assert checker.find_disagreements(tmp_path) == []


def test_an_interpreter_prefixed_invocation_is_not_reported(tmp_path):
    """`bash scripts/x.sh` needs no exec bit — 644 is correct there."""
    _init_repo(tmp_path)
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "deploy.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("Run: bash scripts/deploy.sh\n", encoding="utf-8")
    _stage_all(tmp_path)

    assert checker.find_disagreements(tmp_path) == []


@pytest.mark.integration
def test_repository_is_currently_clean():
    """Audit of THIS tree, deselected by ci.yml's marker filter (#13668).

    Kept because it is genuinely useful to run deliberately, but it asserts on
    live repository state: any PR adding a documented invocation of a script
    without its exec bit fails it, while the checker itself is correct and
    untouched. As a per-PR gate that is a red check nobody caused, which is how
    people learn to ignore red checks. The three fixture tests above are what
    actually guard the checker.
    """
    problems = checker.find_disagreements()
    assert problems == [], "\n".join(problems[:10])


def test_archival_files_are_not_scanned():
    """A changelog records what someone once ran; it is not an instruction."""
    assert "CHANGELOG.md" in checker._ARCHIVAL
    assert ".session/" in checker._ARCHIVAL
