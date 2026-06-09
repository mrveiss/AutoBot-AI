# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC module shared pytest fixtures (GH#8251).

Provides:
- test_db_session: async SQLAlchemy session scoped to the test
- company_factory: creates a minimal company row
- agent_factory: creates a minimal agent row attached to a company
"""

import uuid
from typing import AsyncGenerator, Callable

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from user_management.database import get_async_session_factory


@pytest_asyncio.fixture
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Async SQLAlchemy session for LLC tests.

    Uses the same factory as the rest of the test suite so LLC tests share
    the test database configuration from user_management/.
    """
    session_factory = get_async_session_factory()
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture
def company_factory(test_db_session: AsyncSession) -> Callable:
    """Factory that inserts a minimal company row and returns its id."""

    async def _create(name: str = "Test LLC Co") -> str:
        company_id = str(uuid.uuid4())
        await test_db_session.execute(
            "INSERT INTO companies (id, name) VALUES (:id, :name)",
            {"id": company_id, "name": name},
        )
        return company_id

    return _create


@pytest.fixture
def agent_factory(test_db_session: AsyncSession, company_factory: Callable) -> Callable:
    """Factory that inserts a minimal agent row attached to a company."""

    async def _create(company_id: str | None = None, name: str = "TestAgent") -> str:
        if company_id is None:
            company_id = await company_factory()
        agent_id = str(uuid.uuid4())
        await test_db_session.execute(
            "INSERT INTO agents (id, company_id, name) VALUES (:id, :company_id, :name)",
            {"id": agent_id, "company_id": company_id, "name": name},
        )
        return agent_id

    return _create
