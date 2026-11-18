# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM agent ledger: admin only, install-wide, unreachable vs empty, honest about gaps (#18391).

Real `work_claims` / `claim_waitlist` / `dev_loop_actions` against fakeredis; the
real `require_permission(ADMIN_SYSTEM)` gate decides who gets in, with only the
JWT -> user step (`get_current_user`) replaced.
"""

from __future__ import annotations

import importlib.util
import secrets
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[3]
for _p in (str(_ROOT), str(_ROOT / "autobot-slm-backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import autobot_shared.logging_manager as _logging_manager  # noqa: E402


class _NoConfig:
    """What `get_logger` needs from a config manager when the SLM conftest has stubbed `config` as a MagicMock."""

    @staticmethod
    def get_nested(_key, default=None):
        return default


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_auth_import import load_real_auth  # noqa: E402

_auth = load_real_auth(secrets.token_hex(32))
get_current_user = _auth.get_current_user

# This SLM conftest replaces `config` with a MagicMock, which `logging_manager` reads rotation sizes from
# (`'>' not supported between 'MagicMock' and 'int'`). The shared coordination modules log through
# `get_logger` as the rest of the repo does, so the harness is bridged here for the import only.
with patch.object(_logging_manager, "_get_config_manager", lambda: _NoConfig()):
    from autobot_shared.coordination import claim_waitlist as wl_mod
    from autobot_shared.coordination import dev_loop_actions as dla
    from autobot_shared.coordination import ledger_projection as lp_mod
    from autobot_shared.coordination import ledger_read
    from autobot_shared.coordination import work_claims as wc_mod
    from autobot_shared.coordination.claim_waitlist import join
    from autobot_shared.coordination.work_claims import release_scope, renew, try_acquire

    _spec = importlib.util.spec_from_file_location(
        "slm_agent_ledger_18391", _ROOT / "autobot-slm-backend/api/agent_ledger.py"
    )
    ledger_api = importlib.util.module_from_spec(_spec)
    # The conftest stubs `services.auth` (a MagicMock gate gates nothing); the router is loaded against the real one.
    # Only that key is swapped and restored: `patch.dict(sys.modules)` would also evict every module the router
    # imports (yield_ask, rate_limiter), so the tests' `rate_limiter` patch could land on a different module
    # instance than the router's limiter whenever no earlier test had imported it.
    _prev_auth = sys.modules.get("services.auth")
    sys.modules["services.auth"] = _auth
    try:
        _spec.loader.exec_module(ledger_api)
    finally:
        if _prev_auth is None:
            sys.modules.pop("services.auth", None)
        else:
            sys.modules["services.auth"] = _prev_auth

try:
    import fakeredis
    import fakeredis.aioredis as fakeredis_async
except ImportError:  # pragma: no cover
    fakeredis_async = None
    fakeredis = None  # type: ignore[assignment]

READ_PATHS = (
    "claims",
    "waitlists",
    "contention",
    "conflicts",
    "activity",
    "dev-loop",
    "dev-loop/5",
    "sources",
    "presence",
    "peer-messages",
    "idle-subscribers",
)


def _client(role: str, sub: str | None = "someone") -> TestClient:
    app = FastAPI()
    app.include_router(ledger_api.router, prefix="/api/monitoring")
    user = {"role": role, "admin": role == "admin"} | ({"sub": sub} if sub is not None else {})
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


@pytest_asyncio.fixture
async def redis(monkeypatch):
    if fakeredis_async is None:
        pytest.skip("fakeredis[lua] not installed")
    client = fakeredis_async.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)

    async def _client_fn(database: str = "main"):
        return client

    for module in (wc_mod, wl_mod, dla, ledger_read, lp_mod):
        monkeypatch.setattr(module, "get_async_redis_client", _client_fn)
    yield client
    await client.flushall()


@pytest.mark.parametrize("path", READ_PATHS)
def test_a_non_admin_is_refused_on_every_route(path):
    assert _client("readonly").get(f"/api/monitoring/agent-ledger/{path}").status_code == 403


@pytest.mark.asyncio
async def test_an_admin_sees_every_companys_claims_waiters_contention_and_dev_loop(redis):
    await try_acquire("path:a/f", agent_id="co-a-agent", task_id="t", intent="a work")
    await try_acquire("path:b/f", agent_id="co-b-agent", task_id="t", intent="b work")
    await try_acquire("provider:anthropic", agent_id="dev-session", task_id="t", intent="quota")
    await join("provider:anthropic", agent_id="co-a-agent", task_id="t2", intent="needs quota")
    assert await renew("path:a/f", agent_id="co-a-agent", task_id="t")
    await dla.record_dev_loop_action(
        dla.build_action(5, intent="triage", outcome=dla.OUTCOME_SKIPPED_CLAIMED, estimated_tokens=0, reason="held")
    )
    api = _client("admin")

    claims = api.get("/api/monitoring/agent-ledger/claims").json()
    assert {c["agent_id"] for c in claims["claims"]} == {"co-a-agent", "co-b-agent", "dev-session"}
    assert {c["scope"]: c["renewals"] for c in claims["claims"]}["path:a/f"] == 1
    assert [c["scope"] for c in api.get("/api/monitoring/agent-ledger/claims?kind=provider").json()["claims"]] == [
        "provider:anthropic"
    ]
    assert api.get("/api/monitoring/agent-ledger/waitlists").json()["waiters"][0]["agent_id"] == "co-a-agent"
    resource = api.get("/api/monitoring/agent-ledger/contention").json()["resources"]
    assert [(r["scope"], r["contended"], [h["agent_id"] for h in r["holders"]]) for r in resource] == [
        ("provider:anthropic", True, ["dev-session"])
    ]
    assert api.get("/api/monitoring/agent-ledger/dev-loop").json()["issues"] == [5]
    assert api.get("/api/monitoring/agent-ledger/dev-loop/5").json()["actions"][0]["outcome"] == "skipped_claimed"
    assert (
        api.get("/api/monitoring/agent-ledger/dev-loop/6").json()["actions"] == []
    )  # untouched issue: read fine, nothing there


@pytest.mark.asyncio
async def test_conflicts_report_a_refused_release(redis):
    await try_acquire("path:a/f", agent_id="owner", task_id="t", intent="x")
    await release_scope("path:a/f", agent_id="intruder", task_id="s")
    body = _client("admin").get("/api/monitoring/agent-ledger/conflicts").json()
    assert [(c["kind"], c["agent_id"], c["other_agent_id"]) for c in body["conflicts"]] == [
        ("release_refused", "intruder", "owner")
    ]


@pytest.mark.asyncio
async def test_an_empty_ledger_is_200_empty_and_an_unreachable_one_is_503(redis, monkeypatch):
    await try_acquire(
        "path:z/f", agent_id="x", task_id="t", intent="control"
    )  # control: the read path works and sees data
    api = _client("admin")
    assert api.get("/api/monitoring/agent-ledger/claims").json()["count"] == 1
    await redis.flushall()
    for path, key in (
        ("claims", "claims"),
        ("waitlists", "waiters"),
        ("conflicts", "conflicts"),
        ("dev-loop", "issues"),
    ):
        response = api.get(f"/api/monitoring/agent-ledger/{path}")
        assert (response.status_code, response.json()[key]) == (200, []), path

    async def _none(database: str = "main"):
        return None

    for module in (wc_mod, wl_mod, dla, ledger_read, lp_mod):
        monkeypatch.setattr(module, "get_async_redis_client", _none)
    for path in ("claims", "waitlists", "contention", "conflicts", "activity", "dev-loop", "dev-loop/5"):
        response = api.get(f"/api/monitoring/agent-ledger/{path}")
        assert response.status_code == 503, path
        assert response.json()["error"] == "ledger_unavailable" and response.json()["detail"]


def test_sources_name_what_is_unreachable_instead_of_showing_it_empty(monkeypatch):
    async def _none(database: str = "main"):
        return None

    for module in (wc_mod, wl_mod, dla, ledger_read, lp_mod):
        monkeypatch.setattr(module, "get_async_redis_client", _none)
    sources = {s["source"]: s for s in _client("admin").get("/api/monitoring/agent-ledger/sources").json()["sources"]}
    assert not any(s["reachable"] for s in sources.values())
    assert {"claims", "waitlists", "events", "dev_loop"} <= set(sources)
    for gap in ("presence", "ai_stack_agents", "live_sessions", "peer_messages", "idle_subscribers"):
        assert sources[gap]["reachable"] is False and sources[gap]["reason"] == ledger_read.GENERIC_DETAIL


async def _publish(redis, **rows):  # noqa: ANN001, ANN003
    from autobot_shared.coordination.ledger_schemas import IdleSubscriberRow, PeerMessageRow, PresenceRow

    await lp_mod.publish(
        redis,
        presence=rows.get(
            "presence", [PresenceRow(kind="company_os", tenant_id="co-1", name="writer", busy=True, last_seen=1.0)]
        ),
        peer_messages=rows.get(
            "peer_messages",
            [
                PeerMessageRow(
                    recipient_kind="company_os",
                    recipient_name="writer",
                    pending=2,
                    senders=["a"],
                    oldest_at=1.0,
                    tenant_id="co-1",
                )
            ],
        ),
        idle_subscribers=rows.get(
            "idle_subscribers",
            [
                IdleSubscriberRow(
                    subscriber="w",
                    target_kind="ai_stack",
                    target_name="chat",
                    since=1.0,
                    expires_at=9.0,
                    tenant_id=None,
                )
            ],
        ),
    )


@pytest.mark.asyncio
async def test_live_state_is_read_from_the_user_backends_snapshot_with_its_company_18632(redis):
    await _publish(redis)
    client = _client("admin")
    presence = client.get("/api/monitoring/agent-ledger/presence").json()
    assert [(r["name"], r["tenant_id"], r["busy"]) for r in presence["agents"]] == [("writer", "co-1", True)]
    peers = client.get("/api/monitoring/agent-ledger/peer-messages").json()["recipients"]
    assert peers == [
        {
            "recipient_kind": "company_os",
            "recipient_name": "writer",
            "pending": 2,
            "senders": ["a"],
            "oldest_at": 1.0,
            "tenant_id": "co-1",
        }
    ]  # counts and sender names only -- the row has no field that could carry content
    idle = client.get("/api/monitoring/agent-ledger/idle-subscribers").json()["subscribers"]
    assert [(s["subscriber"], s["target_name"]) for s in idle] == [("w", "chat")]
    sources = {s["source"]: s for s in client.get("/api/monitoring/agent-ledger/sources").json()["sources"]}
    for name in ("presence", "ai_stack_agents", "live_sessions", "peer_messages", "idle_subscribers"):
        assert sources[name]["reachable"] is True


@pytest.mark.asyncio
async def test_a_redis_error_while_probing_marks_live_sources_unreachable_not_a_500_18632(redis, monkeypatch):
    from redis.exceptions import ConnectionError as RedisConnectionError

    await _publish(redis)

    async def _down(*_args, **_kwargs):
        raise RedisConnectionError("redis down")

    monkeypatch.setattr(redis, "get", _down)
    response = _client("admin").get("/api/monitoring/agent-ledger/sources")
    assert response.status_code == 200
    sources = {s["source"]: s for s in response.json()["sources"]}
    for name in ("presence", "ai_stack_agents", "live_sessions", "peer_messages", "idle_subscribers"):
        assert sources[name]["reachable"] is False
        assert sources[name]["reason"] == ledger_read.GENERIC_DETAIL  # unreadable, not "never published"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        '{"rows": []}',
        '{"published_at": "t"}',
        '{"rows": {}, "published_at": "t"}',
        '{"rows": [{"kind": 1}], "published_at": "t"}',
    ],
)
async def test_a_corrupt_snapshot_is_the_typed_503_and_sources_say_why_18632(redis, raw):
    await redis.set(lp_mod.projection_key(lp_mod.SOURCE_PRESENCE), raw)
    response = _client("admin").get("/api/monitoring/agent-ledger/presence")
    assert response.status_code == 503 and response.json()["error"] == "ledger_unavailable"
    sources = {s["source"]: s for s in _client("admin").get("/api/monitoring/agent-ledger/sources").json()["sources"]}
    if raw.endswith('"t"}') and '"kind": 1' in raw:
        assert sources["presence"]["reachable"] is True  # the envelope is valid; only the route validates rows
    else:
        assert sources["presence"] == {"source": "presence", "reachable": False, "reason": lp_mod.CORRUPT_DETAIL}


@pytest.mark.asyncio
async def test_a_missing_snapshot_is_the_typed_503_never_an_empty_list_18632(redis):
    for path in ("presence", "peer-messages", "idle-subscribers"):
        response = _client("admin").get(f"/api/monitoring/agent-ledger/{path}")
        assert response.status_code == 503
        assert response.json()["error"] == "ledger_unavailable"
    sources = {s["source"]: s for s in _client("admin").get("/api/monitoring/agent-ledger/sources").json()["sources"]}
    assert sources["presence"]["reason"] == lp_mod.NOT_PUBLISHED_DETAIL


@pytest.mark.asyncio
async def test_an_empty_snapshot_is_200_empty_not_a_503_18632(redis):
    await _publish(redis, presence=[], peer_messages=[], idle_subscribers=[])
    body = _client("admin").get("/api/monitoring/agent-ledger/presence").json()
    assert body == {"agents": [], "count": 0}


@pytest.mark.asyncio
async def test_a_snapshot_expires_after_the_projection_ttl_18632(redis):
    await _publish(redis)
    ttl = await redis.ttl(lp_mod.projection_key(lp_mod.SOURCE_PRESENCE))
    assert 0 < ttl <= lp_mod.PROJECTION_TTL_S


def test_the_slm_ledgers_only_write_is_the_yield_request_18599():
    unsafe = {(m, r.path) for r in ledger_api.router.routes for m in r.methods - {"GET", "HEAD"}}
    assert unsafe == {("POST", "/agent-ledger/claims/yield-request")}


YIELD_URL = "/api/monitoring/agent-ledger/claims/yield-request"


@pytest_asyncio.fixture
async def yield_env(redis, monkeypatch):
    """The ledger fixture plus the rate limiter and the SLM's own publish/record on the same fakeredis."""
    from autobot_shared import rate_limiter as rl_mod

    async def _client_fn(database: str = "main"):
        return redis

    monkeypatch.setattr(rl_mod, "get_async_redis_client", _client_fn)
    monkeypatch.setattr(ledger_api, "get_async_redis_client", _client_fn)
    pubsub = redis.pubsub()
    await pubsub.subscribe("a2a:events:t-u")
    await pubsub.get_message(timeout=1)  # the subscribe confirmation
    yield redis, pubsub


