# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A person asks a claim holder to release over HTTP (#18599); free text is capped once (#18563).

Real claims, rate limiter and ledger events against fakeredis. Only the org context and the
JWT -> user step are overridden; the task manager is a recorder so the PUBLISHED event can be read.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import agent_ledger
from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared import rate_limiter as rl_mod
from autobot_shared.coordination import claim_waitlist as wl_mod
from autobot_shared.coordination import ledger_events, ledger_read
from autobot_shared.coordination import work_claims as wc_mod
from autobot_shared.coordination.work_claims import list_claims, try_acquire
from services import claim_yield
from user_management.services import TenantContext

try:
    import fakeredis
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None
    fakeredis = None  # type: ignore[assignment]

CO_A, CO_B = uuid.uuid4(), uuid.uuid4()
USER = uuid.uuid4()
URL = "/coordination/ledger/claims/yield-request"


class _Published:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def publish_event(self, task_id: str, payload: dict) -> None:
        self.events.append((task_id, payload))


@pytest_asyncio.fixture
async def redis(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed")
    client = fakeredis_async.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    for module in (wc_mod, wl_mod, ledger_read, rl_mod, claim_yield):
        monkeypatch.setattr(module, "get_async_redis_client", _client)
    yield client
    await client.flushall()


@pytest.fixture
def bus(monkeypatch):
    published = _Published()
    monkeypatch.setattr(claim_yield, "get_task_manager", lambda: published)
    return published


def _client(company: uuid.UUID = CO_A, authed: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(agent_ledger.router, prefix="/coordination")
    if not authed:  # the real JWT step answers 401 with no user; its own chain is tested elsewhere

        def _no_user():
            raise HTTPException(status_code=401, detail="Authentication required")

        app.dependency_overrides[get_current_user] = _no_user
    else:
        app.dependency_overrides[get_current_user] = lambda: {"id": str(USER), "role": "user"}
        app.dependency_overrides[require_org_context] = lambda: TenantContext(org_id=company)
    return TestClient(app, raise_server_exceptions=False)


def _ask(client: TestClient, scope="path:a/f", holder="t-a", reason="need it"):
    return client.post(URL, json={"scope": scope, "holder_task_id": holder, "reason": reason})


async def _hold(scope: str, task: str, company: uuid.UUID | None, intent: str = "work"):
    await try_acquire(
        scope, agent_id="holder", task_id=task, intent=intent, company_id=str(company) if company else None
    )


@pytest.mark.asyncio
async def test_a_member_asks_and_the_ledger_records_the_person_and_the_claim_stays_held(redis, bus):
    await _hold("path:a/f", "t-a", CO_A)
    response = _ask(_client())
    assert response.status_code == 200
    token = response.json()["token"]
    ((task_id, sent),) = bus.events
    assert (task_id, sent["token"], sent["requester_agent_id"]) == ("t-a", token, f"user:{USER}")
    assert sent["requester_task_id"].startswith("ui:")
    events = await ledger_events.read_events(redis)
    assert [(e["type"], e["token"], e["requester_agent_id"]) for e in events] == [
        ("yield_requested", token, f"user:{USER}")
    ]
    assert [(c.scope, c.task_id) for c in await list_claims()] == [("path:a/f", "t-a")]  # nothing released


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scope", "holder", "stamp"),
    [
        ("path:b/f", "t-b", CO_B),  # another company's claim
        ("path:u/f", "t-u", None),  # unstamped / install-wide
        ("path:a/f", "someone-else", CO_A),  # right claim, wrong holder_task_id
        ("path:nothing/f", "t-a", CO_A),  # no such claim
    ],
)
async def test_a_claim_the_caller_may_not_see_is_404_with_one_message_and_nothing_is_sent(
    redis, bus, scope, holder, stamp
):
    await _hold("path:a/f", "t-a", CO_A)
    if scope != "path:a/f" and scope != "path:nothing/f":
        await _hold(scope, holder, stamp)
    response = _ask(_client(), scope=scope, holder=holder)
    assert response.status_code == 404
    assert response.json() == {"detail": "no such claim"}
    assert bus.events == [] and await ledger_events.read_events(redis) == []


@pytest.mark.asyncio
async def test_an_oversized_request_is_a_422_at_parse_time_and_nothing_is_sent_18607(redis, bus):
    from autobot_shared.coordination.ledger_events import TEXT_CAP
    from autobot_shared.coordination.ledger_schemas import ID_MAX_LEN, SCOPE_MAX_LEN

    await _hold("path:a/f", "t-a", CO_A)
    client = _client()
    assert _ask(client, reason="r" * (TEXT_CAP + 1)).status_code == 422
    assert _ask(client, holder="t" * (ID_MAX_LEN + 1)).status_code == 422
    assert _ask(client, scope="path:" + "s" * SCOPE_MAX_LEN).status_code == 422
    assert _ask(client, scope="").status_code == 422
    assert bus.events == []
    assert _ask(client, reason="r" * TEXT_CAP).status_code == 200  # the cap itself is accepted


@pytest.mark.asyncio
async def test_unauthenticated_is_401(redis, bus):
    await _hold("path:a/f", "t-a", CO_A)
    assert any(d.dependency is get_current_user for d in agent_ledger.router.dependencies)
    assert _ask(_client(authed=False)).status_code == 401
    assert bus.events == []


@pytest.mark.asyncio
async def test_a_repeat_within_the_window_is_429_and_a_404_never_spends_the_allowance(redis, bus):
    await _hold("path:a/f", "t-a", CO_A)
    assert _ask(_client(), holder="wrong").status_code == 404
    assert _ask(_client()).status_code == 200
    again = _ask(_client())
    assert again.status_code == 429
    assert len(bus.events) == 1
    assert [c.task_id for c in await list_claims()] == ["t-a"]


@pytest.mark.asyncio
async def test_a_long_reason_is_cut_in_the_published_event_and_the_ledger_copy_18563(redis, bus):
    """The route refuses an over-cap reason (#18607); a caller below the route still gets the cut (#18563)."""
    from autobot_shared.coordination.yield_ask import ask_holder_to_release

    await _hold("path:a/f", "t-a", CO_A)
    await ask_holder_to_release(
        str(CO_A),
        user_id="u-1",
        scope="path:a/f",
        holder_task_id="t-a",
        reason="x" * (ledger_events.TEXT_CAP * 3),
        issue=claim_yield.request_yield,
    )
    assert bus.events[0][1]["reason"] == "x" * ledger_events.TEXT_CAP
    assert (await ledger_events.read_events(redis))[0]["reason"] == "x" * ledger_events.TEXT_CAP


@pytest.mark.asyncio
async def test_a_long_intent_is_stored_and_served_cut_but_ids_are_not_18563(redis, bus):
    long_id = "t-" + "i" * (ledger_events.TEXT_CAP * 2)
    await _hold("path:a/f", long_id, CO_A, intent="y" * (ledger_events.TEXT_CAP * 3))
    served = _client().get("/coordination/ledger/claims").json()["claims"][0]
    assert served["intent"] == "y" * ledger_events.TEXT_CAP
    assert served["task_id"] == long_id
