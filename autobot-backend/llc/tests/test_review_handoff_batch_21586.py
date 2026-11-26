# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent status route, the handoff's side effects and the review approval (#21586, #21587, #21589, #21590).

Real services and a real in-memory database; only what leaves the process is faked (Redis, the artifact ingest,
the worktree removal, the brief generator).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api import work_items as work_items_api
from llc.deps import get_session
from llc.models.activity import LLCActivityLog
from llc.models.enums import MembershipRole, WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.membership import LLCCompanyMembership
from llc.models.review_gate import LLCReviewGatePolicy
from llc.models.work_item import LLCWorkItem
from llc.services import after_commit
from llc.services.activity_log import LLCActivityLogService
from llc.services.handoff import HandoffService
from llc.services.work_item_own_task import InvalidTransition, release_agent_fence
from llc.services.work_item_service import WorkItemService
from llc.tests import _e2e_harness as harness
from user_management.services import TenantContext

pytestmark = pytest.mark.asyncio

_COMPANY = uuid.UUID("1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d")
_ITEM = uuid.UUID("2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e")
_MISSING = uuid.UUID("3c4d5e6f-7a8b-4c9d-8e1f-2a3b4c5d6e7f")
_NODE = uuid.UUID("4d5e6f7a-8b9c-4d0e-9f2a-3b4c5d6e7f80")
_OTHER_NODE = uuid.UUID("5e6f7a8b-9c0d-4e1f-8a3b-4c5d6e7f8091")
_REVIEWER = uuid.UUID("6f7a8b9c-0d1e-4f2a-9b4c-5d6e7f8091a2")
_STRANGER = uuid.UUID("7a8b9c0d-1e2f-4a3b-8c5d-6e7f8091a2b3")
_SLUG = "agent-21586"
_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
_FENCE = f"llc:checkout:{_ITEM}"
#: The real scheduler, kept before the fixture swaps it for a spy (the after-commit indexing tests need it).
_REAL_INGEST = WorkItemService._trigger_artifact_ingest


@pytest_asyncio.fixture
async def factory():  # noqa: ANN201
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    await harness.create_loop_schema(engine)
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def effects(factory):  # noqa: ANN001, ANN201
    """Fake only what leaves the process; the services, the routers and the database are real."""
    published = AsyncMock()
    with (
        patch("user_management.database.get_async_session_factory", return_value=factory),
        patch("llc.services.work_item_own_task.get_async_redis_client", new=AsyncMock(return_value=None)),
        patch(
            "llc.services.commit_publish.get_async_redis_client",
            new=AsyncMock(return_value=MagicMock(publish=published)),
        ),
        patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=MagicMock())),
        patch("llc.services.handoff.release_agent_fence", new=AsyncMock()) as fence,
        patch("llc.services.handoff.delete_if_value", new=AsyncMock(return_value=True)) as human_fence,
        patch("llc.services.handoff.wake_for_item_changes", new=AsyncMock()),
        patch.object(HandoffService, "_record_a2h_activity", new=AsyncMock()),
        patch.object(HandoffService, "_record_h2a_activity", new=AsyncMock()),
        patch.object(HandoffService, "_ingest_kb", new=AsyncMock(return_value=[])),
        patch.object(HandoffService, "_generate_and_update_brief_async", new=AsyncMock()) as a2h_brief,
        patch.object(HandoffService, "_generate_and_update_h2a_brief_async", new=AsyncMock()) as h2a_brief,
        patch.object(HandoffService, "_generate_brief", new=MagicMock(return_value={"title": "t"})),
        patch.object(WorkItemService, "_trigger_artifact_ingest", new=AsyncMock()) as ingest,
        patch("llc.services.work_item_service.release_workspace_for_task", new=AsyncMock()) as release,
        patch.object(LLCActivityLogService, "_publish_after_commit", new=AsyncMock()),
    ):
        yield SimpleNamespace(
            fence=fence, human_fence=human_fence, a2h_brief=a2h_brief, h2a_brief=h2a_brief,
            ingest=ingest, release=release, published=published,
        )  # fmt: skip
        await asyncio.gather(*after_commit.after_commit_tasks)