def _ask(
    role: str, holder: str = "t-u", scope: str = "path:u/f", reason: str | None = None, sub: str | None = "someone"
):
    from autobot_shared.coordination import ledger_events

    body = {
        "scope": scope,
        "holder_task_id": holder,
        "reason": "r" * ledger_events.TEXT_CAP if reason is None else reason,
    }
    return _client(role, sub=sub).post(YIELD_URL, json=body)


@pytest.mark.asyncio
async def test_an_admin_asks_for_an_install_wide_claim_and_it_is_published_recorded_and_kept_18599(yield_env):
    from autobot_shared.coordination import ledger_events

    redis, pubsub = yield_env
    await try_acquire("path:u/f", agent_id="dev-session", task_id="t-u", intent="x")
    response = _ask("admin")
    assert response.status_code == 200
    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1)
    import json as _json

    sent = _json.loads(message["data"])
    assert (sent["event"], sent["token"], sent["requester_agent_id"]) == (
        "work_claim_yield_request",
        response.json()["token"],
        "user:someone",
    )
    assert sent["reason"] == "r" * ledger_events.TEXT_CAP
    assert [e["type"] for e in await ledger_events.read_events(redis)] == ["yield_requested"]
    assert [c.task_id for c in await wc_mod.list_claims()] == ["t-u"]  # asking released nothing
    assert _ask("admin").status_code == 429  # a repeat inside the window


