# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The project backfill is a preview, then a person's approval, then the write (#18978, #17038).

Through the real routes on SQLite: request (POST), decide (the LLC approvals route), and the registered
post-approval action. Rows without a project are seeded straight into the table, the way old data got there.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api.approvals import router as approvals_router
from llc.api.project_backfill import router as backfill_router
from llc.deps import get_session
from llc.models.enums import MembershipRole
from llc.models.enums import WorkItemType as T
from llc.models.membership import LLCCompanyMembership
from llc.models.sprint import LLCProject
from llc.models.work_item import LLCWorkItem
from llc.services.project_backfill import DEFAULT_PROJECT_NAME, preview_project_backfill
from llc.tests import _e2e_harness as harness
from models.approval import Approval, ApprovalComment, TaskApprovalLink
from user_management.models.base import Base
from user_management.services import TenantContext

COMPANY, OTHER = uuid.uuid4(), uuid.uuid4()
OWNER, ADMIN2, MEMBER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
PROJECT = uuid.uuid4()
PERSON = {"auth_method": "session"}


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    extra = [Approval.__table__, ApprovalComment.__table__, TaskApprovalLink.__table__]
    for table in extra:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    tables = harness.loop_tables() + extra
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as session:
        for user, role in ((OWNER, MembershipRole.OWNER), (MEMBER, MembershipRole.MEMBER)):
            session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=COMPANY, user_id=user, role=role.value))
        session.add(LLCProject(id=PROJECT, company_id=COMPANY, name="Real"))
        await session.commit()
    yield maker
    await engine.dispose()


@pytest.fixture(autouse=True)
def _outside_world(factory):
    audit = AsyncMock(return_value=True)
    with (
        patch("services.project_backfill_proposal.get_async_session_factory", lambda: factory),
        patch("services.project_backfill_action.audit_log", audit),
        patch("events.bus.publish_event", AsyncMock()),
        patch("llc.api.approvals.ApprovalService.publish_decided", AsyncMock()),
        patch("llc.api.approvals.ApprovalService.log_decision_to_kb", AsyncMock()),
    ):
        yield audit


def _client(factory, user: uuid.UUID) -> TestClient:
    app = FastAPI()
    app.include_router(backfill_router, prefix="/api/llc")
    app.include_router(approvals_router, prefix="/api/llc")

    async def _session():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user), "username": "person", **PERSON}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(org_id=COMPANY, user_id=user)
    return TestClient(app)


async def _add_admin(factory, user=ADMIN2):
    async with factory() as session:
        session.add(
            LLCCompanyMembership(id=uuid.uuid4(), company_id=COMPANY, user_id=user, role=MembershipRole.ADMIN.value)
        )
        await session.commit()


async def _item(factory, kind, *, parent=None, project=None, company=COMPANY) -> uuid.UUID:
    async with factory() as session:
        row = LLCWorkItem(
            id=uuid.uuid4(), company_id=company, type=kind, title="t", labels=[], parent_id=parent,
            identifier=f"X-{uuid.uuid4().hex[:8]}", project_id=project,
        )  # fmt: skip
        session.add(row)
        await session.commit()
        return row.id


async def _seed(factory):
    """epic (has a project) > pbi (none) > task (none); a lone task (none); another company's lone task."""
    epic = await _item(factory, T.EPIC, project=PROJECT)
    pbi = await _item(factory, T.PBI, parent=epic)
    task = await _item(factory, T.TASK, parent=pbi)
    lone = await _item(factory, T.TASK)
    theirs = await _item(factory, T.TASK, company=OTHER)
    return {"pbi": pbi, "task": task, "lone": lone, "theirs": theirs}


async def _project_of(factory, item_id):
    async with factory() as session:
        return (await session.get(LLCWorkItem, item_id)).project_id


async def _projects(factory, company=COMPANY):
    async with factory() as session:
        stmt = sa.select(LLCProject).where(LLCProject.company_id == company)
        return list((await session.execute(stmt)).scalars().all())


def _request(client):
    return client.post(f"/api/llc/companies/{COMPANY}/project-backfill")


def _decide(client, approval_id, decision="approved"):
    return client.post(f"/api/llc/approvals/{approval_id}/decide", json={"decision": decision})


@pytest.mark.asyncio
async def test_the_preview_counts_and_changes_nothing(factory):
    ids = await _seed(factory)
    body = _client(factory, OWNER).get(f"/api/llc/companies/{COMPANY}/project-backfill").json()
    assert body == {
        "missing": 3, "from_ancestor": 2, "to_default": 1, "foreign_ancestor_project_skipped": 0,
        "default_project_exists": False, "default_project_would_be_created": True,
    }  # fmt: skip
    for key in ("pbi", "task", "lone"):
        assert await _project_of(factory, ids[key]) is None
    assert [p.name for p in await _projects(factory)] == ["Real"]  # the default was not created


@pytest.mark.asyncio
async def test_requesting_files_an_approval_and_writes_no_row(factory):
    ids = await _seed(factory)
    response = _request(_client(factory, OWNER))
    assert response.status_code == 202 and response.json()["status"] == "pending"
    assert await _project_of(factory, ids["lone"]) is None
    assert len(await _projects(factory)) == 1