async def _seed(  # noqa: ANN202
    factory,  # noqa: ANN001
    *,
    type_: WorkItemType = WorkItemType.TASK,
    status: WorkItemStatus = WorkItemStatus.IN_PROGRESS,
    agent: uuid.UUID | None = _NODE,
    user: uuid.UUID | None = None,
    reviewer: uuid.UUID | None = None,
    gated: bool = False,
    checked_out: bool = True,
):
    """One item held by *agent* (with a live checkout) or by person *user*, in *status*."""
    async with factory() as session:
        session.add(
            LLCWorkItem(
                id=_ITEM,
                company_id=_COMPANY,
                type=type_,
                identifier="T-21586",
                title="a work item",
                status=status,
                priority=WorkItemPriority.MEDIUM,
                labels=[],
                linked_pr_urls=[],
                requires_approval_before=[],
                backlog_position=0,
                needs_triage=False,
                assignee_agent_id=agent,
                assignee_user_id=user,
                assignee_type="agent" if agent else ("user" if user else None),
                checkout_run_id="run-1" if agent and checked_out else None,
                checkout_locked_at=_NOW if (agent or user) and checked_out else None,
                reviewer_user_id=reviewer,
            )
        )
        if gated:
            session.add(
                LLCReviewGatePolicy(
                    company_id=_COMPANY,
                    item_type=WorkItemType.BUG,
                    requires_human_review=True,
                    reviewer_role=None,  # the role is enforced now (#21588); these tests are not about it
                    requires_cross_vendor_review=False,
                )
            )
        for member in (_REVIEWER, _STRANGER):
            session.add(LLCCompanyMembership(company_id=_COMPANY, user_id=member, role=MembershipRole.MEMBER))
        await session.commit()


async def _row(factory) -> LLCWorkItem:  # noqa: ANN001
    async with factory() as session:
        return (await session.execute(select(LLCWorkItem).where(LLCWorkItem.id == _ITEM))).scalar_one()


async def _snapshot(factory) -> tuple:  # noqa: ANN001
    row = await _row(factory)
    return row.status, row.assignee_agent_id, row.assignee_user_id, row.reviewer_user_id, row.version


async def _actions(factory) -> list[str]:  # noqa: ANN001
    async with factory() as session:
        rows = await session.execute(select(LLCActivityLog.action).where(LLCActivityLog.entity_id == _ITEM))
        return sorted(rows.scalars())


async def _settle() -> None:
    """Let the effects the commit queued run."""
    await asyncio.sleep(0)
    await asyncio.gather(*after_commit.after_commit_tasks)


# --- #21586: the agent status route -----------------------------------------------------------------------------


async def _agent_sets(item_id: uuid.UUID, status: str, node: uuid.UUID | None = _NODE) -> dict:
    from llc.api.agent_api import StatusUpdate, update_work_item_status

    with (
        patch("llc.api.agent_api.agent_context", return_value=(_SLUG, str(_COMPANY))),
        patch("llc.api.agent_api.agent_node_uuid", new=AsyncMock(return_value=node)),
    ):
        request: Any = object()  # agent_context is patched; the request is unused
        return await update_work_item_status(str(item_id), StatusUpdate(status=status), request)


async def test_an_agent_moves_an_item_it_holds(factory) -> None:  # noqa: ANN001
    await _seed(factory)

    answer = await _agent_sets(_ITEM, "blocked")

    assert (answer["updated"], answer["status"]) == (True, "blocked")
    assert (await _row(factory)).status == WorkItemStatus.BLOCKED


