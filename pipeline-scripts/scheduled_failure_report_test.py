# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fixture tests for scheduled_failure_report.py (#21592): discovery, verdict, plan, text and the sweep.

No network: a fake API answers from literal fixtures and records every request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
import scheduled_failure_report as mod

REPO = "example-org/example-repo"
RUN_URL = "https://github.com/example-org/example-repo/actions/runs/{}"
NIGHTLY = mod.ScheduledWorkflow("nightly.yml", "Nightly")


def run(run_id: int, conclusion: Optional[str], created: str, status: str = "completed") -> Dict[str, Any]:
    return {
        "id": run_id,
        "conclusion": conclusion,
        "status": status,
        "created_at": created,
        "run_started_at": created,
        "html_url": RUN_URL.format(run_id),
    }


FAILED_JOBS = [
    {"name": "lint", "conclusion": "success", "steps": [{"name": "Checkout", "conclusion": "success"}]},
    {
        "name": "build",
        "conclusion": "failure",
        "steps": [
            {"name": "Set up job", "conclusion": "success"},
            {"name": "Compile", "conclusion": "failure"},
            {"name": "Upload", "conclusion": "skipped"},
        ],
    },
]


# ---- discovery -------------------------------------------------------------------------


def _plant(root: Path, name: str, text: str) -> None:
    (root / name).write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param("name: A\non:\n  schedule:\n    - cron: '0 1 * * *'\n", True, id="map-with-bare-on-key"),
        pytest.param("name: A\n'on':\n  schedule:\n    - cron: '0 1 * * *'\n", True, id="map-with-quoted-on-key"),
        pytest.param(
            "on:\n  push:\n    branches: [main]\n  schedule:\n    - cron: '5 4 * * 1'\n  workflow_dispatch:\n",
            True,
            id="schedule-among-other-events",
        ),
        pytest.param("on: schedule\njobs: {}\n", False, id="string-form-has-no-cron"),
        pytest.param("on: [push, schedule]\njobs: {}\n", False, id="list-form-has-no-cron"),
        pytest.param("on: push\njobs: {}\n", False, id="string-form-other-event"),
        pytest.param("on:\n  schedule: []\n", False, id="empty-schedule-list"),
        pytest.param("on:\n  schedule:\n    # - cron: '0 1 * * *'\n  push:\n", False, id="cron-commented-out"),
        pytest.param("on:\n  workflow_call:\n", False, id="reusable-workflow"),
        pytest.param("jobs: {}\n", False, id="no-trigger-at-all"),
    ],
)
def test_a_workflow_is_scheduled_only_when_its_on_map_carries_a_cron(tmp_path: Path, text: str, expected: bool) -> None:
    _plant(tmp_path, "w.yml", text)
    found, problems = mod.scan_workflows(tmp_path)
    assert (len(found) == 1) is expected
    assert problems == []


def test_discovery_reads_both_extensions_names_the_workflow_and_falls_back_to_the_file_stem(tmp_path: Path) -> None:
    cron = "on:\n  schedule:\n    - cron: '0 1 * * *'\n"
    _plant(tmp_path, "b.yaml", cron)
    _plant(tmp_path, "a.yml", f"name: Alpha job\n{cron}")
    _plant(tmp_path, "c.yml", "on: push\n")
    assert mod.scheduled_workflows(tmp_path) == [
        mod.ScheduledWorkflow("a.yml", "Alpha job"),
        mod.ScheduledWorkflow("b.yaml", "b"),
    ]


def test_an_unparseable_workflow_is_reported_not_skipped(tmp_path: Path) -> None:
    _plant(tmp_path, "broken.yml", "on: [unclosed\n")
    found, problems = mod.scan_workflows(tmp_path)
    assert found == []
    assert len(problems) == 1 and problems[0].startswith("broken.yml:")


def test_the_real_workflow_directory_yields_scheduled_workflows() -> None:
    found, problems = mod.scan_workflows()
    assert problems == []
    assert "scheduled-failure-report.yml" in {wf.file for wf in found}