@pytest.mark.asyncio
async def test_an_oversized_request_is_a_422_at_parse_time_and_nothing_is_sent_18607(yield_env):
    from autobot_shared.coordination import ledger_events
    from autobot_shared.coordination.ledger_schemas import ID_MAX_LEN, SCOPE_MAX_LEN

    redis, pubsub = yield_env
    await try_acquire("path:u/f", agent_id="dev-session", task_id="t-u", intent="x")
    assert _ask("admin", reason="r" * (ledger_events.TEXT_CAP + 1)).status_code == 422
    assert _ask("admin", holder="t" * (ID_MAX_LEN + 1)).status_code == 422
    assert _ask("admin", scope="path:" + "s" * SCOPE_MAX_LEN).status_code == 422
    assert _ask("admin", holder="").status_code == 422
    assert await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2) is None
    assert await ledger_events.read_events(redis) == []


@pytest.mark.asyncio
async def test_a_token_without_a_subject_is_401_never_the_shared_user_none_18607(yield_env):
    redis, pubsub = yield_env
    await try_acquire("path:u/f", agent_id="dev-session", task_id="t-u", intent="x")
    assert _ask("admin", sub=None).status_code == 401
    assert _ask("admin", sub="").status_code == 401
    assert await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.2) is None
    assert _ask("admin").status_code == 200  # a real subject still asks, and its window is untouched


@pytest.mark.asyncio
async def test_the_yield_request_is_admin_only_and_404s_for_a_wrong_holder_or_no_claim_18599(yield_env):
    await try_acquire("path:u/f", agent_id="dev-session", task_id="t-u", intent="x")
    assert _ask("readonly").status_code == 403
    assert _ask("admin", holder="other").status_code == 404
    assert _ask("admin", scope="path:none/f").status_code == 404


@pytest.mark.asyncio
async def test_an_unreachable_store_while_asking_is_the_typed_503_not_a_500_18599(yield_env, monkeypatch):
    from autobot_shared.coordination.work_claims import ClaimUnavailable

    await try_acquire("path:u/f", agent_id="dev-session", task_id="t-u", intent="x")

    async def _down(*_args, **_kwargs):
        raise ClaimUnavailable("redis down")

    monkeypatch.setattr(ledger_api, "_publish", _down)
    response = _ask("admin")
    assert response.status_code == 503
    assert "redis down" not in response.text  # the cause stays in the log
