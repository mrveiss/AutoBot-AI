# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15139 — the retry sweep must reach the pull requests it was built for, and
its admission control must survive widening from one sha to every open PR.

Before this module, the workflow step computed
``HEAD_SHA: ${{ github.event.pull_request.head.sha || github.sha }}`` and only
ran on non-``pull_request`` events — where ``github.event.pull_request`` is
always unset, so ``HEAD_SHA`` always fell back to ``github.sha``, the BASE
branch tip. A red PR head was never the sha classified or re-dispatched. This
module instead lists every open pull request against the base branch (the same
pattern ``ci_dispatch_watchdog.py --check dispatch`` already uses) and sweeps
each head.

Widening the sweep to N pull requests makes the admission control sharper, not
softer, so every gate is covered here with its own test, each proven by
mutation (reintroduce the defect, watch the test fail, then revert):

* the re-run budget is spent ACROSS the whole sweep and stops the sweep before
  it reaches the next pull request, not reset per PR,
* an in-progress run count at the capacity ceiling declines the sweep outright,
* an unreadable rate-limit budget declines rather than being read as headroom,
* a run already at ``run_attempt >= 2`` is left red, never retried again, and
* the candidates that get re-dispatched carry an open PR's head sha, never a
  base-branch tip that no PR is red on.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest

_PIPELINE_DIR = Path(__file__).resolve().parents[1] / "pipeline-scripts"
REPO = "mrveiss/AutoBot-AI"


