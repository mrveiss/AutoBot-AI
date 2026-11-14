# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every route that can set a work item to done goes through the one review-gated path (#21503).

The agent API, the REST transition and the board move are driven through the REAL routers and services over an
in-memory database. Only the outward effects are faked: Redis, the handoff's notification, brief and audit row,
the artifact ingest and the live-event publish.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api import boards as boards_api
from llc.api import work_items as work_items_api
from llc.deps import get_session
from llc.models.activity import LLCActivityLog
from llc.models.board import LLCBoard, LLCBoardColumn
from llc.models.enums import BoardType, MembershipRole, WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.membership import LLCCompanyMembership
from llc.models.review_gate import LLCReviewGatePolicy
from llc.models.work_item import LLCWorkItem
from llc.services import after_commit
from llc.services.activity_log import LLCActivityLogService
from llc.services.handoff import HandoffService
from llc.services.work_item_service import InvalidTransition, WorkItemService
from llc.tests import _e2e_harness as harness
from user_management.services import TenantContext

pytestmark = pytest.mark.asyncio

_COMPANY = uuid.UUID("0f1d7a52-3c88-4b6e-9a0d-61c2b7e4f905")
_ITEM = uuid.UUID("9c2e4b1a-7d35-4f08-8e6a-3b1d5c7a9e02")
_NODE = uuid.UUID("b3c1e7a2-9d4f-4c68-a1f5-2e8d6b0c7a43")
_OTHER_NODE = uuid.UUID("c4d2f8b3-ae50-4d79-b206-3f9e7c1d8b54")
_REVIEWER = uuid.UUID("5799065e-4061-4af8-bee7-64e65f1a2b91")
_CREATOR = uuid.UUID("6a8a176f-5172-4b09-8cf8-75f76a2b3ca2")
_HUMAN = uuid.UUID("7b9b2870-6283-4c1a-9d09-86a87b3c4db3")
_BOARD = uuid.UUID("8cac3981-7394-4d2b-8e1a-97b98c4d5ec4")
_DONE_COLUMN = uuid.UUID("9dbd4a92-84a5-4e3c-9f2b-a8ca9d5e6fd5")
_SLUG = "agent-21503"
_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
_PERSON = {"id": str(_HUMAN), "auth_method": "session"}
_SERVICE = {"id": str(_HUMAN), "auth_method": "session", "service": True}
#: A token that is not a login session: the verified-user shape without ``login_token``.
_TOKEN = {"id": str(_HUMAN), "auth_method": "jwt"}
#: The stand-in the auth middleware yields when authentication is disabled.
_AUTH_OFF = {"user_id": "admin", "sub": "admin", "username": "admin", "role": "admin", "auth_disabled": True}


async def _create_board_tables(engine) -> None:  # noqa: ANN001
    tables = [LLCBoard.__table__, LLCBoardColumn.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._rebind_enums_by_value(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: harness.Base.metadata.create_all(sync_conn, tables=tables))


@pytest_asyncio.fixture
async def factory():  # noqa: ANN201
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    await harness.create_loop_schema(engine)
    await _create_board_tables(engine)
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def effects(factory):  # noqa: ANN001, ANN201
    """Fake only what leaves the process; the services, the routers and the database are real."""
    with (
        patch("user_management.database.get_async_session_factory", return_value=factory),
        patch("llc.services.work_item_own_task.get_async_redis_client", new=AsyncMock(return_value=None)),
        patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=MagicMock())),
        patch("llc.services.handoff.delete_if_holder", new=AsyncMock()) as fence,
        patch.object(HandoffService, "_record_a2h_activity", new=AsyncMock()),
        patch.object(HandoffService, "_publish_a2h_notification", new=AsyncMock()),
        patch.object(HandoffService, "_generate_and_update_brief_async", new=AsyncMock()),
        patch.object(HandoffService, "_generate_brief", new=MagicMock(return_value={})),
        patch.object(WorkItemService, "_trigger_artifact_ingest", new=AsyncMock()),
        patch("llc.services.work_item_service.release_workspace_for_task", new=AsyncMock()) as release,
        patch.object(LLCActivityLogService, "_publish_after_commit", new=AsyncMock()),
        patch("llc.services.board.get_async_redis_client", new=AsyncMock(return_value=None)),
        patch("llc.kb.collections.KbCollectionManager.archive_collection", new=AsyncMock()),
    ):
        yield SimpleNamespace(fence=fence, release=release)
        await asyncio.gather(*after_commit.after_commit_tasks)


