# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The duplication guard's scope is stated once, and its triggers agree with it (#17377).

`duplication-guard.yml` names its scope in four places: the two scan steps, the
"Explain failure" step and the `paths:` triggers. The first three now read one pair
of job env values, ``MAIN_SCOPE_DIRS`` and ``SLM_SCOPE_DIRS``. The triggers cannot:
GitHub evaluates `on.*.paths` before any env exists. So this test is the agreement
check for that last copy.

A trigger list that drifts from the scan fails silently in one direction: a tree
that is scanned but not a trigger is only measured when some OTHER tree changes,
so a PR adding duplication there alone never runs the guard. #17377 widened the main
scope to `scripts/`, `tools/` and `pipeline-scripts/`; without this, adding them
to the scan and forgetting the triggers would have looked done.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

WORKFLOW = Path(".github/workflows/duplication-guard.yml")

#: jscpd ``-f`` language names, mapped to the file extensions a trigger glob uses.
_LANGUAGE_EXTENSIONS = {"python": {"py"}, "typescript": {"ts"}, "javascript": {"js"}, "vue": {"vue"}}

#: A trigger glob of the shape ``<tree>/**/*.<ext>``.
_TRIGGER = re.compile(r"^(?P<tree>.+)/\*\*/\*\.(?P<ext>[a-z]+)$")


def _document() -> dict:
    return yaml.safe_load((repo_root() / WORKFLOW).read_text(encoding="utf-8"))


def _scope_trees(document: dict) -> set[str]:
    env = document["jobs"][next(iter(document["jobs"]))]["env"]
    return set(env["MAIN_SCOPE_DIRS"].split()) | set(env["SLM_SCOPE_DIRS"].split())


def _scanned_extensions(document: dict) -> set[str]:
    job = document["jobs"][next(iter(document["jobs"]))]
    found: set[str] = set()
    for step in job["steps"]:
        match = re.search(r"-f ([a-z,]+)", step.get("run", ""))
        if match:
            for language in match.group(1).split(","):
                found |= _LANGUAGE_EXTENSIONS[language]
    return found


def disagreements(document: dict, event: str) -> list[str]:
    """Ways *event*'s trigger paths disagree with the scanned scope. Empty means they agree."""
    # PyYAML reads the bare key `on` as boolean True.
    triggers = document[True][event]["paths"]
    trees, extensions, problems = set(), _scanned_extensions(document), []
    for glob in triggers:
        if glob == ".github/workflows/duplication-guard.yml":
            continue
        match = _TRIGGER.match(glob)
        if match is None:
            problems.append(f"{event}: trigger {glob!r} is not of the form <tree>/**/*.<ext>")
            continue
        trees.add(match["tree"])
        if match["ext"] not in extensions:
            problems.append(f"{event}: trigger {glob!r} names an extension jscpd is not asked to scan")
    scope = _scope_trees(document)
    problems += [f"{event}: scanned tree {t!r} has no trigger" for t in sorted(scope - trees)]
    problems += [f"{event}: trigger tree {t!r} is not scanned" for t in sorted(trees - scope)]
    return problems


@pytest.mark.parametrize("event", ["pull_request", "push"])
def test_the_triggers_name_exactly_the_scanned_trees(event: str) -> None:
    problems = disagreements(_document(), event)
    assert not problems, "duplication-guard.yml's triggers and scope disagree:\n  " + "\n  ".join(problems)


def test_the_main_scope_covers_the_repos_own_tooling() -> None:
    """The owner's #17377 decision: the tooling trees are scanned, so a fork there is measured."""
    env = _document()["jobs"][next(iter(_document()["jobs"]))]["env"]
    assert {"scripts", "tools", "pipeline-scripts"} <= set(env["MAIN_SCOPE_DIRS"].split())


def test_the_detector_reports_a_scanned_tree_with_no_trigger() -> None:
    """Contrast: drop one tree's trigger and the comparison must say so, by name."""
    document = _document()
    document[True]["push"]["paths"] = [p for p in document[True]["push"]["paths"] if not p.startswith("tools/")]
    assert "push: scanned tree 'tools' has no trigger" in disagreements(document, "push")


def test_the_detector_reports_a_trigger_for_an_unscanned_tree() -> None:
    document = _document()
    document[True]["pull_request"]["paths"].append("docs/**/*.py")
    assert "pull_request: trigger tree 'docs' is not scanned" in disagreements(document, "pull_request")
