# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company OS agent-ledger routes: tenant isolation, unreachable vs empty, read-only (#18391).

The org context is overridden (its own chain is `agent_presence_test`'s subject);
the company -> agent-slug lookup is stood in for with a dict, so the isolation
under test is the router's: company A is handed only company A's rows.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import agent_ledger
from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.coordination import claim_waitlist as wl_mod
from autobot_shared.coordination import dev_loop_actions as dla
from autobot_shared.coordination import ledger_read
from autobot_shared.coordination import work_claims as wc_mod
from autobot_shared.coordination.claim_company import set_company
from autobot_shared.coordination.claim_waitlist import join
from autobot_shared.coordination.work_claims import release_scope, try_acquire
from protocols import idle_notice
from protocols.agent_communication import AgentIdentity
from protocols.agent_kind import AgentKind
from protocols.agent_presence import AgentPresenceRegistry
from protocols.idle_notice import IdleSubscription
from protocols.peer_inbox import PeerInboxDirectory
from user_management.services import TenantContext

try:
    import fakeredis
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None
    fakeredis = None  # type: ignore[assignment]

CO_A, CO_B = uuid.uuid4(), uuid.uuid4()


@pytest_asyncio.fixture
async def redis(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed")
    client = fakeredis_async.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)

    async def _client(database: str = "main"):
        return client

    for module in (wc_mod, wl_mod, dla, ledger_read):
        monkeypatch.setattr(module, "get_async_redis_client", _client)
    yield client
    await client.flushall()


@pytest.fixture
def world(monkeypatch):
    registry = AgentPresenceRegistry(ttl_seconds=60)
    directory = PeerInboxDirectory(registry)
    monkeypatch.setattr(agent_ledger, "get_presence_registry", lambda: registry)
    monkeypatch.setattr(agent_ledger, "get_peer_inbox_directory", lambda: directory)

    monkeypatch.setattr(idle_notice, "_ACTIVE", {})
    monkeypatch.setattr(agent_ledger, "active_subscriptions", idle_notice.active_subscriptions)
    return registry, directory


def _who(company: uuid.UUID, name: str) -> AgentIdentity:
    return AgentIdentity(agent_id=name, agent_type="test", kind=AgentKind.COMPANY_OS, name=name, tenant_id=str(company))


def _client(company: uuid.UUID) -> TestClient:
    app = FastAPI()
    app.include_router(agent_ledger.router, prefix="/coordination")
    app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "role": "user"}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(org_id=company)
    return TestClient(app, raise_server_exceptions=False)


def _get(company, path):
    return _client(company).get(f"/coordination/ledger/{path}")


async def _seed():
    stamps = {"a-agent": str(CO_A), "b-agent": str(CO_B), "dev-session": None}
    for (agent, company), scope in zip(stamps.items(), ("path:a/f", "path:b/f", "provider:x")):
        await try_acquire(scope, agent_id=agent, task_id="t", intent=f"{agent} work", company_id=company)
    for agent in ("a-agent", "b-agent"):
        await join("path:shared/f", agent_id=agent, task_id="t", intent="wait", company_id=stamps[agent])


@pytest.mark.asyncio
async def test_company_a_cannot_see_company_b_claims_waiters_or_events(redis, world):
    await _seed()
    set_company(str(CO_A))  # A's authenticated context reaches for B's claim
    try:
        await release_scope("path:b/f", agent_id="a-agent", task_id="t-x")
    finally:
        set_company(None)
    a_claims = _get(CO_A, "claims").json()
    b_claims = _get(CO_B, "claims").json()
    assert [c["agent_id"] for c in a_claims["claims"]] == ["a-agent"]
    assert [c["agent_id"] for c in b_claims["claims"]] == ["b-agent"]  # install-wide dev-session claim is in neither
    assert [w["agent_id"] for w in _get(CO_A, "waitlists").json()["waiters"]] == ["a-agent"]
    assert [w["agent_id"] for w in _get(CO_B, "waitlists").json()["waiters"]] == ["b-agent"]
    # Each party sees only its own side of the refused release; neither learns the other's ids.
    a_row = _get(CO_A, "conflicts").json()["conflicts"][0]
    b_row = _get(CO_B, "conflicts").json()["conflicts"][0]
    assert (a_row["agent_id"], a_row["other_agent_id"]) == ("a-agent", None)
    assert (b_row["agent_id"], b_row["other_agent_id"]) == (None, "b-agent")
    assert {r["agent_id"] for r in _get(CO_A, "activity").json()["activity"]} == {"a-agent"}
    assert "b-agent" not in _get(CO_A, "activity").text


def test_presence_peer_messages_and_idle_subscribers_are_scoped_to_the_callers_company(world):
    registry, directory = world
    for company, name in ((CO_A, "a-agent"), (CO_B, "b-agent")):
        registry.report(kind=AgentKind.COMPANY_OS, tenant_id=str(company), name=name, instance_id="i", busy=True)
        sender = _who(company, f"{name}-peer")
        registry.report(
            kind=AgentKind.COMPANY_OS, tenant_id=str(company), name=f"{name}-peer", instance_id="j", busy=False
        )
        directory.send(
            kind=AgentKind.COMPANY_OS, name=name, sender=sender, content="secret body", message_id=f"m-{name}"
        )
    for company, name, other in ((CO_A, "a-agent", "b-agent"), (CO_B, "b-agent", "a-agent")):
        idle_notice._ACTIVE[hash(name)] = IdleSubscription(
            f"{name}-waiter", AgentKind.COMPANY_OS, str(company), name, 1.0, 9.0
        )
        presence = _get(company, "presence").json()
        assert {r["name"] for r in presence["agents"]} == {name, f"{name}-peer"}
        pending = _get(company, "peer-messages")
        assert [(r["recipient_name"], r["pending"], r["senders"]) for r in pending.json()["recipients"]] == [
            (name, 1, [f"{name}-peer"])
        ]
        assert "secret body" not in pending.text and other not in pending.text  # metadata only, own tenant only
        assert [s["subscriber"] for s in _get(company, "idle-subscribers").json()["subscribers"]] == [f"{name}-waiter"]


