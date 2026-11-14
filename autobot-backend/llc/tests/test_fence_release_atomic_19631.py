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
from datetime import datetime, timezone
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

# Constants (not uuid4) because they feed parametrize ids: every xdist worker must collect identical ids.
_USER = "5799065e-4061-4af8-bee7-64e65f1a2b91"
_NEW_USER = str(uuid.uuid4())
_AGENT = "b3c1e7a2-9d4f-4c68-a1f5-2e8d6b0c7a43"
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


async def _drop(redis, item_id: str, agent_id: str, generation) -> None:
    with patch.object(own_task, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        await own_task.release_agent_fence(item_id, agent_id, generation)


async def test_release_agent_fence_drops_the_agents_fence_of_the_released_generation(redis):
    for value, generation in ((f"{_AGENT}#run-1", "run-1"), (_AGENT, None)):
        item_id = str(uuid.uuid4())
        await redis.set(_key(item_id), value)
        await _drop(redis, item_id, _AGENT, generation)
        assert await redis.get(_key(item_id)) is None


async def test_release_agent_fence_keeps_the_same_agents_next_checkout(redis):
    """The release committed, then the same agent checked out again (new generation) before the delete ran."""
    for value, generation in ((f"{_AGENT}#run-2", "run-1"), (f"{_AGENT}#run-2", None), (_AGENT, "run-1")):
        item_id = str(uuid.uuid4())
        await redis.set(_key(item_id), value)
        await _drop(redis, item_id, _AGENT, generation)
        assert await redis.get(_key(item_id)) == value


async def test_release_agent_fence_keeps_another_holders_fence(redis):
    lookalike = f"{_AGENT}-2"  # shares the releasing agent's id as a text prefix, not as a holder
    for value in (f"{_OTHER_AGENT}#run-1", f"user:{_USER}", f"{lookalike}#run-1"):
        item_id = str(uuid.uuid4())
        await redis.set(_key(item_id), value)
        await _drop(redis, item_id, _AGENT, "run-1")
        assert await redis.get(_key(item_id)) == value


async def test_release_agent_fence_matches_a_fence_written_under_a_raw_spelling(redis):
    """A fence written before requests were canonicalised can name the agent in upper case or unhyphenated."""
    for value in (f"{_AGENT.upper()}#run-1", f"{_AGENT.replace('-', '')}#run-1", _AGENT.upper()):
        item_id = str(uuid.uuid4())
        await redis.set(_key(item_id), value)
        await _drop(redis, item_id, _AGENT, None if "#" not in value else "run-1")
        assert await redis.get(_key(item_id)) is None
    item_id = str(uuid.uuid4())
    await redis.set(_key(item_id), f"{_OTHER_AGENT.upper()}#run-1")
    await _drop(redis, item_id, _AGENT, "run-1")
    assert await redis.get(_key(item_id)) == f"{_OTHER_AGENT.upper()}#run-1"


async def test_release_agent_fence_releases_a_fence_a_client_returns_as_bytes():
    """A client without ``decode_responses`` returns the holder as bytes; the release still matches and drops it."""
    raw = fakeredis.aioredis.FakeRedis(decode_responses=False)
    item_id = str(uuid.uuid4())
    await raw.set(_key(item_id), f"{_AGENT}#run-1")
    assert isinstance(await raw.get(_key(item_id)), bytes)
    await _drop(raw, item_id, _AGENT, "run-1")
    assert await raw.get(_key(item_id)) is None


async def test_release_agent_fence_with_an_absent_fence_deletes_nothing_and_does_not_raise(redis):
    item_id = str(uuid.uuid4())
    await _drop(redis, item_id, _AGENT, "run-1")
    assert await redis.get(_key(item_id)) is None


async def test_release_agent_fence_logs_a_redis_failure_and_does_not_raise(caplog):
    """The release is already committed: a failed fence drop is logged like ``_delete_fence`` and the TTL ends it."""
    redis = MagicMock(get=AsyncMock(side_effect=ConnectionError("redis down")))
    await _drop(redis, "wid", _AGENT, "run-1")  # does not raise
    redis.get.assert_awaited_once()
    assert "expires on its TTL" in caplog.text


async def test_release_agent_fence_without_redis_is_a_no_op():
    await _drop(None, str(uuid.uuid4()), _AGENT, "run-1")


async def _release(redis, fence: str):
    """Run ``WorkItemService.release`` on a row at generation run-1; return the fence after commit and the drop."""
    item_id = str(uuid.uuid4())
    item = MagicMock(id=uuid.UUID(item_id), assignee_agent_id=uuid.UUID(_AGENT), checkout_run_id="run-1", version=1)
    await redis.set(_key(item_id), fence)
    deferred: list = []
    service = wis.WorkItemService(activity_log=MagicMock(record=AsyncMock()))
    with patch.object(own_task, "defer_until_commit", new=lambda _s, cb, _d, **_k: deferred.append(cb)):
        await service.release(_unclaim_session(item), item_id, _AGENT)
    assert item.checkout_run_id is None
    assert await redis.get(_key(item_id)) == fence  # nothing is dropped before the commit
    with patch.object(own_task, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        await deferred[0]()
    return await redis.get(_key(item_id))


async def test_release_drops_the_fence_of_the_generation_the_locked_row_held(redis):
    assert await _release(redis, f"{_AGENT}#run-1") is None


async def test_release_keeps_the_fence_of_a_checkout_the_same_agent_took_after_the_commit(redis):
    assert await _release(redis, f"{_AGENT}#run-2") == f"{_AGENT}#run-2"


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
        await own_task.release_agent_fence(item_id, release.agent_id, "run-1")
    assert await redis.get(_key(item_id)) is None


@pytest.mark.parametrize("value", ["", f"user:{_USER}", "agent-1", "not-a-uuid"])
def test_a_request_refuses_an_agent_id_that_is_not_an_agent_uuid(value):
    for model in (work_items_api.CheckoutRequest, work_items_api.ReleaseRequest):
        with pytest.raises(ValidationError):
            model(agent_id=value)


async def test_a_refused_checkout_keeps_a_fence_a_new_holder_took_while_it_ran(redis):
    """The checkout took the fence, its TTL lapsed and a person took the key before the refusal dropped it."""
    item_id = str(uuid.uuid4())
    item = MagicMock(
        id=uuid.UUID(item_id), checkout_run_id=None, assignee_agent_id=None,
        assignee_user_id=uuid.UUID(_USER), checkout_locked_at=datetime.now(timezone.utc),
    )  # fmt: skip

    async def execute(*_args, **_kwargs):
        await redis.set(_key(item_id), f"user:{_NEW_USER}")
        return MagicMock(scalar_one_or_none=MagicMock(return_value=item))

    service = wis.WorkItemService(activity_log=MagicMock(record=AsyncMock()))
    with patch.object(wis, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        with pytest.raises(wis.CheckoutConflict):
            await service.checkout(MagicMock(execute=execute), item_id, _AGENT, run_id="run-1")
    assert await redis.get(_key(item_id)) == f"user:{_NEW_USER}"


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


def test_fence_agent_names_a_raw_spelling_canonically_so_a_checkout_sees_its_own_old_fence():
    """The checkout's holder test compares ``fence_agent(existing)`` with the canonical request id (#19631)."""
    assert own_task.fence_agent(f"{_AGENT.upper()}#run-1") == _AGENT
    assert own_task.fence_agent(_AGENT.replace("-", "")) == _AGENT
    assert own_task.fence_agent(f"user:{_USER}") == f"user:{_USER}"
