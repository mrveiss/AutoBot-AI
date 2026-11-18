# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A release may name the checkout generation it ends; a stale one is refused (#21499).

``run_id`` on the release request is optional. Sent, it must equal ``checkout_run_id`` on the row read under the
lock, else 409 and the row and fence stay. Omitted, the release goes by the generation read under the lock.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llc.api import work_items as work_items_api
from llc.api._release_request import ReleaseRequest
from llc.services import work_item_own_task as own_task
from llc.services import work_item_service as wis

_AGENT = "b3c1e7a2-9d4f-4c68-a1f5-2e8d6b0c7a43"
_OTHER_AGENT = "7e0a94c3-52b1-4d6f-93a8-c4f1d2b60e75"
_USER = "5799065e-4061-4af8-bee7-64e65f1a2b91"
_ORG = uuid.UUID("0f1d7a52-3c88-4b6e-9a0d-61c2b7e4f905")
_ITEM_ID = uuid.UUID("9c2e4b1a-7d35-4f08-8e6a-3b1d5c7a9e02")


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _held_at(run_id: str) -> MagicMock:
    return MagicMock(
        id=_ITEM_ID, company_id=_ORG, assignee_agent_id=uuid.UUID(_AGENT), assignee_user_id=None,
        checkout_run_id=run_id, version=1,
    )  # fmt: skip


def _session(item) -> MagicMock:
    session = MagicMock(flush=AsyncMock(), commit=AsyncMock())
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=item)))
    return session


async def _release(item, run_id, deferred: list):
    service = wis.WorkItemService(activity_log=MagicMock(record=AsyncMock()))
    with patch.object(own_task, "defer_until_commit", new=lambda _s, cb, _d, **_k: deferred.append(cb)):
        return await service.release(_session(item), str(_ITEM_ID), _AGENT, run_id=run_id)


async def test_a_release_naming_an_earlier_generation_is_refused_and_leaves_the_row_and_fence():
    """Before: ``release`` took no ``run_id`` (TypeError); a replayed release cleared the later checkout."""
    item, deferred = _held_at("run-2"), []
    with pytest.raises(wis.CheckoutConflict, match="not released"):
        await _release(item, "run-1", deferred)
    assert item.checkout_run_id == "run-2"
    assert item.version == 1
    assert deferred == []


@pytest.mark.parametrize("run_id", ["run-1", None])
async def test_a_release_naming_the_current_generation_or_none_clears_the_checkout_and_queues_the_fence(run_id):
    item, deferred = _held_at("run-1"), []
    released = await _release(item, run_id, deferred)
    assert released.checkout_run_id is None
    assert len(deferred) == 1


async def test_the_fence_dropped_is_the_generation_the_row_held_not_the_one_the_request_named(redis):
    item, deferred = _held_at("run-1"), []
    await redis.set(f"llc:checkout:{_ITEM_ID}", f"{_AGENT}#run-1")
    await _release(item, None, deferred)
    with patch.object(own_task, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        await deferred[0]()
    assert await redis.get(f"llc:checkout:{_ITEM_ID}") is None


@pytest.mark.parametrize(
    ("agent_id", "fence", "kept"),
    [
        (None, f"{_OTHER_AGENT}#run-1", False),
        (None, f"{_AGENT}#run-2", True),
        (_AGENT, f"{_OTHER_AGENT}#run-1", True),
        (_AGENT, f"{_AGENT}#run-1", False),
        (_AGENT, f"user:{_USER}", True),
    ],
)
async def test_the_one_generation_drop_keeps_a_fence_of_another_generation_or_another_named_agent(
    redis, agent_id, fence, kept
):
    await redis.set("llc:checkout:k", fence)
    await own_task.drop_fence_of_generation(redis, "llc:checkout:k", "run-1", agent_id)
    assert (await redis.get("llc:checkout:k") == fence) is kept


def test_the_request_model_takes_an_optional_run_id():
    assert ReleaseRequest(agent_id=_AGENT).run_id is None
    assert ReleaseRequest(agent_id=_AGENT, run_id="run-1").run_id == "run-1"


def _client(item) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(work_items_api.router)

    async def _override_session():
        yield _session(item)

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: {"id": _USER, "user_id": _USER, "auth_method": "session"}
    app.dependency_overrides[require_org_context] = lambda: SimpleNamespace(org_id=_ORG, user_id=_USER)
    return TestClient(app)


def test_the_release_route_answers_409_to_a_stale_run_id_and_leaves_the_checkout():
    item = _held_at("run-2")
    service = wis.WorkItemService(activity_log=MagicMock(record=AsyncMock()))
    service.get = AsyncMock(return_value=item)
    with patch.object(work_items_api, "_service", return_value=service):
        response = _client(item).post(f"/work-items/{_ITEM_ID}/release", json={"agent_id": _AGENT, "run_id": "run-1"})
    assert response.status_code == 409
    assert item.checkout_run_id == "run-2"
