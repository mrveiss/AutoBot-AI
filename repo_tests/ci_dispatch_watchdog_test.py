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

    def __init__(self, runs_by_sha=None, repository=REPO, approve_response=(201, "")):
        self.repository = repository
        self._runs_by_sha = runs_by_sha or {}
        self.approved = []
        self.statuses = []
        self._approve_response = approve_response

    def runs_for_sha(self, sha):
        value = self._runs_by_sha[sha]
        if isinstance(value, Exception):
            raise value
        return value

    def approve_run(self, run_id):
        self.approved.append(run_id)
        return self._approve_response

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
    outcome = watchdog._approve_head(
        api, 42, [_parked(id=7, head_repository={"full_name": FORK})], budget=30, dry_run=False
    )
    assert api.approved == []
    assert (outcome.approved, outcome.refused, outcome.raced) == (0, 0, 0)
    assert outcome.budget == 30
    assert outcome.exhausted is False


def test_a_fork_head_is_flagged_by_collect_heads(watchdog):
    heads = watchdog.collect_heads(
        [{"number": 1, "head": {"sha": "a" * 40, "repo": {"full_name": FORK}}, "html_url": "u"}],
        REPO,
    )
    assert heads[0].same_repo is False


def test_same_repo_head_is_recognised(watchdog):
    heads = watchdog.collect_heads(
        [{"number": 1, "head": {"sha": "b" * 40, "repo": {"full_name": REPO}}, "html_url": "u"}],
        REPO,
    )
    assert heads[0].same_repo is True


def test_the_sweep_skips_a_fork_head_entirely(watchdog):
    sha = "f" * 40
    api = _FakeApi({sha: [_parked(id=99, head_repository={"full_name": FORK})]})
    head = watchdog.PullHead(number=8, sha=sha, updated_at=_ts(5), url="u", same_repo=False)
    outcome = watchdog._sweep_once(api, [head], budget=30, dry_run=False)
    assert api.approved == []
    assert (outcome.approved, outcome.refused, outcome.budget) == (0, 0, 30)
    assert outcome.touched == set()
    assert outcome.deferred == set()


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
    runs = [
        _run(status="queued", conclusion=None, created_at=_ts(45), name="Unit & Integration Tests")
    ]
    state, description = watchdog.classify_dispatch(runs, _ts(45), NOW, 10, 30, False)
    assert state == "failure"
    assert "no runner available" in description


def test_queued_run_behind_a_busy_pool_is_pending_not_failure(watchdog):
    """Normal contention on the singleton runner must not raise a false outage."""
    runs = [
        _run(status="queued", conclusion=None, created_at=_ts(45), name="Unit & Integration Tests")
    ]
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
    blocked = watchdog.publish_dispatch_states(
        api, [head], config, dry_run=False, pool_serving=True
    )
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
    outcome = watchdog._sweep_once(api, heads, budget=30, dry_run=False)
    assert outcome.approved == 1
    assert outcome.refused == 0
    assert outcome.unsettled is True
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


# --- wedged self-hosted jobs (#13341) ---------------------------------------
#
# The required `Unit & Integration Tests` context ran for over three hours
# against a declared `timeout-minutes: 30`. GitHub enforces that timeout from
# the runner side, so a runner that stops making progress never receives the
# cancellation. Two consequences these tests pin down: the job is not
# distinguishable from a healthy one, and — worse — it made the pool read as
# ALIVE, so the queue stacking up behind it was dismissed as contention.


def _job(minutes_running, labels=("self-hosted", "Linux", "X64"), name="Unit & Integration Tests"):
    return {
        "name": name,
        "status": "in_progress",
        "labels": list(labels),
        "started_at": _ts(minutes_running),
        "html_url": "https://github.com/x/y/actions/runs/1/job/2",
    }


def _pool_api(jobs, run=None):
    class _Api:
        repository = REPO

        def recent_runs(self, per_page=100, run_status=""):
            return [run or {"id": 1, "name": "Frontend Testing Suite", "head_sha": "abc123def456"}]

        def run_jobs(self, run_id):
            return jobs

    return _Api()


