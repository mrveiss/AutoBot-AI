# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``/orchestration/services/{name}/{start,stop,restart}`` refuse a non-unit-name before any playbook runs (#19005).

A name absent from the service registry plus a ``node_id`` in the body takes
``_per_node_systemd_action`` -> ``_run_ssh_service_action`` -> ``manage-service.yml`` with the raw
name. The routes now carry the same unit-name guard as the fleet routes (422), and
``execute_playbook`` validates again as the backstop.

The real ``services.auth`` (the service-management gate is the real decision) and the real ORM are loaded.
"""

from __future__ import annotations

import secrets
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI

from testkit.fake_async_session import FakeAsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_auth_import import load_real_auth  # noqa: E402
from _real_orm_import import import_modules_with_real_orm  # noqa: E402

_auth = load_real_auth(secrets.token_hex(32))


async def _real_get_db():  # replaced per test through dependency_overrides
    yield None


_stub_db_module = types.ModuleType("services.database")
_stub_db_module.get_db = _real_get_db
_stub_db_module.db_service = None

with patch.dict(sys.modules, {"services.auth": _auth, "services.database": _stub_db_module}):
    (_api,) = import_modules_with_real_orm(import_names=("api.orchestration",))

_ACTIONS = ("start", "stop", "restart")
_ADMIN = {"admin": True, "role": "admin", "sub": "root"}
_USER = {"admin": False, "role": "user", "sub": "mallory"}
_NODE = SimpleNamespace(node_id="n1", ip_address="node.example.test", hostname="h")


@pytest.fixture
async def env(monkeypatch):
    executor = MagicMock()
    executor.execute_playbook = AsyncMock(return_value={"success": True, "output": ""})
    registry = SimpleNamespace(registry=SimpleNamespace(get_service=lambda _name: None))  # not a registry service
    monkeypatch.setattr(_api, "service_orchestrator", registry)
    who = {"user": _ADMIN}
    app = FastAPI()
    app.include_router(_api.router)
    app.dependency_overrides[_auth.get_current_user] = lambda: who["user"]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:

        async def post(name: str, action: str):
            app.dependency_overrides[_api.get_db] = lambda: FakeAsyncSession(results=[[_NODE], []])
            with patch("services.playbook_executor.get_playbook_executor", return_value=executor):
                return await client.post(f"/orchestration/services/{name}/{action}", json={"node_id": "n1"})

        yield SimpleNamespace(post=post, executor=executor, who=who)


@pytest.mark.parametrize("action", _ACTIONS)
@pytest.mark.parametrize(
    "name",
    [
        "x;%20rm%20-rf%20~",
        "a%0Ab",
        "$(id)",
        "a&&b",
        "-H",
        "%7B%7B%207*7%20%7D%7D",
        "r%C3%A9dis",
        "redis%E2%80%90stack",
        "x" * 300,
    ],
)
async def test_a_hostile_name_is_422_and_no_playbook_runs(env, name, action):
    response = await env.post(name, action)

    assert response.status_code == 422, response.text
    env.executor.execute_playbook.assert_not_awaited()


@pytest.mark.parametrize("action", _ACTIONS)
async def test_a_valid_unit_name_still_reaches_the_playbook(env, action):
    response = await env.post("redis-stack.service", action)

    assert response.status_code == 200, response.text
    env.executor.execute_playbook.assert_awaited_once()
    assert env.executor.execute_playbook.await_args.kwargs["extra_vars"]["service_name"] == "redis-stack.service"


@pytest.mark.parametrize("action", _ACTIONS)
async def test_the_service_management_gate_is_unchanged(env, action):
    env.who["user"] = _USER

    response = await env.post("redis-stack.service", action)

    assert response.status_code == 403, response.text
    env.executor.execute_playbook.assert_not_awaited()
