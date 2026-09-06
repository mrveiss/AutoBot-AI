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
    session = _FakeSession()
    _install_fake_db(monkeypatch, session)
    job = _job([_stage("slm_self_update", ["Firing Ansible self-update", "queued"])])

    await resume_plan._persist_resume_plan(job, [], "abc123def456")

    assert session.added, "nothing was written to Settings at all"
    plan = json.loads(session.added[0].value)
    assert plan["stage_logs"]["slm_self_update"] == [
        "Firing Ansible self-update",
        "queued",
    ], f"the stored plan does not carry the stage's lines: {plan.get('stage_logs')!r}"


@pytest.mark.asyncio
async def test_the_persisted_slice_is_bounded(monkeypatch, resume_plan):
    """It lives in a Settings row, not a process, so it must not carry 200 lines."""
    session = _FakeSession()
    _install_fake_db(monkeypatch, session)
    cap = resume_plan._RESUME_PLAN_LOG_LINES
    job = _job([_stage("fleet_nodes", [f"line {i}" for i in range(cap + 25)])])

    await resume_plan._persist_resume_plan(job, [], "abc123def456")

    stored = json.loads(session.added[0].value)["stage_logs"]["fleet_nodes"]
    assert len(stored) == cap, f"stored {len(stored)} lines, expected the {cap} cap"
    assert stored[-1] == f"line {cap + 24}", "the cap kept the OLDEST lines; it must keep the newest"


def test_an_older_plan_version_is_still_accepted(resume_plan):
    """The compatibility that keeps this fix from being an outage.

    A straight bump rejects the plan written by the update that deploys this
    change: the SLM restarts, cannot read its own plan, and wedges. Asserted on
    the value, not on the source text.
    """
    supported = resume_plan._SUPPORTED_RESUME_PLAN_VERSIONS
    assert resume_plan._RESUME_PLAN_VERSION in supported
    assert len(supported) >= 2, (
        f"only {sorted(supported)} accepted; the previous plan version must stay readable "
        "or the deploying update wedges itself"
    )
