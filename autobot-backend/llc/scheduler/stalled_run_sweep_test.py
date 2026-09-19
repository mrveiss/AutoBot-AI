# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The stalled-run sweep must sweep, and must not sweep what is still alive (#16817).

The defect this closes was not a wrong result — it was no result at all: nothing read
``llc_heartbeat_runs`` back to decide a run had stopped. So the tests that matter are
the ones that fail if the sweep ever stops selecting: a sweep that quietly matches
nothing is indistinguishable from the state before it existed.
"""

import importlib
from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture
def sweep(monkeypatch):
    """Import with a short timeout so the tests do not depend on the six-hour default."""
    monkeypatch.setenv("LLC_RUN_STALL_TIMEOUT_SECONDS", "60")
    module = importlib.import_module("llc.scheduler.stalled_run_sweep")
    return importlib.reload(module)


def test_the_timeout_is_env_var_backed_not_a_literal(sweep):
    assert sweep.STALL_TIMEOUT_SECONDS == 60


def test_the_default_is_used_when_the_env_var_is_absent(monkeypatch):
    monkeypatch.delenv("LLC_RUN_STALL_TIMEOUT_SECONDS", raising=False)
    module = importlib.reload(importlib.import_module("llc.scheduler.stalled_run_sweep"))
    assert module.STALL_TIMEOUT_SECONDS == 6 * 60 * 60


def test_a_run_older_than_the_cutoff_is_past_it(sweep):
    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    assert old <= sweep._cutoff()


def test_a_fresh_run_is_not_past_the_cutoff(sweep):
    fresh = datetime.now(timezone.utc) - timedelta(seconds=5)
    assert fresh > sweep._cutoff()


def test_only_non_terminal_statuses_are_candidates(sweep):
    """A completed or failed run is finished; sweeping it would rewrite history."""
    assert set(sweep.NON_TERMINAL_STATUSES) == {"queued", "running"}
    for terminal in ("completed", "failed", "interrupted", "timeout"):
        assert terminal not in sweep.NON_TERMINAL_STATUSES


def test_the_error_says_the_sweep_decided_it(sweep):
    """A swept run must be tellable from an adapter-reported timeout.

    Both end as status ``timeout``. The status alone cannot answer "did the adapter
    time out, or did we lose contact", and that is the question an operator asks
    first. The error text is the only place that distinguishes them.
    """
    message = sweep.STALL_ERROR.format(seconds=60)
    assert "sweep" in message
    assert "60" in message
    assert "16817" in message


def test_the_sweep_is_registered_as_a_named_celery_task(sweep):
    """An unregistered task is a sweep that never runs — the state before this."""
    assert sweep.run_stalled_run_sweep.name == "llc.scheduler.stalled_run_sweep.run_stalled_run_sweep"
