# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20214: a resumed rollback reads its ref once from the persisted plan and runs the fleet stage inside it."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).parent))
from _code_sync_import import import_code_sync  # noqa: E402

import_code_sync()

from api import _resume_plan  # noqa: E402
from api.code_sync import UpdateAllJob, _execute_resume, _make_stage  # noqa: E402
from services.rollback_target import current_rollback_ref, deploy_ref_vars, rollback_scope  # noqa: E402
from testkit.fake_async_session import FakeAsyncSession  # noqa: E402

SHA = "a" * 40
_NAMES = ("github_fetch", "code_source_pull", "slm_self_update", "fleet_nodes")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _job():
    return UpdateAllJob(
        job_id="j", status="running", created_at="2026-01-01T00:00:00+00:00", stages=[_make_stage(n) for n in _NAMES]
    )


class _Stored:
    """Stands in for the ``Setting`` row: keeps the value the persister wrote."""

    key = None  # the persister builds `Setting.key == ...` for its lookup

    def __init__(self, key, value):
        self.key, self.value = key, value


class _DbService:
    def __init__(self, session):
        self._session = session

    def session(self):
        outer = self

        class _Ctx:
            async def __aenter__(self):
                return outer._session

            async def __aexit__(self, *exc):
                return False

        return _Ctx()


def _persisted_plan(job) -> dict:
    """Run the real persister and return what it stored, JSON-decoded as the resume hook decodes it."""
    session = FakeAsyncSession()
    with (
        patch("services.database.db_service", _DbService(session), create=True),
        patch.object(_resume_plan, "Setting", _Stored),
    ):
        _run(_resume_plan._persist_resume_plan(job, ["n1"], SHA))
    return json.loads(session.added[0].value)


def _resume(plan: dict):
    """Drive the real ``_execute_resume`` with every stage but the fleet stubbed; report what the fleet stage saw."""
    job, seen = _job(), {}

    async def fleet(j, remaining):
        seen["ref"] = current_rollback_ref()
        seen["vars"] = await deploy_ref_vars("update-all-nodes.yml")

    with (
        patch("api.code_sync.wait_for_detached_self_update", AsyncMock(return_value=True)),
        patch("api.code_sync._resume_verify_slm_stage", AsyncMock(return_value=True)),
        patch("api.code_sync._run_fleet_stage", fleet),
        patch("api.code_sync._clear_resume_plan", AsyncMock()),
    ):
        _run(_execute_resume(job, SHA, ["n1"], plan))
    return job, seen


def test_a_rollback_plan_written_by_the_persister_resumes_inside_the_scope():
    with rollback_scope(SHA):
        plan = _persisted_plan(_job())
    assert (plan["deploy_ref"], plan["is_rollback"]) == (SHA, True)
    job, seen = _resume(plan)
    assert seen["ref"] == SHA and seen["vars"] == {"deploy_ref": SHA, "deploy_is_rollback": "true"}
    assert current_rollback_ref() is None and job.status == "running"


def test_an_ordinary_plan_resumes_without_a_scope():
    plan = _persisted_plan(_job())
    assert (plan["deploy_ref"], plan["is_rollback"]) == (None, False)
    _, seen = _resume(plan)
    assert seen["ref"] is None and seen["vars"] == {}


def test_a_rollback_plan_that_lost_its_ref_fails_the_job_and_never_runs_the_fleet():
    for bad in ({"is_rollback": True}, {"is_rollback": True, "deploy_ref": "main"}):
        job, seen = _resume(bad)
        assert job.status == "failed" and "target commit" in job.failure_reason
        assert seen == {}
