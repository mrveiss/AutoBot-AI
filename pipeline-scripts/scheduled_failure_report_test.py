# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fixture tests for scheduled_failure_report.py and scheduled_failure_issues.py (#21592).

Discovery, verdict, plan, text, markers and the core sweep decisions. The never-run, person's-issue,
failure-handling and ``main`` cases are in ``scheduled_failure_report_sweep_test.py``, which imports this
file's fakes. No network: a fake API answers from literal fixtures and records every request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest
import scheduled_failure_issues as iss
import scheduled_failure_report as mod

REPO = "example-org/example-repo"
RUN_URL = "https://github.com/example-org/example-repo/actions/runs/{}"
NIGHTLY = mod.ScheduledWorkflow("nightly.yml", "Nightly")
WEEKLY = mod.ScheduledWorkflow("weekly.yml", "Weekly")
UMBRELLA = {"number": 30, "title": "Umbrella", "body": iss.REPORT_MARKER.format(file="umbrella")}


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
FAILING = [run(5, "failure", "2026-11-03T04:00:00Z")]
PASSING = [run(7, "success", "2026-11-05T04:00:00Z")]


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
    ("state", "has_issue", "human", "action"),
    [
        pytest.param("failing", False, False, "open", id="failing-without-issue-opens"),
        pytest.param("failing", True, False, "update", id="failing-with-issue-updates"),
        pytest.param("failing", True, True, "update", id="failing-with-a-persons-issue-comments-there"),
        pytest.param("passing", True, False, "close", id="passing-with-own-issue-closes"),
        pytest.param("passing", True, True, "recovered-note", id="passing-with-a-persons-issue-only-notes"),
        pytest.param("passing", False, False, "none", id="passing-without-issue-is-quiet"),
        pytest.param("never-run", False, False, "none", id="never-run-is-quiet"),
        pytest.param("never-run", True, False, "none", id="never-run-keeps-an-existing-issue"),
        pytest.param("never-fired", False, False, "open", id="never-fired-opens"),
        pytest.param("never-fired", True, False, "update", id="never-fired-updates"),
        pytest.param("inconclusive", True, False, "none", id="inconclusive-keeps-an-existing-issue"),
        pytest.param("inconclusive", False, False, "none", id="inconclusive-is-quiet"),
    ],
)
def test_the_plan_follows_state_and_issue(state: str, has_issue: bool, human: bool, action: str) -> None:
    issue = {"number": 5} if has_issue else None
    assert mod.plan_for(mod.Verdict(state, {"id": 1}), issue, human) == action


@pytest.mark.parametrize(
    ("state", "age", "settled"),
    [
        pytest.param("never-run", 8, "never-fired", id="older-than-the-threshold"),
        pytest.param("never-run", 7, "never-run", id="exactly-the-threshold-is-still-young"),
        pytest.param("never-run", 0, "never-run", id="added-today"),
        pytest.param("never-run", None, "never-run", id="age-unknown-never-escalates"),
        pytest.param("failing", 400, "failing", id="only-a-never-run-workflow-is-settled"),
    ],
)
def test_a_never_run_workflow_becomes_never_fired_only_past_the_threshold(
    state: str, age: Optional[int], settled: str
) -> None:
    assert mod.settle(mod.Verdict(state), age, threshold=7).state == settled


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


def test_the_never_fired_body_says_so_and_carries_the_never_key() -> None:
    body = mod.issue_body(NIGHTLY, None, mod.Failure(), 30)
    assert "<!-- scheduled-failure-run:never -->" in body and "30 days ago" in body and "ever completed" in body


def test_the_title_is_not_the_identity() -> None:
    body = mod.issue_body(NIGHTLY, run(1, "failure", "2026-11-03T04:00:00Z"), mod.Failure())
    renamed = {"number": 3, "title": "anything a person typed", "body": body}
    assert iss.build_targets([renamed], ["nightly.yml"]).own == {"nightly.yml": renamed}
    titled_only = {"number": 4, "title": mod.issue_title(NIGHTLY), "body": "no marker here"}
    assert iss.build_targets([titled_only], ["nightly.yml"]).own == {}


