# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A checkout fence is released only while it still names the releaser, in one atomic step (#19631).

Each test seeds the fence with a NEW holder's value (the fence was re-taken after the old holder's TTL
lapsed), runs the old holder's release path against a real Lua engine, and asserts the new holder's fence
stands; the positive case (the releaser's own value goes) pairs with it. Same pattern as the run-cancel
test of #19607.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from llc.api import work_items as work_items_api
from llc.services import handoff as handoff_module
from llc.services import work_item_own_task as own_task
from llc.services import work_item_service as wis
from llc.services.handoff import HandoffService

_USER = str(uuid.uuid4())
_NEW_USER = str(uuid.uuid4())
_AGENT = str(uuid.uuid4())
_OTHER_AGENT = str(uuid.uuid4())
_ORG = uuid.uuid4()


@pytest.fixture
def redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _key(item_id: str) -> str:
    return f"llc:checkout:{item_id}"


def _unclaim_session(item) -> MagicMock:
    session = MagicMock(flush=AsyncMock(), commit=AsyncMock())
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=item)))
    return session


async def _unclaim(redis, item_id: str) -> None:
    item = MagicMock(assignee_user_id=uuid.UUID(_USER), status=None, started_at=None, version=1)
    service = wis.WorkItemService(activity_log=MagicMock(record=AsyncMock()))
    with patch.object(wis, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        await service.unclaim_human(_unclaim_session(item), item_id, _USER, str(_ORG))


async def test_unclaim_releases_the_claimants_own_fence(redis):
    item_id = str(uuid.uuid4())
    await redis.set(_key(item_id), f"user:{_USER}")
    await _unclaim(redis, item_id)
    assert await redis.get(_key(item_id)) is None


async def test_unclaim_keeps_a_fence_a_new_holder_took_after_the_ttl_lapsed(redis):
    for taken_by in (f"user:{_NEW_USER}", f"{_AGENT}#run-2"):
        item_id = str(uuid.uuid4())
        await redis.set(_key(item_id), taken_by)
        await _unclaim(redis, item_id)
        assert await redis.get(_key(item_id)) == taken_by


async def test_release_agent_fence_drops_the_agents_fence_in_any_generation(redis):
    for value in (f"{_AGENT}#run-1", _AGENT):
        item_id = str(uuid.uuid4())
        await redis.set(_key(item_id), value)
        with patch.object(own_task, "get_async_redis_client", new=AsyncMock(return_value=redis)):
            await own_task.release_agent_fence(item_id, _AGENT)
        assert await redis.get(_key(item_id)) is None


async def test_release_agent_fence_keeps_another_holders_fence(redis):
    lookalike = f"{_AGENT}-2"  # shares the releasing agent's id as a text prefix, not as a holder
    for value in (f"{_OTHER_AGENT}#run-2", f"user:{_USER}", f"{lookalike}#run-1"):
        item_id = str(uuid.uuid4())
        await redis.set(_key(item_id), value)
        with patch.object(own_task, "get_async_redis_client", new=AsyncMock(return_value=redis)):
            await own_task.release_agent_fence(item_id, _AGENT)
        assert await redis.get(_key(item_id)) == value


async def test_release_agent_fence_logs_a_redis_failure_and_does_not_raise(caplog):
    """The release is already committed: a failed fence drop is logged like ``_delete_fence`` and the TTL ends it."""
    redis = MagicMock(eval=AsyncMock(side_effect=ConnectionError("redis down")))
    with patch.object(own_task, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        await own_task.release_agent_fence("wid", _AGENT)  # does not raise
    redis.eval.assert_awaited_once()
    assert "expires on its TTL" in caplog.text


async def test_release_agent_fence_without_redis_is_a_no_op():
    with patch.object(own_task, "get_async_redis_client", new=AsyncMock(return_value=None)):
        await own_task.release_agent_fence(str(uuid.uuid4()), _AGENT)


async def test_the_release_route_drops_the_fence_after_the_commit_with_the_releasing_agent():
    calls: list = []
    service = MagicMock(
        get=AsyncMock(return_value=MagicMock(company_id=_ORG)),
        release=AsyncMock(return_value=MagicMock()),
    )
    session = MagicMock(commit=AsyncMock(side_effect=lambda: calls.append("commit")))

    async def fence(item_id, agent_id):
        calls.append(("fence", item_id, agent_id))

    with (
        patch.object(work_items_api, "_service", return_value=service),
        patch.object(work_items_api, "release_agent_fence", new=fence),
        patch.object(work_items_api, "_item_to_dict", new=AsyncMock(return_value={})),
    ):
        await work_items_api.release_work_item(
            "wid", work_items_api.ReleaseRequest(agent_id=_AGENT), session, {}, SimpleNamespace(org_id=_ORG)
        )
    assert calls == ["commit", ("fence", "wid", _AGENT)]


def test_a_release_request_refuses_an_agent_id_carrying_the_generation_separator():
    """``a#b`` would otherwise name the holder ``a`` in generation ``b`` and release that fence."""
    with pytest.raises(ValidationError):
        work_items_api.ReleaseRequest(agent_id="agent#run")


_SPELLINGS = (_AGENT.upper(), _AGENT.replace("-", ""), f"urn:uuid:{_AGENT}")


@pytest.mark.parametrize("spelling", _SPELLINGS)
async def test_a_non_canonical_agent_id_reaches_the_fence_canonical_and_the_release_matches(redis, spelling):
    """Checkout and release both name the agent by request; each spelling must end as the stored assignee's form."""
    checkout = work_items_api.CheckoutRequest(agent_id=spelling, run_id="run-1")
    release = work_items_api.ReleaseRequest(agent_id=spelling)
    assert checkout.agent_id == release.agent_id == _AGENT
    item_id = str(uuid.uuid4())
    await redis.set(_key(item_id), own_task.checkout_fence_value(checkout.agent_id, checkout.run_id))
    with patch.object(own_task, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        await own_task.release_agent_fence(item_id, release.agent_id)
    assert await redis.get(_key(item_id)) is None


@pytest.mark.parametrize("value", ["", f"user:{_USER}", "agent-1", "not-a-uuid"])
def test_a_request_refuses_an_agent_id_that_is_not_an_agent_uuid(value):
    for model in (work_items_api.CheckoutRequest, work_items_api.ReleaseRequest):
        with pytest.raises(ValidationError):
            model(agent_id=value)


async def _agent_to_human(redis, item_id: str) -> None:
    item = MagicMock(assignee_agent_id=uuid.UUID(_AGENT), project_id=None, title="t", description="d", version=1)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=item)))
    service = HandoffService()
    service._generate_brief = MagicMock(return_value={})
    service._record_a2h_activity = AsyncMock()
    service._publish_a2h_notification = AsyncMock()
    service._generate_and_update_brief_async = AsyncMock()
    with patch.object(handoff_module, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        await service.agent_to_human(session, item_id, _AGENT, str(uuid.uuid4()), str(_ORG))
    await asyncio.gather(*service._background_tasks)


async def test_agent_to_human_drops_the_handing_off_agents_fence(redis):
    item_id = str(uuid.uuid4())
    await redis.set(_key(item_id), f"{_AGENT}#run-1")
    await _agent_to_human(redis, item_id)
    assert await redis.get(_key(item_id)) is None


async def test_agent_to_human_keeps_a_fence_another_holder_took(redis):
    item_id = str(uuid.uuid4())
    await redis.set(_key(item_id), f"{_OTHER_AGENT}#run-2")
    await _agent_to_human(redis, item_id)
    assert await redis.get(_key(item_id)) == f"{_OTHER_AGENT}#run-2"


async def _release_human_fence(redis, item_id: str) -> None:
    with patch.object(handoff_module, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        await HandoffService()._release_redis_key(item_id, _USER)


async def test_human_to_agent_drops_the_humans_fence_in_both_accepted_forms(redis):
    for value in (f"user:{_USER}", _USER):
        item_id = str(uuid.uuid4())
        await redis.set(_key(item_id), value)
        await _release_human_fence(redis, item_id)
        assert await redis.get(_key(item_id)) is None


async def test_human_to_agent_keeps_a_fence_another_holder_took(redis):
    for value in (f"user:{_NEW_USER}", _NEW_USER, f"{_AGENT}#run-2"):
        item_id = str(uuid.uuid4())
        await redis.set(_key(item_id), value)
        await _release_human_fence(redis, item_id)
        assert await redis.get(_key(item_id)) == value


async def test_human_to_agent_release_does_not_read_then_delete_from_the_client():
    """The old release was GET, compare, DEL from the client: a fence re-taken in the gap was deleted."""
    redis = MagicMock(get=AsyncMock(), delete=AsyncMock(), eval=AsyncMock(return_value=1))
    await _release_human_fence(redis, str(uuid.uuid4()))
    redis.get.assert_not_awaited()
    redis.delete.assert_not_awaited()
    redis.eval.assert_awaited_once()


def _client() -> TestClient:
    """The smallest app that reaches the request models: the work-item router, with identity and session stubbed."""
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(work_items_api.router)

    async def _session():
        yield AsyncMock()

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_current_user] = lambda: {"id": _USER, "user_id": _USER, "auth_method": "session"}
    app.dependency_overrides[require_org_context] = lambda: SimpleNamespace(org_id=_ORG, user_id=_USER)
    return TestClient(app)


@pytest.mark.parametrize("route", ["checkout", "release"])
def test_the_route_answers_422_to_an_agent_id_that_is_not_an_agent_uuid(route):
    response = _client().post(f"/work-items/{uuid.uuid4()}/{route}", json={"agent_id": "agent-1"})
    assert response.status_code == 422
