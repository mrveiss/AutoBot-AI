# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A human claim's actor and tenant come from the session, and a failed audit fails cleanly (#13999).

An audit write shares the operation's transaction, so when it fails the operation must fail with
it and leave nothing behind -- in the database (the route never commits) and in Redis (the
checkout lock), and the route must answer 500, not the 404/400 it keeps for the caller's errors.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from llc.models.enums import WorkItemStatus
from llc.services import work_item_service as wis
from llc.services.actor import ActivityRecordError
from user_management.services import TenantContext

_USER = uuid.uuid4()
_ORG = uuid.uuid4()
_FORGED_USER, _FORGED_ORG = str(uuid.uuid4()), str(uuid.uuid4())


class _Redis:
    """A dict-backed Redis: the checkout lock either survives an operation or it does not."""

    def __init__(self, held: dict[str, str] | None = None):
        self.data = dict(held or {})

    async def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return False
        self.data[key] = value
        return True

    async def get(self, key):
        return self.data.get(key)

    async def delete(self, key):
        self.data.pop(key, None)

    async def eval(self, _script, _numkeys, key, expected):
        """The compare-and-delete the service's release-if-owner sends."""
        if self.data.get(key) != expected:
            return 0
        del self.data[key]
        return 1


def _failing_log() -> MagicMock:
    return MagicMock(record=AsyncMock(side_effect=ValueError("Invalid entity_id UUID")))


def _session(item) -> MagicMock:
    session = MagicMock(flush=AsyncMock(), commit=AsyncMock())
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=item)))
    return session


def _item(**kw) -> MagicMock:
    base = dict(
        status=WorkItemStatus.READY,
        version=1,
        assignee_user_id=None,
        assignee_agent_id=None,
        started_at=None,
        co_worker_type=None,
        co_worker_agent_id=None,
        co_worker_user_id=None,
        co_working_enabled=False,
    )
    base.update(kw)
    return MagicMock(**base)


