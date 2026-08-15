# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Company scoping and naming rules for :class:`LLCRole` (#14221 step 1).

The two-company case exists because a single-company fixture cannot distinguish
"the WHERE clause works" from "the WHERE clause was deleted" — with only one
company's rows in the database, every assertion passes either way. That gap has
now had to be closed independently five times in this module (#13936, #13969,
#13942, #14222, #14210), so it is written first here rather than discovered
again.

Uses a minimal self-contained SQLite fixture (LLCRole only), following
``test_contacts_scoping.py``: a role does not participate in the e2e loop, and
importing ``_e2e_harness`` is only for its already-registered JSONB/UUID compile
shims.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.role import LLCRole
from llc.services.role import RoleService

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness  # noqa: F401
from user_management.models.base import Base


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[LLCRole.__table__])
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


@pytest.mark.asyncio
async def test_company_a_never_sees_company_bs_roles(session_factory):  # noqa: ANN001
    """The reproduction: deleting the WHERE must fail this, and only this."""
    service = RoleService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()

    async with session_factory() as session:
        await service.create(session, company_id=company_a, name="Head of Sales")
        await service.create(session, company_id=company_b, name="SRE")
        await service.create(session, company_id=company_b, name="Marketing Lead")
        await session.commit()

    async with session_factory() as session:
        listed = await service.list_by_company(session, company_a)

    assert [role.name for role in listed] == [
        "Head of Sales"
    ], f"company B's roles leaked into company A: {[r.name for r in listed]}"


@pytest.mark.asyncio
async def test_get_is_scoped_so_another_companys_role_is_invisible(session_factory):  # noqa: ANN001
    service = RoleService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()

    async with session_factory() as session:
        theirs = await service.create(session, company_id=company_b, name="SRE")
        await session.commit()
        theirs_id = theirs.id

    async with session_factory() as session:
        # Knowing the id must not be enough to read it from another company.
        assert await service.get(session, company_a, theirs_id) is None
        assert await service.get(session, company_b, theirs_id) is not None


@pytest.mark.asyncio
async def test_delete_never_removes_another_companys_role(session_factory):  # noqa: ANN001
    service = RoleService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()

    async with session_factory() as session:
        theirs = await service.create(session, company_id=company_b, name="SRE")
        await session.commit()
        theirs_id = theirs.id

    async with session_factory() as session:
        removed = await service.delete(session, company_a, theirs_id)
        await session.commit()

    assert removed is False
    async with session_factory() as session:
        assert await service.get(session, company_b, theirs_id) is not None


@pytest.mark.asyncio
async def test_two_companies_may_each_have_the_same_role_name(session_factory):  # noqa: ANN001
    """Uniqueness is per company — a 'Head of Sales' in each is two roles."""
    service = RoleService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()

    async with session_factory() as session:
        a_role = await service.create(session, company_id=company_a, name="Head of Sales")
        b_role = await service.create(session, company_id=company_b, name="Head of Sales")
        await session.commit()

    assert a_role.id != b_role.id


@pytest.mark.asyncio
async def test_a_blank_name_is_rejected(session_factory):  # noqa: ANN001
    """A whitespace name would satisfy NOT NULL while naming nothing."""
    service = RoleService()
    async with session_factory() as session:
        with pytest.raises(ValueError):
            await service.create(session, company_id=uuid.uuid4(), name="   ")


@pytest.mark.asyncio
async def test_create_requires_a_company(session_factory):  # noqa: ANN001
    service = RoleService()
    async with session_factory() as session:
        with pytest.raises(ValueError):
            await service.create(session, company_id=None, name="Orphan")


@pytest.mark.asyncio
async def test_update_is_scoped_and_still_trims(session_factory):  # noqa: ANN001
    service = RoleService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()

    async with session_factory() as session:
        theirs = await service.create(session, company_id=company_b, name="SRE")
        await session.commit()
        theirs_id = theirs.id

    async with session_factory() as session:
        assert await service.update(session, company_a, theirs_id, name="Hijacked") is None
        updated = await service.update(session, company_b, theirs_id, name="  Platform SRE  ")
        assert updated is not None and updated.name == "Platform SRE"
        await session.commit()


class _RecordingActivityLog:
    """Captures ``record()`` calls. A stateful fake, not a MagicMock.

    A MagicMock would make "an event was emitted" and "nothing was written"
    look identical, which is the failure this module has hit before — so the
    calls are actually kept and asserted against.
    """

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def record(self, **kwargs) -> None:  # noqa: ANN003
        self.events.append(kwargs)


@pytest.mark.asyncio
async def test_mutations_emit_activity_log_events(session_factory):  # noqa: ANN001
    """The service claims an audit trail; this is what proves one exists.

    ``role.deleted`` is the one that would silently vanish: it needs the row
    read *before* the DELETE, so an implementation that logs afterwards emits
    an event with no entity behind it — or none at all.
    """
    log = _RecordingActivityLog()
    service = RoleService(activity_log=log)
    company = uuid.uuid4()

    async with session_factory() as session:
        role = await service.create(session, company_id=company, name="SRE", actor="u1")
        await service.update(session, company, role.id, name="Platform SRE", actor="u1")
        assert await service.delete(session, company, role.id, actor="u1") is True
        await session.commit()

    assert [e["event_type"] for e in log.events] == [
        "role.created",
        "role.updated",
        "role.deleted",
    ]
    assert {e["entity_id"] for e in log.events} == {str(role.id)}
    assert all(e["entity_type"] == "llc_role" for e in log.events)
    assert all(e["company_id"] == str(company) for e in log.events)


@pytest.mark.asyncio
async def test_a_no_op_update_emits_nothing(session_factory):  # noqa: ANN001
    """An update that changes no permitted field is not an event."""
    log = _RecordingActivityLog()
    service = RoleService(activity_log=log)
    company = uuid.uuid4()

    async with session_factory() as session:
        role = await service.create(session, company_id=company, name="SRE")
        log.events.clear()
        await service.update(session, company, role.id, not_a_column="ignored")
        await session.commit()

    assert log.events == []


@pytest.mark.asyncio
async def test_a_scoped_out_delete_emits_nothing(session_factory):  # noqa: ANN001
    """Failing to delete another company's role must not log a deletion."""
    log = _RecordingActivityLog()
    service = RoleService(activity_log=log)
    company_a, company_b = uuid.uuid4(), uuid.uuid4()

    async with session_factory() as session:
        role = await service.create(session, company_id=company_b, name="SRE")
        await session.commit()
        log.events.clear()

    async with session_factory() as session:
        assert await service.delete(session, company_a, role.id) is False
        await session.commit()

    assert log.events == []