def test_a_wedged_job_is_not_evidence_that_the_pool_is_healthy(watchdog):
    """The false negative: a hung job is in_progress on a self-hosted label."""
    state = watchdog.inspect_self_hosted_pool(_pool_api([_job(185)]), 10, 45, NOW)
    assert state.serving is False
    assert len(state.overdue) == 1


def test_a_wedged_job_is_reported_with_the_head_it_is_blocking(watchdog):
    state = watchdog.inspect_self_hosted_pool(_pool_api([_job(185)]), 10, 45, NOW)
    entry = state.overdue[0]
    assert entry.head_sha == "abc123def456"
    assert entry.job == "Unit & Integration Tests"
    assert entry.elapsed_minutes == pytest.approx(185, abs=1)
    assert "185m" in entry.describe()


def test_a_self_hosted_job_inside_the_ceiling_is_healthy_not_wedged(watchdog):
    """29 minutes is inside every declared timeout in the repository."""
    state = watchdog.inspect_self_hosted_pool(_pool_api([_job(29)]), 10, 45, NOW)
    assert state.serving is True
    assert state.overdue == []


def test_a_long_running_github_hosted_job_is_not_wedged(watchdog):
    """marker-tests declares 180m on ubuntu-latest and holds no singleton."""
    state = watchdog.inspect_self_hosted_pool(
        _pool_api([_job(120, labels=("ubuntu-latest",))]), 10, 45, NOW
    )
    assert state.overdue == []


def test_a_job_that_has_not_started_is_never_wedged(watchdog):
    assert (
        watchdog.job_is_overdue({"status": "in_progress", "labels": ["self-hosted"]}, NOW, 45)
        is False
    )


def test_a_completed_job_is_never_wedged(watchdog):
    job = _job(185)
    job["status"] = "completed"
    assert watchdog.job_is_overdue(job, NOW, 45) is False


def test_the_wedged_run_is_found_even_when_it_is_the_oldest_of_many(watchdog):
    """
    The detector's real failure mode, invisible to every other test here.

    `GET /actions/runs` returns NEWEST first, and a wedged run is by definition
    the OLDEST in-progress one. Truncating the newest N to the lookup budget
    therefore drops exactly the run being looked for. Measured live: 12 runs in
    progress, the wedging one the oldest of the 12, a budget of 10 — missed.
    """
    healthy = [
        {"id": i, "name": "CI", "head_sha": f"sha{i}", "run_started_at": _ts(i)}
        for i in range(1, 12)
    ]
    wedged = {
        "id": 99,
        "name": "Frontend Testing Suite",
        "head_sha": "wedged",
        "run_started_at": _ts(185),
    }

    class _Api:
        repository = REPO

        def recent_runs(self, per_page=100, run_status=""):
            # Newest first, exactly as GitHub returns it.
            return healthy + [wedged]

        def run_jobs(self, run_id):
            if run_id == 99:
                return [_job(185)]
            return [_job(2, name="Something Fine")]

    state = watchdog.inspect_self_hosted_pool(_Api(), 10, 45, NOW)
    assert [entry.head_sha for entry in state.overdue] == ["wedged"]


def test_a_healthy_job_alongside_a_wedged_one_still_proves_liveness(watchdog):
    state = watchdog.inspect_self_hosted_pool(
        _pool_api([_job(185), _job(3, name="Build Test")]), 10, 45, NOW
    )
    assert state.serving is True
    assert [entry.job for entry in state.overdue] == ["Unit & Integration Tests"]


def test_overdue_jobs_are_grouped_by_head(watchdog):
    a = watchdog.OverdueJob("sha-a", "wf", "job1", 90.0, "u")
    b = watchdog.OverdueJob("sha-a", "wf", "job2", 91.0, "u")
    c = watchdog.OverdueJob("", "wf", "job3", 92.0, "u")
    grouped = watchdog.overdue_by_head([a, b, c])
    assert list(grouped) == ["sha-a"]
    assert len(grouped["sha-a"]) == 2


