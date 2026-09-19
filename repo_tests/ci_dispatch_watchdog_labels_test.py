# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16309 — the dispatch watchdog reads a starved run's queued-job labels before it names a runner pool.

The watchdog published ``failure: ... self-hosted run(s) queued ... no runner
available`` on approved PRs whose queued jobs carried ``ubuntu-latest``. That was
GitHub-hosted concurrency saturation, reported as an outage of a self-hosted pool
that serves no job here. The ``labels`` on ``GET /actions/runs/{id}/jobs`` name
the pool a job waits for, so:

* a hosted-only queue is saturation, with its counts, and never an outage;
* a self-hosted job queued while no self-hosted job is served is still an outage;
* a mixed queue names only its self-hosted runs in the outage;
* a job ``pending`` on a concurrency group (#16320's ``queue: max``) is not starved.

This lives in its own file rather than ``ci_dispatch_watchdog_test.py``, which sits
at its frozen size ceiling.
"""

from __future__ import annotations

import importlib.util
from datetime import datetime, timedelta, timezone

import pytest
from repo_tests._paths import repo_root

_SCRIPTS = repo_root() / "pipeline-scripts"

NOW = datetime(2026, 9, 11, 12, 0, 0, tzinfo=timezone.utc)
REPO = "mrveiss/AutoBot-AI"
WORKFLOW_PATH = ".github/workflows/frontend-test.yml"
GRACE, STALL = 10, 30
_PROBE_CONFIG = {"stall_minutes": 45, "max_job_lookups": 5, "job_overdue_minutes": 45}


def _load(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def wd():
    return _load("ci_dispatch_watchdog")


@pytest.fixture(scope="module")
def pools():
    return _load("ci_dispatch_labels")


def _ts(minutes_ago, now=NOW):
    return (now - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _live_ts(minutes_ago):
    """Relative to the real clock, for the entry points that read it themselves."""
    return _ts(minutes_ago, datetime.now(timezone.utc))


def _starved(run_id, name, created_at=None, **overrides):
    run = {
        "id": run_id,
        "name": name,
        "status": "queued",
        "conclusion": None,
        "created_at": created_at or _ts(45),
        "path": WORKFLOW_PATH,
    }
    run.update(overrides)
    return run


def _job(status, *labels):
    return {"name": "job", "status": status, "labels": list(labels)}


def _hosted(status="queued"):
    return _job(status, "ubuntu-latest")


def _self_hosted(pools, status="queued"):
    return _job(status, pools.SELF_HOSTED_LABEL, "Linux", "X64")


def _classify(wd, runs, jobs, pool_serving=False, declared=None, hosted_running=7):
    """*declared* is the set of workflow paths declaring a self-hosted job; None means unreadable."""
    return wd.classify_dispatch(runs, _ts(45), NOW, GRACE, STALL, pool_serving, (), declared, jobs, hosted_running)


class _LabelsJobsApi:
    """Serves job listings by run id, records which runs were listed, and records statuses."""

    repository = REPO

    def __init__(self, jobs_by_run, queued=(), running=()):
        self._jobs = jobs_by_run
        self._queued = list(queued)
        self._running = list(running)
        self.listed = []
        self.statuses = []

    def run_jobs(self, run_id):
        self.listed.append(run_id)
        value = self._jobs.get(run_id, [])
        if isinstance(value, Exception):
            raise value
        return value

    def recent_runs(self, per_page=100, run_status=""):
        return list(self._queued) if run_status == "queued" else list(self._running)

    def runs_for_sha(self, sha):
        return list(self._queued)

    def set_status(self, sha, state, context, description, target_url):
        self.statuses.append((state, description))
        return 201


# --- the dispatch verdict ----------------------------------------------------


def test_a_hosted_only_queue_is_saturation_not_an_outage(wd):
    """Unreadable declarations and no self-hosted job served: the pair that used to publish an outage."""
    runs = [_starved(1, "Frontend Testing Suite"), _starved(2, "Code Quality")]

    state, description = _classify(wd, runs, {1: [_hosted(), _hosted()], 2: [_hosted()]})

    assert state == "pending"
    assert description.startswith("hosted-runner concurrency saturated (3 queued, 7 running)")
    assert "no runner available" not in description


def test_a_queued_self_hosted_job_with_an_idle_pool_is_an_outage(wd, pools):
    """The label outranks the declaration: this workflow declares no self-hosted job."""
    runs = [_starved(1, "Frontend Testing Suite")]

    state, description = _classify(wd, runs, {1: [_self_hosted(pools)]}, declared=set())

    assert state == "failure"
    assert description.startswith("1 self-hosted run(s) queued over 30m with no runner available")


def test_a_queued_self_hosted_job_behind_a_serving_pool_is_contention(wd, pools):
    runs = [_starved(1, "Frontend Testing Suite")]

    state, description = _classify(wd, runs, {1: [_self_hosted(pools)]}, pool_serving=True)

    assert state == "pending"
    assert "busy queue" in description


def test_a_mixed_queue_names_only_its_self_hosted_runs_in_the_outage(wd, pools):
    runs = [_starved(1, "Code Quality"), _starved(2, "Frontend Testing Suite")]
    jobs = {1: [_hosted()], 2: [_self_hosted(pools), _hosted()]}

    state, description = _classify(wd, runs, jobs, declared=set())

    assert state == "failure"
    assert description.startswith("1 self-hosted run(s)")
    assert "Frontend Testing Suite" in description
    assert "Code Quality" not in description


def test_a_mixed_queue_behind_a_serving_pool_reports_the_hosted_saturation(wd, pools):
    runs = [_starved(1, "Code Quality"), _starved(2, "Frontend Testing Suite")]
    jobs = {1: [_hosted()], 2: [_self_hosted(pools), _hosted()]}

    state, description = _classify(wd, runs, jobs, pool_serving=True)

    assert state == "pending"
    assert description.startswith("hosted-runner concurrency saturated (1 queued, 7 running)")
    assert "Code Quality" in description


def test_a_job_pending_on_its_concurrency_group_is_not_starvation(wd):
    """#16320's shards wait their turn as `pending`: that is dispatch, not a stall."""
    runs = [_starved(1, "AutoBot CI/CD Pipeline")]

    state, description = _classify(wd, runs, {1: [_hosted("pending")]})

    assert state == "success"
    assert "dispatched" in description


def test_a_run_with_no_readable_job_is_placed_by_its_workflow(wd):
    """#13045's `jobs: []` carries no label, so the declared `runs-on` decides (#14364)."""
    runs = [_starved(1, "Frontend Testing Suite")]

    declared_state, _ = _classify(wd, runs, {1: []}, declared={WORKFLOW_PATH})
    undeclared_state, description = _classify(wd, runs, {}, declared=set())

    assert declared_state == "failure"
    assert undeclared_state == "pending"
    assert "busy queue" in description


def test_an_unknown_running_count_is_stated_not_invented(wd):
    _, description = _classify(wd, [_starved(1, "Code Quality")], {1: [_hosted()]}, hosted_running=None)

    assert "(1 queued, unknown running)" in description


def test_a_queued_job_without_labels_names_no_pool(pools):
    run = _starved(1, "Code Quality")

    assert pools.place_run(run, [_job("queued")], set()) == pools.UNATTRIBUTED
    assert pools.place_run(run, [_job("queued")], None) == pools.SELF_HOSTED


def test_an_unattributable_run_stays_reportable(pools):
    """Unknown must not silence a real outage — it resolves toward reporting."""
    no_paths_known = None
    no_path_on_run = {WORKFLOW_PATH}

    assert pools.run_requires_self_hosted(_starved(1, "a"), no_paths_known) is True
    assert pools.run_requires_self_hosted({"id": 1}, no_path_on_run) is True
    assert pools.run_requires_self_hosted(_starved(1, "a", path=""), no_path_on_run) is True


# --- the budgeted job reads ----------------------------------------------------


def test_the_job_reader_spends_no_more_than_its_budget(wd, pools):
    """A saturated queue is when hundreds of runs starve, and the token's hourly budget is shared."""
    api = _LabelsJobsApi({1: [_hosted()], 2: [_hosted()], 3: [_hosted()]})
    notes = []
    reader = pools.QueuedJobReader(api, wd.WatchdogApiError, notes.append, budget=2)

    first = reader.read([_starved(1, "a"), _starved(2, "b")])
    second = reader.read([_starved(3, "c")])
    reader.read([_starved(3, "c")])

    assert api.listed == [1, 2]
    assert sorted(first) == [1, 2]
    assert second == {}
    assert len(notes) == 1, "the spent budget is said once per sweep, not once per head"


def test_a_failed_job_listing_leaves_the_run_to_its_workflow(wd, pools):
    api = _LabelsJobsApi({1: wd.WatchdogApiError("HTTP 502")})
    notes = []
    reader = pools.QueuedJobReader(api, wd.WatchdogApiError, notes.append, budget=5)

    assert reader.read([_starved(1, "a")]) == {}
    assert "HTTP 502" in notes[0]


def test_an_unset_budget_is_the_module_default(wd, pools):
    reader = pools.QueuedJobReader(_LabelsJobsApi({}), wd.WatchdogApiError, [].append)

    assert reader.remaining == pools.DEFAULT_QUEUED_JOB_LOOKUPS


def test_load_config_supplies_the_queued_job_budget(wd, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "token")
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setenv("WATCHDOG_MAX_QUEUED_JOB_LOOKUPS", "12")

    assert wd.load_config()["max_queued_job_lookups"] == 12


# --- the wiring: sweep, pool inspection and starvation probe -------------------


def test_the_sweep_publishes_saturation_from_the_labels_it_read(wd, tmp_path):
    """End to end through publish_dispatch_states, with the workflow declarations unreadable."""
    api = _LabelsJobsApi({1: [_hosted()]}, queued=[_starved(1, "Frontend Testing Suite", _live_ts(60))])
    head = wd.PullHead(number=5, sha="head", updated_at=_live_ts(60), url="u", same_repo=True)
    config = {"grace_minutes": GRACE, "stall_minutes": STALL, "status_context": "ctx"}
    config["workflow_dir"] = str(tmp_path / "absent")

    wd.publish_dispatch_states(api, [head], config, dry_run=False, pool_serving=False, hosted_running=4)

    assert api.listed == [1]
    [(state, description)] = api.statuses
    assert state == "pending"
    assert description.startswith("hosted-runner concurrency saturated (1 queued, 4 running)")


def test_the_pool_inspection_counts_the_hosted_jobs_running(wd):
    running = [{"id": 1, "name": "CI", "head_sha": "head"}]
    api = _LabelsJobsApi({1: [_hosted("in_progress"), _hosted("in_progress"), _hosted()]}, running=running)

    pool = wd.inspect_self_hosted_pool(api, 5, now=NOW)

    assert pool.serving is False
    assert pool.hosted_running == 2


def _probe_queue():
    return [{"id": 9, "name": "CI", "status": "queued", "created_at": _live_ts(60), "head_branch": "b"}]


def test_the_starvation_probe_ignores_a_hosted_queue(wd, tmp_path):
    """The run carries no `path`, so its workflow cannot rule the pool out: only the label does."""
    api = _LabelsJobsApi({9: [_hosted()]}, queued=_probe_queue())

    assert wd.check_runner_starvation(api, {**_PROBE_CONFIG, "workflow_dir": str(tmp_path)}) == 0


def test_the_starvation_probe_still_fails_on_a_queued_self_hosted_job(wd, pools, tmp_path):
    api = _LabelsJobsApi({9: [_self_hosted(pools)]}, queued=_probe_queue())

    assert wd.check_runner_starvation(api, {**_PROBE_CONFIG, "workflow_dir": str(tmp_path)}) == 1