@pytest.mark.asyncio
async def test_failed_audit_on_claim_fails_the_claim_and_gives_the_lock_back():
    redis = _Redis()
    svc = wis.WorkItemService(activity_log=_failing_log())
    session, wid = _session(_item()), str(uuid.uuid4())
    with patch.object(wis, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        with pytest.raises(ActivityRecordError):
            await svc.claim_human(session, wid, str(_USER), str(_ORG))
    assert redis.data == {}
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_failed_audit_on_claim_keeps_a_same_user_fence_this_call_did_not_take():
    wid = str(uuid.uuid4())
    held = {f"llc:checkout:{wid}": f"user:{_USER}"}
    redis = _Redis(held)
    svc = wis.WorkItemService(activity_log=_failing_log())
    with patch.object(wis, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        with pytest.raises(ActivityRecordError):
            await svc.claim_human(_session(_item()), wid, str(_USER), str(_ORG))
    assert redis.data == held


@pytest.mark.asyncio
async def test_failed_audit_on_transition_to_done_runs_no_external_side_effect():
    can_finish = next(st for st, to in wis._ALLOWED_TRANSITIONS.items() if WorkItemStatus.DONE in to)
    svc = wis.WorkItemService(activity_log=_failing_log())
    svc._trigger_artifact_ingest = AsyncMock()
    release = AsyncMock()
    with patch("services.task_workspace.release_for_task", new=release):
        with pytest.raises(ActivityRecordError):
            await svc.transition_to_done(
                _session(_item(status=can_finish.value)), str(uuid.uuid4()), str(_ORG), actor_user_id=str(_USER)
            )
    svc._trigger_artifact_ingest.assert_not_called()
    release.assert_not_called()


@pytest.mark.asyncio
async def test_failed_audit_on_unclaim_keeps_the_lock_with_the_rolled_back_claim():
    key = "llc:checkout:%s"
    wid = str(uuid.uuid4())
    redis = _Redis({key % wid: f"user:{_USER}"})
    svc = wis.WorkItemService(activity_log=_failing_log())
    session = _session(_item(assignee_user_id=_USER, status=WorkItemStatus.IN_PROGRESS))
    with patch.object(wis, "get_async_redis_client", new=AsyncMock(return_value=redis)):
        with pytest.raises(ActivityRecordError):
            await svc.unclaim_human(session, wid, str(_USER), str(_ORG))
    assert redis.data == {key % wid: f"user:{_USER}"}
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_failed_audit_on_enable_and_disable_coworking_fails_the_operation():
    svc = wis.WorkItemService(activity_log=_failing_log())
    session = _session(_item())
    common = dict(company_id=str(_ORG), actor_id=str(_USER), actor_type="user", caller_role="owner")
    with pytest.raises(ActivityRecordError):
        await svc.enable_coworking(
            session,
            work_item_id=str(uuid.uuid4()),
            co_worker_type="agent",
            co_worker_agent_id=str(uuid.uuid4()),
            **common,
        )
    with pytest.raises(ActivityRecordError):
        await svc.disable_coworking(session, work_item_id=str(uuid.uuid4()), **common)
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_failed_audit_on_transition_to_done_fails_the_transition():
    can_finish = next(st for st, to in wis._ALLOWED_TRANSITIONS.items() if WorkItemStatus.DONE in to)
    svc = wis.WorkItemService(activity_log=_failing_log())
    svc._trigger_artifact_ingest = AsyncMock()
    session = _session(_item(status=can_finish.value))
    with pytest.raises(ActivityRecordError):
        await svc.transition_to_done(session, str(uuid.uuid4()), str(_ORG), actor_user_id=str(_USER))
    session.commit.assert_not_called()


def _client(service: MagicMock) -> TestClient:
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api import work_items  # noqa: PLC0415

    app = FastAPI()
    app.include_router(work_items.router, prefix="/api/llc")
    session = MagicMock(commit=AsyncMock())

    async def _fake_session():
        yield session

    app.dependency_overrides[work_items.get_session] = _fake_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=_ORG, user_id=_USER, is_platform_admin=False
    )
    patch.object(work_items, "_service", return_value=service).start()
    patch.object(work_items, "_item_to_dict", new=AsyncMock(return_value={"ok": True})).start()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _stop_patches():
    yield
    patch.stopall()


def _service_mock(**ops) -> MagicMock:
    svc = MagicMock(get=AsyncMock(return_value=MagicMock(company_id=_ORG)))
    for name, effect in ops.items():
        setattr(svc, name, AsyncMock(**effect))
    return svc


@pytest.mark.parametrize("op", ["claim", "unclaim"])
def test_routes_take_the_user_and_tenant_from_the_session_and_ignore_the_body(op):
    svc = _service_mock(**{f"{op}_human": {"return_value": MagicMock()}})
    body = {"user_id": _FORGED_USER, "company_id": _FORGED_ORG}
    assert _client(svc).post(f"/api/llc/work-items/{uuid.uuid4()}/{op}", json=body).status_code == 200
    sent = getattr(svc, f"{op}_human").await_args.kwargs
    assert (sent["user_id"], sent["company_id"]) == (str(_USER), str(_ORG))


@pytest.mark.parametrize("op", ["claim", "unclaim"])
def test_routes_accept_an_empty_body(op):
    """The frontend posts ``{}``; the session supplies everything."""
    svc = _service_mock(**{f"{op}_human": {"return_value": MagicMock()}})
    assert _client(svc).post(f"/api/llc/work-items/{uuid.uuid4()}/{op}", json={}).status_code == 200


@pytest.mark.parametrize("op", ["claim", "unclaim"])
def test_a_failed_audit_is_a_500_but_a_real_not_found_keeps_its_status(op):
    wid = uuid.uuid4()
    failing = _service_mock(**{f"{op}_human": {"side_effect": ActivityRecordError("boom")}})
    assert _client(failing).post(f"/api/llc/work-items/{wid}/{op}", json={}).status_code == 500
    patch.stopall()
    missing = _service_mock(**{f"{op}_human": {"side_effect": ValueError("not found")}})
    expected = 404 if op == "claim" else 400
    assert _client(missing).post(f"/api/llc/work-items/{wid}/{op}", json={}).status_code == expected
