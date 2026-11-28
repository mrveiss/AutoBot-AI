# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No workflow or action reads a field only a ``pull_request`` event carries (#20825).

A dispatched run has no ``pull_request`` payload. Every such expression evaluates to EMPTY there and reads as a
clean ``false``: a label test that never matches, a draft test that never trips, a base that is the empty
string. Nothing fails, which is the defect. A fact about the pull request comes from the ``pr-context`` action
(looked up live); the only places the literal ``'pull_request'`` may remain are the ``event:`` argument of the
gate-verdict action (``... && 'pull_request' || github.event_name``) and a comment.
"""

from __future__ import annotations

import re

import pytest
from repo_tests._pr_dispatch import action_files, load, strings, workflow_files

#: pattern name -> regex over the strings a workflow evaluates or runs.
FORBIDDEN = {
    "pull_request payload": re.compile(r"github\.event\.pull_request\b"),
    "head_ref": re.compile(r"github\.head_ref\b"),
    "base_ref": re.compile(r"github\.base_ref\b"),
    "event action": re.compile(r"github\.event\.action\b"),
    "event label": re.compile(r"github\.event\.label\b"),
    "event name compared with pull_request": re.compile(r"event_name\s*[!=]=\s*['\"]?pull_request"),
    "event name compared (shell)": re.compile(r"\"\$\{?(?:EVENT|EVENT_NAME|GITHUB_EVENT_NAME)\}?\"\s*[!=]=?\s*['\"]?pull_request"),
    "actor compared": re.compile(r"github\.actor\s*[!=]="),
    "merge ref parent": re.compile(r"HEAD\^[12]\b"),
}


def findings(text: str) -> list[str]:
    """The forbidden patterns in *text*, shell comment lines excluded (a comment may explain what was removed)."""
    code = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    return sorted(name for name, pattern in FORBIDDEN.items() if pattern.search(code))


def _scan() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in [*workflow_files(), *action_files()]:
        hits = sorted({name for s in strings(load(path)) for name in findings(s)})
        if hits:
            found[path.parent.name + "/" + path.name] = hits
    return found


def test_the_population_is_every_workflow_and_action() -> None:
    assert len(workflow_files()) > 60 and len(action_files()) > 8
    assert sum(1 for p in workflow_files() for _ in strings(load(p))) > 5000, "the scan read almost nothing"


def test_no_pull_request_only_field_is_left() -> None:
    assert _scan() == {}


@pytest.mark.parametrize(
    ("expression", "name"),
    [
        ("${{ github.event.pull_request.number }}", "pull_request payload"),
        ("${{ contains(github.event.pull_request.labels.*.name, 'land-next') }}", "pull_request payload"),
        ("ref: ${{ github.head_ref }}", "head_ref"),
        ("BASE_REF: ${{ github.base_ref }}", "base_ref"),
        ("${{ github.event.action == 'labeled' }}", "event action"),
        ("${{ github.event.label.name != 'land-next' }}", "event label"),
        ("${{ github.event_name == 'pull_request' }}", "event name compared with pull_request"),
        ("${{ github.event_name != 'pull_request' || x }}", "event name compared with pull_request"),
        ('if [ "${EVENT}" = "pull_request" ]; then', "event name compared (shell)"),
        ("${{ github.actor == 'dependabot[bot]' }}", "actor compared"),
        ("git diff HEAD^1 HEAD", "merge ref parent"),
    ],
)
def test_control_each_pattern_is_caught(expression: str, name: str) -> None:
    assert name in findings(expression), (expression, findings(expression))


@pytest.mark.parametrize(
    "expression",
    [
        "${{ needs.changes.outputs.is_pr == 'true' && 'pull_request' || github.event_name }}",
        "username: ${{ github.actor }}",
        "${{ inputs.pr_number != '' }}",
        "${{ steps.pr.outputs.admitted == 'true' }}",
    ],
)
def test_control_the_allowed_forms_are_not_flagged(expression: str) -> None:
    assert findings(expression) == []