def test_a_wedged_head_is_published_as_a_failure_not_a_healthy_in_progress(watchdog):
    overdue = [
        watchdog.OverdueJob("sha", "Frontend Testing Suite", "Unit & Integration Tests", 185.0, "u")
    ]
    state, description = watchdog.classify_dispatch([_run()], _ts(5), NOW, 10, 30, True, overdue)
    assert state == "failure"
    assert "wedged" in description


def test_a_wedged_head_never_reads_as_success(watchdog):
    """Otherwise-green runs must not mask a job holding a required context."""
    overdue = [watchdog.OverdueJob("sha", "wf", "job", 200.0, "u")]
    state, _ = watchdog.classify_dispatch([_run(), _run(id=2)], _ts(5), NOW, 10, 30, True, overdue)
    assert state == "failure"


def test_a_head_with_no_wedged_job_is_unaffected(watchdog):
    state, _ = watchdog.classify_dispatch([_run()], _ts(5), NOW, 10, 30, True, [])
    assert state == "success"


# --- starvation probe vs. a wedged job --------------------------------------


def _starvation_api(queued, jobs):
    class _Api:
        repository = REPO

        def recent_runs(self, per_page=100, run_status=""):
            if run_status == "queued":
                return queued
            return [{"id": 1, "name": "Frontend Testing Suite", "head_sha": "sha"}]

        def run_jobs(self, run_id):
            return jobs

    return _Api()


_STARVATION_CONFIG = {"stall_minutes": 45, "max_job_lookups": 5, "job_overdue_minutes": 45}


def _live_ts(minutes_ago):
    """Relative to the real clock — check_runner_starvation reads it itself."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def _live_job(minutes_running, name="Unit & Integration Tests"):
    return {
        "name": name,
        "status": "in_progress",
        "labels": ["self-hosted", "Linux", "X64"],
        "started_at": _live_ts(minutes_running),
    }


def _live_queue():
    return [
        {"id": 9, "name": "CI", "status": "queued", "created_at": _live_ts(60), "head_branch": "b"}
    ]


def test_a_wedged_job_fails_the_probe_even_with_an_empty_queue(watchdog):
    """It is a fault the moment it happens — it is holding a required check."""
    api = _starvation_api([], [_live_job(185)])
    assert watchdog.check_runner_starvation(api, _STARVATION_CONFIG) == 1


def test_a_queue_behind_a_wedged_job_is_no_longer_dismissed_as_contention(watchdog):
    """The regression this check existed to catch and previously reported green."""
    api = _starvation_api(_live_queue(), [_live_job(185)])
    assert watchdog.check_runner_starvation(api, _STARVATION_CONFIG) == 1


def test_a_queue_behind_genuinely_busy_work_is_still_contention(watchdog):
    api = _starvation_api(_live_queue(), [_live_job(4, name="Build Test")])
    assert watchdog.check_runner_starvation(api, _STARVATION_CONFIG) == 0


def test_a_quiet_healthy_pool_still_passes(watchdog):
    assert watchdog.check_runner_starvation(_starvation_api([], []), _STARVATION_CONFIG) == 0


def test_starvation_with_no_runner_at_all_still_fails(watchdog):
    """#13045's original condition must keep failing."""
    api = _starvation_api(_live_queue(), [])
    assert watchdog.check_runner_starvation(api, _STARVATION_CONFIG) == 1


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
    outcome = watchdog._approve_head(api, 1, runs, budget=3, dry_run=True)
    assert api.approved == []
    assert (outcome.approved, outcome.refused) == (0, 0)
    # Budget consumed so the preview matches the cap a real sweep would hit.
    assert outcome.budget == 0
    assert outcome.exhausted is True


# --- event-scoped sweeps (#12823 pull_request trigger) ----------------------