def test_two_own_issues_for_one_workflow_keep_the_lowest_number() -> None:
    body = iss.REPORT_MARKER.format(file="nightly.yml")
    targets = iss.build_targets([{"number": 9, "body": body}, {"number": 4, "body": body}], ["nightly.yml"])
    assert targets.own["nightly.yml"]["number"] == 4


def test_the_umbrella_is_found_by_its_marker_not_by_number() -> None:
    other = {"number": 31, "title": "Umbrella: failing scheduled workflows", "body": "no marker"}
    targets = iss.build_targets([other, UMBRELLA], ["nightly.yml"])
    assert targets.umbrella == UMBRELLA and targets.own == {} and targets.human == {}


def test_events_come_from_the_body_then_the_comments_in_order() -> None:
    issue = {"body": iss.RUN_MARKER.format(key=10)}
    comments = [
        {"body": iss.RUN_MARKER.format(key=11)},
        {"body": "no marker"},
        {"body": None},
        {"body": iss.RECOVERED_MARKER.format(key=12)},
    ]
    events = iss.marker_events(issue, comments)
    assert events == [("run", "10"), ("run", "11"), ("recovered", "12")]
    assert iss.reported_keys(events) == {"10", "11"} and not iss.last_word_is_failure(events)


def tracks(file: str) -> str:
    return iss.TRACKS_MARKER.format(file=file)


def test_a_tracks_marker_anywhere_in_the_body_opts_a_persons_issue_in() -> None:
    tracked = {"number": 50, "title": "audit", "body": f"text\n{tracks('nightly.yml')}\nmore text"}
    targets = iss.build_targets([tracked], ["nightly.yml", "weekly.yml"])
    assert targets.human == {"nightly.yml": tracked} and targets.own == {}


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("nightly.yml is red", id="the-file-name-in-prose"),
        pytest.param("see .github/workflows/nightly.yml", id="the-file-name-with-its-path"),
        pytest.param("`nightly.yml`", id="the-file-name-in-code"),
        pytest.param("<!-- scheduled-failure-tracks:nightly.yml.bak -->", id="a-marker-for-another-file"),
        pytest.param("<!-- scheduled-failure-tracks: nightly.yml -->", id="a-malformed-marker"),
    ],
)
def test_a_mere_mention_does_not_opt_an_issue_in(body: str) -> None:
    item = {"number": 50, "title": "nightly.yml fails", "body": body}
    targets = iss.build_targets([item], ["nightly.yml"])
    assert targets.human == {} and targets.own == {}


def test_a_persons_issue_never_includes_the_umbrella_or_a_file_that_has_an_own_issue() -> None:
    umbrella = {**UMBRELLA, "body": UMBRELLA["body"] + "\n" + tracks("nightly.yml")}
    own = {"number": 41, "title": "own", "body": iss.REPORT_MARKER.format(file="weekly.yml")}
    tracked = {"number": 50, "title": "a", "body": tracks("nightly.yml")}
    also = {"number": 60, "title": "b", "body": tracks("weekly.yml")}
    targets = iss.build_targets([umbrella, own, tracked, also], ["nightly.yml", "weekly.yml"])
    assert targets.human == {"nightly.yml": tracked}  # weekly.yml has an own issue: no person's issue is looked up
    assert targets.own == {"weekly.yml": own}


def test_two_persons_issues_tracking_one_file_keep_the_lowest_number() -> None:
    items = [
        {"number": 70, "title": "x", "body": tracks("nightly.yml")},
        {"number": 50, "title": "y", "body": tracks("nightly.yml")},
    ]
    assert iss.build_targets(items, ["nightly.yml"]).human["nightly.yml"]["number"] == 50


# ---- the sweep -------------------------------------------------------------------------


