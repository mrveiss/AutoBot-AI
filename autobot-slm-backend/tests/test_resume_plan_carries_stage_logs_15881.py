# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The update log must survive the restart the update performs (#15881).

`_stage_log` appends to `stage.log_lines`, an in-memory list on a job object
held by the SLM process -- and the self-update restarts that process. Every
line the operator was watching died with it, and the resumed job wrote
"completed before restart" placeholders *over* the real history. A clean update
was then indistinguishable from a wedged one: on the day this was filed the play
finished `ok=282 changed=57 failed=0` while the GUI log still ended at
"Firing Ansible self-update (fire-and-forget)".

These tests exercise the real `_persist_resume_plan` against a fake session and
read what it actually serialises. An earlier version asserted only that the
source text contained `"stage_logs"` -- which passes whether or not the value
reaches the Settings row, and is the same could-not-fail shape that had #15770
reopened. Review caught it; the fix is to run the function.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[1] / "api"


class _FakeResult:
    def __init__(self, existing):
        self._existing = existing

    def scalar_one_or_none(self):
        return self._existing


class _FakeSession:
    """Captures what the writer stores, so the assertion reads the real value."""

    def __init__(self, existing=None):
        self.existing = existing
        self.added = []
        self.committed = False

    async def execute(self, _stmt):
        return _FakeResult(self.existing)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False


def _install_fake_db(monkeypatch, session):
    module = types.ModuleType("services.database")
    module.db_service = types.SimpleNamespace(session=lambda: session)
    monkeypatch.setitem(sys.modules, "services.database", module)


class _ExistingRow:
    """A stand-in for the Settings row, so the writer takes its UPDATE path.

    The create path calls `Setting(key=..., value=...)`. Several python-suite
    shards import this module with the SLM config stack replaced by MagicMock,
    which makes `Setting` a MagicMock too -- so `.value` came back a MagicMock
    and `json.loads` raised. Reading a value off a class the harness may have
    mocked tests the harness, not the writer. Updating a row we own reads back
    exactly what the writer serialised, under either harness.
    """

    def __init__(self):
        self.key = None
        self.value = None


def _stored_plan(session):
    """The JSON the writer actually persisted, whichever path it took."""
    if session.existing is not None and session.existing.value is not None:
        return json.loads(session.existing.value)
    assert session.added, "nothing was written to Settings at all"
    return json.loads(session.added[0].value)


def _stage(name, lines):
    return types.SimpleNamespace(name=name, log_lines=list(lines))


def _job(stages):
    return types.SimpleNamespace(job_id="job-1", created_at="2026-09-06T00:00:00Z", stages=stages)


@pytest.fixture
def resume_plan():
    sys.path.insert(0, str(_API.parent))
    return pytest.importorskip("api._resume_plan")


@pytest.mark.asyncio
async def test_the_persisted_row_actually_contains_the_stage_lines(monkeypatch, resume_plan):
    """The behavioural check: read the JSON the writer stored, not the source text."""
    session = _FakeSession(existing=_ExistingRow())
    _install_fake_db(monkeypatch, session)
    job = _job([_stage("slm_self_update", ["Firing Ansible self-update", "queued"])])

    await resume_plan._persist_resume_plan(job, [], "abc123def456")

    plan = _stored_plan(session)
    assert plan["stage_logs"]["slm_self_update"] == [
        "Firing Ansible self-update",
        "queued",
    ], f"the stored plan does not carry the stage's lines: {plan.get('stage_logs')!r}"


@pytest.mark.asyncio
async def test_the_persisted_slice_is_bounded(monkeypatch, resume_plan):
    """It lives in a Settings row, not a process, so it must not carry 200 lines."""
    session = _FakeSession(existing=_ExistingRow())
    _install_fake_db(monkeypatch, session)
    cap = resume_plan._RESUME_PLAN_LOG_LINES
    job = _job([_stage("fleet_nodes", [f"line {i}" for i in range(cap + 25)])])

    await resume_plan._persist_resume_plan(job, [], "abc123def456")

    stored = _stored_plan(session)["stage_logs"]["fleet_nodes"]
    assert len(stored) == cap, f"stored {len(stored)} lines, expected the {cap} cap"
    assert stored[-1] == f"line {cap + 24}", "the cap kept the OLDEST lines; it must keep the newest"


def test_a_v1_plan_written_by_the_deploying_update_is_still_readable(resume_plan):
    """The compatibility that keeps this fix from being an outage.

    Review (#15880) caught the earlier version of this test asserting on
    `_SUPPORTED_RESUME_PLAN_VERSIONS` itself -- which passes no matter what the
    gate does with it. Changing the check back to `!= _RESUME_PLAN_VERSION` (what
    the code said before v1 support, so the likeliest edit anyone makes) left the
    old assertion green while v1 plans were discarded. It ran the gate's inputs
    and never the gate.

    It is worse than a silent skip: the rejection path calls
    `_clear_resume_plan()`, so a v1 plan is DELETED rather than passed over, and
    the wedge it causes cannot be cleared by restarting.
    """
    supported = resume_plan.plan_version_is_supported
    assert supported({"version": 1}), (
        "a v1 plan is rejected -- the update deploying this change writes v1 before "
        "the restart and would discard its own resume plan, then clear it"
    )
    assert supported({"version": resume_plan._RESUME_PLAN_VERSION})
    assert not supported({"version": 99}), "an unknown future version must not be read"
    assert not supported({}), "a plan with no version must not be read"


class _Stage:
    """Mirrors `UpdateAllStage`'s shape: constructed empty, logs appended later."""

    def __init__(self, name, status, message):
        self.name = name
        self.status = status
        self.message = message
        self.log_lines = []


def test_a_restored_stage_carries_its_pre_restart_lines(resume_plan):
    """The restore direction. Persisting the lines is worthless if nothing reads them."""
    stage = resume_plan.restored_stage(
        _Stage,
        "github_fetch",
        "success",
        "completed before restart",
        {"github_fetch": ["Fetching latest commit ...", "Fetched remote commit abc123"]},
    )
    assert stage.log_lines[:2] == ["Fetching latest commit ...", "Fetched remote commit abc123"]


def test_the_restart_is_marked_and_marked_last(resume_plan):
    """AC2: a reader must be able to tell which lines predate the restart.

    The marker has to sit *after* the carried lines -- ahead of them it would
    label the restored history as post-restart, which is the same lie the
    placeholder told.
    """
    stage = resume_plan.restored_stage(_Stage, "code_source_pull", "success", "done", {"code_source_pull": ["a", "b"]})
    assert "restarted" in stage.log_lines[-1]
    assert stage.log_lines[:2] == ["a", "b"]


def test_a_plan_without_logs_still_restores_a_usable_stage(resume_plan):
    """The other direction, which the issue calls out by name.

    A v1 plan carries no `stage_logs`. It must still resume -- rejecting it
    would discard the resume plan of the very update deploying this change.
    And it must not gain a bare marker: a lone "SLM restarted here" over an
    empty log is the placeholder problem wearing a new label.
    """
    stage = resume_plan.restored_stage(_Stage, "slm_self_update", "running", "SLM restarting ...", {})
    assert stage.log_lines == []
    assert stage.message == "SLM restarting ..."
