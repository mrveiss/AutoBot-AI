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

# Step-level `if` may read inputs.issue (the manual re-check) but never the triggering event.
_EVENT_ONLY_MARKERS = ("github.event.issue", "github.event.action", "github.event.label")
_WINDOWED = ("triage", "structure", "wording")

GOOD = {
    "concurrency": {"group": "issue-triage-single-run", "cancel-in-progress": False},
    "jobs": {
        "window": {"runs-on": "x"},
        "triage": {"needs": "window", "runs-on": "x", "steps": [{"run": "x"}]},
        "structure": {"needs": "window", "runs-on": "x", "steps": [{"if": "inputs.issue != ''", "run": "x"}]},
        "wording": {"needs": ["window"], "runs-on": "x"},
    },
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
        for step in body.get("steps", []):
            if any(marker in str(step.get("if", "")) for marker in _EVENT_ONLY_MARKERS):
                found.append(f"job {job} has a step that skips on an event-level condition")
        needs = body.get("needs", [])
        if job in _WINDOWED and "window" not in ([needs] if isinstance(needs, str) else needs):
            found.append(f"job {job} does not need the window job, so it would read only its own event")
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
        (_variant(jobs={"j": {"steps": [{"if": "github.event.action == 'edited'"}]}}), "step that skips"),
        (
            _variant(jobs={"triage": {"needs": "window"}, "structure": {"needs": "window"}, "wording": {}}),
            "job wording does not need",
        ),
        (
            _variant(jobs={"triage": {}, "structure": {"needs": "window"}, "wording": {"needs": "window"}}),
            "job triage does not need",
        ),
        (
            _variant(jobs={"triage": {"needs": "window"}, "structure": {"needs": "x"}, "wording": {"needs": "window"}}),
            "job structure does not need",
        ),
        (_variant(jobs={"j": {"if": "startsWith(github.event.label.name, 'phase:')"}}), "event-level condition"),
    ],
)
def test_each_way_to_fan_out_or_lose_an_event_is_caught(doc, expected):
    assert any(expected in line for line in violations(doc)), violations(doc)


def test_the_real_workflow_is_the_file_the_guard_names():
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert {"window", "triage", "structure", "wording"} <= set(doc["jobs"]), "the guard no longer binds to the jobs"
    assert "issues" in (doc.get(True) or doc.get("on"))


def cursor_violations(doc: dict, prefix: str) -> list[str]:
    """Why the window could not advance (or would advance past unfinished work)."""
    job = doc.get("jobs", {}).get("cursor")
    if job is None:
        return ["no cursor job: the window never advances"]
    found = []
    needs = job.get("needs", [])
    missing = set(_WINDOWED + ("window",)) - set([needs] if isinstance(needs, str) else needs)
    if missing:
        found.append(f"cursor job does not need {sorted(missing)}, so it can succeed past a failed job")
    if not str(job.get("name", "")).startswith(prefix):
        found.append(f"cursor job name does not start with {prefix!r}, so last_success_cursor cannot find it")
    if "if" in job:
        found.append("cursor job has an `if`: it must run exactly when every job it needs succeeded")
    return found


_PREFIX = "Window cursor "
_CURSOR_JOB = {"name": _PREFIX + "${{ needs.window.outputs.until }}", "needs": ["window", *_WINDOWED]}


def _with_cursor(**changes) -> dict:
    doc = copy.deepcopy(GOOD)
    doc["jobs"]["cursor"] = {**_CURSOR_JOB, **changes}
    return doc


def test_the_good_cursor_job_passes():
    assert cursor_violations(_with_cursor(), _PREFIX) == []


@pytest.mark.parametrize(
    "doc, expected",
    [
        (GOOD, "no cursor job"),
        (_with_cursor(needs=["window", "triage", "structure"]), "wording"),
        (_with_cursor(needs="window"), "structure"),
        (_with_cursor(name="Cursor ${{ needs.window.outputs.until }}"), "name does not start"),
        (_with_cursor(**{"if": "always()"}), "has an `if`"),
    ],
)
def test_each_way_the_cursor_can_break_is_caught(doc, expected):
    assert any(expected in line for line in cursor_violations(doc, _PREFIX)), cursor_violations(doc, _PREFIX)


def test_the_real_cursor_job_matches_the_script_that_reads_it():
    import sys

    sys.path.insert(0, str(repo_root() / "pipeline-scripts"))
    import issue_structure

    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert issue_structure.CURSOR_JOB_PREFIX == _PREFIX
    assert cursor_violations(doc, issue_structure.CURSOR_JOB_PREFIX) == []


def test_the_real_workflow_runs_one_run_at_a_time():
    doc = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert violations(doc) == []