# ---- verdict and plan ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("runs", "state", "decisive_id"),
    [
        pytest.param([run(1, "success", "2026-11-01T01:00:00Z")], "passing", 1, id="success"),
        pytest.param([run(1, "failure", "2026-11-01T01:00:00Z")], "failing", 1, id="failure"),
        pytest.param([run(1, "timed_out", "2026-11-01T01:00:00Z")], "failing", 1, id="timed-out-fails"),
        pytest.param([run(1, "startup_failure", "2026-11-01T01:00:00Z")], "failing", 1, id="startup-failure-fails"),
        pytest.param(
            [run(2, "cancelled", "2026-11-02T01:00:00Z"), run(1, "failure", "2026-11-01T01:00:00Z")],
            "failing",
            1,
            id="cancelled-newest-defers-to-older-failure",
        ),
        pytest.param(
            [run(2, "skipped", "2026-11-02T01:00:00Z"), run(1, "success", "2026-11-01T01:00:00Z")],
            "passing",
            1,
            id="skipped-newest-defers-to-older-success",
        ),
        pytest.param(
            [run(1, "success", "2026-11-01T01:00:00Z"), run(2, "failure", "2026-11-02T01:00:00Z")],
            "failing",
            2,
            id="newest-by-date-not-by-list-position",
        ),
        pytest.param(
            [run(2, "cancelled", "2026-11-02T01:00:00Z"), run(1, "skipped", "2026-11-01T01:00:00Z")],
            "inconclusive",
            None,
            id="nothing-decisive",
        ),
        pytest.param([], "never-run", None, id="never-run"),
    ],
)
def test_the_newest_decisive_completed_run_sets_the_state(
    runs: List[Dict[str, Any]], state: str, decisive_id: Optional[int]
) -> None:
    verdict = mod.verdict_of(runs)
    assert verdict.state == state
    assert (verdict.run or {}).get("id") == decisive_id


@pytest.mark.parametrize(
    ("state", "has_issue", "action"),
    [
        pytest.param("failing", False, "open", id="failing-without-issue-opens"),
        pytest.param("failing", True, "update", id="failing-with-issue-updates"),
        pytest.param("passing", True, "close", id="passing-with-issue-closes"),
        pytest.param("passing", False, "none", id="passing-without-issue-is-quiet"),
        pytest.param("never-run", False, "none", id="never-run-is-quiet"),
        pytest.param("never-run", True, "none", id="never-run-keeps-an-existing-issue"),
        pytest.param("inconclusive", True, "none", id="inconclusive-keeps-an-existing-issue"),
        pytest.param("inconclusive", False, "none", id="inconclusive-is-quiet"),
    ],
)
def test_the_plan_follows_state_and_issue(state: str, has_issue: bool, action: str) -> None:
    issue = {"number": 5} if has_issue else None
    assert mod.plan_for(mod.Verdict(state, {"id": 1}), issue) == action


def test_the_first_failing_job_and_step_are_named() -> None:
    assert mod.first_failure(FAILED_JOBS) == mod.Failure("build", "Compile")


def test_a_run_that_started_no_job_says_so() -> None:
    assert mod.first_failure([]).job == mod.NO_JOB_STARTED


def test_a_failed_job_without_a_failed_step_keeps_the_job_name() -> None:
    jobs = [{"name": "build", "conclusion": "timed_out", "steps": [{"name": "Compile", "conclusion": "cancelled"}]}]
    assert mod.first_failure(jobs) == mod.Failure("build", mod.NOT_DETERMINED)


# ---- text and markers ------------------------------------------------------------------


def test_the_issue_body_carries_the_markers_and_the_facts_and_nothing_internal() -> None:
    failed = run(77, "failure", "2026-11-03T04:05:06Z")
    body = mod.issue_body(NIGHTLY, failed, mod.Failure("build", "Compile"))
    assert body.splitlines()[0] == "<!-- scheduled-failure-report:nightly.yml -->"
    assert "<!-- scheduled-failure-run:77 -->" in body
    facts = (
        "Nightly",
        ".github/workflows/nightly.yml",
        RUN_URL.format(77),
        "failure",
        "2026-11-03",
        "build",
        "Compile",
    )
    assert [fact for fact in facts if fact not in body] == []
    assert "/home/" not in body and "/opt/" not in body