@pytest.mark.parametrize(
    ("kwargs", "node"),
    [
        ({"agent": _OTHER_NODE}, _NODE),
        ({"agent": None}, _NODE),
        ({"agent": None, "user": _REVIEWER}, _NODE),
        ({}, None),
    ],
    ids=["held-by-another-agent", "held-by-no-one", "held-by-a-person", "agent-with-no-node"],
)
async def test_an_agent_cannot_move_an_item_it_does_not_hold(factory, kwargs, node) -> None:  # noqa: ANN001
    await _seed(factory, **kwargs)
    before = await _row(factory)

    with pytest.raises(HTTPException) as refused:
        await _agent_sets(_ITEM, "blocked", node)
    with pytest.raises(HTTPException) as missing:
        await _agent_sets(_MISSING, "blocked", node)

    # the refusal is the answer for a missing item, with the id the caller asked for the only difference
    assert (refused.value.status_code, missing.value.status_code) == (404, 404)
    assert refused.value.detail.replace(str(_ITEM), "<id>") == missing.value.detail.replace(str(_MISSING), "<id>")
    assert (await _row(factory)).status == before.status


@pytest.mark.parametrize("target", ["done", "in_progress", "cancelled"])
async def test_an_agent_cannot_move_an_item_out_of_review_past_its_reviewer(factory, target) -> None:  # noqa: ANN001
    await _seed(factory, status=WorkItemStatus.IN_REVIEW, reviewer=_REVIEWER)

    with pytest.raises(HTTPException) as refused:
        await _agent_sets(_ITEM, target)

    assert refused.value.status_code == 409 and "waiting on its reviewer" in refused.value.detail
    assert (await _row(factory)).status == WorkItemStatus.IN_REVIEW
    assert await _actions(factory) == []


async def test_an_agent_that_handed_an_item_to_review_no_longer_moves_it(factory) -> None:  # noqa: ANN001
    await _seed(factory, type_=WorkItemType.BUG, reviewer=_REVIEWER, gated=True)
    assert (await _agent_sets(_ITEM, "done"))["status"] == "in_review"

    with pytest.raises(HTTPException) as refused:
        await _agent_sets(_ITEM, "done")

    assert refused.value.status_code == 404
    assert (await _row(factory)).status == WorkItemStatus.IN_REVIEW


# --- #21589: a handoff's side effects follow the commit --------------------------------------------------------


def _fail_next_commit(session: AsyncSession) -> None:
    def _boom(_session: Any) -> None:
        raise RuntimeError("the commit failed")

    event.listen(session.sync_session, "before_commit", _boom, once=True)


async def _a2h(session: AsyncSession) -> HandoffService:
    service = HandoffService()
    await service.agent_to_human(session, str(_ITEM), str(_NODE), str(_REVIEWER), str(_COMPANY))
    return service


async def _h2a(session: AsyncSession) -> HandoffService:
    service = HandoffService()
    await service.human_to_agent(
        session,
        work_item_id=str(_ITEM),
        target_agent_id=str(_NODE),
        user_id=str(_REVIEWER),
        company_id=str(_COMPANY),
        human_notes="please continue",
    )
    return service


def _effects_ran(effects, direction: str) -> dict[str, int]:  # noqa: ANN001
    a2h = direction == "a2h"
    fence, brief = (effects.fence, effects.a2h_brief) if a2h else (effects.human_fence, effects.h2a_brief)
    return {"fence": fence.await_count, "brief": brief.await_count, "notified": effects.published.await_count}


_DIRECTIONS = [("a2h", _a2h, {"user": None}), ("h2a", _h2a, {"agent": None, "user": _REVIEWER})]


@pytest.mark.parametrize(("direction", "handoff", "seed"), _DIRECTIONS, ids=["agent-to-human", "human-to-agent"])
async def test_a_handoff_runs_nothing_before_the_commit_and_everything_after(  # noqa: ANN001
    factory, effects, direction, handoff, seed
) -> None:
    await _seed(factory, **seed)
    async with factory() as session:
        service = await handoff(session)
        await _settle()
        assert _effects_ran(effects, direction) == {"fence": 0, "brief": 0, "notified": 0}
        assert not service._background_tasks
        await session.commit()
        await _settle()
        await asyncio.gather(*service._background_tasks)

    assert _effects_ran(effects, direction) == {"fence": 1, "brief": 1, "notified": 1}