def _load(name: str, filename: str):
    """Load *filename* under *name* and register it in ``sys.modules`` first.

    Registering before ``exec_module`` means the sibling ``from X import Y``
    statements inside ci_dispatch_retry.py and ci_red_cause.py resolve to
    THESE loaded copies rather than triggering (or missing) a second load.
    """
    spec = importlib.util.spec_from_file_location(name, _PIPELINE_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_LOADED_NAMES = ("ci_dispatch_watchdog", "ci_red_cause", "ci_dispatch_retry")


@pytest.fixture()
def retry():
    """A fresh, isolated load of the module under test and its dependencies.

    Installs and removes each name in the same try/finally. Leaving them in
    ``sys.modules`` contaminates every test collected afterwards on the same
    worker -- the guard caught exactly that here, and it is the defect class
    #13224/#15338 exist for. The baseline is not the answer: it only shrinks.
    """
    saved = {name: sys.modules.get(name) for name in _LOADED_NAMES}
    try:
        watchdog = _load("ci_dispatch_watchdog", "ci_dispatch_watchdog.py")
        _load("ci_red_cause", "ci_red_cause.py")
        module = _load("ci_dispatch_retry", "ci_dispatch_retry.py")
        module.GitHubApi = watchdog.GitHubApi  # exposed for test construction below
        yield module
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


class _FakeTransport:
    """Stands in for ``GitHubApi.request`` — every call is recorded and routed
    by URL shape, the same way the real REST API is reached by path."""

    def __init__(
        self,
        *,
        rate_limit: Tuple[int, Dict[str, Any]] = (200, {"resources": {"core": {"remaining": 5000}}}),
        in_progress_count: int = 0,
        pulls: Optional[List[Dict[str, Any]]] = None,
        check_runs: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        jobs: Optional[Dict[int, Dict[str, Any]]] = None,
        rerun_response: Tuple[int, Dict[str, Any]] = (200, {}),
    ) -> None:
        self.rate_limit = rate_limit
        self.in_progress_count = in_progress_count
        self.pulls = pulls or []
        self.check_runs = check_runs or {}
        self.jobs = jobs or {}
        self.rerun_response = rerun_response
        self.calls: List[Tuple[str, str]] = []
        self.rerun_ids: List[int] = []

    def __call__(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None):
        self.calls.append((method, path))
        if path == "/rate_limit":
            return self.rate_limit
        if "/actions/runs?" in path:
            return 200, {"workflow_runs": [{"id": i} for i in range(self.in_progress_count)]}
        if "/pulls?" in path:
            return 200, self.pulls
        if "/commits/" in path and "/check-runs" in path:
            sha = path.split("/commits/")[1].split("/check-runs")[0]
            return 200, {"check_runs": self.check_runs.get(sha, [])}
        if "/actions/jobs/" in path:
            job_id = int(path.split("/actions/jobs/")[1].split("?")[0])
            job = self.jobs.get(job_id)
            return (200, job) if job is not None else (404, {"message": "not found"})
        if method == "POST" and "/rerun-failed-jobs" in path:
            run_id = int(path.split("/actions/runs/")[1].split("/rerun-failed-jobs")[0])
            self.rerun_ids.append(run_id)
            return self.rerun_response
        raise AssertionError(f"unexpected request: {method} {path}")


def _pull(number: int, sha: str, repo: str = REPO) -> Dict[str, Any]:
    return {
        "number": number,
        "head": {"sha": sha, "repo": {"full_name": repo}},
        "updated_at": "2026-08-29T00:00:00Z",
        "html_url": f"https://example.invalid/pull/{number}",
    }


def _infra_check_run(job_id: int) -> Dict[str, Any]:
    """A completed, red, Actions-app check run — resolves to job *job_id*."""
    return {
        "name": "Code Quality",
        "status": "completed",
        "conclusion": "failure",
        "id": job_id,
        "app": {"slug": "github-actions"},
        "html_url": "https://example.invalid/run",
    }


def _starved_job(run_id: int, run_attempt: int) -> Dict[str, Any]:
    """Zero executed steps — classifies as runner-starvation, an infra cause."""
    return {"run_id": run_id, "run_attempt": run_attempt, "steps": []}


def _api(retry_module, transport: _FakeTransport):
    api = retry_module.GitHubApi("token", REPO)
    api.request = transport
    return api


# --- budget is spent across the whole sweep, not reset per pull request ----


def test_budget_exhausted_mid_sweep_stops_before_the_next_pr(retry, monkeypatch):
    transport = _FakeTransport(
        pulls=[_pull(10, "sha-pr-10"), _pull(11, "sha-pr-11")],
        check_runs={
            "sha-pr-10": [_infra_check_run(501)],
            "sha-pr-11": [_infra_check_run(502)],
        },
        jobs={501: _starved_job(9001, 1), 502: _starved_job(9002, 1)},
    )
    api = _api(retry, transport)
    monkeypatch.setenv("CI_RETRY_MAX_RERUNS", "1")
    monkeypatch.setattr(retry, "build_api", lambda: api)

    rc = retry.run(dry_run=False)

    assert rc == 0
    # Only PR #10's red was spent against the budget — PR #11's was left red
    # rather than the budget resetting for it.
    assert transport.rerun_ids == [9001]


# --- capacity at the ceiling declines the sweep outright --------------------


def test_capacity_at_ceiling_declines_the_sweep(retry, monkeypatch):
    transport = _FakeTransport(
        in_progress_count=retry.DEFAULT_CAPACITY_CEILING,
        pulls=[_pull(20, "sha-pr-20")],
        check_runs={"sha-pr-20": [_infra_check_run(601)]},
        jobs={601: _starved_job(9101, 1)},
    )
    api = _api(retry, transport)
    monkeypatch.setattr(retry, "build_api", lambda: api)

    rc = retry.run(dry_run=False)

    assert rc == 0
    assert transport.rerun_ids == []
    # Declined before even listing open PRs — nothing downstream was spent.
    assert not any("/pulls?" in path for _, path in transport.calls)


# --- an unreadable rate-limit budget is spent, never treated as headroom ----


def test_unreadable_rate_limit_declines_rather_than_proceeding(retry, monkeypatch):
    transport = _FakeTransport(
        rate_limit=(503, {"message": "service unavailable"}),
        pulls=[_pull(30, "sha-pr-30")],
        check_runs={"sha-pr-30": [_infra_check_run(701)]},
        jobs={701: _starved_job(9201, 1)},
    )
    api = _api(retry, transport)
    monkeypatch.setattr(retry, "build_api", lambda: api)

    rc = retry.run(dry_run=False)

    assert rc == 0
    assert transport.rerun_ids == []
    assert not any("/pulls?" in path for _, path in transport.calls)


# --- one retry per run: a second attempt stays red --------------------------


def test_run_attempt_two_or_more_is_left_red_not_retried(retry, monkeypatch):
    transport = _FakeTransport(
        pulls=[_pull(40, "sha-pr-40")],
        check_runs={"sha-pr-40": [_infra_check_run(801)]},
        jobs={801: _starved_job(9301, 2)},  # already at attempt 2
    )
    api = _api(retry, transport)
    monkeypatch.setattr(retry, "build_api", lambda: api)

    rc = retry.run(dry_run=False)

    assert rc == 0
    assert transport.rerun_ids == []


# --- the sweep reaches an open PR's head sha, never a base-branch tip -------


def test_sweep_reaches_an_open_prs_head_sha_not_a_base_tip(retry, monkeypatch):
    pr_head_sha = "pr-head-sha"
    base_tip_sha = "base-tip-sha"  # deliberately not registered below
    transport = _FakeTransport(
        pulls=[_pull(42, pr_head_sha)],
        check_runs={pr_head_sha: [_infra_check_run(901)]},
        jobs={901: _starved_job(9401, 1)},
    )
    api = _api(retry, transport)
    monkeypatch.setattr(retry, "build_api", lambda: api)

    rc = retry.run(dry_run=False)

    assert rc == 0
    assert transport.rerun_ids == [9401]
    assert not any(base_tip_sha in path for _, path in transport.calls)
