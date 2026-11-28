# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``LLCActivityLog`` flushed through the real ORM on a migrated schema (#20150).

The model sits on ``LLCBase`` and its ``company_id`` foreign key named ``organizations.id``, a table
of the other metadata. Declaring it was harmless; flushing a row raised ``NoReferencedTableError``,
so every activity write failed (pause, resume and every other service that records one).

Needs the disposable Postgres the migration gate provides (skipped without it).
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_INSERT_ORG = (
    "INSERT INTO organizations (id, name, slug, max_users, is_active, kb_inheritance_weight) "
    "VALUES (:id, 'company-20150', 'company-20150', -1, true, 0.6)"
)


def _entry(company_id: uuid.UUID):
    import llc.models  # noqa: F401 - registers the models the mapper configuration resolves
    import user_management.models  # noqa: F401
    from llc.models.activity import LLCActivityLog

    return LLCActivityLog(
        company_id=company_id,
        actor_type="system",
        entity_type="agent",
        entity_id=uuid.uuid4(),
        action="control.agent.paused",
        after_state={"status": "paused"},
    )


async def test_flush_writes_the_row_and_the_database_still_enforces_the_company(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    company = uuid.uuid4()
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(_INSERT_ORG), {"id": company})
        async with AsyncSession(engine) as session:
            entry = _entry(company)
            session.add(entry)
            await session.commit()
            stored = (await session.execute(text("SELECT count(*) FROM llc_activity_log"))).scalar_one()
        assert stored == 1
        async with AsyncSession(engine) as session:
            session.add(_entry(uuid.uuid4()))
            with pytest.raises(Exception, match="foreign key"):
                await session.commit()
    finally:
        await engine.dispose()


def _foreign_key_diffs(sync_conn) -> list:
    """The add/remove foreign-key operations autogenerate finds on ``llc_activity_log``."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from sqlalchemy import MetaData

    import models.workflow  # noqa: F401 - the Company OS tables name its composite key
    from llc.models.activity import LLCBase
    from user_management.models.base import Base

    combined = MetaData()
    for metadata in (Base.metadata, LLCBase.metadata):
        for table in metadata.tables.values():
            table.to_metadata(combined)
    diffs = compare_metadata(MigrationContext.configure(sync_conn), combined)
    return [d for d in diffs if d[0] in ("add_fk", "remove_fk") and d[1].parent.name == "llc_activity_log"]


async def test_the_model_declares_the_foreign_key_the_migration_creates(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    _entry(uuid.uuid4())  # imports every model into the metadata
    engine = create_async_engine(fresh_db_url)
    try:
        async with engine.connect() as conn:
            assert await conn.run_sync(_foreign_key_diffs) == []
    finally:
        await engine.dispose()
