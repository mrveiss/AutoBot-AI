# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fleet updates skip every node that is not fully enrolled: failed, pending, degraded (#21036).

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
import models.enrollment_skip as _enrollment  # noqa: E402

with real_modules_swapped():
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

FAILED, COMPLETED = "deployment_failed", "deployment_completed"
ENROLL_FAILED = ("Enrollment failed for node x: boom", True)
ENROLL_DONE = ("Enrollment completed for node x", True)
_FAILED = {"n-failed", "n-completed-then-failed"}
#: node_id -> the state named in its skip reason (owner decision 2026-11-09: every node not fully enrolled).
_SKIPPED = {
    **{n: "failed" for n in _FAILED},
    "n-pending": "pending",
    "n-enrolling": "pending",
    "n-degraded": "degraded",
}
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
    "n-pending": [],
    "n-enrolling": [],
    # a failed UPDATE job is not a failed enrollment
    "n-update-failed": [(COMPLETED, ENROLL_DONE), (FAILED, ("Update job j1 failed", False))],
    # a historical FAILED enrollment event written before the marker existed is not evidence
    "n-historical-failed": [(FAILED, ("Enrollment failed for node x: old", False))],
}


@pytest.fixture(autouse=True)
def slm_external_url(monkeypatch):
    """The SLM external URL both code paths read; the unit env's stubbed settings has no real one."""
    for module in (code_sync, _executor):
        monkeypatch.setattr(module.settings, "external_url", "http://slm.example.test:8000", raising=False)


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
            status = {"n-degraded": "degraded", "n-pending": "pending", "n-enrolling": "enrolling"}.get(
                node_id, "online"
            )
            beat = None if node_id == "n-never-heartbeat" else datetime.now(timezone.utc)
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


async def test_split_skips_every_unenrolled_node_naming_its_state_and_targets_the_rest(maker):
    async with maker() as db:
        targets, skipped = await _events.split_enrollment_failed(db, list(_EVENTS))
    assert {s.node_id: s.reason for s in skipped} == {
        n: _enrollment.enrollment_skip_reason(st) for n, st in _SKIPPED.items()
    }
    assert targets == [n for n in _EVENTS if n not in _SKIPPED]
    assert {"n-completed", "n-retried", "n-selfreg", "n-historical-failed", "n-update-failed"} <= set(targets)


@pytest.mark.parametrize("node_id,state", sorted(_SKIPPED.items()))
async def test_each_unenrolled_state_is_skipped_with_its_own_reason(maker, node_id, state):
    async with maker() as db:
        targets, skipped = await _events.split_enrollment_failed(db, [node_id, "n-completed"])
    assert targets == ["n-completed"]
    assert [(s.node_id, s.reason) for s in skipped] == [(node_id, f"skipped: not fully enrolled ({state})")]


async def test_a_fully_enrolled_node_is_targeted_and_skips_nothing(maker):
    async with maker() as db:
        targets, skipped = await _events.split_enrollment_failed(db, ["n-completed"])
    assert (targets, skipped) == (["n-completed"], [])


async def test_empty_target_list_runs_no_query():
    assert await _events.get_enrollment_failed_node_ids(None, []) == set()


async def test_collect_outdated_drops_unenrolled_nodes_and_counts_them(maker, monkeypatch):
    class _Svc:
        def session(self):
            return maker()

    async def _no_deps(_component):
        return False

    monkeypatch.setattr(code_sync.settings, "external_url", "http://slm.example.test:8000", raising=False)
    monkeypatch.setattr(code_sync, "select", select)
    monkeypatch.setattr(code_sync, "Node", _db.Node)
    monkeypatch.setattr(code_sync, "split_enrollment_failed", _events.split_enrollment_failed)
    monkeypatch.setattr(code_sync, "get_slm_self_node", _events.get_slm_self_node)
    monkeypatch.setattr(code_sync, "_compute_deps_changed", _no_deps)
    job = code_sync.UpdateAllJob(
        job_id="j-21036",
        stages=[
            code_sync.UpdateAllStage(name=n)
            for n in ("github_fetch", "code_source_pull", "slm_self_update", "fleet_nodes")
        ],
    )

    ids = await code_sync._collect_outdated_node_ids(job, "a" * 40, _Svc())

    assert set(_SKIPPED).isdisjoint(ids)
    assert {s.node_id: s.reason for s in job.enrollment_skipped_nodes} == {
        n: _enrollment.enrollment_skip_reason(st) for n, st in _SKIPPED.items()
    }
    assert set(ids) == set(_EVENTS) - set(_SKIPPED)


