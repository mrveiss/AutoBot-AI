# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The role hourly rate, and who may change it (GH#14607).

The rate moves every cost figure derived from it, so it carries the same
company-admin gate as the other role attachments (#14221). These cover the
gate and the validation; the arithmetic it feeds is tested in
``test_step_cost.py`` against the pure function.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.role_rate import LLCRoleRate
from llc.services.authz import NotAuthorisedError
from llc.services.role_rate import RoleRateService
from llc.tests import _e2e_harness as harness


@pytest_asyncio.fixture
async def engine():  # noqa: ANN201
    eng = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    await harness.create_loop_schema(eng)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:  # noqa: ANN001
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with factory() as s:
        yield s


@pytest.fixture
def service() -> RoleRateService:
    return RoleRateService()


def test_the_model_is_registered_in_metadata() -> None:
    """An unregistered model is absent from ``Base.metadata``.

    That has already caused a real defect in this area: a table that autogenerate
    would propose to DROP, and partial indexes that were never built in tests.
    Asserting registration is cheaper than rediscovering it.
    """
    from llc import models as llc_models

    assert hasattr(llc_models, "LLCRoleRate")
    assert LLCRoleRate.__tablename__ in LLCRoleRate.metadata.tables


@pytest.mark.asyncio
async def test_a_role_with_no_rate_reads_as_none_not_zero(session: AsyncSession, service: RoleRateService) -> None:
    """The distinction the whole costing chain rests on."""
    assert await service.get(session, uuid.uuid4(), uuid.uuid4()) is None


@pytest.mark.asyncio
async def test_currency_must_be_a_three_letter_code(session: AsyncSession, service: RoleRateService) -> None:
    """A free-text unit must never reach a figure people read as money."""
    for bad in ("", "US", "DOLLAR", "12$"):
        with pytest.raises(ValueError):
            await service.set_rate(
                session,
                company_id=uuid.uuid4(),
                role_id=uuid.uuid4(),
                hourly_rate=Decimal("10"),
                currency=bad,
                actor_user_id=uuid.uuid4(),
            )


@pytest.mark.asyncio
async def test_a_negative_rate_is_refused(session: AsyncSession, service: RoleRateService) -> None:
    with pytest.raises(ValueError):
        await service.set_rate(
            session,
            company_id=uuid.uuid4(),
            role_id=uuid.uuid4(),
            hourly_rate=Decimal("-1"),
            currency="EUR",
            actor_user_id=uuid.uuid4(),
        )


@pytest.mark.asyncio
async def test_a_non_admin_cannot_set_a_rate(session: AsyncSession, service: RoleRateService) -> None:
    """Validation runs first, so this uses valid inputs and still must fail.

    A test that passed invalid inputs would go green on the ValueError and
    prove nothing about the authorisation gate.
    """
    with pytest.raises(NotAuthorisedError):
        await service.set_rate(
            session,
            company_id=uuid.uuid4(),
            role_id=uuid.uuid4(),
            hourly_rate=Decimal("100"),
            currency="EUR",
            actor_user_id=uuid.uuid4(),  # no membership row exists for this user
        )


@pytest.mark.asyncio
async def test_an_absent_actor_cannot_set_a_rate(session: AsyncSession, service: RoleRateService) -> None:
    with pytest.raises(NotAuthorisedError):
        await service.set_rate(
            session,
            company_id=uuid.uuid4(),
            role_id=uuid.uuid4(),
            hourly_rate=Decimal("100"),
            currency="EUR",
            actor_user_id=None,  # type: ignore[arg-type]
        )
