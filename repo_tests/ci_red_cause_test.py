# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15139 — a red check must name WHICH of its causes produced it.

Three non-code conditions and one real one render as the same red tile:

* a run that never obtained a runner (zero executed steps),
* toolchain provisioning failing (the first failing step is the setup action),
* a superseded run (``conclusion: cancelled``), and
* an actual test failure.

The first two are re-queueable and the last must never be, so the classifier is
only useful if it is right about which is which. These tests pin all four, and
pin the direction it fails in when it cannot tell: ``undetermined`` grades as a
REAL failure, because re-queueing a genuine test failure until it merges is the
unsurvivable error.

The vacuity tests exist because the naive version of this tool reads ``steps``
off ``GET /commits/{sha}/check-runs``, which has no ``steps`` array at all, and
therefore sees "zero steps executed" on every red check ever. A classifier that
can pass by classifying nothing is worse than none.
"""

import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "pipeline-scripts" / "ci_red_cause.py"

SHA = "8d3fa7d22af3dba8728665f9ff73c1c38c8f5498"
REPO = "mrveiss/AutoBot-AI"


def _load():
    spec = importlib.util.spec_from_file_location("ci_red_cause", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rc():
    return _load()


def _step(number: int, name: str, conclusion) -> Dict[str, Any]:
    return {"number": number, "name": name, "conclusion": conclusion, "status": "completed"}


def _check(**overrides) -> Dict[str, Any]:
    check = {
        "id": 98783580325,
        "name": "python-suite shard 12/12",
        "status": "completed",
        "conclusion": "failure",
        "app": {"slug": "github-actions"},
        "html_url": "https://example.invalid/job",
    }
    check.update(overrides)
    return check


class _FakeApi:
    """Records the paths asked for, so a test can prove the jobs endpoint was used."""

    def __init__(self, responses: Dict[str, Tuple[int, Any]], default=(404, None)):
        self.responses = responses
        self.default = default
        self.repository = REPO
        self.calls: List[str] = []

    def request(self, method: str, path: str):
        self.calls.append(path)
        for fragment, response in self.responses.items():
            if fragment in path:
                return response
        return self.default


def _checks_response(checks: List[Dict[str, Any]]) -> Tuple[int, Any]:
    return 200, {"total_count": len(checks), "check_runs": checks}


# --------------------------------------------------------------------------
# The three causes, told apart.  One test per class, all against step lists
# shaped like the real payloads recorded on the issue.
# --------------------------------------------------------------------------


def test_zero_executed_steps_is_runner_starvation(rc):
    """Run 32984154162: status queued, jobs: [], not a single step executed."""
    steps = [_step(n, f"step {n}", None) for n in range(1, 15)]
    cause, detail = rc.classify_steps(steps)
    assert cause == rc.CAUSE_STARVATION
    assert "0 of 14" in detail
    assert cause in rc.INFRASTRUCTURE_CAUSES
    assert cause not in rc.REAL_FAILURE_CAUSES


def test_setup_action_failure_is_provisioning(rc):
    """Job 98783580325: 9 of 14 steps ran, step 4 was the setup action."""
    steps = [
        _step(1, "Set up job", "success"),
        _step(2, "Run actions/checkout@v7", "success"),
        _step(3, "Prepare", "success"),
        _step(4, "Run ./.github/actions/setup-python-suite", "failure"),
        _step(9, "Run unit tests — slm-backend", "failure"),
    ]
    cause, detail = rc.classify_steps(steps)
    assert cause == rc.CAUSE_PROVISIONING
    assert "setup-python-suite" in detail
    assert cause in rc.INFRASTRUCTURE_CAUSES
    assert cause not in rc.REAL_FAILURE_CAUSES


def test_test_step_failure_is_a_real_failure(rc):
    steps = [
        _step(1, "Set up job", "success"),
        _step(2, "Run ./.github/actions/setup-python-suite", "success"),
        _step(3, "Run unit tests — slm-backend", "failure"),
    ]
    cause, detail = rc.classify_steps(steps)
    assert cause == rc.CAUSE_TEST
    assert "unit tests" in detail
    assert cause in rc.REAL_FAILURE_CAUSES
    assert cause not in rc.INFRASTRUCTURE_CAUSES


def test_downstream_test_failure_does_not_mask_the_setup_failure(rc):
    """
    The LAST failing step in job 98783580325 is a test step, and reading it
    would call a provisioning outage a code defect. Only the FIRST one is
    evidence.
    """
    steps = [
        _step(4, "Run ./.github/actions/setup-python-suite", "failure"),
        _step(9, "Run unit tests — slm-backend", "failure"),
    ]
    assert rc.first_failing_step(steps)["number"] == 4
    assert rc.classify_steps(steps)[0] == rc.CAUSE_PROVISIONING


def test_cancelled_is_superseded_not_a_failure_and_not_requeueable(rc):
    """Check run 98236533493 — a newer push retired it. `gh pr checks` says `fail`."""
    cause, detail, ran, total = rc.classify_job_payload(_check(conclusion="cancelled"), None)
    assert cause == rc.CAUSE_SUPERSEDED
    assert "fresh run" in detail
    assert cause not in rc.REAL_FAILURE_CAUSES
    assert cause not in rc.INFRASTRUCTURE_CAUSES
    assert (ran, total) == (None, None)


# --------------------------------------------------------------------------
# Fail-safe: everything unknowable grades as a real failure.
# --------------------------------------------------------------------------


def test_absent_steps_array_is_undetermined_never_starvation(rc):
    """
    THE bug this tool exists to prevent. A check-runs list element has no
    ``steps``; a classifier that reads it as "zero steps executed" calls every
    genuine red a starved runner and re-queues it.
    """
    cause, detail, ran, total = rc.classify_job_payload(_check(), {"id": 1, "conclusion": "failure"})
    assert cause == rc.CAUSE_UNDETERMINED
    assert "no 'steps' array" in detail
    assert cause in rc.REAL_FAILURE_CAUSES
    assert cause not in rc.INFRASTRUCTURE_CAUSES
    assert (ran, total) == (None, None)


def test_unreachable_jobs_endpoint_is_undetermined(rc):
    cause, _, _, _ = rc.classify_job_payload(_check(), None, fetch_error="jobs endpoint unreachable")
    assert cause == rc.CAUSE_UNDETERMINED
    assert cause in rc.REAL_FAILURE_CAUSES


def test_non_actions_app_is_undetermined(rc):
    api = _FakeApi({})
    red = rc.classify_check_run(api, _check(app={"slug": "some-linter"}))
    assert red.cause == rc.CAUSE_UNDETERMINED
    assert red.real_failure is True
    assert red.infrastructure is False
    assert api.calls == [], "a non-Actions check has no job to fetch"


def test_no_cause_in_the_step_list_is_undetermined(rc):
    steps = [_step(1, "Set up job", "success"), _step(2, "Run tests", "success")]
    assert rc.classify_steps(steps)[0] == rc.CAUSE_UNDETERMINED


@pytest.mark.parametrize(
    "cause",
    ["runner-starvation", "provisioning-failure", "test-failure", "superseded", "undetermined"],
)
def test_no_cause_ever_stops_blocking_the_merge(rc, cause):
    """A cause is information attached to a red, never a way to pass one."""
    red = rc.RedCause("c", "failure", cause, "d", None, None, None, "")
    assert red.blocks_merge is True


def test_undetermined_is_in_neither_the_infrastructure_nor_the_clean_set(rc):
    assert rc.CAUSE_UNDETERMINED not in rc.INFRASTRUCTURE_CAUSES
    assert rc.CAUSE_UNDETERMINED in rc.REAL_FAILURE_CAUSES


def test_every_cause_has_a_remedy_and_none_of_them_says_re_queue(rc):
    """
    Measured on run 33149960063: `rerun-failed-jobs` advanced the attempt
    WITHOUT re-executing the failed matrix leg — same job id, same started_at,
    only the dependents re-ran. `infrastructure=True` therefore means "the diff
    is not indicted", never "re-running will fix it", and no remedy string may
    imply otherwise.
    """
    causes = {
        rc.CAUSE_STARVATION,
        rc.CAUSE_PROVISIONING,
        rc.CAUSE_SUPERSEDED,
        rc.CAUSE_TEST,
        rc.CAUSE_UNDETERMINED,
    }
    assert set(rc.REMEDIES) == causes
    for cause, remedy in rc.REMEDIES.items():
        assert remedy.strip(), cause
        assert "re-queue" not in remedy.lower(), cause


def test_infrastructure_is_about_blame_not_about_the_remedy(rc):
    red = rc.RedCause("c", "failure", rc.CAUSE_PROVISIONING, "d", None, 9, 14, "")
    assert red.infrastructure is True
    assert red.real_failure is False
    assert "rerun-failed-jobs" in red.remedy
    assert "new head commit" in red.remedy
    assert red.as_dict()["infrastructure"] is True
    assert red.as_dict()["remedy"] == red.remedy


# --------------------------------------------------------------------------
# Vacuity: the tool must not be able to pass by classifying nothing.
# --------------------------------------------------------------------------


def test_commit_with_no_check_runs_is_indeterminate_not_clean(rc):
    api = _FakeApi({"check-runs": _checks_response([])})
    report = rc.classify_commit(api, SHA)
    assert report.indeterminate is True
    assert report.reds == []
    assert rc.resolve_exit_code(report, exit_zero=False) == 2
    assert "NOT a clean bill of health" in report.message


def test_unreachable_check_runs_listing_is_indeterminate(rc):
    api = _FakeApi({"check-runs": (rc.NO_RESPONSE_STATUS, {"message": "transport failure"})})
    report = rc.classify_commit(api, SHA)
    assert report.indeterminate is True
    assert rc.resolve_exit_code(report, exit_zero=False) == 2


def test_exit_zero_cannot_suppress_an_indeterminate_result(rc):
    """--exit-zero is for report-only callers. It may hide red; never silence."""
    api = _FakeApi({"check-runs": _checks_response([])})
    report = rc.classify_commit(api, SHA)
    assert rc.resolve_exit_code(report, exit_zero=True) == 2


def test_red_present_exits_one_whatever_the_cause(rc):
    """An infrastructure red is still red — the exit code never grades on cause."""
    job = {"steps": [_step(n, f"step {n}", None) for n in range(1, 5)]}
    api = _FakeApi({"check-runs": _checks_response([_check()]), "actions/jobs/": (200, job)})
    report = rc.classify_commit(api, SHA)
    assert [red.cause for red in report.reds] == [rc.CAUSE_STARVATION]
    assert rc.resolve_exit_code(report, exit_zero=False) == 1


def test_green_commit_with_checks_exits_zero(rc):
    green = _check(conclusion="success")
    api = _FakeApi({"check-runs": _checks_response([green])})
    report = rc.classify_commit(api, SHA)
    assert report.indeterminate is False
    assert report.reds == []
    assert rc.resolve_exit_code(report, exit_zero=False) == 0


def test_classification_reads_the_jobs_endpoint_not_the_listing(rc):
    """
    Only ``GET /actions/jobs/{id}`` carries ``steps``. If this stops being
    called the tool is guessing, and every red becomes ``undetermined``.
    """
    job = {"steps": [_step(1, "Run tests", "failure")]}
    api = _FakeApi({"check-runs": _checks_response([_check()]), "actions/jobs/": (200, job)})
    rc.classify_commit(api, SHA)
    assert any("/actions/jobs/98783580325" in call for call in api.calls)


# --------------------------------------------------------------------------
# Supporting behaviour.
# --------------------------------------------------------------------------


def test_every_red_rendering_conclusion_is_treated_as_red(rc):
    for conclusion in ("failure", "cancelled", "timed_out", "startup_failure", "stale"):
        assert rc.is_red(_check(conclusion=conclusion)) is True
    assert rc.is_red(_check(conclusion="success")) is False
    assert rc.is_red(_check(status="in_progress", conclusion=None)) is False


def test_skipped_and_queued_steps_do_not_count_as_executed(rc):
    steps = [_step(1, "a", "skipped"), _step(2, "b", None), _step(3, "c", "success")]
    assert [s["number"] for s in rc.executed_steps(steps)] == [3]


def test_provisioning_markers_are_overridable(rc, monkeypatch):
    monkeypatch.setenv("CI_RED_CAUSE_PROVISIONING_MARKERS", "install the toolchain")
    assert rc.is_provisioning_step("Install the toolchain") is True
    assert rc.is_provisioning_step("Run ./.github/actions/setup-python-suite") is False
    monkeypatch.setenv("CI_RED_CAUSE_PROVISIONING_MARKERS", "   ,  ")
    assert rc.is_provisioning_step("Run ./.github/actions/setup-python-suite") is True


def test_timed_out_step_counts_as_a_failing_step(rc):
    """exit 124 surfaces as `timed_out` on some runners — the apt case (#15139)."""
    steps = [_step(4, "Run ./.github/actions/setup-python-suite", "timed_out")]
    assert rc.classify_steps(steps)[0] == rc.CAUSE_PROVISIONING