def test_scoping_selects_only_the_firing_pull_request(watchdog):
    heads = [
        watchdog.PullHead(1, "a" * 40, _ts(5), "u", True),
        watchdog.PullHead(2, "b" * 40, _ts(5), "u", True),
        watchdog.PullHead(3, "c" * 40, _ts(5), "u", True),
    ]
    assert [head.number for head in watchdog.select_heads(heads, 2)] == [2]


def test_scoping_off_returns_every_head(watchdog):
    heads = [
        watchdog.PullHead(1, "a" * 40, _ts(5), "u", True),
        watchdog.PullHead(2, "b" * 40, _ts(5), "u", True),
    ]
    assert watchdog.select_heads(heads, 0) == heads


def test_an_unknown_pr_number_selects_nothing_rather_than_everything(watchdog):
    """Falling back to 'all heads' would restore the full-queue cost this avoids."""
    heads = [watchdog.PullHead(1, "a" * 40, _ts(5), "u", True)]
    assert watchdog.select_heads(heads, 999) == []


def test_scoping_to_a_fork_pr_still_never_approves_it(watchdog):
    """SECURITY: the fork guard is independent of how the head was selected."""
    sha = "9" * 40
    api = _FakeApi({sha: [_parked(id=77, head_repository={"full_name": FORK})]})
    api.open_pull_requests = lambda base: [
        {
            "number": 12,
            "head": {"sha": sha, "repo": {"full_name": FORK}},
            "html_url": "u",
            "updated_at": _ts(5),
        },
        {
            "number": 13,
            "head": {"sha": "8" * 40, "repo": {"full_name": REPO}},
            "html_url": "u",
            "updated_at": _ts(5),
        },
    ]
    api.recent_runs = lambda per_page=100, run_status="": []
    api.run_jobs = lambda run_id: []
    config = {
        "base_branch": "Dev_new_gui",
        "grace_minutes": 10,
        "stall_minutes": 30,
        "status_context": "ctx",
        "max_approvals": 30,
        "poll_attempts": 1,
        "poll_interval_seconds": 1,
        "max_job_lookups": 5,
        "job_overdue_minutes": 45,
        "only_pr": 12,
    }
    assert watchdog.check_dispatch(api, config, dry_run=False) == 0
    assert api.approved == []
    # The untouched same-repo PR was not swept either — scoping held.
    assert [sha for sha, _state, _desc in api.statuses] == [sha]


def test_scoping_to_a_same_repo_pr_still_approves_its_parked_bot_runs(watchdog):
    sha = "7" * 40
    api = _FakeApi({sha: [_parked(id=55)]})
    api.open_pull_requests = lambda base: [
        {
            "number": 21,
            "head": {"sha": sha, "repo": {"full_name": REPO}},
            "html_url": "u",
            "updated_at": _ts(5),
        }
    ]
    api.recent_runs = lambda per_page=100, run_status="": []
    api.run_jobs = lambda run_id: []
    config = {
        "base_branch": "Dev_new_gui",
        "grace_minutes": 10,
        "stall_minutes": 30,
        "status_context": "ctx",
        "max_approvals": 30,
        "poll_attempts": 1,
        "poll_interval_seconds": 1,
        "max_job_lookups": 5,
        "job_overdue_minutes": 45,
        "only_pr": 21,
    }
    assert watchdog.check_dispatch(api, config, dry_run=False) == 0
    assert api.approved == [55]


def test_a_closed_or_renumbered_scope_target_sweeps_nothing(watchdog, capsys):
    api = _FakeApi()
    api.open_pull_requests = lambda base: [
        {
            "number": 1,
            "head": {"sha": "6" * 40, "repo": {"full_name": REPO}},
            "html_url": "u",
            "updated_at": _ts(5),
        }
    ]
    config = {"base_branch": "Dev_new_gui", "only_pr": 4242}
    assert watchdog.check_dispatch(api, config, dry_run=False) == 0
    assert api.approved == []
    assert api.statuses == []
    assert "nothing to sweep" in capsys.readouterr().out


def test_only_pr_zero_means_every_open_pr(watchdog, monkeypatch):
    monkeypatch.setenv("WATCHDOG_ONLY_PR", "0")
    assert watchdog._env_non_negative_int("WATCHDOG_ONLY_PR", 0) == 0


