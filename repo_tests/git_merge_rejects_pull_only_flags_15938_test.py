# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`git merge --no-rebase` is not a merge flag, and it fails silently (#15938).

``--rebase`` / ``--no-rebase`` belong to ``git pull``. ``git merge`` has no
rebase mode to disable and rejects the flag outright::

    error: unknown option `no-rebase'

`auto-merge-base-into-parked-branches.yml` passed it, so **every** merge died on
argument parsing — and the `else` arm that caught the failure was labelled
``CONFLICTS``. Measured on the 2026-09-09 02:42 run: ``updated=0
conflicted=11``, job green. A trial of the same eleven branches without the flag
merged five cleanly and hit two real conflicts, so the workflow had never merged
anything in its life.

**Why it survived.** The flag was added *defensively*, against a repo- or
user-level ``pull.rebase`` silently turning the merge into a rebase — a risk
that does not exist, because ``pull.rebase`` governs ``git pull``. So a guard
against an impossible failure disabled the thing it guarded. And the outcome it
produced, "these branches conflict", is exactly what a reader expects from
long-parked branches: plausible, self-explanatory, and wrong.

Two checks, because the defect had two halves and either alone would have let it
through: the flag must not be passed, and a merge that fails **without** a
conflict must not be filed as one.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.lint._scan_helpers import tracked_paths

from ._paths import repo_root

#: Flags that belong to `git pull` and are rejected by `git merge`.
PULL_ONLY = ("--no-rebase", "--rebase")

MERGE_CALL = re.compile(r"\bgit\s+merge\b([^\n;|&]*)")

SCANNED = ("*.sh", "*.yml", "*.yaml", "*.py")

#: This file states the pattern in prose and in its own fixtures.
EXEMPT = {"repo_tests/git_merge_rejects_pull_only_flags_15938_test.py"}

WORKFLOW = ".github/workflows/auto-merge-base-into-parked-branches.yml"


def offending_lines(text: str) -> list[tuple[int, str]]:
    """`git merge` invocations carrying a pull-only flag, ignoring comments."""
    out = []
    for number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        for match in MERGE_CALL.finditer(line):
            args = match.group(1)
            if any(re.search(rf"{re.escape(flag)}\b", args) for flag in PULL_ONLY):
                out.append((number, line.strip()))
                break
    return out


def test_no_tracked_file_passes_a_pull_only_flag_to_git_merge() -> None:
    root = repo_root()
    offenders = []
    for rel in tracked_paths(root, *SCANNED):
        if rel in EXEMPT:
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        offenders += [(rel, n, line) for n, line in offending_lines(text)]

    assert not offenders, "\n".join(
        f"{rel}:{n}: {line}\n"
        "    `--rebase`/`--no-rebase` are `git pull` flags; `git merge` rejects them "
        "with `error: unknown option`. The merge does not happen, and callers that "
        "treat a non-zero exit as a conflict report the branch as unmergeable "
        "instead of reporting themselves as broken (#15938)."
        for rel, n, line in offenders
    )


# ------------------------------------------------------------ the classification
#
# Removing the flag fixes today's instance. What stops the next one is that a
# merge failing for any OTHER reason can no longer be filed as a conflict, so the
# job says "I am broken" rather than "these branches are".


def test_the_parked_branch_job_distinguishes_a_conflict_from_a_failure() -> None:
    text = (repo_root() / WORKFLOW).read_text(encoding="utf-8")
    assert "grep -q '^CONFLICT'" in text, (
        f"{WORKFLOW} must classify a failed merge by looking for git's own CONFLICT "
        "marker. Without that, every non-conflict failure is reported as a conflict, "
        "which is how #15938 stayed green for the life of the file."
    )
    assert "errored+=(" in text, (
        f"{WORKFLOW} must keep non-conflict failures in their own bucket; folding "
        "them into `conflicted` is the defect, not the reporting of it."
    )
    assert re.search(
        r"\$\{#errored\[@\]\} -gt 0 \]; then\s*\n\s+echo \"::error::", text
    ), (
        f"{WORKFLOW} must FAIL when a merge fails without a conflict. A conflict is "
        "information about a branch; a non-conflict failure is a defect in the job, "
        "and a job that cannot fail cannot report one."
    )


# ------------------------------------------------------------ guarding the matcher


def test_the_matcher_catches_the_shape_that_shipped() -> None:
    assert offending_lines('git merge --no-rebase --no-edit "origin/$BASE"')
    assert offending_lines("    if git merge --no-rebase --no-edit x; then")
    assert offending_lines("git merge --rebase foo")


def test_the_matcher_leaves_valid_merges_and_prose_alone() -> None:
    """A false positive here would refuse the fix along with the defect."""
    assert not offending_lines('git merge --no-edit "origin/$BASE"')
    assert not offending_lines("git merge --no-ff --no-commit topic")
    assert not offending_lines("# never pass git merge --no-rebase; it is a pull flag")
    # `git pull --no-rebase` is correct usage and must not be touched.
    assert not offending_lines("git pull --no-rebase origin main")
    # A merge with no flags at all.
    assert not offending_lines("git merge origin/Dev_new_gui")


# ---------------------------------------------------- where a workspace starts
#
# The other half of #15938. `git worktree add -b <branch> <dir>` with no start
# point branches from the main tree's HEAD, so a new workspace silently inherits
# whatever that tree last fetched. Freshness used to be a side effect of having a
# PR: auto-update-pr-branches.yml keeps PR branches current, and before the first
# push there was no mechanism at all.

WORKSPACE = "autobot-backend/services/task_workspace.py"


def test_a_new_workspace_branches_from_a_fetched_base() -> None:
    text = (repo_root() / WORKSPACE).read_text(encoding="utf-8")
    assert "def _fetched_base_ref(" in text, (
        f"{WORKSPACE} must resolve its base ref through a helper that fetches first; "
        "branching from the main tree's HEAD inherits that tree's staleness."
    )
    assert '"git", "worktree", "add", "-b", branch, str(workspace_dir), base_ref' in text, (
        f"{WORKSPACE} must pass an explicit start point to `git worktree add`. "
        "Without one git uses HEAD, which is the defect: the call looks correct and "
        "the branch point is whatever the shared tree happened to be on."
    )
    assert "AUTOBOT_WORKSPACE_BASE_REF" in text, (
        f"{WORKSPACE} must take the base ref from an env-var-backed constant, not a "
        "literal at the call site."
    )


def test_the_base_ref_is_registered_and_distinct_from_the_build_branch() -> None:
    """Two different questions must not share one variable.

    `AUTOBOT_GIT_BRANCH` records the branch this instance was BUILT from;
    `AUTOBOT_WORKSPACE_BASE_REF` says where NEW work starts. Reusing the first
    for the second would be correct today and wrong the moment a deployment runs
    from anything but the base -- the reuse itself is the defect, not the value.
    """
    registry = (repo_root() / "autobot_shared" / "env_registry.py").read_text(encoding="utf-8")
    assert 'name="AUTOBOT_WORKSPACE_BASE_REF"' in registry, (
        "AUTOBOT_WORKSPACE_BASE_REF must be declared in the env registry — an env var "
        "read but never registered is invisible to every tool that enumerates config."
    )