def test_the_title_is_not_the_identity() -> None:
    body = mod.issue_body(NIGHTLY, run(1, "failure", "2026-11-03T04:00:00Z"), mod.Failure())
    renamed = {"number": 3, "title": "anything a person typed", "body": body}
    assert mod.issues_by_workflow([renamed]) == {"nightly.yml": renamed}
    titled_only = {"number": 4, "title": mod.issue_title(NIGHTLY), "body": "no marker here"}
    assert mod.issues_by_workflow([titled_only]) == {}


def test_two_issues_for_one_workflow_keep_the_lowest_number() -> None:
    body = mod.REPORT_MARKER.format(file="nightly.yml")
    issues = [{"number": 9, "body": body}, {"number": 4, "body": body}]
    assert mod.issues_by_workflow(issues)["nightly.yml"]["number"] == 4


def test_reported_run_ids_come_from_the_body_and_the_comments() -> None:
    issue = {"body": mod.RUN_MARKER.format(run_id=10)}
    comments = [{"body": mod.RUN_MARKER.format(run_id=11)}, {"body": "no marker"}, {"body": None}]
    assert mod.reported_run_ids(issue, comments) == {10, 11}


# ---- the sweep -------------------------------------------------------------------------


class FakeApi:
    """Answers from literal fixtures; records every request. Nothing leaves the process."""

    repository = REPO
    api_root = "https://api.example.invalid"
    token = "x"

    def __init__(self, runs: Dict[str, List[Dict[str, Any]]], issues: Optional[List[Dict[str, Any]]] = None) -> None:
        self.runs = runs
        self.issues = issues or []
        self.calls: List[Tuple[str, str, Any]] = []

    def request(self, method: str, path: str, payload: Any = None) -> Tuple[int, Any]:
        self.calls.append((method, path, payload))
        if method == "GET" and "/actions/workflows/" in path:
            file = path.split("/actions/workflows/")[1].split("/runs")[0]
            return (200, {"workflow_runs": self.runs[file]}) if file in self.runs else (404, {"message": "Not Found"})
        if method == "GET" and "/issues?" in path:
            return 200, self.issues if "page=1" in path else []
        if method == "POST" and path.endswith("/issues"):
            return 201, {"number": 900}
        if method == "POST" and path.endswith("/comments"):
            return 201, {"id": 1}
        return 200, {}

    def run_jobs(self, run_id: int) -> List[Dict[str, Any]]:
        return FAILED_JOBS

    def writes(self) -> List[Tuple[str, str, Any]]:
        return [call for call in self.calls if call[0] != "GET"]


def _sweep(api: FakeApi, comments: Optional[Dict[int, List[Dict[str, Any]]]] = None, dry_run: bool = False):
    client = mod.SweepClient(api, comments=lambda number: (comments or {}).get(number, []))
    return mod.sweep(client, [NIGHTLY], dry_run)


def _open_issue(number: int = 40, run_id: int = 1) -> Dict[str, Any]:
    body = mod.REPORT_MARKER.format(file="nightly.yml") + "\n" + mod.RUN_MARKER.format(run_id=run_id)
    return {"number": number, "body": body}


def test_a_failing_workflow_without_an_issue_opens_one_with_the_report_labels() -> None:
    api = FakeApi({"nightly.yml": [run(5, "failure", "2026-11-03T04:00:00Z")]})
    outcomes, errors = _sweep(api)
    assert errors == []
    assert outcomes == [mod.Outcome("nightly.yml", "failing", "open", 900)]
    ((method, path, payload),) = api.writes()
    assert (method, path.endswith("/issues")) == ("POST", True)
    assert payload["labels"] == ["bug", "ci"]
    assert mod.REPORT_MARKER.format(file="nightly.yml") in payload["body"]
    assert "Compile" in payload["body"]


def test_a_repeat_failure_adds_a_comment_with_the_new_run_to_the_existing_issue() -> None:
    api = FakeApi({"nightly.yml": [run(6, "failure", "2026-11-04T04:00:00Z")]}, [_open_issue(run_id=5)])
    outcomes, _ = _sweep(api)
    assert outcomes == [mod.Outcome("nightly.yml", "failing", "update", 40)]
    ((method, path, payload),) = api.writes()
    assert (method, path.endswith("/issues/40/comments")) == ("POST", True)
    assert RUN_URL.format(6) in payload["body"] and "failure" in payload["body"] and "Compile" in payload["body"]
    assert "2026-11-04" in payload["body"]


