# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The issue-triage workflow runs ONE run at a time, not one per issue event (#21854).

Owner rule 2026-11-19: "there should be only one; one is enough". A per-issue concurrency
group let a bulk edit fan out into one run per event (185 runs in a day, up to 12 for one
issue). The design pinned here: one WORKFLOW-WIDE group with ``cancel-in-progress: false``
(one running, at most one pending, a newer pending replaces the older), no job-level group,
and no event-level ``if`` on a job - a run whose jobs all skip still takes the pending slot
and would displace a run that did the work. Nothing is lost because every run covers what
changed since the last successful run (pipeline-scripts/issue_structure.py ``window``).

Measurement discipline (MEASUREMENT_DISCIPLINE.md): the detector is checked against
fixtures that must fail, and the real workflow is checked to still be the file it names,
so a renamed job or key cannot turn the guard into an empty pass.
"""

from __future__ import annotations

import copy

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml", reason="PyYAML needed to parse the workflow")

_WORKFLOW = repo_root() / ".github" / "workflows" / "issue-triage.yml"
_PER_EVENT_MARKERS = ("github.event.issue", "github.event.action", "github.event.label", "inputs.")

GOOD = {
    "concurrency": {"group": "issue-triage-single-run", "cancel-in-progress": False},
    "jobs": {"window": {"runs-on": "x"}, "triage": {"needs": "window", "runs-on": "x"}},
}


def violations(doc: dict) -> list[str]:
    """Why this workflow could still run more than one triage run, or lose an event."""
    found = []
    group = doc.get("concurrency")
    if not isinstance(group, dict):
        return ["no workflow-level concurrency group"]
    name = str(group.get("group", ""))
    if not name or any(marker in name for marker in _PER_EVENT_MARKERS):
        found.append(f"group {name!r} is empty or varies per event")
    if group.get("cancel-in-progress") is not False:
        found.append("cancel-in-progress must be false: a cancelled run loses its events")
    for job, body in doc.get("jobs", {}).items():
        if "concurrency" in body:
            found.append(f"job {job} has its own concurrency group")
        if any(marker in str(body.get("if", "")) for marker in _PER_EVENT_MARKERS):
            found.append(f"job {job} skips on an event-level condition")
    return found


def _variant(**changes) -> dict:
    doc = copy.deepcopy(GOOD)
    for key, value in changes.items():
        doc[key] = value
    return doc


def test_the_good_fixture_passes():
    assert violations(GOOD) == []


@pytest.mark.parametrize(
    "doc, expected",
    [
        (_variant(concurrency=None), "no workflow-level"),
        (
            _variant(concurrency={"group": "t-${{ github.event.issue.number }}", "cancel-in-progress": False}),
            "varies per event",
        ),
        (
            _variant(concurrency={"group": "t-${{ inputs.issue || 'sweep' }}", "cancel-in-progress": False}),
            "varies per event",
        ),
        (_variant(concurrency={"group": "g", "cancel-in-progress": True}), "cancel-in-progress"),
        (_variant(concurrency={"group": "g"}), "cancel-in-progress"),
        (
            _variant(jobs={"j": {"concurrency": {"group": "j-${{ github.event.issue.number }}"}}}),
            "own concurrency group",
        ),
        (_variant(jobs={"j": {"if": "github.event.action == 'opened'"}}), "event-level condition"),
        (_variant(jobs={"j": {"if": "startsWith(github.event.label.name, 'phase:')"}}), "event-level condition"),
    ],
)
def test_each_way_to_fan_out_or_lose_an_event_is_caught(doc, expected):
    assert any(expected in line for line in violations(doc)), violations(doc)


def test_the_real_workflow_is_the_file_the_guard_names():
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert {"window", "triage", "structure", "wording"} <= set(doc["jobs"]), "the guard no longer binds to the jobs"
    assert "issues" in (doc.get(True) or doc.get("on"))


def test_the_real_workflow_runs_one_run_at_a_time():
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert violations(doc) == []