class FakeApi:
    """Answers from literal fixtures; records every request. Nothing leaves the process."""

    repository = REPO
    api_root = "https://api.example.invalid"
    token = "x"

    def __init__(
        self,
        runs: Dict[str, List[Dict[str, Any]]],
        issues: Optional[List[Dict[str, Any]]] = None,
        umbrella: bool = True,
        milestones: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        self.runs = runs
        self.issues = ([UMBRELLA] if umbrella else []) + (issues or [])
        self.milestones = [{"number": 7, "title": iss.MILESTONE_TITLE}] if milestones is None else milestones
        self.calls: List[Tuple[str, str, Any]] = []

    def request(self, method: str, path: str, payload: Any = None) -> Tuple[int, Any]:
        self.calls.append((method, path, payload))
        if method == "GET" and "/actions/workflows/" in path:
            file = path.split("/actions/workflows/")[1].split("/runs")[0]
            return (200, {"workflow_runs": self.runs[file]}) if file in self.runs else (404, {"message": "Not Found"})
        if method == "GET" and "/milestones?" in path:
            return 200, self.milestones
        if method == "GET" and "/issues?" in path:
            return 200, self.issues if "page=1" in path else []
        if method == "POST" and path.endswith("/issues"):
            return 201, {"number": 900, "id": 9000}
        if method == "POST" and (path.endswith("/comments") or path.endswith("/sub_issues")):
            return 201, {"id": 1}
        return 200, {}

    def run_jobs(self, run_id: int) -> List[Dict[str, Any]]:
        return FAILED_JOBS

    def writes(self) -> List[Tuple[str, str, Any]]:
        return [call for call in self.calls if call[0] != "GET"]

    def count(self, needle: str) -> int:
        return sum(1 for method, path, _ in self.calls if method == "GET" and needle in path)


Comments = Optional[Dict[int, List[Dict[str, Any]]]]


def make_client(api: FakeApi, comments: Comments = None) -> mod.SweepClient:
    return mod.SweepClient(api, comments=lambda number: (comments or {}).get(number, []))


def do_sweep(
    api: FakeApi,
    comments: Comments = None,
    dry_run: bool = False,
    workflows: Optional[List[mod.ScheduledWorkflow]] = None,
    age_of: Optional[Callable[[str], Optional[int]]] = None,
):
    return mod.sweep(make_client(api, comments), workflows or [NIGHTLY], dry_run, age_of)


def own_issue(number: int = 40, key: Any = 1, file: str = "nightly.yml") -> Dict[str, Any]:
    body = iss.REPORT_MARKER.format(file=file) + "\n" + iss.RUN_MARKER.format(key=key)
    return {"number": number, "title": "own", "body": body}


def person_issue(number: int = 50, file: str = "nightly.yml") -> Dict[str, Any]:
    return {"number": number, "title": f"{file} keeps failing", "body": f"a person wrote this\n{tracks(file)}"}


def test_a_failing_workflow_without_an_issue_opens_one_with_the_structure_and_attaches_it() -> None:
    api = FakeApi({"nightly.yml": FAILING})
    outcomes, errors = do_sweep(api)
    assert errors == []
    assert outcomes == [mod.Outcome("nightly.yml", "failing", "open", 900)]
    create, attach = api.writes()
    assert create[1].endswith("/issues")
    assert create[2]["labels"] == ["bug", "ci", iss.PHASE_LABEL] and create[2]["milestone"] == 7
    assert iss.REPORT_MARKER.format(file="nightly.yml") in create[2]["body"] and "Compile" in create[2]["body"]
    assert attach[1].endswith("/issues/30/sub_issues") and attach[2] == {"sub_issue_id": 9000}


def test_the_milestone_is_looked_up_once_per_run_by_title() -> None:
    runs = {"nightly.yml": FAILING, "weekly.yml": FAILING}
    api = FakeApi(runs, milestones=[{"number": 3, "title": "another"}, {"number": 7, "title": iss.MILESTONE_TITLE}])
    outcomes, errors = do_sweep(api, workflows=[NIGHTLY, WEEKLY])
    assert errors == [] and [o.action for o in outcomes] == ["open", "open"]
    assert api.count("/milestones?") == 1


def test_a_missing_umbrella_is_a_problem_and_the_issue_is_still_opened() -> None:
    api = FakeApi({"nightly.yml": FAILING}, umbrella=False)
    outcomes, errors = do_sweep(api)
    assert outcomes[0].action == "open" and any("umbrella" in e for e in errors)
    assert [w[1].endswith("/sub_issues") for w in api.writes()] == [False]


def test_a_missing_milestone_is_a_problem_and_the_issue_is_still_opened_without_one() -> None:
    api = FakeApi({"nightly.yml": FAILING}, milestones=[])
    outcomes, errors = do_sweep(api)
    assert outcomes[0].action == "open" and any("milestone" in e for e in errors)
    assert "milestone" not in api.writes()[0][2]


def test_a_repeat_failure_adds_a_comment_with_the_new_run_to_the_existing_issue() -> None:
    api = FakeApi({"nightly.yml": [run(6, "failure", "2026-11-04T04:00:00Z")]}, [own_issue(key=5)])
    outcomes, _ = do_sweep(api)
    assert outcomes == [mod.Outcome("nightly.yml", "failing", "update", 40)]
    ((method, path, payload),) = api.writes()
    assert (method, path.endswith("/issues/40/comments")) == ("POST", True)
    assert RUN_URL.format(6) in payload["body"] and "failure" in payload["body"] and "Compile" in payload["body"]
    assert "2026-11-04" in payload["body"]


def test_the_same_failing_run_is_never_reported_twice() -> None:
    api = FakeApi({"nightly.yml": FAILING}, [own_issue(key=5)])
    outcomes, _ = do_sweep(api)
    assert outcomes == [mod.Outcome("nightly.yml", "failing", "already-reported", 40)]
    assert api.writes() == []


def test_a_run_reported_in_a_comment_is_not_reported_again() -> None:
    api = FakeApi({"nightly.yml": [run(6, "failure", "2026-11-04T04:00:00Z")]}, [own_issue(key=5)])
    comments = {40: [{"body": iss.RUN_MARKER.format(key=6) + "\nfailed again"}]}
    outcomes, _ = do_sweep(api, comments)
    assert outcomes[0].action == "already-reported"
    assert api.writes() == []


def test_a_passing_latest_run_comments_and_closes_the_own_issue() -> None:
    api = FakeApi({"nightly.yml": PASSING}, [own_issue()])
    outcomes, _ = do_sweep(api)
    assert outcomes == [mod.Outcome("nightly.yml", "passing", "close", 40)]
    comment, patch = api.writes()
    assert comment[1].endswith("/issues/40/comments") and RUN_URL.format(7) in comment[2]["body"]
    assert patch[0] == "PATCH" and patch[1].endswith("/issues/40")
    assert patch[2] == {"state": "closed", "state_reason": "completed"}


def test_a_cancelled_newest_run_leaves_a_failing_issue_open_and_quiet() -> None:
    runs = [run(8, "cancelled", "2026-11-05T04:00:00Z"), run(5, "failure", "2026-11-03T04:00:00Z")]
    api = FakeApi({"nightly.yml": runs}, [own_issue(key=5)])
    outcomes, _ = do_sweep(api)
    assert outcomes[0].action == "already-reported"
    assert api.writes() == []


def test_dry_run_reads_everything_and_writes_nothing() -> None:
    for runs, issues, action in (
        (FAILING, [], "would-open"),
        ([run(6, "failure", "2026-11-04T04:00:00Z")], [own_issue(key=5)], "would-update"),
        (PASSING, [own_issue()], "would-close"),
        (PASSING, [person_issue()], "none"),
    ):
        api = FakeApi({"nightly.yml": runs}, issues)
        outcomes, _ = do_sweep(api, dry_run=True)
        assert outcomes[0].action == action
        assert api.writes() == []


def test_the_run_listing_asks_only_for_completed_scheduled_runs() -> None:
    api = FakeApi({"nightly.yml": []})
    do_sweep(api)
    listing = [path for method, path, _ in api.calls if "/actions/workflows/" in path]
    assert len(listing) == 1
    assert "event=schedule" in listing[0] and "status=completed" in listing[0]
