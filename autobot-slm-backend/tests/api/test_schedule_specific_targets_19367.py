# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A schedule updates only outdated nodes -- for ``specific``, only its selected ones -- on both paths (#19367).

Owner decision on #19367: "Run now" and the timed run select the same nodes, through the one
``get_schedule_target_nodes``. The nodes live in a real in-memory database, so "only the outdated
ones" is read from rows the query filtered, not from a mock that returns whatever it is given.
"""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path
from types import SimpleNamespace
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
    (_executor,) = import_modules_with_real_orm(
        (), path_loaded={"services.schedule_executor": SLM_ROOT / "services" / "schedule_executor.py"}
    )

_db = REAL_MODULES["models.database"]
with real_modules_swapped():
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

#: node_id -> code_status. The specific schedule selects n-old, n-new and n-old2; n-other is outdated but unselected.
_NODES = {"n-old": "outdated", "n-new": "up_to_date", "n-old2": "outdated", "n-other": "outdated"}
_SELECTED = ["n-old", "n-new", "n-old2"]
_ALL_OUTDATED = ["n-old", "n-old2", "n-other"]

#: schedule id -> (target_type, target_nodes, the nodes it must target). AC of #19367: all, specific, fallback.
_CASES = {
    1: ("specific", _SELECTED, ["n-old", "n-old2"]),
    2: ("all", None, _ALL_OUTDATED),
    3: ("specific", [], []),  # nothing selected touches nothing, never the whole fleet
    4: ("specific", None, []),
    5: ("tag", ["any-tag"], _ALL_OUTDATED),  # the fallback: no tag filter exists, so every outdated node
}
_IDS = [f"{t}-{n!r}" for t, n, _ in _CASES.values()]


@pytest.fixture
async def maker():
    with real_modules_swapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine
        async with engine.begin() as conn:
            await conn.run_sync(_db.Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
    async with factory() as db:
        for node_id, code_status in _NODES.items():
            db.add(_db.Node(node_id=node_id, hostname=node_id, ip_address="node.example.test", code_status=code_status))
        for sid, (target_type, target_nodes, _) in _CASES.items():
            row = {"id": sid, "name": f"s{sid}", "target_type": target_type, "target_nodes": target_nodes}
            db.add(_db.UpdateSchedule(cron_expression="0 2 * * *", **row))
        await db.commit()
    yield factory
    await engine.dispose()


def _queue_spy(seen: list):
    async def queue_schedule_job(db, schedule, nodes):
        seen.extend(sorted(n.node_id for n in nodes))
        return SimpleNamespace(job_id="j1", nodes={})

    return queue_schedule_job


async def test_outdated_values_match_the_enum():
    assert {_db.CodeStatus.OUTDATED.value, _db.CodeStatus.UP_TO_DATE.value} == set(_NODES.values())


@pytest.mark.parametrize("sid", list(_CASES), ids=_IDS)
async def test_run_now_targets_only_outdated_nodes(maker, monkeypatch, sid):
    seen: list = []

    async def _no_run(job):
        return None

    monkeypatch.setattr(code_sync, "select", select)
    monkeypatch.setattr(code_sync, "UpdateSchedule", _db.UpdateSchedule)
    monkeypatch.setattr(code_sync, "get_schedule_target_nodes", _executor.get_schedule_target_nodes)
    monkeypatch.setattr(code_sync, "queue_schedule_job", _queue_spy(seen))
    monkeypatch.setattr(code_sync, "_run_fleet_sync_job", _no_run)
    async with maker() as db:
        await code_sync.run_schedule(sid, db, {})
    assert seen == _CASES[sid][2]


@pytest.mark.parametrize("sid", list(_CASES), ids=_IDS)
async def test_timed_run_targets_only_outdated_nodes(maker, monkeypatch, sid):
    seen: list = []

    async def _run_fleet_sync_job(job):
        return None

    fake = types.ModuleType("api.code_sync")
    fake.queue_schedule_job, fake._run_fleet_sync_job = _queue_spy(seen), _run_fleet_sync_job
    monkeypatch.setitem(sys.modules, "api.code_sync", fake)
    monkeypatch.setattr(_executor, "db_service", SimpleNamespace(session=maker))
    target_type, target_nodes, expected = _CASES[sid]
    schedule = SimpleNamespace(id=sid, name=f"s{sid}", target_type=target_type, target_nodes=target_nodes)
    assert (await _executor.execute_schedule(schedule))[0] is True
    assert seen == expected


def _picks(name: str) -> bool:
    return "target_nodes" in name


def test_one_selection_function_and_both_paths_call_it():
    rels = ("api/code_sync.py", "services/schedule_executor.py")
    sources = {rel: (SLM_ROOT / rel).read_text(encoding="utf-8") for rel in rels}
    defs = {
        rel: [n.name for n in ast.walk(ast.parse(text)) if isinstance(n, ast.AsyncFunctionDef) and _picks(n.name)]
        for rel, text in sources.items()
    }
    assert defs == {"api/code_sync.py": [], "services/schedule_executor.py": ["get_schedule_target_nodes"]}
    assert "from services.schedule_executor import get_schedule_target_nodes" in sources["api/code_sync.py"]
    assert all("await get_schedule_target_nodes(db, schedule)" in text for text in sources.values())