async def test_an_unmarked_historical_failed_event_does_not_skip(maker):
    async with maker() as db:
        failed = await _events.get_enrollment_failed_node_ids(db, ["n-historical-failed", "n-update-failed"])
    assert failed == set()


async def test_scheduled_selection_applies_the_same_filter(maker):
    schedule = types.SimpleNamespace(target_type="all", target_nodes=None)
    async with maker() as db:
        picked = {n.node_id for n in await _executor.get_schedule_target_nodes(db, schedule)}
    assert picked == set(_EVENTS) - set(_SKIPPED)


async def test_scheduled_specific_selection_also_skips_unenrolled_nodes(maker):
    schedule = types.SimpleNamespace(
        target_type="specific", target_nodes=["n-failed", "n-completed", "n-degraded", "n-pending"]
    )
    async with maker() as db:
        picked = {n.node_id for n in await _executor.get_schedule_target_nodes(db, schedule)}
    assert picked == {"n-completed"}


async def test_a_never_heartbeated_online_node_is_not_skipped(maker):
    async with maker() as db:
        targets, skipped = await _events.split_enrollment_failed(db, ["n-never-heartbeat"])
    assert (targets, skipped) == (["n-never-heartbeat"], [])


async def test_collect_outdated_never_drops_the_slm_self_node(maker, monkeypatch):
    class _Svc:
        def session(self):
            return maker()

    async def _no_deps(_component):
        return False

    async with maker() as db:
        db.add(
            _db.Node(
                node_id="n-slm-self",
                hostname="n-slm-self",
                ip_address="slm.example.test",
                status="pending",
                last_heartbeat=datetime.now(timezone.utc),
                code_status="outdated",
            )
        )
        await db.commit()
    monkeypatch.setattr(code_sync.settings, "external_url", "http://slm.example.test:8000", raising=False)
    monkeypatch.setattr(code_sync, "select", select)
    monkeypatch.setattr(code_sync, "Node", _db.Node)
    monkeypatch.setattr(code_sync, "split_enrollment_failed", _events.split_enrollment_failed)
    monkeypatch.setattr(code_sync, "get_slm_self_node", _events.get_slm_self_node)
    monkeypatch.setattr(code_sync, "_compute_deps_changed", _no_deps)
    job = code_sync.UpdateAllJob(
        job_id="j-21036-self",
        stages=[
            code_sync.UpdateAllStage(name=n)
            for n in ("github_fetch", "code_source_pull", "slm_self_update", "fleet_nodes")
        ],
    )

    ids = await code_sync._collect_outdated_node_ids(job, "a" * 40, _Svc())

    assert "n-slm-self" in ids
    assert "n-slm-self" not in {s.node_id for s in job.enrollment_skipped_nodes}


async def test_scheduled_run_never_drops_the_slm_self_node(maker, monkeypatch):
    async with maker() as db:
        db.add(
            _db.Node(
                node_id="n-slm-self",
                hostname="n-slm-self",
                ip_address="slm.example.test",
                status="pending",
                code_status="outdated",
            )
        )
        await db.commit()
    monkeypatch.setattr(_executor.settings, "external_url", "http://slm.example.test:8000", raising=False)
    monkeypatch.setattr(_executor, "select", select)
    monkeypatch.setattr(_executor, "Node", _db.Node)
    schedule = types.SimpleNamespace(target_type="all", target_nodes=[])

    async with maker() as db:
        nodes = await _executor.get_schedule_target_nodes(db, schedule)

    ids = {n.node_id for n in nodes}
    assert "n-slm-self" in ids
    assert "n-pending" not in ids


@pytest.mark.parametrize(
    "external_url", ["", "no-host-here", "http://absent.example.test:8000"], ids=["empty", "hostless", "unmatched"]
)
async def test_slm_self_node_id_is_none_without_a_usable_or_matching_host(maker, external_url):
    """Breaks if the helper raises (or returns a row) for an empty, hostless or unmatched URL."""
    async with maker() as db:
        assert await _events.get_slm_self_node_id(db, external_url) is None


