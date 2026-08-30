# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The parked-branch drift workflow merges; it never rebases or force-pushes (#15306).

#15306's design rests on one property: a parked branch is usually checked out in
some session's worktree, so its history must not be rewritten. Rebasing or
force-pushing orphans that session's local HEAD and makes its next push
non-fast-forward -- silently, and only discovered by whoever next tries to push.
That property is invisible in review once the file is long, so it is asserted
here instead of trusted.

WHY THIS STRIPS COMMENTS FIRST. The workflow's own header explains at length why
it merges rather than rebases, and why it never forces. A guard that scanned the
raw file would match that prose and fail on the very text documenting the
correct behaviour -- a false positive that trains its reader to ignore it. Only
executable shell survives the strip.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _REPO_ROOT / ".github/workflows/auto-merge-base-into-parked-branches.yml"

# `git rebase` as a command, not the substring: the script legitimately passes
# `git merge --no-rebase`, which is the OPPOSITE of the forbidden operation and
# must not be flagged as it.
_REBASE = re.compile(r"\bgit\s+(?:-\S+\s+)*rebase\b")
# Any force flag on a push, long or short.
_FORCE_PUSH = re.compile(r"\bgit\s+push\b[^\n]*?(?:--force\b|--force-with-lease\b|\s-f\b)")

_PROTECTED = ("Dev_new_gui", "main", "master")


def _shell_bodies() -> list[str]:
    """Every `run:` script in the workflow, with shell comments removed."""
    spec = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    bodies = []
    for job in spec["jobs"].values():
        for step in job.get("steps", []):
            if "run" in step:
                stripped = "\n".join(
                    line for line in step["run"].splitlines()
                    if not line.lstrip().startswith("#")
                )
                bodies.append(stripped)
    return bodies


def test_workflow_exists() -> None:
    """The reach check: every assertion below is vacuous if the file moved."""
    assert _WORKFLOW.is_file(), (
        f"{_WORKFLOW.relative_to(_REPO_ROOT)} is missing. If it was renamed, update this "
        f"guard -- do not delete it: it is the only thing asserting #15306's core property."
    )


def test_never_rebases() -> None:
    for body in _shell_bodies():
        hit = _REBASE.search(body)
        assert hit is None, (
            f"the parked-branch workflow runs `{hit.group(0)}`. It must MERGE, never rebase "
            f"(#15306): these branches are checked out in live sessions' worktrees, and "
            f"rewriting their history orphans those sessions' HEADs."
        )


def test_never_force_pushes() -> None:
    for body in _shell_bodies():
        hit = _FORCE_PUSH.search(body)
        assert hit is None, (
            f"the parked-branch workflow force-pushes: `{hit.group(0)}`. A branch that will "
            f"not merge must be SKIPPED and reported, never overwritten (#15306)."
        )


def test_reach_the_guard_actually_reads_shell() -> None:
    """A guard that parses nothing reports clean over everything.

    Without this, a schema change that stopped yielding `run:` bodies would make
    every assertion above pass by examining an empty list.
    """
    bodies = _shell_bodies()
    assert bodies, "no `run:` scripts parsed out of the workflow; the guard is inspecting nothing"
    joined = "\n".join(bodies)
    assert "git merge" in joined, (
        "the workflow no longer runs `git merge`; either it was rewritten to use another "
        "mechanism (update this guard deliberately) or the parse broke"
    )


def test_protected_branches_are_never_push_targets() -> None:
    """The base and the trunks must never receive one of these merge commits."""
    joined = "\n".join(_shell_bodies())
    for line in joined.splitlines():
        if "git push" not in line:
            continue
        for protected in _PROTECTED:
            assert f"refs/heads/{protected}" not in line, (
                f"the workflow pushes directly to `{protected}`: {line.strip()!r}. "
                f"Protected branches are never targets (#15306)."
            )


def test_does_not_trigger_on_push() -> None:
    """A `push:` trigger would make this fire on its own merge commits, recursively."""
    spec = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    # PyYAML parses a bare `on:` key as the boolean True.
    triggers = spec.get("on", spec.get(True))
    assert triggers is not None, "workflow declares no triggers"
    assert "push" not in triggers, (
        "this workflow must not trigger on `push`: it pushes to branches itself, so a push "
        "trigger would re-fire it on its own merge commits (#15306)."
    )


def test_runs_one_at_a_time() -> None:
    """Concurrent runs would race on the same branches."""
    spec = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert spec.get("concurrency"), (
        "the workflow declares no `concurrency` group; two overlapping scheduled runs would "
        "race on the same branches and could push conflicting merge commits (#15306)."
    )
