# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""099 adds the six one-approval-record columns without touching a row (#13421 S1)."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_PRE = "20261011_098"
_REV = "20261012_099"
_NEW = {"source", "risk_tier", "expires_at", "payload_hash", "resume_ref", "owner_user"}
_ROWS = [
    {"id": uuid.uuid4(), "title": "platform", "type": "workflow_gate", "status": "pending", "company": None},
    {"id": uuid.uuid4(), "title": "company", "type": "hire", "status": "approved", "company": uuid.uuid4()},
]


async def _run(url: str, sql: str, params: dict | None = None):
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text(sql), params or {})
            return [dict(r) for r in result.mappings().all()] if result.returns_rows else None
    finally:
        await engine.dispose()


async def _seed(url: str) -> None:
    for row in _ROWS:
        await _run(
            url,
            "INSERT INTO approvals (id, title, approval_type, status, company_id) "
            "VALUES (:id, :title, :type, :status, :company)",
            row,
        )


async def _columns(url: str) -> dict[str, str]:
    rows = await _run(
        url,
        "SELECT column_name, is_nullable FROM information_schema.columns WHERE table_name = 'approvals'",
    )
    return {r["column_name"]: r["is_nullable"] for r in rows}


async def test_upgrade_adds_five_nullable_columns_and_leaves_every_row_untouched(fresh_db_url):
    assert run_alembic(["upgrade", _PRE], fresh_db_url).returncode == 0
    assert not _NEW & set(await _columns(fresh_db_url)), "the columns must not exist before 098"
    await _seed(fresh_db_url)
    before = await _run(fresh_db_url, "SELECT id, title, approval_type, status, company_id, updated_at FROM approvals")

    result = run_alembic(["upgrade", _REV], fresh_db_url)
    assert result.returncode == 0, result.stderr

    cols = await _columns(fresh_db_url)
    assert _NEW <= set(cols) and all(cols[c] == "YES" for c in _NEW)
    after = await _run(
        fresh_db_url,
        "SELECT id, title, approval_type, status, company_id, updated_at, source, risk_tier, expires_at, "
        "payload_hash, resume_ref, owner_user FROM approvals",
    )
    assert len(after) == len(before) == len(_ROWS)
    assert all(r[c] is None for r in after for c in _NEW)
    key = lambda r: str(r["id"])  # noqa: E731
    for old, new in zip(sorted(before, key=key), sorted(after, key=key)):
        assert {k: new[k] for k in old} == old, "an existing row's columns must be unchanged"


async def test_downgrade_round_trips_an_untouched_table(fresh_db_url):
    assert run_alembic(["upgrade", _PRE], fresh_db_url).returncode == 0
    await _seed(fresh_db_url)
    assert run_alembic(["upgrade", _REV], fresh_db_url).returncode == 0

    down = run_alembic(["downgrade", _PRE], fresh_db_url)
    assert down.returncode == 0, down.stderr
    assert not _NEW & set(await _columns(fresh_db_url))
    assert len(await _run(fresh_db_url, "SELECT id FROM approvals")) == len(_ROWS)
    assert run_alembic(["upgrade", _REV], fresh_db_url).returncode == 0, "upgrade after downgrade must work"


@pytest.mark.parametrize(
    "column,value",
    [("source", "'agent_tool'"), ("risk_tier", "'high'"), ("resume_ref", "'x'"), ("owner_user", "'bob'")],
)
async def test_downgrade_refuses_once_a_new_column_holds_a_value(fresh_db_url, column, value):
    assert run_alembic(["upgrade", _REV], fresh_db_url).returncode == 0
    await _seed(fresh_db_url)
    await _run(
        fresh_db_url,
        f"UPDATE approvals SET {column} = {value} WHERE id = :id",  # nosec B608
        {"id": _ROWS[0]["id"]},
    )

    down = run_alembic(["downgrade", _PRE], fresh_db_url)
    assert down.returncode != 0
    assert "20261012_099 downgrade is refused" in (down.stdout + down.stderr)
    assert _NEW <= set(await _columns(fresh_db_url)), "refused means nothing moved"
