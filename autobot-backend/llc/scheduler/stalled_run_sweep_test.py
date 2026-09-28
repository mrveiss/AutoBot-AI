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
from sqlalchemy.dialects import postgresql

from llc.models.enums import LLCRunStatus


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
    """The human-readable half of the distinction.

    #16817 rewrote this test's premise. It used to read "both end as status
    ``timeout`` ... the error text is the only place that distinguishes them", which
    was true and was the defect: telling a stall from an adapter timeout meant
    matching a formatted message. ``STALLED`` now carries the fact and this carries
    the detail, so a re-wording here can no longer make the two indistinguishable.
    """
    message = sweep.STALL_ERROR.format(seconds=60)
    assert "sweep" in message
    assert "60" in message
    assert "16817" in message


def test_a_swept_run_is_stalled_rather_than_timeout(sweep):
    """AC4: the reason is recorded in the status, not inferred from the error.

    Four sites set ``TIMEOUT`` -- http_adapter, subprocess_base, heartbeat_scheduler
    and this sweep -- so before #16817 a consumer asking "which runs stalled?" had to
    match the error text. A status the sweep alone writes is what makes that a lookup.
    """
    assert LLCRunStatus.STALLED.value == "stalled"
    assert LLCRunStatus.STALLED is not LLCRunStatus.TIMEOUT


@pytest.mark.parametrize("other", ["TIMEOUT", "FAILED", "CANCELLED", "INTERRUPTED"])
def test_stalled_is_distinct_from_every_status_it_could_be_confused_with(other):
    """AC4 names failed and cancelled; timeout is the one it actually shared."""
    assert LLCRunStatus.STALLED.value != getattr(LLCRunStatus, other).value


def test_stalled_is_terminal(sweep):
    """A swept run is over. ``is_terminal`` is a deny-list over {queued, running},
    so this holds by construction -- asserted because that is the property relied on
    when STALLED was added without editing the terminal set."""
    assert LLCRunStatus.STALLED.is_terminal() is True
    assert LLCRunStatus.STALLED.value not in sweep.NON_TERMINAL_STATUSES


def _compiled(sweep):
    """Compiled against PostgreSQL, because that is what runs it.

    The default dialect renders ``FOR UPDATE`` and silently drops ``SKIP LOCKED`` --
    it is a PostgreSQL extension. Asserting against the generic rendering would have
    reported a lock clause that production does not get, which is the shape of error
    this sweep's own tests exist to avoid.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
    return str(sweep._stalled_candidates(cutoff).compile(dialect=postgresql.dialect()))


def test_the_rows_are_locked_and_locked_rows_are_skipped(sweep):
    """AC5, and it is about timing rather than today's behaviour.

    Two beat workers overlapping today would write the same terminal status, so the
    race is invisible. #16818 adds the release of claims, assignments and workspace
    leases to this path -- and the same race then releases each holding twice. The
    lock has to be here before the side effects that need it.
    """
    sql = _compiled(sweep)
    assert "FOR UPDATE" in sql
    assert "SKIP LOCKED" in sql


def test_the_age_comparison_happens_in_sql(sweep):
    """The scan fix: the WHERE carries the age rule, so the sweep does not load every
    non-terminal run and filter in Python. The original comment's NULL reasoning was
    right -- COALESCE is that reasoning expressed where the index can serve it."""
    sql = _compiled(sweep).lower()
    assert "coalesce" in sql
    assert "started_at" in sql and "created_at" in sql


def test_the_sweep_is_registered_as_a_named_celery_task(sweep):
    """An unregistered task is a sweep that never runs — the state before this."""
    assert sweep.run_stalled_run_sweep.name == "llc.scheduler.stalled_run_sweep.run_stalled_run_sweep"


class _Run:
    """A row the sweep may close out. Only the fields the sweep touches."""

    def __init__(self):
        self.status = "running"
        self.finished_at = None
        self.error = None


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Session:
    def __init__(self, rows):
        self._rows = rows
        self.committed = False
        self.statement = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def execute(self, statement):
        self.statement = statement
        return _Result(self._rows)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_the_sweep_writes_stalled_and_closes_the_run_out(sweep, monkeypatch):
    """AC6's status half, driven through `_async_sweep` rather than asserted on the enum.

    Without this, every other AC4 test here passes while the sweep writes whatever it
    likes -- the enum member existing is not the sweep using it. Mutation-checked:
    changing the write back to TIMEOUT fails this and nothing else.
    """
    row = _Run()
    session = _Session([row])
    monkeypatch.setattr(sweep, "get_async_session_factory", lambda: (lambda: session))

    stalled = await sweep._async_sweep()

    assert stalled == 1
    assert row.status == LLCRunStatus.STALLED.value
    assert row.finished_at is not None, "a swept run must be closed out, not just relabelled"
    assert "16817" in row.error
    assert session.committed is True


@pytest.mark.asyncio
async def test_a_sweep_with_nothing_to_do_reports_zero_rather_than_silence(sweep, monkeypatch):
    """AC7: a sweep that found nothing and a sweep that did not run must differ.

    The count is the return value, and it is logged unconditionally -- so zero is a
    measurement here, not an absence of one.
    """
    session = _Session([])
    monkeypatch.setattr(sweep, "get_async_session_factory", lambda: (lambda: session))

    assert await sweep._async_sweep() == 0
    assert session.committed is True
