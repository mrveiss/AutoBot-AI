# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The scan-path ``_upsert_service`` in ``api/services.py`` stores only real unit names (#19005).

A service name discovered on a node is later passed to ``manage-service.yml`` as an extra var, so a
name that is not a systemd unit name is dropped at ingest. Same harness as
``test_service_action_injection_18359.py``: the real ORM and an in-memory database, so "not stored"
is read from the table rather than from a mock.
"""

from __future__ import annotations

import secrets
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_auth_import import load_real_auth  # noqa: E402
from _real_orm_import import (  # noqa: E402
    REAL_MODULES,
    SLM_ROOT,
    import_modules_with_real_orm,
    real_modules_swapped,
)

_auth = load_real_auth(secrets.token_hex(32))


async def _real_get_db():  # never called: _upsert_service takes the session directly
    yield None


_fake_db = types.ModuleType("services.database")
_fake_db.get_db = _real_get_db
_fake_db.db_service = None

with patch.dict(sys.modules, {"services.auth": _auth, "services.database": _fake_db}):
    _categorizer, _api = import_modules_with_real_orm(
        import_names=("api.services",),
        path_loaded={"services.service_categorizer": SLM_ROOT / "services" / "service_categorizer.py"},
    )

_db = REAL_MODULES["models.database"]
with real_modules_swapped():
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_NODE_ID = "n-scan"
_HOSTILE = [
    "{{ lookup('pipe', 'id') }}",
    "a b",
    'x"y',
    "x'y",
    "a;b",
    "a\nb",
    "-H",
    "x" * 300,
    "../x",
    "redis\u2010stack",
    "r\u00e9dis",
]
_ACTIVE = {"active": "active", "sub": "running"}


@pytest.fixture
async def session():
    with real_modules_swapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine
        async with engine.begin() as conn:
            await conn.run_sync(_db.Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
    async with maker() as db:
        db.add(_db.Node(node_id=_NODE_ID, hostname="h", ip_address="node.example.test", status="online"))
        await db.commit()
        yield db
    await engine.dispose()


async def _stored_names(db) -> list[str]:
    result = await db.execute(select(_db.Service.service_name).where(_db.Service.node_id == _NODE_ID))
    return list(result.scalars().all())


@pytest.mark.parametrize("name", _HOSTILE, ids=lambda n: repr(n)[:30])
async def test_a_hostile_discovered_name_is_dropped_and_not_stored(session, name):
    outcome = await _api._upsert_service(session, _NODE_ID, name, _ACTIVE, datetime.now(timezone.utc))
    await session.commit()

    assert outcome == (False, False)
    assert await _stored_names(session) == []


async def test_a_real_unit_name_is_stored(session):
    outcome = await _api._upsert_service(session, _NODE_ID, "redis-stack.service", _ACTIVE, datetime.now(timezone.utc))
    await session.commit()

    assert outcome == (True, False)
    assert await _stored_names(session) == ["redis-stack.service"]


async def test_a_hostile_name_does_not_stop_the_real_one_beside_it(session):
    now = datetime.now(timezone.utc)
    await _api._upsert_service(session, _NODE_ID, "{{ 7*7 }}", _ACTIVE, now)
    await _api._upsert_service(session, _NODE_ID, "autobot-backend", _ACTIVE, now)
    await session.commit()

    assert await _stored_names(session) == ["autobot-backend"]
