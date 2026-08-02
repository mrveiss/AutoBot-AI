# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#12823 / #13045 — the CI dispatch watchdog must never report ``success`` for a
head commit whose CI has not demonstrably dispatched, and must never release a
gated fork run.

The production failure modes covered here:

* runs created with ``conclusion=action_required`` (parked behind the fork-PR
  approval policy after ``auto-update-pr-branches`` pushes as the bot),
* runs created but never allocated a job while the self-hosted runner pool is
  empty (``status=queued``, ``jobs: []``),
* an API error being mistaken for "CI never dispatched", and
* ``POST /actions/runs/{id}/approve`` — an approve-a-FORK-run endpoint — being
  pointed at a fork pull request, which would execute contributor-supplied code
  on the self-hosted runner.

``interpret_probe`` is covered because it decides whether owner action is
required, and because an earlier revision failed OPEN on every unrecognised
response.
"""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "pipeline-scripts" / "ci_dispatch_watchdog.py"

NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)
REPO = "mrveiss/AutoBot-AI"
FORK = "someone-else/AutoBot-AI"


def _load():
    spec = importlib.util.spec_from_file_location("ci_dispatch_watchdog", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def watchdog():
    return _load()


def _ts(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(**overrides):
    run = {
        "id": 1,
        "name": "Code Quality",
        "status": "completed",
        "conclusion": "success",
        "created_at": _ts(5),
        "head_repository": {"full_name": REPO},
        "triggering_actor": {"login": "github-actions[bot]"},
    }
    run.update(overrides)
    return run


def _parked(**overrides):
    return _run(status="completed", conclusion="action_required", **overrides)


class _FakeApi:
    """Records approve calls so a test can assert what was NOT approved."""

    def __init__(self, runs_by_sha=None, repository=REPO):
        self.repository = repository
        self._runs_by_sha = runs_by_sha or {}
        self.approved = []
        self.statuses = []

    def runs_for_sha(self, sha):
        value = self._runs_by_sha[sha]
        if isinstance(value, Exception):
            raise value
        return value

    def approve_run(self, run_id):
        self.approved.append(run_id)
        return 201, ""

    def set_status(self, sha, state, context, description, target_url):
        self.statuses.append((sha, state, description))
        return 201


# --- timestamp helpers -----------------------------------------------------


@pytest.mark.parametrize(
    "value,expected_minutes",
    [
        ("2026-08-02T11:30:00Z", 30.0),
        ("2026-08-02T11:30:00+00:00", 30.0),
        ("2026-08-02T12:00:00Z", 0.0),
    ],
)
def test_age_minutes_parses_github_timestamps(watchdog, value, expected_minutes):
    assert watchdog.age_minutes(value, NOW) == pytest.approx(expected_minutes)


@pytest.mark.parametrize("value", [None, "", "not-a-timestamp"])
def test_age_minutes_returns_none_for_unusable_input(watchdog, value):
    assert watchdog.age_minutes(value, NOW) is None


# --- SECURITY: fork pull requests must never be auto-approved --------------


def test_a_fork_origin_parked_run_is_never_approvable(watchdog):
    run = _parked(head_repository={"full_name": FORK})
    eligible, reason = watchdog.is_approvable(run, REPO)
    assert eligible is False
    assert FORK in reason


def test_sweep_never_approves_a_fork_origin_parked_run(watchdog):
    """The end-to-end guard: approve() must not be called for a fork run."""
    api = _FakeApi()
    approved, refused, budget = watchdog._approve_head(
        api, 42, [_parked(id=7, head_repository={"full_name": FORK})], budget=30, dry_run=False
    )
    assert api.approved == []
    assert (approved, refused) == (0, 0)
    assert budget == 30


def test_a_fork_head_is_flagged_by_collect_heads(watchdog):
    heads = watchdog.collect_heads(
        [{"number": 1, "head": {"sha": "a" * 40, "repo": {"full_name": FORK}}, "html_url": "u"}], REPO
    )
    assert heads[0].same_repo is False


def test_same_repo_head_is_recognised(watchdog):
    heads = watchdog.collect_heads(
        [{"number": 1, "head": {"sha": "b" * 40, "repo": {"full_name": REPO}}, "html_url": "u"}], REPO
    )
    assert heads[0].same_repo is True


def test_the_sweep_skips_a_fork_head_entirely(watchdog):
    sha = "f" * 40
    api = _FakeApi({sha: [_parked(id=99, head_repository={"full_name": FORK})]})
    head = watchdog.PullHead(number=8, sha=sha, updated_at=_ts(5), url="u", same_repo=False)
    approved, refused, budget, _unsettled, touched = watchdog._sweep_once(api, [head], budget=30, dry_run=False)
    assert api.approved == []
    assert (approved, refused, budget) == (0, 0, 30)
    assert touched == set()


def test_a_run_parked_for_a_human_actor_is_not_approvable(watchdog):
    run = _parked(triggering_actor={"login": "Some-Contributor"})
    eligible, reason = watchdog.is_approvable(run, REPO)
    assert eligible is False
    assert "branch-update bot" in reason


def test_a_same_repo_bot_parked_run_is_approvable(watchdog):
    eligible, reason = watchdog.is_approvable(_parked(), REPO)
    assert eligible is True
    assert reason == ""


def test_a_run_with_no_head_repository_is_treated_as_a_fork(watchdog):
    """Missing provenance must fail closed, not open."""
    run = _parked()
    del run["head_repository"]
    assert watchdog.is_approvable(run, REPO)[0] is False


# --- #12823: parked runs ---------------------------------------------------


def test_parked_run_is_reported_as_failure(watchdog):
    runs = [_parked(name="Code Quality"), _parked(id=2, name="PR Template Check")]
    state, description = watchdog.classify_dispatch(runs, _ts(5), NOW, 10, 30)
    assert state == "failure"
    assert "parked awaiting approval" in description
    assert "Code Quality" in description


def test_parked_run_outranks_otherwise_green_runs(watchdog):
    """A head with 20 green runs and one parked run is still not verified."""
    runs = [_run(id=i) for i in range(20)]
    runs.append(_parked(id=99, name="Enforce Pre-commit Hooks"))
    state, _ = watchdog.classify_dispatch(runs, _ts(60), NOW, 10, 30)
    assert state == "failure"


# --- #13045: starved runs and absent runs ----------------------------------


def test_queued_run_past_the_stall_threshold_with_an_empty_pool_is_failure(watchdog):
    runs = [_run(status="queued", conclusion=None, created_at=_ts(45), name="Unit & Integration Tests")]
    state, description = watchdog.classify_dispatch(runs, _ts(45), NOW, 10, 30, False)
    assert state == "failure"
    assert "no runner available" in description


def test_queued_run_behind_a_busy_pool_is_pending_not_failure(watchdog):
    """Normal contention on the singleton runner must not raise a false outage."""
    runs = [_run(status="queued", conclusion=None, created_at=_ts(45), name="Unit & Integration Tests")]
    state, description = watchdog.classify_dispatch(runs, _ts(45), NOW, 10, 30, True)
    assert state == "pending"
    assert "busy runner pool" in description


def test_a_busy_queue_is_still_never_success(watchdog):
    runs = [_run(status="queued", conclusion=None, created_at=_ts(45))]
    state, _ = watchdog.classify_dispatch(runs, _ts(45), NOW, 10, 30, True)
    assert state != "success"


def test_queued_run_inside_the_stall_threshold_is_success(watchdog):
    runs = [_run(status="queued", conclusion=None, created_at=_ts(4))]
    state, _ = watchdog.classify_dispatch(runs, _ts(4), NOW, 10, 30, False)
    assert state == "success"


def test_no_runs_past_the_grace_window_is_failure(watchdog):
    state, description = watchdog.classify_dispatch([], _ts(30), NOW, 10, 30)
    assert state == "failure"
    assert "never dispatched" in description


def test_no_runs_inside_the_grace_window_is_pending_not_success(watchdog):
    """Absence must never read as green, even before the grace window closes."""
    state, _ = watchdog.classify_dispatch([], _ts(2), NOW, 10, 30)
    assert state == "pending"


def test_unparseable_head_timestamp_with_no_runs_is_failure(watchdog):
    state, _ = watchdog.classify_dispatch([], None, NOW, 10, 30)
    assert state == "failure"


def test_dispatched_runs_are_success(watchdog):
    state, description = watchdog.classify_dispatch([_run(), _run(id=2)], _ts(5), NOW, 10, 30)
    assert state == "success"
    assert "2 workflow run(s) dispatched" in description


def test_description_never_exceeds_the_github_limit(watchdog):
    runs = [_parked(id=i, name=f"A very long workflow name number {i}" * 4) for i in range(30)]
    _, description = watchdog.classify_dispatch(runs, _ts(5), NOW, 10, 30)
    assert len(description) <= watchdog.MAX_STATUS_DESCRIPTION


# --- an API error is not a diagnosis ---------------------------------------


def test_an_api_error_publishes_unknown_not_never_dispatched(watchdog):
    """One rate-limit window must not assert a root cause on every open PR."""
    sha = "c" * 40
    api = _FakeApi({sha: watchdog.WatchdogApiError("HTTP 429: rate limited")})
    head = watchdog.PullHead(number=5, sha=sha, updated_at=_ts(60), url="u", same_repo=True)
    config = {"grace_minutes": 10, "stall_minutes": 30, "status_context": "ctx"}
    blocked = watchdog.publish_dispatch_states(api, [head], config, dry_run=False, pool_serving=True)
    assert blocked == 1
    _, state, description = api.statuses[0]
    assert state == "pending"
    assert "unknown" in description
    assert "never dispatched" not in description


def test_a_sweep_survives_an_api_error_on_one_head(watchdog):
    good, bad = "d" * 40, "e" * 40
    api = _FakeApi({good: [_parked(id=11)], bad: watchdog.WatchdogApiError("HTTP 500")})
    heads = [
        watchdog.PullHead(1, bad, _ts(5), "u", True),
        watchdog.PullHead(2, good, _ts(5), "u", True),
    ]
    approved, refused, _budget, unsettled, _touched = watchdog._sweep_once(api, heads, budget=30, dry_run=False)
    assert approved == 1
    assert refused == 0
    assert unsettled is True
    assert api.approved == [11]


# --- starvation / runner liveness ------------------------------------------


def test_starved_runs_selects_only_job_less_queued_runs(watchdog):
    runs = [
        _run(id=1, status="queued", conclusion=None, created_at=_ts(90)),
        _run(id=2, status="queued", conclusion=None, created_at=_ts(5)),
        _run(id=3, status="in_progress", conclusion=None, created_at=_ts(90)),
        _run(id=4, status="completed", conclusion="success", created_at=_ts(90)),
    ]
    assert [run["id"] for run in watchdog.starved_runs(runs, NOW, 30)] == [1]


def test_waiting_status_counts_as_unstarted(watchdog):
    runs = [_run(id=7, status="waiting", conclusion=None, created_at=_ts(60))]
    assert watchdog.starved_runs(runs, NOW, 30)


def test_only_a_self_hosted_label_proves_the_singleton_is_alive(watchdog):
    """A GitHub-hosted job executing says nothing about the self-hosted pool."""
    assert watchdog.job_is_self_hosted({"labels": ["self-hosted", "Linux", "X64"]}) is True
    assert watchdog.job_is_self_hosted({"labels": ["ubuntu-latest"]}) is False
    assert watchdog.job_is_self_hosted({"labels": []}) is False
    assert watchdog.job_is_self_hosted({}) is False


def test_a_github_hosted_job_does_not_prove_the_pool_is_serving(watchdog):
    """The old heuristic counted any in_progress run and was near-always true."""

    class _Api:
        repository = REPO

        def recent_runs(self, per_page=100, run_status=""):
            return [{"id": 1}]

        def run_jobs(self, run_id):
            return [{"status": "in_progress", "labels": ["ubuntu-latest"]}]

    assert watchdog.self_hosted_pool_is_serving(_Api(), 10) is False


def test_a_self_hosted_job_proves_the_pool_is_serving(watchdog):
    class _Api:
        repository = REPO

        def recent_runs(self, per_page=100, run_status=""):
            return [{"id": 1}]

        def run_jobs(self, run_id):
            return [{"status": "in_progress", "labels": ["self-hosted", "Linux", "X64"]}]

    assert watchdog.self_hosted_pool_is_serving(_Api(), 10) is True


def test_runner_liveness_is_none_when_it_cannot_be_established(watchdog):
    class _Api:
        repository = REPO

        def recent_runs(self, per_page=100, run_status=""):
            raise watchdog.WatchdogApiError("HTTP 429")

    assert watchdog.self_hosted_pool_is_serving(_Api(), 10) is None


# --- approval-capability probe ---------------------------------------------


def test_probe_detects_a_credential_without_actions_write(watchdog):
    permitted, explanation = watchdog.interpret_probe(403, "Resource not accessible by integration")
    assert permitted is False
    assert "lacks permission" in explanation


def test_probe_detects_a_credential_with_actions_write(watchdog):
    permitted, _ = watchdog.interpret_probe(403, "This workflow run is not waiting for approval")
    assert permitted is True


def test_probe_treats_an_accepted_approval_as_permitted(watchdog):
    permitted, _ = watchdog.interpret_probe(201, "")
    assert permitted is True


@pytest.mark.parametrize(
    "status,message",
    [
        (401, "Bad credentials"),
        (404, "Not Found"),
        (429, "API rate limit exceeded"),
        (500, "Server Error"),
        (502, "<html>bad gateway</html>"),
        (0, "transport failure: timed out"),
    ],
)
def test_probe_never_fails_open_on_an_unrecognised_response(watchdog, status, message):
    """401/404/429/5xx/transport must be UNRESOLVED, never 'assumed permitted'."""
    permitted, explanation = watchdog.interpret_probe(status, message)
    assert permitted is None
    assert "unresolved" in explanation.lower()


def test_probe_selects_successful_runs_not_completed_ones(watchdog):
    """Parked runs ARE status=completed, so completed candidates are all parked."""

    class _Api:
        asked_for = None

        def recent_runs(self, per_page=100, run_status=""):
            _Api.asked_for = run_status
            return [{"id": 2, "status": "completed", "conclusion": "success"}]

        def approve_run(self, run_id):
            return 403, "This workflow run is not waiting for approval"

    permitted, _ = watchdog.probe_approval_capability(_Api())
    assert _Api.asked_for == "success"
    assert permitted is True


def test_probe_reports_unresolved_when_no_candidate_exists(watchdog):
    class _Api:
        def recent_runs(self, per_page=100, run_status=""):
            return []

    permitted, explanation = watchdog.probe_approval_capability(_Api())
    assert permitted is None
    assert "unresolved" in explanation


def test_probe_is_skipped_and_unresolved_on_a_dry_run(watchdog):
    """--dry-run must issue no approve request at all."""

    class _Api:
        def recent_runs(self, per_page=100, run_status=""):
            raise AssertionError("a dry run must not query for probe candidates")

        def approve_run(self, run_id):
            raise AssertionError("a dry run must not POST approve")

    permitted, explanation = watchdog.probe_approval_capability(_Api(), dry_run=True)
    assert permitted is None
    assert "dry-run" in explanation


def test_probe_reports_unresolved_when_the_listing_fails(watchdog):
    class _Api:
        def recent_runs(self, per_page=100, run_status=""):
            raise watchdog.WatchdogApiError("HTTP 429: rate limited")

    permitted, explanation = watchdog.probe_approval_capability(_Api())
    assert permitted is None
    assert "unresolved" in explanation


# --- dry run is side-effect free -------------------------------------------


def test_dry_run_approves_nothing_but_still_consumes_budget(watchdog):
    api = _FakeApi()
    runs = [_parked(id=i) for i in range(5)]
    approved, refused, budget = watchdog._approve_head(api, 1, runs, budget=3, dry_run=True)
    assert api.approved == []
    assert (approved, refused) == (0, 0)
    # Budget consumed so the preview matches the cap a real sweep would hit.
    assert budget == 0


# --- configuration ----------------------------------------------------------


def test_thresholds_come_from_the_environment(watchdog, monkeypatch):
    monkeypatch.setenv("WATCHDOG_STALL_MINUTES", "7")
    assert watchdog._env_int("WATCHDOG_STALL_MINUTES", 30) == 7


def test_non_positive_threshold_is_rejected(watchdog, monkeypatch):
    monkeypatch.setenv("WATCHDOG_STALL_MINUTES", "0")
    with pytest.raises(watchdog.WatchdogConfigError):
        watchdog._env_int("WATCHDOG_STALL_MINUTES", 30)


def test_missing_repository_is_rejected(watchdog, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "not-a-repo")
    with pytest.raises(watchdog.WatchdogConfigError):
        watchdog.load_config()


# --- sweep polling ----------------------------------------------------------


def test_head_with_no_runs_yet_is_polled_again(watchdog):
    """Right after update-branch returns, an empty result means 'too early'."""
    assert watchdog.needs_another_look([]) is True


def test_head_with_a_parked_run_is_polled_again(watchdog):
    assert watchdog.needs_another_look([_run(), _parked(id=2)]) is True


def test_head_with_dispatched_runs_is_settled(watchdog):
    assert watchdog.needs_another_look([_run(), _run(id=2)]) is False