def test_the_same_failing_run_is_never_reported_twice() -> None:
    api = FakeApi({"nightly.yml": [run(5, "failure", "2026-11-03T04:00:00Z")]}, [_open_issue(run_id=5)])
    outcomes, _ = _sweep(api)
    assert outcomes == [mod.Outcome("nightly.yml", "failing", "already-reported", 40)]
    assert api.writes() == []


def test_a_run_reported_in_a_comment_is_not_reported_again() -> None:
    api = FakeApi({"nightly.yml": [run(6, "failure", "2026-11-04T04:00:00Z")]}, [_open_issue(run_id=5)])
    comments = {40: [{"body": mod.RUN_MARKER.format(run_id=6) + "\nfailed again"}]}
    outcomes, _ = _sweep(api, comments)
    assert outcomes[0].action == "already-reported"
    assert api.writes() == []


def test_a_passing_latest_run_comments_and_closes_the_issue() -> None:
    api = FakeApi({"nightly.yml": [run(7, "success", "2026-11-05T04:00:00Z")]}, [_open_issue()])
    outcomes, _ = _sweep(api)
    assert outcomes == [mod.Outcome("nightly.yml", "passing", "close", 40)]
    comment, patch = api.writes()
    assert comment[1].endswith("/issues/40/comments") and RUN_URL.format(7) in comment[2]["body"]
    assert patch[0] == "PATCH" and patch[1].endswith("/issues/40")
    assert patch[2] == {"state": "closed", "state_reason": "completed"}


def test_a_cancelled_newest_run_leaves_a_failing_issue_open_and_quiet() -> None:
    runs = [run(8, "cancelled", "2026-11-05T04:00:00Z"), run(5, "failure", "2026-11-03T04:00:00Z")]
    api = FakeApi({"nightly.yml": runs}, [_open_issue(run_id=5)])
    outcomes, _ = _sweep(api)
    assert outcomes[0].action == "already-reported"
    assert api.writes() == []


def test_a_workflow_that_never_ran_is_neither_opened_nor_an_error() -> None:
    for runs in ({"nightly.yml": []}, {}):
        api = FakeApi(runs)
        outcomes, errors = _sweep(api)
        assert outcomes == [mod.Outcome("nightly.yml", "never-run", "none", None)]
        assert errors == [] and api.writes() == []


def test_dry_run_reads_everything_and_writes_nothing() -> None:
    for runs, issues, action in (
        ([run(5, "failure", "2026-11-03T04:00:00Z")], [], "would-open"),
        ([run(6, "failure", "2026-11-04T04:00:00Z")], [_open_issue(run_id=5)], "would-update"),
        ([run(7, "success", "2026-11-05T04:00:00Z")], [_open_issue()], "would-close"),
    ):
        api = FakeApi({"nightly.yml": runs}, issues)
        outcomes, _ = _sweep(api, dry_run=True)
        assert outcomes[0].action == action
        assert api.writes() == []


def test_the_run_listing_asks_only_for_completed_scheduled_runs() -> None:
    api = FakeApi({"nightly.yml": []})
    _sweep(api)
    listing = [path for method, path, _ in api.calls if "/actions/workflows/" in path]
    assert len(listing) == 1
    assert "event=schedule" in listing[0] and "status=completed" in listing[0]


def test_a_listing_failure_is_reported_and_the_other_workflows_still_run() -> None:
    class Flaky(FakeApi):
        def request(self, method: str, path: str, payload: Any = None) -> Tuple[int, Any]:
            if "/actions/workflows/nightly.yml/" in path:
                return 500, {"message": "boom"}
            return super().request(method, path, payload)

    other = mod.ScheduledWorkflow("weekly.yml", "Weekly")
    api = Flaky({"weekly.yml": [run(9, "success", "2026-11-05T04:00:00Z")]})
    outcomes, errors = mod.sweep(mod.SweepClient(api, comments=lambda n: []), [NIGHTLY, other], False)
    assert [o.file for o in outcomes] == ["weekly.yml"]
    assert len(errors) == 1 and errors[0].startswith("nightly.yml:")
