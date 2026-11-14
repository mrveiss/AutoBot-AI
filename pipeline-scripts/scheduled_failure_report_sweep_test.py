# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The rest of the sweep's fixture tests (#21592): never-run workflows, a person's issue, failure handling, main.

Shares the fakes of ``scheduled_failure_report_test.py`` (split at the 600-line file ceiling). No network.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import issue_api as ia
import pytest
import scheduled_failure_issues as iss
import scheduled_failure_report as mod
from scheduled_failure_report_test import (
    FAILING,
    NIGHTLY,
    PASSING,
    REPO,
    WEEKLY,
    FakeApi,
    do_sweep,
    own_issue,
    person_issue,
)

# ---- a workflow that never ran ---------------------------------------------------------


def test_a_young_or_undated_never_run_workflow_is_a_warning_line_and_nothing_else() -> None:
    for runs, age in (({"nightly.yml": []}, 2), ({}, 2), ({"nightly.yml": []}, None)):
        api = FakeApi(runs)
        outcomes, errors = do_sweep(api, age_of=lambda file, age=age: age)
        assert [(o.state, o.action, o.issue) for o in outcomes] == [("never-run", "none", None)]
        assert outcomes[0].note.startswith("WARNING") and errors == [] and api.writes() == []
        assert "\tWARNING" in outcomes[0].line()


def test_an_old_never_run_workflow_opens_an_issue_saying_it_never_fired() -> None:
    api = FakeApi({"nightly.yml": []})
    outcomes, errors = do_sweep(api, age_of=lambda file: 30)
    assert errors == [] and [(o.state, o.action) for o in outcomes] == [("never-fired", "open")]
    body = api.writes()[0][2]["body"]
    assert "<!-- scheduled-failure-run:never -->" in body and "30 days ago" in body


def test_a_never_fired_report_is_made_once_and_then_left_alone() -> None:
    api = FakeApi({"nightly.yml": []}, [own_issue(key="never")])
    outcomes, _ = do_sweep(api, age_of=lambda file: 30)
    assert outcomes[0].action == "already-reported" and api.writes() == []


# ---- a person's issue ------------------------------------------------------------------


def test_a_persons_issue_with_the_tracks_marker_gets_the_comment_and_no_issue_is_opened() -> None:
    api = FakeApi({"nightly.yml": FAILING}, [person_issue()])
    outcomes, errors = do_sweep(api)
    assert errors == [] and outcomes == [mod.Outcome("nightly.yml", "failing", "update", 50)]
    ((method, path, payload),) = api.writes()
    assert path.endswith("/issues/50/comments") and "<!-- scheduled-failure-run:5 -->" in payload["body"]
    assert "tracks `nightly.yml`" in payload["body"]


def test_an_issue_that_only_names_the_file_is_not_commented_on_and_the_sweep_opens_its_own() -> None:
    mention = {"number": 50, "title": "nightly.yml keeps failing", "body": "see .github/workflows/nightly.yml"}
    api = FakeApi({"nightly.yml": FAILING}, [mention])
    outcomes, errors = do_sweep(api)
    assert errors == [] and outcomes == [mod.Outcome("nightly.yml", "failing", "open", 900)]
    assert api.writes()[0][1].endswith("/issues") and not any("/issues/50/" in w[1] for w in api.writes())


def test_the_same_run_already_reported_on_a_persons_issue_writes_nothing() -> None:
    api = FakeApi({"nightly.yml": FAILING}, [person_issue()])
    comments = {50: [{"body": iss.RUN_MARKER.format(key=5) + "\nreported"}]}
    outcomes, _ = do_sweep(api, comments)
    assert outcomes[0].action == "already-reported" and api.writes() == []


def test_recovery_on_a_persons_issue_is_one_note_and_never_a_close() -> None:
    api = FakeApi({"nightly.yml": PASSING}, [person_issue()])
    comments = {50: [{"body": iss.RUN_MARKER.format(key=5) + "\nreported"}]}
    outcomes, _ = do_sweep(api, comments)
    assert outcomes == [mod.Outcome("nightly.yml", "passing", "recovered-note", 50)]
    ((method, path, payload),) = api.writes()
    assert method == "POST" and path.endswith("/issues/50/comments")
    assert "passes" in payload["body"] and "<!-- scheduled-failure-recovered:7 -->" in payload["body"]


def test_recovery_is_not_repeated_and_a_passing_workflow_never_noted_on_stays_quiet() -> None:
    noted = {50: [{"body": iss.RUN_MARKER.format(key=5)}, {"body": iss.RECOVERED_MARKER.format(key=7)}]}
    for comments in (noted, {}):
        api = FakeApi({"nightly.yml": PASSING}, [person_issue()])
        outcomes, _ = do_sweep(api, comments)
        assert outcomes[0].action == "none" and api.writes() == []


def test_two_persons_issues_tracking_one_file_comment_on_the_lowest_number_only() -> None:
    api = FakeApi({"nightly.yml": FAILING}, [person_issue(70), person_issue(50)])
    outcomes, _ = do_sweep(api)
    assert outcomes[0].issue == 50 and api.writes()[0][1].endswith("/issues/50/comments")