async def _seed(  # noqa: ANN202
    factory,  # noqa: ANN001
    *,
    type_: WorkItemType = WorkItemType.BUG,
    status: WorkItemStatus = WorkItemStatus.IN_PROGRESS,
    agent: uuid.UUID | None = _NODE,
    reviewer: uuid.UUID | None = None,
    creator: uuid.UUID | None = None,
    gated: bool = True,
    members: tuple[uuid.UUID, ...] = (_REVIEWER, _CREATOR),
):
    """One item (held by *agent* with a live checkout) and, when *gated*, a bug policy that requires review."""
    async with factory() as session:
        session.add(
            LLCWorkItem(
                id=_ITEM,
                company_id=_COMPANY,
                type=type_,
                identifier="T-21503",
                title="a work item",
                status=status,
                priority=WorkItemPriority.MEDIUM,
                labels=[],
                linked_pr_urls=[],
                requires_approval_before=[],
                backlog_position=0,
                needs_triage=False,
                assignee_agent_id=agent,
                assignee_type="agent" if agent else None,
                checkout_run_id="run-1" if agent else None,
                checkout_locked_at=_NOW if agent else None,
                reviewer_user_id=reviewer,
                created_by_user_id=creator,
            )
        )
        if gated:
            session.add(
                LLCReviewGatePolicy(
                    company_id=_COMPANY,
                    item_type=WorkItemType.BUG,
                    requires_human_review=True,
                    reviewer_role="admin",
                    requires_cross_vendor_review=False,
                )
            )
        for user in members:
            session.add(LLCCompanyMembership(company_id=_COMPANY, user_id=user, role=MembershipRole.MEMBER))
        session.add(LLCBoard(id=_BOARD, company_id=_COMPANY, type=BoardType.KANBAN, name="Board"))
        await session.flush()
        session.add(LLCBoardColumn(id=_DONE_COLUMN, board_id=_BOARD, name="Done", position=1, status_filter=["done"]))
        await session.commit()


async def _row(factory) -> LLCWorkItem:  # noqa: ANN001
    async with factory() as session:
        return (await session.execute(select(LLCWorkItem).where(LLCWorkItem.id == _ITEM))).scalar_one()


async def _completed_rows(factory) -> list[LLCActivityLog]:  # noqa: ANN001
    async with factory() as session:
        rows = await session.execute(
            select(LLCActivityLog).where(
                LLCActivityLog.entity_id == _ITEM, LLCActivityLog.action == "work_item.completed"
            )
        )
        return list(rows.scalars())


async def _agent_asks_for_done(node: uuid.UUID | None = _NODE) -> dict:
    from llc.api.agent_api import StatusUpdate, update_work_item_status

    with (
        patch("llc.api.agent_api.agent_context", return_value=(_SLUG, str(_COMPANY))),
        patch("llc.api.agent_api.agent_node_uuid", new=AsyncMock(return_value=node)),
    ):
        request: Any = object()  # agent_context is patched; the request is unused
        return await update_work_item_status(str(_ITEM), StatusUpdate(status="done"), request)


def _client(factory, user: dict) -> httpx.AsyncClient:  # noqa: ANN001
    app = FastAPI()
    app.include_router(work_items_api.router, prefix="/api/llc")
    app.include_router(boards_api.router, prefix="/api/llc")

    async def _session():  # noqa: ANN202
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_COMPANY, user_id=_HUMAN, is_platform_admin=False
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _rest_done(factory, user: dict) -> httpx.Response:  # noqa: ANN001
    async with _client(factory, user) as client:
        return await client.post(f"/api/llc/work-items/{_ITEM}/transition", json={"status": "done"})


async def _board_done(factory, user: dict) -> httpx.Response:  # noqa: ANN001
    async with _client(factory, user) as client:
        body = {"work_item_id": str(_ITEM), "column_id": str(_DONE_COLUMN)}
        return await client.post(f"/api/llc/boards/{_BOARD}/move", json=body)


# --- the agent API --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reviewer", "expected"),
    [(_REVIEWER, _REVIEWER), (None, _CREATOR)],
    ids=["the-items-reviewer", "the-creator-when-no-reviewer"],
)
async def test_a_gated_finish_by_the_holder_goes_to_review(factory, effects, reviewer, expected):  # noqa: ANN001
    await _seed(factory, reviewer=reviewer, creator=_CREATOR)

    answer = await _agent_asks_for_done()

    row = await _row(factory)
    assert answer["status"] == "in_review"
    assert (row.status, row.reviewer_user_id, row.assignee_user_id) == (WorkItemStatus.IN_REVIEW, expected, expected)
    assert (row.assignee_agent_id, row.checkout_run_id, row.checkout_locked_at, row.completed_at) == (None,) * 4
    assert effects.fence.await_args.args[1:] == (f"llc:checkout:{_ITEM}", str(_NODE))
    assert await _completed_rows(factory) == []


