# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dependency change detection must span the whole deployment (#15430).

`update-all-nodes.yml` decides whether to run `npm ci` / `pip install` by
diffing the tree for manifest changes. It used to diff ``HEAD~1..HEAD`` — a
one-commit window — while a deploy moves the installed tree from
``.deployed_commit`` to HEAD, which is usually many commits.

That mismatch took `/slm/` down. The `package.json` bump was **11 commits**
behind HEAD, so the one-commit window saw no manifest change, `npm ci` was
skipped, and the build ran against a `node_modules` that no longer satisfied
`package.json`. The build failed, vite had already emptied `dist/`, and nginx
answered 403 for every path under `/slm/`.

The failure mode is timing-shaped, which is what made it look like a race: the
same commit deploys cleanly when it happens to be HEAD and breaks silently the
moment anything lands on top of it.

These tests read the playbook as data. They cannot run ansible, so they assert
the two properties that made the outage possible:

* the diff base is the deployed commit, not a fixed offset from HEAD;
* an unknown base installs rather than skips.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PLAYBOOK = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "playbooks" / "update-all-nodes.yml"


def _text() -> str:
    return _PLAYBOOK.read_text(encoding="utf-8")


def _tasks() -> list[dict]:
    document = yaml.safe_load(_text())
    found: list[dict] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            if "name" in node and any(k for k in node if k != "name"):
                found.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    return found


def test_the_playbook_this_guard_reads_is_present() -> None:
    assert _PLAYBOOK.is_file(), f"{_PLAYBOOK} is missing — this guard is pinned to the wrong path"
    assert len(_tasks()) > 50, "the playbook parsed to too few tasks — the walk is not reaching it"


def test_dependency_diffs_do_not_use_a_fixed_offset_from_head() -> None:
    """`HEAD~1..HEAD` cannot see a bump merged before the last commit."""
    offenders = [
        line.strip()
        for line in _text().splitlines()
        if re.search(r"diff --name-only", line) or re.search(r"prev_commit\.stdout", line)
    ]
    fixed_offset = [line for line in offenders if "prev_commit" in line or "HEAD~" in line]

    assert not fixed_offset, (
        "dependency diff still uses a fixed offset from HEAD (#15430); it must diff from the "
        "deployed commit, which is the span the sync actually applies:\n  " + "\n  ".join(fixed_offset)
    )


def test_dependency_diffs_are_based_on_the_deployed_commit() -> None:
    text = _text()

    assert "deps_diff_base" in text, "no deps_diff_base fact — the diff has no deployment-spanning base"
    assert ".deployed_commit" in text, "the diff base is not read from the .deployed_commit marker"

    diff_lines = [line for line in text.splitlines() if "diff --name-only" in line]
    assert diff_lines, "no dependency diff found at all — this guard is asserting nothing"

    # The base is on the line after `diff --name-only` in these folded scalars.
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "diff --name-only" in line:
            base_line = lines[index + 1]
            assert (
                "deps_diff_base" in base_line
            ), f"dependency diff at line {index + 1} does not use deps_diff_base: {base_line.strip()}"


def test_an_unknown_deployed_commit_installs_rather_than_skips() -> None:
    """Skipping an install is what takes a service down; a redundant one costs time.

    When the marker is missing, unreadable or blank there is no way to prove
    what is installed, so the flags must not resolve to "nothing changed".
    """
    tasks = {task["name"]: task for task in _tasks() if isinstance(task.get("name"), str)}

    flag_task = next(
        (task for name, task in tasks.items() if "Set dependency change flags" in name),
        None,
    )
    assert flag_task is not None, "no dependency-flag task found"

    facts = flag_task.get("set_fact", {})
    for flag in ("python_deps_changed", "node_deps_changed"):
        expression = str(facts.get(flag, ""))
        assert expression, f"{flag} is not set"
        assert "deps_diff_base" in expression and "length == 0" in expression, (
            f"{flag} does not fall back to True when the deployed commit is unknown (#15430): " f"{expression}"
        )


def test_an_already_drifted_install_is_detected_without_a_manifest_change() -> None:
    """A commit diff cannot see an install that is already stale (#15430).

    The host that went down is exactly that case: the bump sits *behind* the
    deployed commit, so no future span will contain it and the build would fail
    on every subsequent deploy. `npm ls` exits non-zero when node_modules does
    not satisfy package.json — the invariant that actually matters — so the
    flag must consider it too, not only the diff.
    """
    tasks = {t["name"]: t for t in _tasks() if isinstance(t.get("name"), str)}

    assert any("installed node tree" in name for name in tasks), (
        "nothing checks whether the installed tree satisfies package.json, so a host that has "
        "already drifted can never recover on its own (#15430)"
    )

    flag_task = next((t for n, t in tasks.items() if "Set dependency change flags" in n), None)
    assert flag_task is not None
    expression = str(flag_task.get("set_fact", {}).get("node_deps_changed", ""))
    assert "node_tree_check" in expression, (
        "node_deps_changed ignores the installed-tree check, so it still only answers "
        f"'did a manifest change in this span': {expression}"
    )


def _staged_publish_tasks() -> tuple[Path, list[dict]]:
    """The task file this playbook delegates its frontend publish to (#15557).

    The staged build used to be spelled out in update-all-nodes.yml, and three
    other entry points carried an unstaged copy of the same step. #15557 moved
    the logic into a shared task file and pointed all four at it, so this guard
    follows the include rather than asserting on the playbook's own text — the
    property is where the logic is, not where it used to be. The include target
    is resolved from the playbook, so renaming the shared file fails here too.
    """
    included = [
        task[key]
        for task in _tasks()
        for key in ("ansible.builtin.include_tasks", "include_tasks")
        if isinstance(task.get(key), str) and "build_publish_slm_frontend" in task[key]
    ]
    assert len(included) == 1, (
        "update-all-nodes.yml no longer delegates its SLM frontend build to exactly one shared "
        f"task file (found {included!r}) — a build outside the shared staged publish can empty "
        "the served dist/ (#15430, #15557)"
    )
    shared = (_PLAYBOOK.parent / included[0]).resolve()
    assert shared.is_file(), f"the shared staged-publish task file is missing: {shared}"
    document = yaml.safe_load(shared.read_text(encoding="utf-8"))
    return shared, [task for task in document if isinstance(task, dict)]


def test_a_failed_frontend_build_cannot_publish_an_empty_bundle() -> None:
    """The outage was a failed build leaving dist/ empty behind nginx."""
    shared, tasks = _staged_publish_tasks()

    assert "dist.staging" in shared.read_text(encoding="utf-8"), (
        "the frontend build still writes straight into the served directory (#15430) — "
        "a failed build empties it and every /slm/ path answers 403"
    )

    names = [task["name"] for task in tasks if isinstance(task.get("name"), str)]
    assert len(names) >= 5, (
        f"the shared staged publish carries only {len(names)} named tasks — build, failure gate, "
        "entrypoint check, refusal, rotate and publish are six steps, so the extraction collapsed"
    )
    assert any("no index.html" in name for name in names), "nothing refuses to publish a bundle without an index.html"
    assert any("build failed" in name for name in names), "a failed build does not fail the play with its own stderr"
