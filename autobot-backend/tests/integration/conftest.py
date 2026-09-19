# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Fixtures for integration tests.

``real_auth_middleware`` (real auth_middleware loaded under an alias key,
#11648) moved up to tests/conftest.py in #11791 so root-level tests share it;
it remains available here through the conftest hierarchy.

JSONB/ARRAY-on-SQLite (#11687): production models use PostgreSQL-only column
types (``postgresql.JSONB`` / ``postgresql.ARRAY``) while integration tests
run ``Base.metadata.create_all`` against in-memory SQLite. SQLite's DDL
compiler has no renderer for those types, so every such test errored at
fixture setup. The ``@compiles(..., "sqlite")`` hooks below render both as
``JSON`` (SQLite has native JSON support; JSONB inherits the generic JSON
bind/result processors, so round-tripping dict/list values keeps working).
Registration is global and idempotent — a no-op for every other dialect, so
PostgreSQL DDL is untouched.
"""

from typing import AsyncGenerator

import pytest
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import StaticPool

from models.mobile_device import MobileDevice
from user_management.models.base import Base


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    """Render PostgreSQL JSONB columns as JSON on SQLite test databases (#11687)."""
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_pg_array_sqlite(element, compiler, **kw):
    """Render PostgreSQL ARRAY columns as JSON on SQLite test databases (#11687)."""
    return "JSON"


# --- Shared mobile-push fixtures (#15150) -----------------------------------
#
# Moved here from test_mobile_push.py when a second module needed them. They
# describe the same in-memory device store either way; leaving them in one test
# module and importing across files makes the dependency invisible to pytest's
# fixture resolution and to anyone reading either file.

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def _test_encryption_service(monkeypatch):
    """Provide a REAL EncryptionService with an injected test master key (#11687).

    ``MobileDevice.device_token`` encrypts/decrypts through the module-level
    ``get_encryption_service()`` singleton, which requires
    ``AUTOBOT_ENCRYPTION_KEY`` — absent in the hermetic test env (ssot config
    reads env once at import, so setting the variable here would be too late).
    Injecting the key keeps the real AES-GCM round-trip under test.
    """
    import encryption_service as enc_mod

    svc = enc_mod.EncryptionService(master_key="integration-test-master-key-0123456789abcdef")
    monkeypatch.setattr(enc_mod, "get_encryption_service", lambda: svc)


@pytest.fixture
async def test_db_engine():
    """Create an in-memory test database engine."""
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    async with engine.begin() as conn:
        # #11834: scope create_all to the tables under test — whole-metadata
        # create_all breaks under whole-dir order when earlier tests import
        # llc models whose Postgres '::jsonb' server_defaults sqlite rejects.
        await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=[MobileDevice.__table__]))

    yield engine

    await engine.dispose()


@pytest.fixture
async def test_db_session(test_db_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async_session = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        test_db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session


@pytest.fixture
def test_user_id():
    """Test user ID."""
    return "test-user-push-123"


@pytest.fixture
def mock_session_factory(test_db_session):
    """Mock session factory for push service.

    Mirrors ``async_sessionmaker``: a SYNC callable whose return value is an
    async context manager yielding the session (#11687 — the old async-def
    version handed ``async with`` a coroutine, which has no ``__aenter__``).
    """

    def factory():
        class SessionContext:
            async def __aenter__(self):
                return test_db_session

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

        return SessionContext()

    return factory
