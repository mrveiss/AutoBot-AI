# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A merged pull request hands its work item to a named reviewer, or leaves it where it is (#21591).

The webhook is driven through the REAL router, handoff and database (in-memory SQLite). Only the outward
effects are faked: Redis, the handoff's notification, brief and audit row.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import re
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.api.github_webhooks import router as webhook_router
from llc.deps import get_session
from llc.models.enums import MembershipRole, WorkItemPriority, WorkItemStatus, WorkItemType
from llc.models.membership import LLCCompanyMembership
from llc.models.work_item import LLCWorkItem, LLCWorkItemComment
from llc.services import after_commit
from llc.services.handoff import HandoffNotAllowed, HandoffService
from llc.tests import _e2e_harness as harness

pytestmark = pytest.mark.asyncio

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_SIGNER = "hook-signer-21591"
_COMPANY = uuid.UUID("1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d")
_ITEM = uuid.UUID("2b3c4d5e-6f7a-4b8c-9d0e-1f2a3b4c5d6e")
_AGENT = uuid.UUID("3c4d5e6f-7a8b-4c9d-8e1f-2a3b4c5d6e7f")
_REVIEWER = uuid.UUID("4d5e6f7a-8b9c-4d0e-9f2a-3b4c5d6e7f80")
_CREATOR = uuid.UUID("5e6f7a8b-9c0d-4e1f-8a3b-4c5d6e7f8091")
_STRANGER = uuid.UUID("6f7a8b9c-0d1e-4f2a-9b4c-5d6e7f8091a2")
_NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)
_PR_URL = "https://github.com/mrveiss/AutoBot-AI/pull/321"


@pytest_asyncio.fixture
async def factory():  # noqa: ANN201
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine (test-local)
    await harness.create_loop_schema(engine)
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        engine, expire_on_commit=False, autoflush=False, class_=AsyncSession  # as the production session is built
    )
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def effects(monkeypatch):  # noqa: ANN001, ANN201
    """Fake only what leaves the process; the router, the handoff and the database are real."""
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", _SIGNER)
    with (
        patch("llc.services.handoff.get_async_redis_client", new=AsyncMock(return_value=MagicMock())),
        patch("llc.services.handoff.release_agent_fence", new=AsyncMock()),
        patch.object(HandoffService, "_record_a2h_activity", new=AsyncMock()),
        patch.object(HandoffService, "_publish_a2h_notification", new=AsyncMock()),
        patch.object(HandoffService, "_generate_and_update_brief_async", new=AsyncMock()),
        patch.object(HandoffService, "_generate_brief", new=MagicMock(return_value={})),
    ):
        yield SimpleNamespace()
        await asyncio.gather(*after_commit.after_commit_tasks)