async def test_a_gated_finish_with_no_reviewer_is_refused(factory, effects) -> None:  # noqa: ANN001
    await _seed(factory)

    with pytest.raises(HTTPException) as refused:
        await _agent_asks_for_done()

    row = await _row(factory)
    assert (refused.value.status_code, "reviewer is required" in refused.value.detail) == (409, True)
    assert (row.status, row.assignee_agent_id, row.checkout_run_id) == (WorkItemStatus.IN_PROGRESS, _NODE, "run-1")
    effects.fence.assert_not_awaited()


async def test_a_gated_finish_by_a_non_holder_is_refused(factory, effects) -> None:  # noqa: ANN001
    await _seed(factory, agent=_OTHER_NODE, reviewer=_REVIEWER)

    with pytest.raises(HTTPException) as refused:
        await _agent_asks_for_done()

    row = await _row(factory)
    assert (refused.value.status_code, "does not hold checkout" in refused.value.detail) == (409, True)
    assert (row.status, row.assignee_agent_id) == (WorkItemStatus.IN_PROGRESS, _OTHER_NODE)
    effects.fence.assert_not_awaited()


async def test_a_gated_finish_by_an_agent_with_no_node_is_refused(factory) -> None:  # noqa: ANN001
    await _seed(factory, reviewer=_REVIEWER)

    with pytest.raises(HTTPException) as refused:
        await _agent_asks_for_done(node=None)

    assert (refused.value.status_code, "has no org node" in refused.value.detail) == (409, True)
    assert (await _row(factory)).status == WorkItemStatus.IN_PROGRESS


async def test_a_gated_finish_whose_creator_left_the_company_is_refused(factory, effects) -> None:  # noqa: ANN001
    await _seed(factory, creator=_CREATOR, members=())

    with pytest.raises(HTTPException) as refused:
        await _agent_asks_for_done()

    row = await _row(factory)
    assert (refused.value.status_code, "not a member" in refused.value.detail) == (409, True)
    assert (row.status, row.assignee_agent_id, row.checkout_run_id) == (WorkItemStatus.IN_PROGRESS, _NODE, "run-1")
    effects.fence.assert_not_awaited()


async def test_an_ungated_finish_by_an_agent_is_done_and_audited(factory, effects) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.TASK)

    answer = await _agent_asks_for_done()

    row = await _row(factory)
    assert answer == {"updated": True, "item_id": str(_ITEM), "status": "done", "comment_id": None}
    assert (row.status, row.checkout_run_id, row.checkout_locked_at) == (WorkItemStatus.DONE, None, None)
    assert row.completed_at is not None
    audit = await _completed_rows(factory)
    assert [(r.actor_type, r.actor_agent_id) for r in audit] == [("agent", _NODE)]
    effects.fence.assert_not_awaited()


# --- the REST transition --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("user", "type_", "code", "status", "audit_rows"),
    [
        (_SERVICE, WorkItemType.BUG, 409, WorkItemStatus.IN_PROGRESS, 0),
        (_SERVICE, WorkItemType.TASK, 200, WorkItemStatus.DONE, 1),
        (_PERSON, WorkItemType.BUG, 200, WorkItemStatus.DONE, 1),
        (_AUTH_OFF, WorkItemType.BUG, 200, WorkItemStatus.DONE, 1),
        (_TOKEN, WorkItemType.BUG, 409, WorkItemStatus.IN_PROGRESS, 0),
    ],
    ids=["service-on-a-gated-type", "service-ungated-type", "person-gated", "auth-disabled-user-gated", "token-gated"],
)
async def test_the_rest_transition_to_done(factory, user, type_, code, status, audit_rows) -> None:  # noqa: ANN001
    await _seed(factory, type_=type_, agent=None)

    response = await _rest_done(factory, user)

    assert response.status_code == code, response.text
    if code == 409:
        assert "requires human review" in response.json()["detail"]
    assert (await _row(factory)).status == status
    assert len(await _completed_rows(factory)) == audit_rows


