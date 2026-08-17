# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Workflows attached to a role, and the guards on attaching them (#14221 step 5).

The load-bearing test is ``test_workflows_survive_a_change_of_holder``: the
whole reason a role is an object is that its workflows do not follow the person.

The second one worth reading is
``test_an_unattributed_legacy_workflow_cannot_be_attached``. ``Workflow.company_id``
is nullable for rows backfilled from Redis. Removing the dedicated NULL branch
reddens that test — verified by mutation — but it is worth being precise about
why: ``None != company_id`` is already ``True``, so the workflow stays refused.
What the branch protects is the *reason* given: "no company attribution yet"
versus a workflow that simply is not visible to this caller at all.

``test_another_companys_workflow_cannot_be_attached`` pins the #14271 fix
directly: attaching another company's workflow is refused with the *same*
"does not exist" message a truly-missing workflow gets, not a distinct
"belongs to company X" — the old distinct message was a cross-tenant
presence oracle for a client-supplied id (#14271).
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import MembershipRole, RoleHolderType
from llc.models.membership import LLCCompanyMembership
from llc.models.role_assignment import LLCRoleAssignment
from llc.models.role_workflow import LLCRoleWorkflow
from llc.services.authz import NotAuthorisedError
from llc.services.role import RoleService
from llc.services.role_assignment import RoleAssignmentService
from llc.services.role_workflow import RoleWorkflowService

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from models.workflow import Workflow
from user_management.models.base import Base
from user_management.models.role import Role


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [
        Role.__table__,
        LLCRoleAssignment.__table__,
        LLCRoleWorkflow.__table__,
        Workflow.__table__,
        LLCCompanyMembership.__table__,
    ]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


#: Attach/detach are admin-gated; this suite acts as one admin throughout.
_ADMIN_USER = uuid.uuid4()


async def _grant_admin(session_factory, company_id: uuid.UUID) -> None:  # noqa: ANN001
    async with session_factory() as session:
        existing = await session.execute(
            sa.select(LLCCompanyMembership.id).where(
                LLCCompanyMembership.company_id == company_id,
                LLCCompanyMembership.user_id == _ADMIN_USER,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company_id,
                user_id=_ADMIN_USER,
                role=MembershipRole.ADMIN.value,
            )
        )
        await session.commit()


async def _seed_role(session_factory, company_id: uuid.UUID, name: str) -> uuid.UUID:  # noqa: ANN001
    await _grant_admin(session_factory, company_id)
    async with session_factory() as session:
        role = await RoleService().create(session, company_id=company_id, name=name, actor_user_id=_ADMIN_USER)
        await session.commit()
        return role.id


async def _seed_workflow(session_factory, workflow_id: str, company_id: uuid.UUID | None) -> str:  # noqa: ANN001
    async with session_factory() as session:
        session.add(Workflow(workflow_id=workflow_id, company_id=company_id, name=workflow_id))
        await session.commit()
        return workflow_id


@pytest.mark.asyncio
async def test_workflows_survive_a_change_of_holder(session_factory):  # noqa: ANN001
    """The point of the whole issue: the workflow belongs to the role.

    Someone leaves, someone else arrives, and the role's workflows are
    untouched throughout.
    """
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "Head of Sales")
    workflow_id = await _seed_workflow(session_factory, "wf-quarterly-report", company)
    workflows = RoleWorkflowService()
    occupancy = RoleAssignmentService()
    leaver, successor = uuid.uuid4(), uuid.uuid4()

    async with session_factory() as session:
        await workflows.attach(
            session, company_id=company, role_id=role_id, workflow_id=workflow_id, actor_user_id=_ADMIN_USER
        )
        tenure = await occupancy.assign(
            session,
            actor_user_id=_ADMIN_USER,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.USER,
            holder_id=leaver,
        )
        await session.commit()
        tenure_id = tenure.id

    async with session_factory() as session:
        await occupancy.end_tenure(session, company, tenure_id, actor_user_id=_ADMIN_USER)
        await occupancy.assign(
            session,
            actor_user_id=_ADMIN_USER,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.USER,
            holder_id=successor,
        )
        await session.commit()

    async with session_factory() as session:
        attached = await workflows.list_for_role(session, company, role_id)

    assert [a.workflow_id for a in attached] == [
        workflow_id
    ], "the role's workflows moved or vanished when the holder changed"