@pytest.mark.asyncio
async def test_approval_moves_items_ancestor_first_then_default_and_leaves_other_companies_alone(factory):
    await _add_admin(factory)
    ids = await _seed(factory)
    approval_id = _request(_client(factory, OWNER)).json()["approval_id"]
    assert _decide(_client(factory, ADMIN2), approval_id).status_code == 200
    assert await _project_of(factory, ids["pbi"]) == PROJECT
    assert await _project_of(factory, ids["task"]) == PROJECT
    default = [p for p in await _projects(factory) if p.name == DEFAULT_PROJECT_NAME]
    assert len(default) == 1 and await _project_of(factory, ids["lone"]) == default[0].id
    assert await _project_of(factory, ids["theirs"]) is None
    assert await _projects(factory, OTHER) == []


@pytest.mark.asyncio
async def test_a_rejected_request_changes_nothing(factory):
    await _add_admin(factory)
    ids = await _seed(factory)
    approval_id = _request(_client(factory, OWNER)).json()["approval_id"]
    assert _decide(_client(factory, ADMIN2), approval_id, "rejected").status_code == 200
    for key in ("pbi", "task", "lone"):
        assert await _project_of(factory, ids[key]) is None
    assert len(await _projects(factory)) == 1


@pytest.mark.asyncio
async def test_a_second_run_does_nothing(factory, _outside_world):
    from services.approval_execution import set_verified_decider
    from services.project_backfill_action import execute_project_backfill

    await _add_admin(factory)
    await _seed(factory)
    approval_id = _request(_client(factory, OWNER)).json()["approval_id"]
    _decide(_client(factory, ADMIN2), approval_id)
    async with factory() as session:
        approval = await session.get(Approval, uuid.UUID(approval_id))
        set_verified_decider(approval, ADMIN2)
        await execute_project_backfill(approval, session)  # the same approval, run again
    async with factory() as session:
        again = await preview_project_backfill(session, COMPANY)
    assert again["missing"] == 0 and again["default_project_would_be_created"] is False
    assert len([p for p in await _projects(factory) if p.name == DEFAULT_PROJECT_NAME]) == 1
    assert _outside_world.await_args.kwargs["details"]["missing"] == 0  # the audit row says it did nothing


@pytest.mark.asyncio
async def test_the_audit_row_carries_the_counts(factory, _outside_world):
    await _add_admin(factory)
    await _seed(factory)
    approval_id = _request(_client(factory, OWNER)).json()["approval_id"]
    _decide(_client(factory, ADMIN2), approval_id)
    details = _outside_world.await_args.kwargs["details"]
    assert (details["missing"], details["from_ancestor"], details["to_default"]) == (3, 2, 1)
    assert details["self_approval"] is False


@pytest.mark.asyncio
async def test_four_eyes_the_requester_cannot_decide_their_own_request_with_two_admins(factory):
    await _add_admin(factory)
    ids = await _seed(factory)
    approval_id = _request(_client(factory, OWNER)).json()["approval_id"]
    _decide(_client(factory, OWNER), approval_id)  # the decision is recorded ...
    assert await _project_of(factory, ids["lone"]) is None  # ... but nothing moved
    async with factory() as session:
        comments = (await session.execute(sa.select(ApprovalComment))).scalars().all()
    assert any("did not complete" in c.body for c in comments)


@pytest.mark.asyncio
async def test_a_sole_admin_may_self_approve_and_it_is_flagged(factory, _outside_world):
    ids = await _seed(factory)
    approval_id = _request(_client(factory, OWNER)).json()["approval_id"]
    _decide(_client(factory, OWNER), approval_id)
    assert await _project_of(factory, ids["pbi"]) == PROJECT
    assert _outside_world.await_args.kwargs["details"]["self_approval"] is True


@pytest.mark.asyncio
async def test_a_plain_member_can_neither_preview_nor_request(factory):
    client = _client(factory, MEMBER)
    assert client.get(f"/api/llc/companies/{COMPANY}/project-backfill").status_code == 403
    assert _request(client).status_code == 403


@pytest.mark.asyncio
async def test_a_project_from_another_company_is_never_taken_and_is_counted(factory):
    """Bad old data: an epic of this company sits in a project of another company. Its children do not inherit it."""
    foreign = uuid.uuid4()
    async with factory() as session:
        session.add(LLCProject(id=foreign, company_id=OTHER, name="Theirs"))
        await session.commit()
    bad_epic = await _item(factory, T.EPIC, project=foreign)
    child = await _item(factory, T.PBI, parent=bad_epic)
    good_epic = await _item(factory, T.EPIC, project=PROJECT)
    fine = await _item(factory, T.PBI, parent=good_epic)
    async with factory() as session:
        before = await preview_project_backfill(session, COMPANY)
    assert (before["missing"], before["from_ancestor"], before["to_default"]) == (2, 1, 1)
    assert before["foreign_ancestor_project_skipped"] == 1
    await _add_admin(factory)
    approval_id = _request(_client(factory, OWNER)).json()["approval_id"]
    _decide(_client(factory, ADMIN2), approval_id)
    default = [p for p in await _projects(factory) if p.name == DEFAULT_PROJECT_NAME]
    assert len(default) == 1
    assert await _project_of(factory, child) == default[0].id  # not the other company's project
    assert await _project_of(factory, fine) == PROJECT
    assert await _project_of(factory, bad_epic) == foreign  # an item that already has a project is never rewritten
