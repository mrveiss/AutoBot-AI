# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``LLCApiKey`` against the schema ``alembic upgrade head`` builds (#20149).

The migrations create the key timestamps as ``timestamptz``; the ORM declared them without
``timezone=True``, so asyncpg refused the aware datetimes ``ApiKeyService.issue_key`` passes
("can't subtract offset-naive and offset-aware datetimes") and a dispatched heartbeat run never
got its key. SQLite accepts either, so only a migrated Postgres can see it.

Needs the disposable Postgres the migration gate provides (skipped without it).
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_TIMESTAMPS = ("last_used_at", "revoked_at", "expires_at", "created_at")


def _key(**stamps):
    from llc.models.api_key import LLCApiKey

    return LLCApiKey(
        id=uuid.uuid4(),
        agent_id="agent-1",
        company_id=str(uuid.uuid4()),
        name="run-key",
        key_hash=uuid.uuid4().hex,
        **stamps,
    )


async def test_aware_datetimes_round_trip_through_the_migrated_table(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    now = datetime.now(timezone.utc)
    stamps = {column: now + timedelta(minutes=i) for i, column in enumerate(_TIMESTAMPS)}
    record = _key(**stamps)
    engine = create_async_engine(fresh_db_url)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            session.add(record)
            await session.commit()
        async with AsyncSession(engine) as session:
            stored = (await session.execute(select(type(record)).where(type(record).id == record.id))).scalar_one()
        assert {column: getattr(stored, column) for column in _TIMESTAMPS} == stamps
    finally:
        await engine.dispose()


def test_every_key_timestamp_is_declared_timezone_aware():
    from llc.models.api_key import LLCApiKey

    naive = [c for c in _TIMESTAMPS if not LLCApiKey.__table__.c[c].type.timezone]
    assert naive == []