@pytest.mark.asyncio
async def test_an_unattributed_legacy_workflow_cannot_be_attached(session_factory):  # noqa: ANN001
    """A NULL company_id must be refused, and refused *distinctly*.

    Pins the error message, not just the refusal — see the module docstring for
    why the distinction is the thing worth protecting here.
    """
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "Head of Sales")
    workflow_id = await _seed_workflow(session_factory, "wf-legacy", None)
    service = RoleWorkflowService()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="no company attribution"):
            await service.attach(
                session, company_id=company, role_id=role_id, workflow_id=workflow_id, actor_user_id=_ADMIN_USER
            )

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == []


@pytest.mark.asyncio
async def test_another_companys_workflow_cannot_be_attached(session_factory):  # noqa: ANN001
    """#14271: refused with the *same* message a missing workflow gets.

    A distinct "belongs to company X" message would tell a company-A admin
    that a specific workflow_id exists somewhere in the installation, outside
    their own company — a cross-tenant presence oracle for a client-supplied
    id. The denial must be indistinguishable from "no such workflow".
    """
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_a = await _seed_role(session_factory, company_a, "Head of Sales")
    theirs = await _seed_workflow(session_factory, "wf-theirs", company_b)
    service = RoleWorkflowService()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="does not exist"):
            await service.attach(
                session, company_id=company_a, role_id=role_a, workflow_id=theirs, actor_user_id=_ADMIN_USER
            )


@pytest.mark.asyncio
async def test_a_missing_workflow_is_refused_separately_from_an_unowned_one(session_factory):  # noqa: ANN001
    """ "No such workflow" and "that workflow has no owner" are different facts."""
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "Head of Sales")
    service = RoleWorkflowService()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="does not exist"):
            await service.attach(
                session, company_id=company, role_id=role_id, workflow_id="wf-nope", actor_user_id=_ADMIN_USER
            )


@pytest.mark.asyncio
async def test_cannot_attach_to_another_companys_role(session_factory):  # noqa: ANN001
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    # Admin of company_a too, or the authorisation gate fires before the
    # scoping check and the test stops exercising scoping.
    await _grant_admin(session_factory, company_a)
    role_b = await _seed_role(session_factory, company_b, "SRE")
    workflow_a = await _seed_workflow(session_factory, "wf-a", company_a)
    service = RoleWorkflowService()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="role .* does not exist in company"):
            await service.attach(
                session, company_id=company_a, role_id=role_b, workflow_id=workflow_a, actor_user_id=_ADMIN_USER
            )


@pytest.mark.asyncio
async def test_attaching_twice_is_refused(session_factory):  # noqa: ANN001
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    workflow_id = await _seed_workflow(session_factory, "wf-1", company)
    service = RoleWorkflowService()

    async with session_factory() as session:
        await service.attach(
            session, company_id=company, role_id=role_id, workflow_id=workflow_id, actor_user_id=_ADMIN_USER
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="already attached"):
            await service.attach(
                session, company_id=company, role_id=role_id, workflow_id=workflow_id, actor_user_id=_ADMIN_USER
            )


