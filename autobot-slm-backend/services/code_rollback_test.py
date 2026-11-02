# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A rollback runs the Update Everything stages with the chosen commit as the target (#20214)."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import api
from services import code_rollback as cr
from services.rollback_commits import CommitInfo
from services.rollback_migrations import BLOCKED, CLEAR, UNKNOWN, MigrationCheck
from services.rollback_target import current_rollback_ref

TARGET = CommitInfo(commit="b" * 40, date="2026-10-01T10:00:00+00:00", subject="an earlier change")
LATEST = "c" * 40


def _fake_cs(*, slm_fired: bool, seen: dict):
    """Stands in for api.code_sync; records what each stage was given and which rollback ref was in scope."""
    stages = {
        n: SimpleNamespace(name=n, status="pending", message=None, completed_at=None, log_lines=[])
        for n in ("github_fetch", "code_source_pull", "slm_self_update", "fleet_nodes")
    }

    async def _github(job, db):
        seen["github_ref"] = current_rollback_ref()
        return LATEST

    async def _outdated(job, commit, db):
        seen["outdated_target"] = commit
        return ["n1"]

    async def _slm(job, commit, outdated, db):
        seen["slm_target"], seen["slm_ref"] = commit, current_rollback_ref()
        return slm_fired

    async def _reconcile(job, commit, outdated):
        seen["reconcile_target"] = commit

    async def _fleet(job, outdated, commit):
        seen["fleet_target"], seen["fleet_ref"] = commit, current_rollback_ref()

    return SimpleNamespace(
        _StageStatus=SimpleNamespace(SKIPPED="skipped"),
        utc_timestamp=lambda: "now",
        _get_stage=lambda job, name: stages[name],
        _mark_progress=lambda job: None,
        _stage_log=lambda stage, msg: stage.log_lines.append(msg),
        _fail_fleet_stage=lambda job, stage, reason: setattr(job, "status", "failed"),
        _run_github_stage=_github,
        _collect_outdated_node_ids=_outdated,
        _run_slm_stage=_slm,
        _reconcile_self_update_stage=_reconcile,
        _run_fleet_stage_or_already_current=_fleet,
        _get_tracker_for_db=AsyncMock(return_value=SimpleNamespace(repo_path="r", remote="origin", branch="main")),
        stages=stages,
    )


@pytest.fixture(autouse=True)
def _still_an_ancestor(monkeypatch):
    monkeypatch.setattr(cr, "resolve_target", AsyncMock(return_value=TARGET))


def _db():
    ref = MagicMock()
    ref.session.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
    ref.session.return_value.__aexit__ = AsyncMock(return_value=False)
    return ref


async def test_self_update_path_passes_the_target_through_every_stage():
    seen: dict = {}
    cs = _fake_cs(slm_fired=True, seen=seen)
    job = SimpleNamespace(status="pending")
    await cr._run_stages(cs, job, _db(), TARGET)
    assert seen["outdated_target"] == seen["slm_target"] == seen["reconcile_target"] == TARGET.commit
    assert seen["slm_target"] != LATEST
    assert cs.stages["code_source_pull"].status == "skipped"
    assert any(TARGET.short in line for line in cs.stages["github_fetch"].log_lines)


async def test_fleet_only_path_passes_the_target_to_the_fleet_stage():
    seen: dict = {}
    cs = _fake_cs(slm_fired=False, seen=seen)
    await cr._run_stages(cs, SimpleNamespace(status="pending"), _db(), TARGET)
    assert seen["fleet_target"] == TARGET.commit
    assert "reconcile_target" not in seen


async def test_orchestrator_scopes_every_playbook_run_to_the_target_and_releases_it(monkeypatch):
    seen: dict = {}
    cs = _fake_cs(slm_fired=False, seen=seen)
    monkeypatch.setitem(sys.modules, "api.code_sync", cs)
    monkeypatch.setattr(api, "code_sync", cs, raising=False)
    monkeypatch.setattr(cr.rollback_audit, "record_rollback", AsyncMock())
    job = SimpleNamespace(status="completed")
    await cr.orchestrator(TARGET, "alice")(job, _db())
    assert seen["github_ref"] == seen["slm_ref"] == seen["fleet_ref"] == TARGET.commit
    assert current_rollback_ref() is None


async def test_a_commit_that_left_the_branch_during_the_fetch_stops_the_run(monkeypatch):
    seen: dict = {}
    cs = _fake_cs(slm_fired=True, seen=seen)
    monkeypatch.setattr(cr, "resolve_target", AsyncMock(side_effect=cr.RollbackRefused("gone")))
    job = SimpleNamespace(status="running")
    await cr._run_stages(cs, job, _db(), TARGET)
    assert job.status == "failed" and "slm_target" not in seen


async def test_the_final_audit_entry_follows_the_job_status(monkeypatch):
    record = AsyncMock()
    monkeypatch.setattr(cr.rollback_audit, "record_rollback", record)
    for status, outcome in (("completed", "success"), ("already_current", "success"), ("failed", "failed")):
        record.reset_mock()
        await cr._record_end("alice", TARGET, SimpleNamespace(status=status))
        assert record.await_args.kwargs["outcome"] == outcome
    record.reset_mock()
    await cr._record_end("alice", TARGET, SimpleNamespace(status="running"))
    record.assert_not_awaited()


def _preflight(deployed, *statuses):
    checks = [
        MigrationCheck(db, s, ["m9"] if s == BLOCKED else [], f"{db} {s}")
        for db, s in zip(("SLM", "backend"), statuses)
    ]
    return cr.Preflight(target=TARGET, deployed=deployed, checks=checks)


def test_a_migration_in_the_way_refuses_and_names_the_database():
    refusal = _preflight("d" * 40, BLOCKED, CLEAR).refusal
    assert refusal == "SLM blocked"


def test_unknown_migration_state_is_a_refusal_not_a_pass():
    assert _preflight("d" * 40, CLEAR, UNKNOWN).refusal == "backend unknown"


def test_a_clear_path_is_allowed():
    assert _preflight("d" * 40, CLEAR, CLEAR).refusal is None


def test_rolling_back_to_what_is_already_deployed_is_refused():
    assert "already runs that commit" in _preflight(TARGET.commit, CLEAR, CLEAR).refusal
