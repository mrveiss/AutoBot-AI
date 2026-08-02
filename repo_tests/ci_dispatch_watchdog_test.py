# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#12823 / #13045 — the CI dispatch watchdog must never report ``success`` for a
head commit whose CI has not demonstrably dispatched.

The two production failure modes are covered directly:

* runs created with ``conclusion=action_required`` (parked behind the fork-PR
  approval policy after ``auto-update-pr-branches`` pushes as the bot), and
* runs created but never allocated a job while the self-hosted runner pool is
  empty (``status=queued``, ``jobs: []``).

``interpret_probe`` is covered too: it is the mechanism that distinguishes "this
credential may not approve runs" from "this run is not in an approvable state",
which is what decides whether owner action is required.
"""

import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "pipeline-scripts" / "ci_dispatch_watchdog.py"

NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc)


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
    }
    run.update(overrides)
    return run


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


# --- #12823: parked runs ---------------------------------------------------


def test_parked_run_is_reported_as_failure(watchdog):
    runs = [
        _run(status="completed", conclusion="action_required", name="Code Quality"),
        _run(id=2, name="PR Template Check", status="completed", conclusion="action_required"),
    ]
    state, description = watchdog.classify_dispatch(runs, _ts(5), NOW, 10, 30)
    assert state == "failure"
    assert "parked awaiting approval" in description
    assert "Code Quality" in description


def test_parked_run_outranks_otherwise_green_runs(watchdog):
    """A head with 20 green runs and one parked run is still not verified."""
    runs = [_run(id=i) for i in range(20)]
    runs.append(_run(id=99, conclusion="action_required", name="Enforce Pre-commit Hooks"))
    state, _ = watchdog.classify_dispatch(runs, _ts(60), NOW, 10, 30)
    assert state == "failure"


# --- #13045: starved runs and absent runs ----------------------------------


def test_queued_run_past_the_stall_threshold_is_failure(watchdog):
    runs = [_run(status="queued", conclusion=None, created_at=_ts(45), name="Unit & Integration Tests")]
    state, description = watchdog.classify_dispatch(runs, _ts(45), NOW, 10, 30)
    assert state == "failure"
    assert "no runner" in description


def test_queued_run_inside_the_stall_threshold_is_success(watchdog):
    runs = [_run(status="queued", conclusion=None, created_at=_ts(4))]
    state, _ = watchdog.classify_dispatch(runs, _ts(4), NOW, 10, 30)
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
    runs = [
        _run(id=i, conclusion="action_required", name=f"A very long workflow name number {i}" * 4) for i in range(30)
    ]
    _, description = watchdog.classify_dispatch(runs, _ts(5), NOW, 10, 30)
    assert len(description) <= watchdog.MAX_STATUS_DESCRIPTION


# --- starvation reporting ---------------------------------------------------


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


def test_probe_is_inconclusive_rather_than_wrong_on_unknown_errors(watchdog):
    permitted, explanation = watchdog.interpret_probe(500, "Server Error")
    assert permitted is True
    assert "inconclusive" in explanation


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
    """Right after update-branch returns, an empty result means "too early"."""
    assert watchdog.needs_another_look([]) is True


def test_head_with_a_parked_run_is_polled_again(watchdog):
    assert watchdog.needs_another_look([_run(), _run(id=2, conclusion="action_required")]) is True


def test_head_with_dispatched_runs_is_settled(watchdog):
    assert watchdog.needs_another_look([_run(), _run(id=2)]) is False
