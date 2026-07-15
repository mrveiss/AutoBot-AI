# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Postgres core tests for the connector-credential dual-write mirror (#10088 / Task 3c-2).

Drives the mirror/delete cores against a real Postgres unified store and verifies the
mirrored copy is envelope-readable (via the read core) after create, update, and delete.
"""

import base64
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from services.credential_read import read_imported_credential_in_session
from services.credential_write import delete_in_session, mirror_in_session
from tests.migrations.conftest import requires_postgres, run_alembic

pytestmark = [pytest.mark.migration_gate, requires_postgres]

_ROOT = base64.urlsafe_b64decode(base64.urlsafe_b64encode(bytes(range(32))))
_OWNER = uuid.uuid4()
_TYPE = "connector_oauth_token"


@pytest.fixture()
async def session(fresh_db_url):
    assert run_alembic(["upgrade", "head"], fresh_db_url).returncode == 0
    engine = create_async_engine(fresh_db_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_mirror_creates_then_readable(session):
    await mirror_in_session(
        session, "sid-1", str(_OWNER), '{"token":"v1"}', _ROOT, name="connector:c:auth", secret_type=_TYPE
    )
    await session.commit()
    out = await read_imported_credential_in_session(session, "sid-1", str(_OWNER), _ROOT)
    assert out == {"created_by": str(_OWNER), "value": '{"token":"v1"}'}


async def test_mirror_updates_existing_in_place(session):
    await mirror_in_session(
        session, "sid-1", str(_OWNER), '{"token":"v1"}', _ROOT, name="connector:c:auth", secret_type=_TYPE
    )
    await session.commit()
    # second mirror without name/type → rotates the existing copy in place
    await mirror_in_session(session, "sid-1", str(_OWNER), '{"token":"v2"}', _ROOT)
    await session.commit()
    out = await read_imported_credential_in_session(session, "sid-1", str(_OWNER), _ROOT)
    assert out == {"created_by": str(_OWNER), "value": '{"token":"v2"}'}


async def test_update_only_skips_when_absent(session):
    # no existing copy + no name/type → no-op (nothing to rotate, cannot create)
    await mirror_in_session(session, "sid-x", str(_OWNER), '{"token":"v"}', _ROOT)
    await session.commit()
    assert await read_imported_credential_in_session(session, "sid-x", str(_OWNER), _ROOT) is None


async def test_delete_removes_unified_copy(session):
    await mirror_in_session(
        session, "sid-1", str(_OWNER), '{"token":"v1"}', _ROOT, name="connector:c:auth", secret_type=_TYPE
    )
    await session.commit()
    await delete_in_session(session, "sid-1", str(_OWNER), _ROOT)
    await session.commit()
    assert await read_imported_credential_in_session(session, "sid-1", str(_OWNER), _ROOT) is None
