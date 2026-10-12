# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``service_name`` on the service start/stop/restart routes cannot reach a remote shell (#18359).

The path parameter used to be interpolated into ``sudo -n systemctl <action> <name>`` and run by a
shell on the node, so ``foo;<cmd>`` was command execution for any caller. The routes now answer
422 for a name that is not a systemd unit name, 404 for a unit the node has no record of, and 403
for a caller without ``service.management``; only a valid request reaches the executor, and the
executor's own argv is checked for the exact quoted command.

The real ``services.auth`` (the 403 is the real permission decision, not a stub), the real ORM and
the real executor are loaded; only the SSH subprocess and the WebSocket broadcast are faked.
"""

from __future__ import annotations

import asyncio
import secrets
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_auth_import import load_real_auth  # noqa: E402
from _real_orm_import import REAL_MODULES, SLM_ROOT, import_modules_with_real_orm, real_modules_swapped  # noqa: E402

_auth = load_real_auth(secrets.token_hex(32))


async def _real_get_db():  # replaced per test through dependency_overrides
    yield None


_fake_db = types.ModuleType("services.database")
_fake_db.get_db = _real_get_db
_fake_db.db_service = None

with patch.dict(sys.modules, {"services.auth": _auth, "services.database": _fake_db}):
    _restart, _guard, _api = import_modules_with_real_orm(
        import_names=("api.service_action_guard", "api.services"),
        path_loaded={"services.service_restart": SLM_ROOT / "services" / "service_restart.py"},
    )

_db = REAL_MODULES["models.database"]
with real_modules_swapped():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_NODE_ID = "n-inject"
_KNOWN = "redis-stack.service"
_ADMIN = {"admin": True, "role": "admin", "sub": "root"}
_OPERATOR = {"admin": False, "role": "operator", "sub": "ops"}
_USER = {"admin": False, "role": "user", "sub": "mallory"}
_PATH_ACTIONS = ("start", "stop", "restart")


class _Proc:
    returncode = 0

    async def communicate(self):
        return b"ok", b""


@pytest.fixture
async def env(monkeypatch):
    """App with the real routers, an in-memory DB seeded with one node + one service, a recording ssh."""
    with real_modules_swapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")  # canonical: ignore py-adhoc-db-engine
        async with engine.begin() as conn:
            await conn.run_sync(_db.Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine
    async with maker() as db:
        db.add(_db.Node(node_id=_NODE_ID, hostname="h", ip_address="node.example.test", status="online"))
        db.add(_db.Service(node_id=_NODE_ID, service_name=_KNOWN, status="stopped"))
        await db.commit()

    spawned: list[list[str]] = []

    async def _spawn(*argv, **kwargs):
        spawned.append(list(argv))
        return _Proc()

    monkeypatch.setattr(_api, "ws_manager", AsyncMock())

    async def _get_db():
        async with maker() as session:
            yield session

    who = {"user": _ADMIN}
    app = FastAPI()
    app.include_router(_api.router)
    app.include_router(_api.fleet_router)
    app.dependency_overrides[_api.get_db] = _get_db
    app.dependency_overrides[_auth.get_current_user] = lambda: who["user"]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:

        async def post(url: str):
            # Installed per call: tests/api/conftest.py swaps in a blocking stand-in for the whole
            # call phase, and "the inner patch wins" (#13312).
            with patch.object(asyncio, "create_subprocess_exec", _spawn):
                return await client.post(url)

        async def get(url: str):
            with patch.object(asyncio, "create_subprocess_exec", _spawn):
                return await client.get(url)

        yield types.SimpleNamespace(post=post, get=get, spawned=spawned, who=who)
    await engine.dispose()


def _node_url(name: str, action: str) -> str:
    return f"/nodes/{_NODE_ID}/services/{name}/{action}"


@pytest.mark.parametrize("action", _PATH_ACTIONS)
@pytest.mark.parametrize(
    "name",
    ["foo;id", "$(id)", "`id`", "a%20b", "-H", "--help", "a%0Aid", "..%2Fx", "a&&b", "a|b", "x" * 300],
)
async def test_an_invalid_unit_name_is_422_and_nothing_is_spawned(env, name, action):
    spawned = env.spawned
    for url in (_node_url(name, action), f"/fleet/services/{name}/{action}"):
        response = await env.post(url)
        assert response.status_code in (422, 404), (url, response.status_code)
        if "%2F" not in name:  # a decoded slash is routed away (404) before the guard
            assert response.status_code == 422, (url, response.status_code)
    assert spawned == []


@pytest.mark.parametrize("action", _PATH_ACTIONS)
async def test_an_unknown_service_record_is_404_and_nothing_is_spawned(env, action):
    spawned = env.spawned
    response = await env.post(_node_url("not-recorded.service", action))
    assert response.status_code == 404
    assert spawned == []


@pytest.mark.parametrize("action", _PATH_ACTIONS)
@pytest.mark.parametrize("caller", [_USER, {"admin": False, "role": "readonly", "sub": "r"}], ids=["user", "readonly"])
async def test_a_caller_without_service_management_is_403_even_for_a_valid_unit(env, caller, action):
    spawned, who = env.spawned, env.who
    who["user"] = caller
    assert (await env.post(_node_url(_KNOWN, action))).status_code == 403
    assert (await env.post(f"/fleet/services/{_KNOWN}/{action}")).status_code == 403
    assert spawned == []


@pytest.mark.parametrize("caller", [_ADMIN, _OPERATOR], ids=["admin", "operator"])
@pytest.mark.parametrize("action", _PATH_ACTIONS)
async def test_a_valid_request_reaches_the_executor_once_with_the_quoted_argv(env, caller, action):
    spawned, who = env.spawned, env.who
    who["user"] = caller
    response = await env.post(_node_url(_KNOWN, action))
    assert response.status_code == 200, response.text
    assert len(spawned) == 1
    assert spawned[0][-1] == f"sudo -n systemctl {action} -- {_KNOWN}"
    assert spawned[0][0] == "/usr/bin/ssh"


async def test_the_fleet_route_validates_then_reaches_the_executor_for_a_known_unit(env):
    spawned = env.spawned
    assert (await env.post("/fleet/services/foo;id/restart")).status_code == 422
    assert spawned == []
    assert (await env.post(f"/fleet/services/{_KNOWN}/restart")).status_code == 200
    assert [argv[-1] for argv in spawned] == [f"sudo -n systemctl restart -- {_KNOWN}"]


# --- the logs route: same validators, 422 before anything is spawned -----------------------------

_HOSTILE_SINCE = ["1h;id", "$(id)", "%60id%60", "%27;id", "1h%0Aid", "-H", "yesterday%20x"]


@pytest.mark.parametrize("name", ["foo;id", "$(id)", "`id`", "a%20b", "-H", "a%0Aid", "x" * 300])
async def test_the_logs_route_refuses_a_hostile_service_name(env, name):
    response = await env.get(f"/nodes/{_NODE_ID}/services/{name}/logs")
    assert response.status_code == 422
    assert env.spawned == []


@pytest.mark.parametrize("since", _HOSTILE_SINCE)
async def test_the_logs_route_refuses_a_hostile_since(env, since):
    response = await env.get(f"/nodes/{_NODE_ID}/services/{_KNOWN}/logs?since={since}")
    assert response.status_code == 422
    assert env.spawned == []


async def test_the_logs_route_runs_a_valid_request_with_the_quoted_command(env):
    response = await env.get(f"/nodes/{_NODE_ID}/services/{_KNOWN}/logs?since=2%20h%20ago&lines=7")
    assert response.status_code == 200, response.text
    assert [argv[-1] for argv in env.spawned] == [f"sudo -n journalctl -u {_KNOWN} -n 7 --no-pager --since='2 h ago'"]