@pytest.mark.parametrize(("direction", "handoff", "seed"), _DIRECTIONS, ids=["agent-to-human", "human-to-agent"])
async def test_a_handoff_whose_commit_fails_leaves_the_fence_the_notification_and_the_brief_untouched(  # noqa: ANN001
    factory, effects, direction, handoff, seed
) -> None:
    await _seed(factory, **seed)
    before = await _snapshot(factory)
    async with factory() as session:
        service = await handoff(session)
        _fail_next_commit(session)
        with pytest.raises(RuntimeError, match="the commit failed"):
            await session.commit()
        await session.rollback()
        await _settle()

    assert _effects_ran(effects, direction) == {"fence": 0, "brief": 0, "notified": 0}
    assert not service._background_tasks
    assert await _snapshot(factory) == before  # the handoff itself was rolled back


# --- #21590: approving a review finishes the item through the one done path ---------------------------------------


async def _approve(factory, user: uuid.UUID = _REVIEWER) -> None:  # noqa: ANN001
    async with factory() as session:
        await HandoffService().approve(session, str(_ITEM), str(user), str(_COMPANY))
        await session.commit()
    await _settle()


async def test_an_approved_item_gets_the_side_effects_of_the_done_path(factory, effects) -> None:  # noqa: ANN001
    await _seed(factory, agent=None, user=_REVIEWER, status=WorkItemStatus.IN_REVIEW, reviewer=_REVIEWER)
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await redis.set(_FENCE, f"user:{_REVIEWER}")

    with patch("llc.services.work_item_own_task.get_async_redis_client", new=AsyncMock(return_value=redis)):
        await _approve(factory)

    row = await _row(factory)
    assert (row.status, row.checkout_run_id, row.checkout_locked_at) == (WorkItemStatus.DONE, None, None)
    assert row.completed_at is not None
    assert await redis.get(_FENCE) is None, "the checkout fence outlived the item"
    effects.ingest.assert_awaited_once()
    assert effects.release.await_args.args[0] == str(_ITEM)
    # the completion row the done path writes, beside the approval row
    assert await _actions(factory) == ["work_item.completed", "work_item.review_approved"]


async def test_an_approval_the_transition_rules_refuse_finishes_nothing(factory, effects) -> None:  # noqa: ANN001
    await _seed(factory, agent=None, status=WorkItemStatus.BACKLOG, reviewer=_REVIEWER)

    with pytest.raises(InvalidTransition, match="not in_review"):
        await _approve(factory)

    assert (await _row(factory)).status == WorkItemStatus.BACKLOG
    effects.ingest.assert_not_awaited()
    assert await _actions(factory) == []


# --- #21587: the review and handoff routes answer their true refusal ---------------------------------------------


def _client(factory, user: uuid.UUID) -> httpx.AsyncClient:  # noqa: ANN001
    app = FastAPI()
    app.include_router(work_items_api.router, prefix="/api/llc")

    async def _session():  # noqa: ANN202
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(user), "auth_method": "session"}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_COMPANY, user_id=user, is_platform_admin=False
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


async def _post(factory, user: uuid.UUID, path: str, body: dict | None = None) -> httpx.Response:  # noqa: ANN001
    async with _client(factory, user) as client:
        return await client.post(f"/api/llc/work-items/{_ITEM}/{path}", json=body or {})


@pytest.mark.parametrize(
    ("path", "body"),
    [("review/approve", None), ("review/request-changes", {"change_request": "redo it"})],
    ids=["approve", "request-changes"],
)
async def test_a_review_by_someone_who_is_not_the_reviewer_is_a_403_with_its_reason(  # noqa: ANN001
    factory, path, body
) -> None:
    await _seed(factory, agent=None, user=_REVIEWER, status=WorkItemStatus.IN_REVIEW, reviewer=_REVIEWER)

    response = await _post(factory, _STRANGER, path, body)

    assert response.status_code == 403, response.text
    assert "is not the reviewer" in response.json()["detail"]
    assert "Internal server error" not in response.text