def test_reading_pending_messages_does_not_drain_them(world):
    registry, directory = world
    registry.report(kind=AgentKind.COMPANY_OS, tenant_id=str(CO_A), name="a-agent", instance_id="i", busy=False)
    sender = _who(CO_A, "a-agent")
    directory.send(kind=AgentKind.COMPANY_OS, name="a-agent", sender=sender, content="c", message_id="m1")
    assert _get(CO_A, "peer-messages").json()["count"] == 1
    assert _get(CO_A, "peer-messages").json()["count"] == 1
    inbox = directory.inbox_for(kind=AgentKind.COMPANY_OS, tenant_id=str(CO_A), name="a-agent")
    assert len(inbox.drain()) == 1


@pytest.mark.asyncio
async def test_an_empty_ledger_is_200_with_an_empty_list(redis, world):
    await try_acquire(
        "path:other/f", agent_id="dev-session", task_id="t", intent="x"
    )  # control: Redis is live and populated
    for path, key in (
        ("claims", "claims"),
        ("waitlists", "waiters"),
        ("conflicts", "conflicts"),
        ("activity", "activity"),
    ):
        response = _get(CO_A, path)
        assert response.status_code == 200, path
        assert response.json()[key] == [] and response.json()["count"] == 0


def test_an_unreachable_ledger_is_503_with_a_typed_body_never_an_empty_list(monkeypatch, world):
    async def _none(database: str = "main"):
        raise ConnectionError("Error 111 connecting to 127.0.0.1:6379. Connection refused.")

    for module in (wc_mod, wl_mod, dla, ledger_read):
        monkeypatch.setattr(module, "get_async_redis_client", _none)
    for path, source in (
        ("claims", "claims"),
        ("waitlists", "waitlists"),
        ("conflicts", "events"),
        ("activity", "claims"),
    ):
        response = _get(CO_A, path)
        assert response.status_code == 503, path
        body = response.json()
        assert body["error"] == "ledger_unavailable" and body["source"] == source and body["detail"]
        assert "127.0.0.1" not in response.text and "6379" not in response.text
        assert set(body) == {"error", "source", "detail"}  # the typed error alone: no rows to mistake for "none"


def test_the_ledger_routes_are_read_only_and_authenticated(world):
    app = FastAPI()
    app.include_router(agent_ledger.router, prefix="/coordination")
    # The router's own routes: `app.routes` can defer an included router (#15093), which made this vacuous.
    unsafe = {(m, r.path) for r in agent_ledger.router.routes for m in getattr(r, "methods", set()) - {"GET", "HEAD"}}
    # The one write is a request to a holder (#18599): it never releases or deletes.
    assert unsafe == {("POST", "/ledger/claims/yield-request")}, "the ledger's only write is the yield request"
    assert any(d.dependency is get_current_user for d in agent_ledger.router.dependencies)
    client = _client(CO_A)
    assert client.post("/coordination/ledger/claims").status_code == 405  # only the yield-request path takes POST
    assert client.delete("/coordination/ledger/claims").status_code == 405


def _coord_client(company: uuid.UUID) -> TestClient:
    from api import coordination

    app = FastAPI()
    app.include_router(coordination.router, prefix="/coordination")
    app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "role": "user"}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(org_id=company)
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.asyncio
async def test_the_legacy_claims_route_is_scoped_to_the_callers_company_18410(redis, world):
    await _seed()
    a = _coord_client(CO_A).get("/coordination/claims").json()
    b = _coord_client(CO_B).get("/coordination/claims").json()
    assert [c["agent_id"] for c in a["claims"]] == ["a-agent"] and a["count"] == 1
    assert [c["agent_id"] for c in b["claims"]] == ["b-agent"]
    # Contrast with the unscoped table the route used to return: all three claims exist.
    from services.claim_projection import claim_table

    assert {c["agent_id"] for c in await claim_table()} == {"a-agent", "b-agent", "dev-session"}
    # Its own filters still work inside the company.
    assert _coord_client(CO_A).get("/coordination/claims?kind=provider").json()["claims"] == []
    assert _coord_client(CO_A).get("/coordination/claims?kind=path").json()["count"] == 1


@pytest.mark.asyncio
async def test_a_user_who_squats_an_unowned_slug_sees_nothing(redis, world):
    """Install-wide and other-company agents are reachable only by name; scoping is by stamp, so naming one reveals nothing."""
    await try_acquire("provider:anthropic", agent_id="dev-session", task_id="t", intent="quota")
    await try_acquire("path:a/f", agent_id="a-agent", task_id="t", intent="x", company_id=str(CO_A))
    for path in ("claims", "waitlists", "conflicts", "activity"):
        assert "dev-session" not in _get(CO_B, path).text and "a-agent" not in _get(CO_B, path).text, path
    assert "dev-session" not in _coord_client(CO_B).get("/coordination/claims?kind=provider").text
