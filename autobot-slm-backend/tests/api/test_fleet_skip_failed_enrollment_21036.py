# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fleet updates skip a node only on positive evidence its enrollment failed (#21036).

Real sqlite, real ORM. Node ids are fixed so a failure names the node.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402
from _real_orm_import import REAL_MODULES, SLM_ROOT, import_modules_with_real_orm, real_modules_swapped  # noqa: E402

import_code_sync()

import api.code_sync as code_sync  # noqa: E402

_fake_db = types.ModuleType("services.database")
_fake_db.db_service = None
with patch.dict(sys.modules, {"services.database": _fake_db}):
    _events, _executor = import_modules_with_real_orm(
        (),
        path_loaded={
            "services.node_events": SLM_ROOT / "services" / "node_events.py",
            "services.schedule_executor": SLM_ROOT / "services" / "schedule_executor.py",
        },
    )

_db = REAL_MODULES["models.database"]
with real_modules_swapped():
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

FAILED, COMPLETED = "deployment_failed", "deployment_completed"
ENROLL_FAILED = ("Enrollment failed for node x: boom", True)
ENROLL_DONE = ("Enrollment completed for node x", True)
_FAILED = {"n-failed", "n-completed-then-failed"}
#: node_id -> its events in order as (event_type, message).
_EVENTS = {
    "n-completed": [(COMPLETED, ENROLL_DONE)],
    "n-failed": [(FAILED, ENROLL_FAILED)],
    # enrolled once, then a later enrollment failed: the LATEST marked event is FAILED
    "n-completed-then-failed": [(COMPLETED, ENROLL_DONE), (FAILED, ENROLL_FAILED)],
    "n-retried": [(FAILED, ENROLL_FAILED), (COMPLETED, ENROLL_DONE)],
    "n-selfreg": [],
    "n-degraded": [],
    "n-never-heartbeat": [],
    # a failed UPDATE job is not a failed enrollment
    "n-update-failed": [(COMPLETED, ENROLL_DONE), (FAILED, ("Update job j1 failed", False))],
    # a historical FAILED enrollment event written before the marker existed is not evidence
    "n-historical-failed": [(FAILED, ("Enrollment failed for node x: old", False))],
}


@pytest.fixture
async def maker():
    with real_modules_swapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine
        async with engine.begin() as conn:
            await conn.run_sync(_db.Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
    async with factory() as db:
        n = 0
        for node_id, events in _EVENTS.items():
            status = "degraded" if node_id == "n-degraded" else "online"
            beat = None if node_id in ("n-degraded", "n-never-heartbeat") else datetime.now(timezone.utc)
            db.add(
                _db.Node(
                    node_id=node_id,
                    hostname=node_id,
                    ip_address="node.example.test",
                    status=status,
                    last_heartbeat=beat,
                    code_status="outdated",
                )
            )
            for event_type, (message, marked) in events:
                n += 1
                db.add(
                    _db.NodeEvent(
                        event_id=f"e{n:03d}",
                        node_id=node_id,
                        event_type=event_type,
                        message=message,
                        details=_events.enrollment_details() if marked else {},
                    )
                )
                await db.flush()
        await db.commit()
    yield factory
    await engine.dispose()


async def test_only_a_latest_failed_enrollment_is_returned(maker):
    async with maker() as db:
        failed = await _events.get_enrollment_failed_node_ids(db, list(_EVENTS))
    assert failed == _FAILED


async def test_split_targets_everyone_else_and_reports_the_skip(maker):
    async with maker() as db:
        targets, skipped = await _events.split_enrollment_failed(db, list(_EVENTS))
    assert [(s.node_id, s.reason) for s in skipped] == [(n, _events.ENROLLMENT_SKIP_REASON) for n in sorted(_FAILED)]
    assert targets == [n for n in _EVENTS if n not in _FAILED]
    assert {"n-completed", "n-retried", "n-selfreg", "n-degraded", "n-never-heartbeat", "n-historical-failed"} <= set(
        targets
    )


async def test_empty_target_list_runs_no_query():
    assert await _events.get_enrollment_failed_node_ids(None, []) == set()


async def test_collect_outdated_drops_failed_enrollment_and_counts_it(maker, monkeypatch):
    class _Svc:
        def session(self):
            return maker()

    async def _no_deps(_component):
        return False

    monkeypatch.setattr(code_sync.settings, "external_url", "http://slm.example.test:8000", raising=False)
    monkeypatch.setattr(code_sync, "select", select)
    monkeypatch.setattr(code_sync, "Node", _db.Node)
    monkeypatch.setattr(code_sync, "split_enrollment_failed", _events.split_enrollment_failed)
    monkeypatch.setattr(code_sync, "_compute_deps_changed", _no_deps)
    job = code_sync.UpdateAllJob(
        job_id="j-21036",
        stages=[
            code_sync.UpdateAllStage(name=n)
            for n in ("github_fetch", "code_source_pull", "slm_self_update", "fleet_nodes")
        ],
    )

    ids = await code_sync._collect_outdated_node_ids(job, "a" * 40, _Svc())

    assert _FAILED.isdisjoint(ids)
    assert {s.node_id for s in job.enrollment_skipped_nodes} == _FAILED
    assert all(s.reason == _events.ENROLLMENT_SKIP_REASON for s in job.enrollment_skipped_nodes)
    assert set(ids) == set(_EVENTS) - _FAILED


async def test_an_unmarked_historical_failed_event_does_not_skip(maker):
    async with maker() as db:
        failed = await _events.get_enrollment_failed_node_ids(db, ["n-historical-failed", "n-update-failed"])
    assert failed == set()


async def test_degraded_and_never_heartbeated_nodes_stay_targeted_for_the_14297_handling(maker):
    """The enrollment filter leaves the #11511/#14297 non-operational handling to the deploy loop."""
    async with maker() as db:
        targets, _ = await _events.split_enrollment_failed(db, ["n-degraded", "n-never-heartbeat", "n-completed"])
        nodes = {
            n.node_id: n for n in (await db.execute(select(_db.Node).where(_db.Node.node_id.in_(targets)))).scalars()
        }
    assert targets == ["n-degraded", "n-never-heartbeat", "n-completed"]
    assert not code_sync._is_node_operational(nodes["n-degraded"])
    assert not code_sync._is_node_operational(nodes["n-never-heartbeat"])
    assert code_sync._is_node_operational(nodes["n-completed"])


async def test_scheduled_selection_applies_the_same_filter(maker):
    schedule = types.SimpleNamespace(target_type="all", target_nodes=None)
    async with maker() as db:
        picked = {n.node_id for n in await _executor.get_schedule_target_nodes(db, schedule)}
    assert picked == set(_EVENTS) - _FAILED


async def test_scheduled_specific_selection_also_skips_failed_enrollment(maker):
    schedule = types.SimpleNamespace(target_type="specific", target_nodes=["n-failed", "n-completed", "n-degraded"])
    async with maker() as db:
        picked = {n.node_id for n in await _executor.get_schedule_target_nodes(db, schedule)}
    assert picked == {"n-completed", "n-degraded"}
