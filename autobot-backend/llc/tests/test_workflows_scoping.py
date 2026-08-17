# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Company-scoping regression test for Workflow (#14210).

This exact row-level ``WHERE company_id`` filter has now had to be pinned
independently four times (#13936, #13969, #13942, #14222) before this table
even existed — pinning it here, on the first commit that introduces the
predicate, rather than waiting for a fifth incident report.

Uses a minimal self-contained SQLite fixture (only Workflow table) — mirrors
``llc/tests/test_contacts_scoping.py`` exactly, including its reason for not
reusing the full ``_e2e_harness`` loop schema.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator
from unittest.mock import patch

import pytest
import pytest_asyncio
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import WorkflowStatus
from llc.services.workflow import WorkflowConflictError, WorkflowService, _is_workflow_unique_conflict

# Importing the harness registers the SQLite compile shims for
# postgresql.JSONB / postgresql.UUID (module-level side effect, safe to reuse
# without modifying the shared file).
from llc.tests import _e2e_harness as harness
from models.workflow import SOURCE_CREATED, SOURCE_LEGACY_REDIS, Workflow
from user_management.models.base import Base

# canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_SQLITE_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    eng = create_async_engine(_SQLITE_MEMORY_URL)
    tables = [Workflow.__table__]
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


async def _seed_workflow(session_factory, company_id: uuid.UUID, *, workflow_id: str, name: str) -> str:  # noqa: ANN001
    async with session_factory() as session:
        svc = WorkflowService()
        workflow = await svc.create(session, company_id, workflow_id, name=name)
        await session.commit()
        return workflow.workflow_id


@pytest.mark.asyncio
async def test_company_a_never_sees_company_bs_workflows(session_factory):  # noqa: ANN001
    """Row-level company scoping on WorkflowService.list_by_company.

    This pins the ``WHERE company_id`` predicate itself — dropping it leaves
    every other CRUD test in this suite green while returning every
    company's workflows from every company's list call.
    """
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()

    await _seed_workflow(session_factory, company_a, workflow_id="wf-a1", name="Deploy A")
    await _seed_workflow(session_factory, company_b, workflow_id="wf-b1", name="Deploy B1")
    await _seed_workflow(session_factory, company_b, workflow_id="wf-b2", name="Deploy B2")

    async with session_factory() as session:
        svc = WorkflowService()
        company_a_workflows = await svc.list_by_company(session, company_a)
        company_b_workflows = await svc.list_by_company(session, company_b)

    assert [w.workflow_id for w in company_a_workflows] == ["wf-a1"]
    assert sorted(w.workflow_id for w in company_b_workflows) == ["wf-b1", "wf-b2"]


@pytest.mark.asyncio
async def test_get_is_scoped_to_the_requesting_company(session_factory):  # noqa: ANN001
    """A workflow fetched with the wrong company_id resolves to None, not the row.

    Complements the list-level test above: ``get()`` is the lookup the API's
    GET/PATCH/DELETE routes use, and has its own independent WHERE clause.
    """
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    await _seed_workflow(session_factory, company_a, workflow_id="wf-a1", name="Deploy A")

    async with session_factory() as session:
        svc = WorkflowService()
        own_company = await svc.get(session, company_a, "wf-a1")
        other_company = await svc.get(session, company_b, "wf-a1")

    assert own_company is not None
    assert own_company.name == "Deploy A"
    assert other_company is None


@pytest.mark.asyncio
async def test_delete_scoped_to_company_never_deletes_another_companys_row(session_factory):  # noqa: ANN001
    """Deleting with the wrong company_id must not remove the row."""
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    await _seed_workflow(session_factory, company_a, workflow_id="wf-a1", name="Deploy A")

    async with session_factory() as session:
        svc = WorkflowService()
        deleted = await svc.delete(session, company_b, "wf-a1")
        await session.commit()

    assert deleted is False

    async with session_factory() as session:
        svc = WorkflowService()
        still_there = await svc.get(session, company_a, "wf-a1")
    assert still_there is not None


@pytest.mark.asyncio
async def test_create_requires_a_company_id(session_factory):  # noqa: ANN001
    """A workflow can never be created without an owning company (#14210).

    The DB column stays nullable to hold legacy backfilled rows (see
    models/workflow.py), so this predicate is enforced at the service layer
    — this test is what actually pins it.
    """
    async with session_factory() as session:
        svc = WorkflowService()
        with pytest.raises(ValueError):
            await svc.create(session, None, "wf-orphan", name="No company")


@pytest.mark.asyncio
async def test_legacy_backfilled_row_has_no_company_and_is_never_returned_by_list(session_factory):  # noqa: ANN001
    """A row inserted directly (bypassing the service, as the Redis backfill
    script does) with company_id=NULL never appears in any company's list —
    it exists (no data loss) but is not attributed to anyone until a human
    reconciles it.
    """
    company_a = uuid.uuid4()
    await _seed_workflow(session_factory, company_a, workflow_id="wf-a1", name="Deploy A")

    async with session_factory() as session:
        session.add(
            Workflow(
                workflow_id="wf-legacy",
                company_id=None,
                name="Recovered from Redis",
                status="planned",
                source=SOURCE_LEGACY_REDIS,
                definition={"goal": "old goal"},
            )
        )
        await session.commit()

    async with session_factory() as session:
        svc = WorkflowService()
        company_a_workflows = await svc.list_by_company(session, company_a)

    assert [w.workflow_id for w in company_a_workflows] == ["wf-a1"]
    assert company_a_workflows[0].source == SOURCE_CREATED


# `status` was a bare String(50) that the backfill populated from `current_step`
# — a step name in a status column. That is #13937's untyped-discriminator
# defect, and #13954 is what it cost: a filter on a value the backend never
# wrote, matching nothing for months. These pin the constraint while the table
# is still empty, which is the cheapest moment it will ever be.


@pytest.mark.asyncio
async def test_create_rejects_a_status_outside_the_vocabulary(session_factory):  # noqa: ANN001
    service = WorkflowService()
    async with session_factory() as session:
        with pytest.raises(ValueError):
            await service.create(
                session,
                company_id=uuid.uuid4(),
                workflow_id="wf-bad",
                status="step_3",  # a step name, the exact shape the backfill used to write
            )


@pytest.mark.asyncio
async def test_update_status_rejects_a_status_outside_the_vocabulary(session_factory):  # noqa: ANN001
    service = WorkflowService()
    company_id = uuid.uuid4()
    async with session_factory() as session:
        await service.create(session, company_id=company_id, workflow_id="wf-ok")
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ValueError):
            await service.update_status(session, company_id, "wf-ok", status="whatever")