@pytest.mark.asyncio
async def test_list_and_detach_are_company_scoped(session_factory):  # noqa: ANN001
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    # Admin of company_a too, or the authorisation gate fires before the
    # scoping check and the test stops exercising scoping.
    await _grant_admin(session_factory, company_a)
    role_b = await _seed_role(session_factory, company_b, "SRE")
    workflow_b = await _seed_workflow(session_factory, "wf-b", company_b)
    service = RoleWorkflowService()

    async with session_factory() as session:
        await service.attach(
            session, company_id=company_b, role_id=role_b, workflow_id=workflow_b, actor_user_id=_ADMIN_USER
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.list_for_role(session, company_a, role_b) == []
        assert await service.detach(session, company_a, role_b, workflow_b, actor_user_id=_ADMIN_USER) is False
        await session.commit()

    async with session_factory() as session:
        assert len(await service.list_for_role(session, company_b, role_b)) == 1


@pytest.mark.asyncio
async def test_detach_removes_the_attachment_and_reports_it(session_factory):  # noqa: ANN001
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    workflow_id = await _seed_workflow(session_factory, "wf-1", company)
    service = RoleWorkflowService()

    async with session_factory() as session:
        await service.attach(
            session, company_id=company, role_id=role_id, workflow_id=workflow_id, actor_user_id=_ADMIN_USER
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.detach(session, company, role_id, workflow_id, actor_user_id=_ADMIN_USER) is True
        assert await service.detach(session, company, role_id, workflow_id, actor_user_id=_ADMIN_USER) is False
        await session.commit()

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == []


@pytest.mark.asyncio
async def test_roles_for_workflow_is_the_reverse_lookup(session_factory):  # noqa: ANN001
    """Which roles run this workflow — scoped, and sorted by role name."""
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    sre = await _seed_role(session_factory, company_a, "SRE")
    lead = await _seed_role(session_factory, company_a, "Team Lead")
    other = await _seed_role(session_factory, company_b, "SRE")
    workflow_a = await _seed_workflow(session_factory, "wf-shared", company_a)
    workflow_b = await _seed_workflow(session_factory, "wf-shared-b", company_b)
    service = RoleWorkflowService()

    async with session_factory() as session:
        for role_id in (sre, lead):
            await service.attach(
                session, company_id=company_a, role_id=role_id, workflow_id=workflow_a, actor_user_id=_ADMIN_USER
            )
        await service.attach(
            session, company_id=company_b, role_id=other, workflow_id=workflow_b, actor_user_id=_ADMIN_USER
        )
        await session.commit()

    async with session_factory() as session:
        found = await service.roles_for_workflow(session, company_a, workflow_a)

    assert [r.name for r in found] == ["SRE", "Team Lead"]


class _RecordingActivityLog:
    """Captures ``record()`` calls — a stateful fake, not a MagicMock."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def record(self, **kwargs) -> None:  # noqa: ANN003
        self.events.append(kwargs)


@pytest.mark.asyncio
async def test_attach_and_detach_are_audited(session_factory):  # noqa: ANN001
    log = _RecordingActivityLog()
    service = RoleWorkflowService(activity_log=log)
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    workflow_id = await _seed_workflow(session_factory, "wf-1", company)

    async with session_factory() as session:
        await service.attach(
            session, company_id=company, role_id=role_id, workflow_id=workflow_id, actor_user_id=_ADMIN_USER
        )
        assert await service.detach(session, company, role_id, workflow_id, actor_user_id=_ADMIN_USER) is True
        await session.commit()

    assert [e["event_type"] for e in log.events] == [
        "role_workflow.attached",
        "role_workflow.detached",
    ]
    assert all(e["entity_type"] == "llc_role_workflow" for e in log.events)
    assert all(e["company_id"] == str(company) for e in log.events)


@pytest.mark.asyncio
async def test_a_refused_attach_emits_nothing(session_factory):  # noqa: ANN001
    log = _RecordingActivityLog()
    service = RoleWorkflowService(activity_log=log)
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    workflow_id = await _seed_workflow(session_factory, "wf-legacy", None)

    async with session_factory() as session:
        with pytest.raises(ValueError):
            await service.attach(
                session, company_id=company, role_id=role_id, workflow_id=workflow_id, actor_user_id=_ADMIN_USER
            )
        await session.rollback()

    assert log.events == []


@pytest.mark.asyncio
async def test_a_member_cannot_attach_a_workflow_to_a_role(session_factory):  # noqa: ANN001
    """Attaching changes what every holder of that role runs — admin only.

    Same shape as the occupancy escalation: a gate on one mutating path is
    worthless while a sibling path that changes the same outcome is open.
    """
    service = RoleWorkflowService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    workflow_id = await _seed_workflow(session_factory, "wf-1", company)
    member = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company,
                user_id=member,
                role=MembershipRole.MEMBER.value,
            )
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(NotAuthorisedError, match="may not perform this change"):
            await service.attach(
                session,
                company_id=company,
                role_id=role_id,
                workflow_id=workflow_id,
                actor_user_id=member,
            )

    async with session_factory() as session:
        assert await service.list_for_role(session, company, role_id) == []


@pytest.mark.asyncio
async def test_a_member_cannot_detach_a_workflow(session_factory):  # noqa: ANN001
    service = RoleWorkflowService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    workflow_id = await _seed_workflow(session_factory, "wf-1", company)
    member = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company,
                user_id=member,
                role=MembershipRole.MEMBER.value,
            )
        )
        await service.attach(
            session,
            company_id=company,
            role_id=role_id,
            workflow_id=workflow_id,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(NotAuthorisedError):
            await service.detach(session, company, role_id, workflow_id, actor_user_id=member)

    async with session_factory() as session:
        assert len(await service.list_for_role(session, company, role_id)) == 1