async def test_a_person_cannot_finish_a_task_waiting_on_another_reviewer(factory) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.TASK, status=WorkItemStatus.IN_REVIEW, agent=None, reviewer=_REVIEWER)

    response = await _rest_done(factory, _PERSON)

    assert response.status_code == 409 and "waiting on its reviewer" in response.json()["detail"]
    assert (await _row(factory)).status == WorkItemStatus.IN_REVIEW
    assert await _completed_rows(factory) == []


@pytest.mark.parametrize(
    ("creator", "code", "status"),
    [(_HUMAN, 200, WorkItemStatus.DONE), (_CREATOR, 409, WorkItemStatus.BACKLOG)],
    ids=["own-task-is-free", "someone-elses-task-keeps-the-rules"],
)
async def test_a_person_finishes_their_own_task_from_any_status(factory, creator, code, status) -> None:  # noqa: ANN001
    await _seed(factory, status=WorkItemStatus.BACKLOG, agent=None, creator=creator)

    response = await _rest_done(factory, _PERSON)

    assert response.status_code == code, response.text
    assert (await _row(factory)).status == status


# --- the board move ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("user", "type_", "code", "status", "audit_rows"),
    [
        (_SERVICE, WorkItemType.BUG, 409, WorkItemStatus.IN_PROGRESS, 0),
        (_SERVICE, WorkItemType.TASK, 200, WorkItemStatus.DONE, 1),
        (_PERSON, WorkItemType.BUG, 200, WorkItemStatus.DONE, 1),
        (_AUTH_OFF, WorkItemType.BUG, 200, WorkItemStatus.DONE, 1),
        (_TOKEN, WorkItemType.BUG, 409, WorkItemStatus.IN_PROGRESS, 0),
    ],
    ids=["service-on-a-gated-type", "service-ungated-type", "person-gated", "auth-disabled-user-gated", "token-gated"],
)
async def test_a_board_move_into_done(factory, user, type_, code, status, audit_rows) -> None:  # noqa: ANN001
    await _seed(factory, type_=type_, agent=None)

    response = await _board_done(factory, user)

    assert response.status_code == code, response.text
    if code == 409:
        assert "requires human review" in response.json()["detail"]
    assert (await _row(factory)).status == status
    assert len(await _completed_rows(factory)) == audit_rows


# --- the service: no route can leave the gate out ---------------------------------------------------------------


async def test_a_move_to_done_that_brings_no_gate_is_still_gated(factory) -> None:  # noqa: ANN001
    await _seed(factory, agent=None)
    async with factory() as session:
        with pytest.raises(InvalidTransition, match="requires human review"):
            await WorkItemService().transition_status(session, str(_ITEM), WorkItemStatus.DONE)
    assert (await _row(factory)).status == WorkItemStatus.IN_PROGRESS


async def test_a_move_to_done_that_brings_no_gate_asks_the_real_one(factory) -> None:  # noqa: ANN001
    """The contrast: an ungated type goes through, so the default is the real gate and not a blanket refusal."""
    await _seed(factory, type_=WorkItemType.TASK, agent=None)
    async with factory() as session:
        await WorkItemService().transition_status(session, str(_ITEM), WorkItemStatus.DONE)
        await session.commit()
    assert (await _row(factory)).status == WorkItemStatus.DONE


async def test_a_finish_with_no_gate_service_is_refused_for_anyone_who_is_not_a_person(factory) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.TASK)
    async with factory() as session:
        with pytest.raises(InvalidTransition, match="no review gate"):
            await WorkItemService().transition_to_done(session, str(_ITEM), actor_agent_id=str(_NODE))
    assert (await _row(factory)).status == WorkItemStatus.IN_PROGRESS


async def test_a_cancel_still_releases_the_task_workspace(factory, effects) -> None:  # noqa: ANN001
    await _seed(factory, agent=None)
    async with factory() as session:
        await WorkItemService().transition_status(session, str(_ITEM), WorkItemStatus.CANCELLED)
        await session.commit()
    assert (await _row(factory)).status == WorkItemStatus.CANCELLED
    assert effects.release.await_args.args[0] == str(_ITEM)


async def test_a_board_move_by_a_credential_with_no_user_id_is_still_a_401(factory) -> None:  # noqa: ANN001
    """Only the auth-disabled stand-in may move a card without a user id; any other such credential is refused."""
    await _seed(factory, type_=WorkItemType.TASK, agent=None)

    response = await _board_done(factory, {"id": "not-a-uuid", "auth_method": "jwt"})

    assert response.status_code == 401, response.text
    assert (await _row(factory)).status == WorkItemStatus.IN_PROGRESS