@pytest.mark.asyncio
async def test_every_defined_status_is_accepted(session_factory):  # noqa: ANN001
    """The case that must stay caught: coercion must not reject valid members."""
    service = WorkflowService()
    company_id = uuid.uuid4()
    for index, member in enumerate(WorkflowStatus):
        async with session_factory() as session:
            created = await service.create(
                session,
                company_id=company_id,
                workflow_id=f"wf-{index}",
                status=member.value,
            )
            assert created.status == member.value
            await session.commit()


# #14271: workflow_id was a GLOBAL primary key while every route/service above
# it treats the identity as company-scoped. The two tests below pin the fix —
# the collision case (two companies sharing a workflow_id, previously
# impossible at the DB layer) and the race case (a same-company duplicate,
# which must still conflict, but cleanly).


@pytest.mark.asyncio
async def test_two_companies_can_create_the_same_workflow_id(session_factory):  # noqa: ANN001
    """The collision case: dropping this pin regresses to a global-unique PK.

    Before #14271, the second create here raised an unhandled
    ``sqlite3.IntegrityError`` / Postgres ``UNIQUE constraint failed:
    workflows.workflow_id`` — company B could never create this id at all,
    and the failure mode (500, not the route's documented 409) was itself a
    cross-tenant presence oracle. Both companies must succeed independently.
    """
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    service = WorkflowService()

    async with session_factory() as session:
        created_a = await service.create(session, company_a, "prod-deploy", name="A's deploy")
        await session.commit()

    async with session_factory() as session:
        created_b = await service.create(session, company_b, "prod-deploy", name="B's deploy")
        await session.commit()

    assert created_a.workflow_id == created_b.workflow_id == "prod-deploy"
    assert created_a.company_id == company_a
    assert created_b.company_id == company_b
    # Distinct rows (distinct surrogate primary keys) sharing a workflow_id —
    # exactly what the composite UNIQUE(company_id, workflow_id) allows and a
    # global PK on workflow_id alone forbids.
    assert created_a.id != created_b.id

    async with session_factory() as session:
        own_a = await service.get(session, company_a, "prod-deploy")
        own_b = await service.get(session, company_b, "prod-deploy")

    assert own_a is not None and own_a.name == "A's deploy"
    assert own_b is not None and own_b.name == "B's deploy"


