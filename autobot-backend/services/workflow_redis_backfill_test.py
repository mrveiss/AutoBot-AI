# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for services/workflow_redis_backfill.py (#14210).

Uses fakeredis (real Redis command semantics, not a MagicMock — see
llm_shared/tests/test_provider_degradation.py for the established pattern in
this repo) so ``scan_iter``/``get`` behave like production Redis rather than
a hand-picked stub that could silently diverge (the MagicMock-store gotcha:
"present" and "never written" must look different).

A self-contained SQLite engine backs the ``workflows`` table — the same
harness ``llc/tests/test_workflows_scoping.py`` uses.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

try:
    import fakeredis.aioredis as fakeredis_async

    _FAKEREDIS_AVAILABLE = True
except ImportError:
    _FAKEREDIS_AVAILABLE = False

from llc.tests import _e2e_harness as harness  # noqa: E402 — registers SQLite compile shims
from models.workflow import SOURCE_LEGACY_REDIS, Workflow  # noqa: E402
from user_management.models.base import Base  # noqa: E402

# canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_SQLITE_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


def _require_fakeredis():
    if not _FAKEREDIS_AVAILABLE:
        pytest.skip("fakeredis not installed — skipping Redis-backed tests")


@contextmanager
def _inject_globals(func, **replacements):
    """Swap names in *func*'s own module globals for the duration of the block.

    Mirrors ``llm_shared/tests/test_provider_degradation.py``'s helper of the
    same name — ``unittest.mock.patch`` resolves through ``sys.modules``,
    which can diverge from the module object the running code actually reads.
    """
    g = func.__globals__
    saved = {k: g[k] for k in replacements}
    g.update(replacements)
    try:
        yield
    finally:
        g.update(saved)


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    eng = create_async_engine(_SQLITE_MEMORY_URL)
    tables = [Workflow.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    # canonical: ignore py-adhoc-db-engine (test-local session factory)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def _seed_redis_workflow(server, workflow_id: str, *, goal: str, done: bool = False, errors=None) -> None:
    redis = fakeredis_async.FakeRedis(server=server, decode_responses=True)
    blob = {
        "workflow_id": workflow_id,
        "goal": goal,
        "current_step": "complete" if done else "executing",
        "done": done,
        "errors": errors or [],
    }
    await redis.set(f"autobot:workflow:{workflow_id}", json.dumps(blob))
    if not done:
        await redis.sadd("autobot:workflow:active", workflow_id)
    await redis.aclose()


@pytest.mark.asyncio
async def test_backfill_copies_redis_workflow_with_null_company(session_factory):  # noqa: ANN001
    """A Redis-persisted workflow lands in the table, unattributed, not discarded."""
    _require_fakeredis()
    import services.workflow_redis_backfill as mod

    server = fakeredis_async.FakeServer()
    await _seed_redis_workflow(server, "wf-1", goal="deploy the app")

    async def _fake_client(*_args, **_kwargs):
        return fakeredis_async.FakeRedis(server=server, decode_responses=True)

    async with session_factory() as session:
        with _inject_globals(mod.backfill, get_async_redis_client=_fake_client):
            report = await mod.backfill(session=session)

    assert report.scanned == 1
    assert report.migrated == ["wf-1"]

    async with session_factory() as session:
        result = await session.execute(select(Workflow).where(Workflow.workflow_id == "wf-1"))
        row = result.scalar_one()

    assert row.company_id is None
    assert row.source == SOURCE_LEGACY_REDIS
    assert row.name == "deploy the app"
    assert row.definition["goal"] == "deploy the app"


@pytest.mark.asyncio
async def test_backfill_is_idempotent(session_factory):  # noqa: ANN001
    """Re-running the backfill never duplicates or overwrites an already-migrated row."""
    _require_fakeredis()
    import services.workflow_redis_backfill as mod

    server = fakeredis_async.FakeServer()
    await _seed_redis_workflow(server, "wf-1", goal="deploy the app")

    async def _fake_client(*_args, **_kwargs):
        return fakeredis_async.FakeRedis(server=server, decode_responses=True)

    async with session_factory() as session:
        with _inject_globals(mod.backfill, get_async_redis_client=_fake_client):
            await mod.backfill(session=session)

    async with session_factory() as session:
        with _inject_globals(mod.backfill, get_async_redis_client=_fake_client):
            second = await mod.backfill(session=session)

    assert second.migrated == []
    assert second.already_present == ["wf-1"]

    async with session_factory() as session:
        result = await session.execute(select(Workflow).where(Workflow.workflow_id == "wf-1"))
        rows = result.scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(session_factory):  # noqa: ANN001
    """--dry-run reports what WOULD migrate but leaves the table empty."""
    _require_fakeredis()
    import services.workflow_redis_backfill as mod

    server = fakeredis_async.FakeServer()
    await _seed_redis_workflow(server, "wf-1", goal="deploy the app")

    async def _fake_client(*_args, **_kwargs):
        return fakeredis_async.FakeRedis(server=server, decode_responses=True)

    async with session_factory() as session:
        with _inject_globals(mod.backfill, get_async_redis_client=_fake_client):
            report = await mod.backfill(dry_run=True, session=session)

    assert report.migrated == ["wf-1"]

    async with session_factory() as session:
        result = await session.execute(select(Workflow))
        rows = result.scalars().all()
    assert rows == []