async def test_an_approval_the_item_state_refuses_is_a_409_with_its_reason(factory) -> None:  # noqa: ANN001
    await _seed(factory, agent=None, status=WorkItemStatus.BACKLOG, reviewer=_REVIEWER)

    response = await _post(factory, _REVIEWER, "review/approve")

    assert response.status_code == 409, response.text
    assert "not in_review" in response.json()["detail"]


@pytest.mark.parametrize(
    "path", ["handoff/to-human", "handoff/to-agent", "review/approve", "review/request-changes", "transition"]
)
async def test_a_missing_item_is_a_404_that_does_not_say_internal_server_error(factory, path) -> None:  # noqa: ANN001
    body = {
        "handoff/to-human": {"reviewer_user_id": str(_REVIEWER)},
        "handoff/to-agent": {"target_agent_id": str(_NODE), "human_notes": "n"},
        "review/request-changes": {"change_request": "redo it"},
        "transition": {"status": "done"},
    }.get(path)

    response = await _post(factory, _REVIEWER, path, body)  # no item was seeded

    assert response.status_code == 404, response.text
    assert "Internal server error" not in response.text


# --- #21640 review: the handed-off checkout generation only; indexing after the approval commits -----------------


@pytest.mark.parametrize(
    ("fence", "kept"),
    [(f"{_NODE}#run-1", False), (f"{_NODE}#run-2", True)],
    ids=["the-handed-off-checkout-is-dropped", "the-same-agents-next-checkout-is-kept"],
)
async def test_a_handoff_drops_only_the_checkout_generation_it_handed_off(  # noqa: ANN001
    factory, effects, fence, kept
) -> None:
    await _seed(factory)  # the agent holds checkout run-1
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    await redis.set(_FENCE, fence)
    effects.fence.side_effect = release_agent_fence  # the real release, behind the fixture's spy
    with patch("llc.services.work_item_own_task.get_async_redis_client", new=AsyncMock(return_value=redis)):
        async with factory() as session:
            await _a2h(session)
            await session.commit()
        await _settle()

    assert effects.fence.await_args.args == (str(_ITEM), str(_NODE), "run-1")
    assert await redis.get(_FENCE) == (fence if kept else None)


async def test_an_approval_indexes_artifacts_only_after_its_commit(factory, effects) -> None:  # noqa: ANN001
    await _seed(factory, agent=None, user=_REVIEWER, status=WorkItemStatus.IN_REVIEW, reviewer=_REVIEWER)
    with (
        patch.object(WorkItemService, "_trigger_artifact_ingest", new=_REAL_INGEST),
        patch("llc.services.work_item_service.index_artifacts_after_commit", new=AsyncMock()) as job,
    ):
        async with factory() as session:
            await HandoffService().approve(session, str(_ITEM), str(_REVIEWER), str(_COMPANY))
            await _settle()
            job.assert_not_awaited()  # nothing is indexed while the approval can still roll back
            await session.commit()
        await _settle()

    job.assert_awaited_once()
    assert (job.await_args.kwargs["work_item_id"], job.await_args.kwargs["identifier"]) == (str(_ITEM), "T-21586")


async def test_an_approval_whose_audit_fails_indexes_nothing(factory, effects) -> None:  # noqa: ANN001
    await _seed(factory, agent=None, user=_REVIEWER, status=WorkItemStatus.IN_REVIEW, reviewer=_REVIEWER)
    with (
        patch.object(WorkItemService, "_trigger_artifact_ingest", new=_REAL_INGEST),
        patch("llc.services.work_item_service.index_artifacts_after_commit", new=AsyncMock()) as job,
        patch("llc.services.handoff.audit", new=AsyncMock(side_effect=RuntimeError("audit store down"))),
    ):
        async with factory() as session:
            with pytest.raises(RuntimeError, match="audit store down"):
                await HandoffService().approve(session, str(_ITEM), str(_REVIEWER), str(_COMPANY))
            await session.rollback()
        await _settle()

    job.assert_not_awaited()
    assert (await _row(factory)).status == WorkItemStatus.IN_REVIEW
