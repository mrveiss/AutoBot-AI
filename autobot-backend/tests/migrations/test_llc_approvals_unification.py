# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""094 copies every llc_approvals row onto the unified approvals table (#17043).

Acceptance proof for the PR 1 migration: seed llc_approvals with a handful of
rows (one of each field populated, one with decided_by_agent_id still NULL —
a never-decided pending approval), upgrade to 094, and assert the row count
on the migrated side matches and every field round-trips onto the new
columns (id, requested_by_agent_id, payload, decided_by_agent_id -> id,
requested_by_agent, context, decided_by_user).
"""

import importlib.util
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.conftest import BACKEND_ROOT, requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_PRE_094 = "20260916_093"  # 094.down_revision
_REV_094 = "20260918_094"
_MIGRATION_FILE = BACKEND_ROOT / "migrations" / "versions" / "20260918_094_unify_llc_approvals_into_approvals.py"

_ROWS = [
    {
        "id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "type": "hire",
        "status": "approved",
        "requested_by_agent_id": uuid.uuid4(),
        "payload": '{"candidate": "agent-42"}',
        "decided_by_agent_id": uuid.uuid4(),
        "decided_at": datetime(2026, 9, 1, tzinfo=timezone.utc),
    },
    {
        "id": uuid.uuid4(),
        "company_id": uuid.uuid4(),
        "type": "budget_override",
        "status": "pending",
        "requested_by_agent_id": uuid.uuid4(),
        "payload": "{}",
        "decided_by_agent_id": None,
        "decided_at": None,
    },
]


async def _seed_llc_approvals(url: str) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            for row in _ROWS:
                await conn.execute(
                    text(
                        "INSERT INTO llc_approvals "
                        "(id, company_id, type, status, requested_by_agent_id, payload, "
                        "decided_by_agent_id, decided_at) "
                        "VALUES (:id, :company_id, :type, :status, :requested_by_agent_id, "
                        ":payload::jsonb, :decided_by_agent_id, :decided_at)"
                    ),
                    row,
                )
    finally:
        await engine.dispose()


async def _fetch_approval(url: str, approval_id: uuid.UUID) -> dict | None:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT company_id, approval_type, status, requested_by_agent, "
                    "context, decided_by_user, decided_at FROM approvals WHERE id = :id"
                ),
                {"id": approval_id},
            )
            row = result.mappings().first()
            return dict(row) if row else None
    finally:
        await engine.dispose()


async def _count(url: str, table: str) -> int:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            # table is always one of this file's own two hardcoded literals, never external input
            return (await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar()  # nosec B608
    finally:
        await engine.dispose()


def _load_copy_sql() -> str:
    """Load ``_COPY_SQL`` from the migration file by path (its name isn't a valid module path)."""
    spec = importlib.util.spec_from_file_location("_rev_094", _MIGRATION_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._COPY_SQL


async def test_094_copies_every_llc_approval_row_onto_approvals(fresh_db_url):
    assert run_alembic(["upgrade", _PRE_094], fresh_db_url).returncode == 0
    await _seed_llc_approvals(fresh_db_url)
    before_llc = await _count(fresh_db_url, "llc_approvals")
    before_approvals = await _count(fresh_db_url, "approvals")
    assert before_llc == len(_ROWS)

    result = run_alembic(["upgrade", _REV_094], fresh_db_url)
    assert result.returncode == 0, result.stderr

    # llc_approvals itself is untouched -- copy, not move.
    assert await _count(fresh_db_url, "llc_approvals") == before_llc
    assert await _count(fresh_db_url, "approvals") == before_approvals + len(_ROWS)

    for row in _ROWS:
        migrated = await _fetch_approval(fresh_db_url, row["id"])
        assert migrated is not None, f"llc_approvals row {row['id']} did not land on approvals"
        assert migrated["company_id"] == row["company_id"]
        assert migrated["approval_type"] == row["type"]
        assert migrated["status"] == row["status"]
        assert migrated["requested_by_agent"] == str(row["requested_by_agent_id"])
        assert migrated["decided_by_user"] == (str(row["decided_by_agent_id"]) if row["decided_by_agent_id"] else None)
        assert migrated["decided_at"] == row["decided_at"]


async def test_094_is_idempotent_on_rerun(fresh_db_url):
    """A second upgrade attempt (e.g. a retried deploy step) copies nothing twice."""
    assert run_alembic(["upgrade", _PRE_094], fresh_db_url).returncode == 0
    await _seed_llc_approvals(fresh_db_url)

    assert run_alembic(["upgrade", _REV_094], fresh_db_url).returncode == 0
    after_first = await _count(fresh_db_url, "approvals")

    # Re-running 094's data copy directly (ON CONFLICT DO NOTHING) must be a no-op.
    # Loaded by path, not a dotted import: the file's digit-leading name isn't
    # a valid Python module path.
    copy_sql = _load_copy_sql()
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(copy_sql))
    finally:
        await engine.dispose()

    assert await _count(fresh_db_url, "approvals") == after_first
