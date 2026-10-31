# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A cost event for a work item that no longer exists breaks the real foreign key, and only that is a 404 (#20168).

SQLite does not enforce the key, so this runs on the disposable Postgres the migration gate provides.
"""

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]


def _event(*, work_item_id, tokens_in=1):
    import llc.models  # noqa: F401 - registers the models the mapper configuration resolves
    from llc.models.company_os_cost import CompanyOsCostEvent

    return CompanyOsCostEvent(
        company_id=uuid.uuid4(),
        agent_id="a",
        work_item_id=work_item_id,
        model="m",
        tokens_in=tokens_in,
        tokens_out=1,
        cost=Decimal("0.01"),
    )


async def test_a_missing_work_item_is_not_found_and_the_transaction_stays_usable(fresh_db_url):
    from llc.exceptions import WorkItemNotInCompany
    from llc.services.budget import _add_event

    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    try:
        async with AsyncSession(engine) as session:
            gone = uuid.uuid4()
            event = _event(work_item_id=gone)
            with pytest.raises(WorkItemNotInCompany):
                await _add_event(session, event, str(gone))
            assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    finally:
        await engine.dispose()


async def test_another_integrity_error_is_not_reported_as_a_missing_work_item(fresh_db_url):
    from llc.services.budget import _add_event

    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    try:
        async with AsyncSession(engine) as session:
            event = _event(work_item_id=None, tokens_in=None)
            with pytest.raises(IntegrityError, match="null value"):
                await _add_event(session, event, "none")
    finally:
        await engine.dispose()