async def test_scheduled_run_with_no_identifiable_self_node_still_filters_unenrolled(maker, monkeypatch):
    """Breaks if the scheduled path raises, or exempts every node, when the self-node lookup returns None."""
    monkeypatch.setattr(_executor.settings, "external_url", "http://absent.example.test:8000", raising=False)
    monkeypatch.setattr(_executor, "select", select)
    monkeypatch.setattr(_executor, "Node", _db.Node)
    schedule = types.SimpleNamespace(target_type="all", target_nodes=None)

    async with maker() as db:
        picked = {n.node_id for n in await _executor.get_schedule_target_nodes(db, schedule)}

    assert picked == set(_EVENTS) - set(_SKIPPED)


async def _add_nodes_sharing_an_address(maker, rows):
    """Add (node_id, roles) rows that share one address, in order, so ``id`` follows the list."""
    async with maker() as db:
        for node_id, roles in rows:
            db.add(
                _db.Node(
                    node_id=node_id,
                    hostname=node_id,
                    ip_address="shared.example.test",
                    roles=roles,
                    status="pending",
                    last_heartbeat=datetime.now(timezone.utc),
                    code_status="outdated",
                )
            )
        await db.commit()


@pytest.mark.parametrize(
    "rows,expected",
    [
        ([("n-dup-first", []), ("n-dup-manager", ["slm-backend"])], "n-dup-manager"),
        ([("n-dup-first", ["slm-frontend"]), ("n-dup-second", [])], "n-dup-first"),
    ],
    ids=["manager-role-wins", "lowest-id-fallback"],
)
async def test_slm_self_node_is_deterministic_when_rows_share_the_address(maker, rows, expected):
    """Breaks if the lookup raises on duplicates (single-row assertion) or picks by anything but role then id."""
    await _add_nodes_sharing_an_address(maker, rows)
    async with maker() as db:
        node = await _events.get_slm_self_node(db, "http://shared.example.test:8000")
        assert node.node_id == expected
        assert await _events.get_slm_self_node_id(db, "http://shared.example.test:8000") == expected


async def test_scheduled_path_does_not_raise_when_rows_share_the_slm_address(maker, monkeypatch):
    """Breaks if the scheduled path raises on duplicate-address rows or stops exempting the chosen self node."""
    await _add_nodes_sharing_an_address(maker, [("n-dup-first", []), ("n-dup-manager", ["slm-backend"])])
    monkeypatch.setattr(_executor.settings, "external_url", "http://shared.example.test:8000", raising=False)
    monkeypatch.setattr(_executor, "select", select)
    monkeypatch.setattr(_executor, "Node", _db.Node)
    schedule = types.SimpleNamespace(target_type="all", target_nodes=None)

    async with maker() as db:
        picked = {n.node_id for n in await _executor.get_schedule_target_nodes(db, schedule)}

    assert "n-dup-manager" in picked
    assert "n-dup-first" not in picked


async def test_update_all_path_keeps_the_chosen_self_node_when_rows_share_the_slm_address(maker, monkeypatch):
    """Breaks if update-all drops the chosen self node (a raise there reads as nothing to update, #21334)."""
    await _add_nodes_sharing_an_address(maker, [("n-dup-first", []), ("n-dup-manager", ["slm-backend"])])

    class _Svc:
        def session(self):
            return maker()

    async def _no_deps(_component):
        return False

    monkeypatch.setattr(code_sync.settings, "external_url", "http://shared.example.test:8000", raising=False)
    monkeypatch.setattr(code_sync, "select", select)
    monkeypatch.setattr(code_sync, "Node", _db.Node)
    monkeypatch.setattr(code_sync, "split_enrollment_failed", _events.split_enrollment_failed)
    monkeypatch.setattr(code_sync, "get_slm_self_node", _events.get_slm_self_node)
    monkeypatch.setattr(code_sync, "_compute_deps_changed", _no_deps)
    stages = [code_sync.UpdateAllStage(name=n) for n in ("github_fetch", "code_source_pull", "slm_self_update")]
    job = code_sync.UpdateAllJob(job_id="j-21036-dup", stages=[*stages, code_sync.UpdateAllStage(name="fleet_nodes")])

    ids = await code_sync._collect_outdated_node_ids(job, "a" * 40, _Svc())

    assert "n-dup-manager" in ids
    assert "n-dup-first" not in ids