async def _seed(  # noqa: ANN202
    factory,  # noqa: ANN001
    *,
    status: WorkItemStatus = WorkItemStatus.IN_PROGRESS,
    agent: uuid.UUID | None = _AGENT,
    reviewer: uuid.UUID | None = None,
    creator: uuid.UUID | None = None,
    members: tuple[uuid.UUID, ...] = (_REVIEWER, _CREATOR),
    linked: bool = True,
) -> None:
    async with factory() as session:
        session.add(
            LLCWorkItem(
                id=_ITEM,
                company_id=_COMPANY,
                type=WorkItemType.BUG,
                identifier="T-21591",
                title="a work item",
                status=status,
                priority=WorkItemPriority.MEDIUM,
                labels=[],
                linked_pr_urls=[_PR_URL] if linked else [],
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
        for user in members:
            session.add(LLCCompanyMembership(company_id=_COMPANY, user_id=user, role=MembershipRole.MEMBER))
        await session.commit()


async def _merge(factory) -> httpx.Response:  # noqa: ANN001
    payload = {
        "action": "closed",
        "pull_request": {
            "html_url": _PR_URL,
            "number": 321,
            "merged": True,
            "head": {"ref": f"llc/{_ITEM}"},
            "body": "",
        },
        "repository": {"full_name": "mrveiss/AutoBot-AI"},
    }
    body = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(_SIGNER.encode(), body, hashlib.sha256).hexdigest()
    app = FastAPI()
    app.include_router(webhook_router)

    async def _session():  # noqa: ANN202
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/webhooks/github",
            content=body,
            headers={"X-GitHub-Event": "pull_request", "X-Hub-Signature-256": signature},
        )


async def _state(factory) -> tuple[LLCWorkItem, list[str]]:  # noqa: ANN001
    async with factory() as session:
        item = (await session.execute(select(LLCWorkItem).where(LLCWorkItem.id == _ITEM))).scalar_one()
        rows = await session.execute(select(LLCWorkItemComment.body).where(LLCWorkItemComment.work_item_id == _ITEM))
        return item, list(rows.scalars())


@pytest.mark.parametrize(
    ("reviewer", "creator", "expected"),
    [(_REVIEWER, None, _REVIEWER), (None, _CREATOR, _CREATOR)],
    ids=["the-items-reviewer", "the-creator-when-no-reviewer"],
)
async def test_a_merge_hands_a_held_item_to_a_named_reviewer(
    factory, reviewer, creator, expected
) -> None:  # noqa: ANN001
    await _seed(factory, reviewer=reviewer, creator=creator)
    assert (await _merge(factory)).json()["status"] == "processed"
    item, comments = await _state(factory)
    assert (item.status, item.reviewer_user_id) == (WorkItemStatus.IN_REVIEW, expected)
    assert (item.assignee_agent_id, item.assignee_user_id, item.checkout_run_id) == (None, expected, None)
    assert any("handed to its reviewer" in c for c in comments)


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({}, "no reviewer and no creator"),
        ({"reviewer": _STRANGER}, "not a member of the company"),
        ({"agent": None, "reviewer": _REVIEWER}, "no agent holds it"),
        ({"status": WorkItemStatus.BACKLOG, "reviewer": _REVIEWER}, "review cannot start from backlog"),
        ({"status": WorkItemStatus.IN_REVIEW, "reviewer": _REVIEWER}, "review cannot start from in_review"),
    ],
    ids=["no-reviewer", "reviewer-not-a-member", "no-holding-agent", "from-backlog", "already-in-review"],
)
async def test_a_merge_that_cannot_name_a_reviewer_leaves_the_item_with_a_comment(  # noqa: ANN001
    factory, kwargs, reason
) -> None:
    await _seed(factory, **kwargs)
    before = kwargs.get("status", WorkItemStatus.IN_PROGRESS)
    assert (await _merge(factory)).json()["status"] == "processed"
    item, comments = await _state(factory)
    assert item.status == before
    assert (item.assignee_agent_id is None) == (kwargs.get("agent", _AGENT) is None)
    assert item.reviewer_user_id == kwargs.get("reviewer")
    assert any("merged; the item stays" in c and reason in c for c in comments)


@pytest.mark.parametrize(
    ("kwargs", "status"),
    [({"reviewer": _REVIEWER}, WorkItemStatus.IN_REVIEW), ({}, WorkItemStatus.IN_PROGRESS)],
    ids=["handed-off", "left-with-a-reason"],
)
async def test_a_first_sighting_merge_keeps_the_pr_link_on_a_session_that_does_not_autoflush(  # noqa: ANN001
    factory, kwargs, status
) -> None:
    await _seed(factory, linked=False, **kwargs)
    assert (await _merge(factory)).json()["status"] == "processed"
    item, comments = await _state(factory)
    assert (item.status, item.linked_pr_urls) == (status, [_PR_URL])
    assert any("linked" in c for c in comments)


async def test_a_repeated_delivery_hands_off_once_and_names_no_ids(factory) -> None:  # noqa: ANN001
    await _seed(factory, reviewer=_REVIEWER)
    handoffs: list[str] = []
    original = HandoffService.agent_to_human

    async def spy(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003, ANN202
        handoffs.append("called")
        return await original(self, *args, **kwargs)

    with patch.object(HandoffService, "agent_to_human", new=spy):
        await _merge(factory)
        await _merge(factory)
    item, comments = await _state(factory)
    assert (len(handoffs), item.status) == (1, WorkItemStatus.IN_REVIEW)
    reasons = [c for c in comments if "merged; the item stays in_review" in c]
    assert len(reasons) == 1
    assert not _UUID.search(reasons[0])


async def test_a_delivery_whose_holder_changed_is_left_with_a_comment_naming_no_agent(factory) -> None:  # noqa: ANN001
    await _seed(factory, reviewer=_REVIEWER)
    refusal = HandoffNotAllowed(f"Agent {_AGENT} does not hold checkout for work item {_ITEM}")
    with patch.object(HandoffService, "agent_to_human", new=AsyncMock(side_effect=refusal)):
        assert (await _merge(factory)).json()["status"] == "processed"
    item, comments = await _state(factory)
    assert item.status == WorkItemStatus.IN_PROGRESS
    reasons = [c for c in comments if "merged; the item stays" in c]
    assert [r for r in reasons if "the agent that held it no longer does" in r]
    assert not any(_UUID.search(r) for r in reasons)