def test_only_pr_rejects_a_negative_number(watchdog, monkeypatch):
    monkeypatch.setenv("WATCHDOG_ONLY_PR", "-1")
    with pytest.raises(watchdog.WatchdogConfigError):
        watchdog._env_non_negative_int("WATCHDOG_ONLY_PR", 0)


# --- a concurrent sweep is not a refusal ------------------------------------

RACE_403 = (403, "This workflow run is not waiting for approval")


def test_the_race_message_is_recognised(watchdog):
    assert watchdog.is_already_released("This workflow run is not waiting for approval") is True
    assert watchdog.is_already_released("Resource not accessible by integration") is False
    assert watchdog.is_already_released("") is False


def test_the_probe_and_the_sweep_agree_about_the_same_message(watchdog):
    """The exact string interpret_probe calls PROOF of permission.

    Reading it as a refusal in one place and as proof of permission in the
    other is what made a benign race demand a security downgrade.
    """
    message = "This workflow run is not waiting for approval"
    assert watchdog.interpret_probe(403, message)[0] is True
    assert watchdog.is_already_released(message) is True


def test_a_run_already_released_by_a_concurrent_sweep_is_not_refused(watchdog):
    api = _FakeApi(approve_response=RACE_403)
    outcome = watchdog._approve_head(api, 7, [_parked(id=3)], budget=30, dry_run=False)
    assert outcome.raced == 1
    assert outcome.refused == 0
    assert outcome.approved == 0


def test_a_genuine_permission_failure_is_still_refused(watchdog):
    api = _FakeApi(approve_response=(403, "Resource not accessible by integration"))
    outcome = watchdog._approve_head(api, 7, [_parked(id=3)], budget=30, dry_run=False)
    assert outcome.refused == 1
    assert outcome.raced == 0


def test_a_raced_sweep_exits_zero_and_never_prints_the_credential_remediation(watchdog, capsys):
    """The whole point: a routine race must not advise relaxing repo security."""
    sha = "a" * 40
    api = _FakeApi({sha: [_parked(id=3)]}, approve_response=RACE_403)
    api.open_pull_requests = lambda base: [
        {
            "number": 31,
            "head": {"sha": sha, "repo": {"full_name": REPO}},
            "html_url": "u",
            "updated_at": _ts(5),
        }
    ]
    api.recent_runs = lambda per_page=100, run_status="": [{"id": 1, "conclusion": "success"}]
    api.run_jobs = lambda run_id: []
    config = _sweep_config()
    assert watchdog.check_dispatch(api, config, dry_run=False) == 0
    out = capsys.readouterr().out
    assert "already released" in out
    assert "relax the repository Actions setting" not in out


# --- budget exhaustion must be loud, not a deferral that never arrives ------


def _sweep_config(**overrides):
    config = {
        "base_branch": "Dev_new_gui",
        "grace_minutes": 10,
        "stall_minutes": 30,
        "status_context": "ctx",
        "max_approvals": 30,
        "poll_attempts": 1,
        "poll_interval_seconds": 1,
        "max_job_lookups": 5,
        "job_overdue_minutes": 45,
    }
    config.update(overrides)
    return config


def test_exhausting_the_budget_marks_the_head_deferred(watchdog):
    api = _FakeApi()
    outcome = watchdog._approve_head(
        api, 9, [_parked(id=i) for i in range(4)], budget=2, dry_run=False
    )
    assert outcome.approved == 2
    assert outcome.exhausted is True


def test_a_sweep_reports_which_prs_the_budget_could_not_reach(watchdog):
    a, b = "1" * 40, "2" * 40
    api = _FakeApi({a: [_parked(id=1), _parked(id=2)], b: [_parked(id=3), _parked(id=4)]})
    heads = [
        watchdog.PullHead(101, a, _ts(5), "u", True),
        watchdog.PullHead(102, b, _ts(5), "u", True),
    ]
    outcome = watchdog._sweep_once(api, heads, budget=3, dry_run=False)
    assert outcome.approved == 3
    assert outcome.deferred == {102}


