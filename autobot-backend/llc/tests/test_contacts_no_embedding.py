# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Contact data must never reach the embedding/knowledge plane (#13969).

An embedding cannot be revoked. If a contact's name/email/phone/notes were
ever pushed into a vector store, deleting the contact could no longer be
honoured — exactly the deletion request ``llc/tests/test_contact_service.py``
proves ``ContactService.delete`` satisfies for the relational row. This file
proves the embedding side never happens in the first place, two ways:

1. Structural: no LLC-contact source file imports ``knowledge``, ``llc.kb``,
   or ``utils.async_chromadb_client`` — the single chokepoint every other
   indexed LLC entity (goals, work items) calls through
   (``utils.async_chromadb_client.get_async_chromadb_client``, see
   ``llc/services/goal.py::_index_goal``).
2. Behavioural, mutation-proved: spy on that chokepoint function and run a
   full create/update/delete cycle through ``ContactService`` against a real
   (in-memory) DB; the spy must never be called. Temporarily adding a call to
   it inside ``ContactService.create`` (mirroring exactly what ``GoalService``
   does for goals) turns this test red; removing it turns it green again.
"""

from __future__ import annotations

import inspect
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.api import contacts as contact_api
from llc.models import contact as contact_model
from llc.models.contact import LLCContact
from llc.services import contact as contact_service
from llc.services.contact import ContactService
from llc.tests import _e2e_harness as harness  # registers SQLite compile shims
from user_management.models.base import Base

_FORBIDDEN_IMPORT_MARKERS = ("knowledge", "llc.kb", "async_chromadb_client")


@pytest.mark.parametrize("module", [contact_model, contact_service, contact_api])
def test_contact_module_never_imports_the_embedding_plane(module) -> None:  # noqa: ANN001
    """Structural guard: source-scan for the forbidden import families.

    Reads the module's own source rather than ``sys.modules`` — a transitive
    import elsewhere in the process must not produce a false positive, and a
    literal ``import knowledge`` line inside this module must always be caught
    regardless of whether it ever executes.
    """
    source = inspect.getsource(module)
    import_lines = [line.strip() for line in source.splitlines() if line.strip().startswith(("import ", "from "))]
    offending = [line for line in import_lines if any(marker in line for marker in _FORBIDDEN_IMPORT_MARKERS)]
    assert not offending, f"{module.__name__} must never import the embedding plane, found: {offending}"


# canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_SQLITE_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    eng = create_async_engine(_SQLITE_MEMORY_URL)
    tables = [LLCContact.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    # canonical: ignore py-adhoc-db-engine (test-local session factory)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest.mark.asyncio
async def test_full_crud_cycle_never_calls_the_chromadb_client(session_factory):  # noqa: ANN001
    """Behavioural guard: create/update/delete a contact, spy on the chokepoint.

    Mutation-proof: temporarily inserting
    ``await get_async_chromadb_client()`` into ``ContactService.create``
    (exactly what ``GoalService._index_goal`` does for goals) turns this red;
    removing it restores green. Verified in the PR description, not re-run
    here, since this file's job is to fail forever after — a mutation left in
    place would defeat its own purpose.
    """
    company_id = uuid.uuid4()

    with patch("utils.async_chromadb_client.get_async_chromadb_client", new=AsyncMock()) as spy:
        async with session_factory() as session:
            svc = ContactService()
            contact = await svc.create(session, company_id, "Acme Supplier", email="s@acme.test", notes="VIP vendor")
            await session.commit()

        async with session_factory() as session:
            svc = ContactService()
            await svc.update(session, company_id, contact.id, notes="Updated note text")
            await session.commit()

        async with session_factory() as session:
            svc = ContactService()
            await svc.delete(session, company_id, contact.id)
            await session.commit()

    spy.assert_not_called()