# ---- failure handling and the issue listing --------------------------------------------


def test_a_listing_failure_is_reported_and_the_other_workflows_still_run() -> None:
    class Flaky(FakeApi):
        def request(self, method: str, path: str, payload: Any = None) -> Tuple[int, Any]:
            if "/actions/workflows/nightly.yml/" in path:
                return 500, {"message": "boom"}
            return super().request(method, path, payload)

    outcomes, errors = do_sweep(Flaky({"weekly.yml": PASSING}), workflows=[NIGHTLY, WEEKLY])
    assert [o.file for o in outcomes] == ["weekly.yml"]
    assert len(errors) == 1 and errors[0].startswith("nightly.yml:")


def _boom(number: int) -> List[Dict[str, Any]]:
    if number == 40:
        raise OSError("connection reset")
    return []


def test_a_comment_read_failure_is_one_workflows_error_not_the_sweeps() -> None:
    runs = {"nightly.yml": FAILING, "weekly.yml": FAILING}
    api = FakeApi(runs, [own_issue(40, 1, "nightly.yml"), own_issue(41, 1, "weekly.yml")])
    outcomes, errors = mod.sweep(mod.SweepClient(api, comments=_boom), [NIGHTLY, WEEKLY], False)
    assert [(o.file, o.action) for o in outcomes] == [("weekly.yml", "update")]
    assert len(errors) == 1 and errors[0].startswith("nightly.yml:") and "OSError" in errors[0]


def test_an_incomplete_issue_listing_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod, "MAX_ISSUE_PAGES", 1)
    crowd = [{"number": 1000 + n, "title": "x", "body": ""} for n in range(100)]
    api = FakeApi({"nightly.yml": FAILING}, crowd)
    with pytest.raises(mod.SweepError, match="partial list"):
        do_sweep(api)
    assert api.writes() == []


class PagedClient:
    repo = REPO

    def __init__(self, pages: List[List[Dict[str, Any]]]) -> None:
        self.pages = pages
        self.paths: List[str] = []

    def call(self, method: str, path: str, payload: Any = None, ok: Tuple[int, ...] = (200,)) -> Any:
        self.paths.append(path)
        return self.pages[len(self.paths) - 1] if len(self.paths) <= len(self.pages) else []


def test_list_issues_drops_pull_requests_keeps_the_filters_and_reports_a_page_cap() -> None:
    pages = [[{"number": 1}, {"number": 2, "pull_request": {}}], [{"number": 3}, {"number": 4}]]
    client = PagedClient(pages)
    items, complete = ia.list_issues(client, {"state": "open", "labels": "bug,ci"}, page_size=2, max_pages=2)
    assert [i["number"] for i in items] == [1, 3, 4] and complete is False
    assert len(client.paths) == 2 and "labels=bug%2Cci" in client.paths[0] and "page=2" in client.paths[1]
    short = PagedClient([[{"number": 1}]])
    assert ia.list_issues(short, {"state": "open"}, page_size=2, max_pages=2) == ([{"number": 1}], True)


# ---- main ------------------------------------------------------------------------------


def _patch_main(monkeypatch: pytest.MonkeyPatch, workflows: List[mod.ScheduledWorkflow], problems: List[str], api: Any):
    monkeypatch.setattr(mod, "scan_workflows", lambda: (workflows, problems))
    monkeypatch.setattr(mod, "build_api", lambda: api)
    monkeypatch.setattr(mod, "git_age_days", lambda file: None)


def test_main_exits_1_when_no_scheduled_workflow_is_found(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_main(monkeypatch, [], [], FakeApi({}))
    assert mod.main([]) == 1


def test_main_exits_1_on_an_unreadable_workflow_but_still_prints_the_table(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _patch_main(monkeypatch, [WEEKLY], ["broken.yml: cannot be read (YAMLError)"], FakeApi({"weekly.yml": PASSING}))
    assert mod.main([]) == 1
    assert "weekly.yml\tpassing\tnone" in capsys.readouterr().out


def test_main_exits_0_on_a_clean_sweep_and_prints_the_table(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _patch_main(monkeypatch, [WEEKLY], [], FakeApi({"weekly.yml": PASSING}))
    assert mod.main([]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "workflow\tstate\taction\tissue\tnote"


def test_main_survives_one_workflows_transport_failure_and_prints_the_rest(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    issues = [own_issue(40, 1, "nightly.yml"), own_issue(41, 1, "weekly.yml")]
    api = FakeApi({"nightly.yml": FAILING, "weekly.yml": PASSING}, issues)
    _patch_main(monkeypatch, [NIGHTLY, WEEKLY], [], api)
    real = mod.SweepClient
    monkeypatch.setattr(mod, "SweepClient", lambda a: real(a, comments=_boom))
    assert mod.main([]) == 1
    assert "weekly.yml\tpassing\tclose\t#41" in capsys.readouterr().out