def test_a_budget_exhausted_sweep_exits_non_zero(watchdog, capsys):
    """Silent deferral to a sweep that never comes is the failure being removed."""
    sha = "3" * 40
    api = _FakeApi({sha: [_parked(id=i) for i in range(5)]})
    api.open_pull_requests = lambda base: [
        {
            "number": 55,
            "head": {"sha": sha, "repo": {"full_name": REPO}},
            "html_url": "u",
            "updated_at": _ts(5),
        }
    ]
    api.recent_runs = lambda per_page=100, run_status="": [{"id": 1, "conclusion": "success"}]
    api.run_jobs = lambda run_id: []
    assert watchdog.check_dispatch(api, _sweep_config(max_approvals=2), dry_run=False) == 1
    out = capsys.readouterr().out
    assert "#55" in out
    assert "not a permissions problem" in out.lower()


def test_budget_exhaustion_does_not_blame_the_credential(watchdog):
    message = watchdog.budget_exhausted_message({1, 2}, 30)
    assert "not a permissions problem" in message.lower()
    assert "30" in message
    assert "WATCHDOG_MAX_APPROVALS" in message


def test_a_dry_run_previews_exhaustion_without_failing(watchdog):
    """A preview changes nothing, so it has nothing to be silent about."""
    sha = "4" * 40
    api = _FakeApi({sha: [_parked(id=i) for i in range(5)]})
    api.open_pull_requests = lambda base: [
        {
            "number": 56,
            "head": {"sha": sha, "repo": {"full_name": REPO}},
            "html_url": "u",
            "updated_at": _ts(5),
        }
    ]
    api.recent_runs = lambda per_page=100, run_status="": []
    api.run_jobs = lambda run_id: []
    assert watchdog.check_dispatch(api, _sweep_config(max_approvals=2), dry_run=True) == 0


def test_the_default_budget_covers_a_realistic_queue(watchdog):
    """27 runs measured on the busiest head x 10 open PRs. Below that, sweeps
    stop part-way and promise a next sweep the schedule cannot deliver."""
    assert watchdog.DEFAULT_MAX_APPROVALS >= 27 * 10


def test_a_bigger_budget_does_not_widen_what_is_approvable(watchdog):
    """SECURITY: the cap bounds HOW MANY, never WHAT. Fork runs stay excluded."""
    api = _FakeApi()
    fork_runs = [_parked(id=i, head_repository={"full_name": FORK}) for i in range(50)]
    outcome = watchdog._approve_head(
        api, 1, fork_runs, budget=watchdog.DEFAULT_MAX_APPROVALS, dry_run=False
    )
    assert api.approved == []
    assert outcome.budget == watchdog.DEFAULT_MAX_APPROVALS
    assert outcome.exhausted is False


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


def test_a_dry_run_does_not_warn_about_the_probe_it_skipped_on_purpose(watchdog, capsys):
    """The warning must stay rare enough to be read when it means something."""
    sha = "1" * 40
    api = _FakeApi({sha: [_run()]})
    api.open_pull_requests = lambda base: [
        {
            "number": 3,
            "head": {"sha": sha, "repo": {"full_name": REPO}},
            "html_url": "u",
            "updated_at": _ts(5),
        }
    ]
    api.recent_runs = lambda per_page=100, run_status="": []
    api.run_jobs = lambda run_id: []
    config = {
        "base_branch": "Dev_new_gui",
        "grace_minutes": 10,
        "stall_minutes": 30,
        "status_context": "ctx",
        "max_approvals": 30,
        "poll_attempts": 1,
        "poll_interval_seconds": 1,
        "max_job_lookups": 5,
        "job_overdue_minutes": 45,
    }
    assert watchdog.check_dispatch(api, config, dry_run=True) == 0
    assert "UNRESOLVED" not in capsys.readouterr().out


