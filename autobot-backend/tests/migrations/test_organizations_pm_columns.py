# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migration 060 adds the missing organizations columns (#10189).

Before this migration, the ``Organization`` ORM model declared
``external_pm_type`` / ``external_pm_config`` / ``kb_inheritance_weight`` but no
migration created them, so an ORM insert against an ``upgrade head`` database
failed with ``UndefinedColumnError``. This test reproduces that insert and
asserts it now succeeds.
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]


async def test_columns_present_and_org_insert_succeeds(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    try:
        # columns exist at head
        async with engine.connect() as conn:
            for col, default in (
                ("external_pm_type", "YES"),
                ("external_pm_config", "YES"),
                ("kb_inheritance_weight", "NO"),
            ):
                nullable = (
                    await conn.execute(
                        text(
                            "SELECT is_nullable FROM information_schema.columns "
                            "WHERE table_name='organizations' AND column_name=:c"
                        ),
                        {"c": col},
                    )
                ).scalar()
                assert nullable == default, f"{col} nullability {nullable} != {default}"

        # the ORM insert that #10189 broke now works (defaults applied: kb_inheritance_weight=0.6)
        from user_management.models.organization import Organization

        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as s:
            org = Organization(id=uuid.uuid4(), name="Acme", slug="acme")
            s.add(org)
            await s.commit()
            assert org.kb_inheritance_weight == 0.6
            assert org.external_pm_type is None
    finally:
        await engine.dispose()