@pytest.mark.asyncio
async def test_same_company_duplicate_workflow_id_raises_a_clean_conflict(session_factory):  # noqa: ANN001
    """The race case: a same-company duplicate must still conflict — cleanly.

    This calls ``WorkflowService.create`` directly twice (bypassing the
    route's pre-check) so it is the DB's ``UNIQUE(company_id, workflow_id)``
    constraint doing the rejecting, not the ``get()``-then-``create()``
    pre-check — the TOCTOU shape a concurrent request would hit. ``create``
    must translate that into ``WorkflowConflictError``, not let an
    ``IntegrityError`` escape unhandled.
    """
    company_id = uuid.uuid4()
    service = WorkflowService()

    async with session_factory() as session:
        await service.create(session, company_id, "wf-dup")
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(WorkflowConflictError):
            await service.create(session, company_id, "wf-dup")

    # The failed create's rollback must not have poisoned the row created
    # before it — no data loss on the conflicting attempt.
    async with session_factory() as session:
        still_there = await service.get(session, company_id, "wf-dup")
    assert still_there is not None


# #14271 review: the IntegrityError catch in create() must be narrow — only
# this table's own UNIQUE(company_id, workflow_id) becomes WorkflowConflictError.
# A different constraint (a future FK/check on this table) must propagate
# unchanged, not be relabelled as a misleading "already exists".


class _FakeAsyncpgUniqueViolation(Exception):
    """Stands in for asyncpg's structured exception shape (has .constraint_name)."""

    def __init__(self, constraint_name: str) -> None:
        super().__init__("duplicate key value violates unique constraint")
        self.constraint_name = constraint_name


def test_is_workflow_unique_conflict_matches_only_its_own_constraint():
    own = IntegrityError("INSERT", {}, _FakeAsyncpgUniqueViolation("uq_workflows_company_workflow"))
    other = IntegrityError("INSERT", {}, _FakeAsyncpgUniqueViolation("some_other_fk_constraint"))
    assert _is_workflow_unique_conflict(own) is True
    assert _is_workflow_unique_conflict(other) is False


def test_is_workflow_unique_conflict_falls_back_to_sqlite_message_shape():
    """No structured constraint_name (sqlite, used under this test suite)."""
    sqlite_message = "UNIQUE constraint failed: workflows.company_id, workflows.workflow_id"
    own = IntegrityError("INSERT", {}, Exception(sqlite_message))
    other = IntegrityError("INSERT", {}, Exception("NOT NULL constraint failed: workflows.workflow_id"))
    assert _is_workflow_unique_conflict(own) is True
    assert _is_workflow_unique_conflict(other) is False


@pytest.mark.asyncio
async def test_create_reraises_a_non_uniqueness_integrity_error(session_factory):  # noqa: ANN001
    """A constraint violation that is NOT this table's own uq_workflows_company_workflow
    must propagate as-is — never become a misleading WorkflowConflictError."""
    service = WorkflowService()
    company_id = uuid.uuid4()
    other_constraint_error = IntegrityError("INSERT", {}, _FakeAsyncpgUniqueViolation("some_other_constraint"))

    async with session_factory() as session:
        with patch.object(session, "flush", side_effect=other_constraint_error):
            with pytest.raises(IntegrityError):
                await service.create(session, company_id, "wf-other-constraint")