def test_a_real_sweep_does_warn_when_the_probe_is_unresolved(watchdog, capsys):
    sha = "2" * 40
    api = _FakeApi({sha: [_run()]})
    api.open_pull_requests = lambda base: [
        {
            "number": 4,
            "head": {"sha": sha, "repo": {"full_name": REPO}},
            "html_url": "u",
            "updated_at": _ts(5),
        }
    ]
    api.recent_runs = lambda per_page=100, run_status="": []
    api.run_jobs = lambda run_id: []
    config = {
        "base_branch": "Dev_new_gui",
        "grace_minutes": 10,
        "stall_minutes": 30,
        "status_context": "ctx",
        "max_approvals": 30,
        "poll_attempts": 1,
        "poll_interval_seconds": 1,
        "max_job_lookups": 5,
        "job_overdue_minutes": 45,
    }
    assert watchdog.check_dispatch(api, config, dry_run=False) == 0
    assert "UNRESOLVED" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# superseded_stuck_runs — force-cancel selection (#13439)
# ---------------------------------------------------------------------------


def _member(run_number: int, minutes_ago: float, **overrides):
    """A queued run in the default concurrency group."""
    base = {
        "id": 1000 + run_number,
        "run_number": run_number,
        "workflow_id": 77,
        "head_branch": "Dev_new_gui",
        "event": "push",
        "status": "queued",
        "conclusion": None,
        "created_at": _ts(minutes_ago),
    }
    base.update(overrides)
    return _run(**base)


def _select(watchdog, runs, grace=5, budget=10):
    return watchdog.superseded_stuck_runs(runs, NOW, REPO, grace, budget)


def test_the_newest_run_in_a_group_is_never_cancelled(watchdog):
    """The newest run is what everything else is waiting for."""
    older, newest = _member(1, 60), _member(2, 30)

    picked = _select(watchdog, [older, newest])

    assert [r["run_number"] for r in picked] == [1]


def test_an_in_progress_run_is_never_cancelled(watchdog):
    """in_progress means real work is happening — cancelling it destroys it."""
    working, newest = _member(1, 60, status="in_progress"), _member(2, 30)

    assert _select(watchdog, [working, newest]) == []


def test_approval_gated_statuses_are_never_cancelled(watchdog):
    """`waiting`/`requested` are approval gates, not a stuck queue."""
    for status in ("waiting", "requested"):
        gated, newest = _member(1, 60, status=status), _member(2, 30)
        assert _select(watchdog, [gated, newest]) == [], status


def test_runs_for_different_events_are_not_the_same_group(watchdog):
    """push and pull_request produce different github.ref, so different groups.

    Grouping them together would treat a PR run as superseding a push run on the
    same branch and cancel work that is not superseded at all.
    """
    push_run = _member(1, 60, event="push")
    pr_run = _member(2, 30, event="pull_request")

    assert _select(watchdog, [push_run, pr_run]) == []


def test_a_run_inside_the_grace_window_is_left_alone(watchdog):
    """A legitimate brief queue must not be mistaken for a stuck one."""
    recent, newest = _member(1, 2), _member(2, 1)

    assert _select(watchdog, [recent, newest], grace=5) == []


def test_selection_is_capped_by_the_budget_oldest_first(watchdog):
    """One sweep cannot cancel the world if the grouping is ever wrong."""
    runs = [_member(n, 100 - n) for n in range(1, 6)]  # 1 oldest ... 5 newest

    picked = _select(watchdog, runs, budget=2)

    assert [r["run_number"] for r in picked] == [1, 2]


def test_fork_runs_are_never_cancelled(watchdog):
    """Same restriction as the approval sweep, for the same reason."""
    fork = _member(1, 60, head_repository={"full_name": "someone/fork"})
    newest = _member(2, 30, head_repository={"full_name": "someone/fork"})

    assert _select(watchdog, [fork, newest]) == []


def test_a_lone_run_is_never_cancelled(watchdog):
    """With nothing newer, nothing supersedes it."""
    assert _select(watchdog, [_member(1, 60)]) == []
