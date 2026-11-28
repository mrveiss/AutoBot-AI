# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``/orchestration/fleet/services/{name}/{start,stop,restart}`` delegate to ``api.services`` (#18714).

The orchestration routes used to run their own Ansible path with the path's ``{name}`` as an
``extra_vars`` value and no unit-name check; neither ``execute_playbook`` nor ``manage-service.yml``
constrains it. They now call the ``api.services`` handler (the validated, canonical one) and carry
its route dependencies, so one executor path remains and the 422 comes with it.

The real ``services.auth`` (the gate is the real decision) and the real ORM are loaded.
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


_fake_db = types.ModuleType("services.database")
_fake_db.get_db = _real_get_db
_fake_db.db_service = None

with patch.dict(sys.modules, {"services.auth": _auth, "services.database": _fake_db}):
    _services_api, _orchestration_api = import_modules_with_real_orm(import_names=("api.services", "api.orchestration"))

_ACTIONS = ("start", "stop", "restart")
_ADMIN = {"admin": True, "role": "admin", "sub": "root"}


def _fake_db(name: str) -> FakeAsyncSession:
    """Holds a service row for ANY name, so only validation can stop a hostile one."""
    return FakeAsyncSession(
        results=[[SimpleNamespace(service_name=name, node_id="n1")], [SimpleNamespace(node_id="n1")]]
    )


@pytest.fixture
async def env(monkeypatch):
    executor = MagicMock()
    executor.execute_playbook = AsyncMock(return_value={"success": True, "output": ""})
    ssh = AsyncMock(return_value=(True, "ok"))
    monkeypatch.setattr(_services_api, "run_ansible_service_action", ssh)
    monkeypatch.setattr(_services_api, "ws_manager", AsyncMock())
    app = FastAPI()
    app.include_router(_orchestration_api.fleet_router)
    app.dependency_overrides[_auth.get_current_user] = lambda: _ADMIN
    transport = httpx.ASGITransport(app=app)
    # Built in the fixture (setup phase): tests/api/conftest.py blocks httpx.AsyncClient in the call phase.
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:

        async def post(name: str, action: str):
            app.dependency_overrides[_orchestration_api.get_db] = lambda: _fake_db(name)
            # import_modules_with_real_orm restores sys.modules, so the handler's call-time
            # ``from api import services`` must find the instance imported above, not re-import it.
            with (
                patch.dict(sys.modules, {"api.services": _services_api}),
                patch("services.playbook_executor.get_playbook_executor", return_value=executor),
            ):
                return await client.post(f"/fleet/services/{name}/{action}")

        yield SimpleNamespace(post=post, executor=executor, ssh=ssh, app=app)


@pytest.mark.parametrize("action", _ACTIONS)
@pytest.mark.parametrize("name", ["x;%20rm%20-rf%20~", "a%0Ab", "$(id)", "a&&b", "-H", "x" * 300])
async def test_a_hostile_unit_name_is_422_and_no_executor_runs(env, name, action):
    response = await env.post(name, action)
    assert response.status_code == 422, response.text
    env.executor.execute_playbook.assert_not_awaited()
    env.ssh.assert_not_awaited()


@pytest.mark.parametrize("action", _ACTIONS)
async def test_a_path_traversal_name_never_reaches_an_executor(env, action):
    response = await env.post("..%2Fx", action)  # a decoded slash is routed away (404) before the guard
    assert response.status_code in (404, 422)
    env.executor.execute_playbook.assert_not_awaited()
    env.ssh.assert_not_awaited()


@pytest.mark.parametrize("action", _ACTIONS)
async def test_the_route_awaits_the_services_implementation_with_the_same_arguments(env, action, monkeypatch):
    canonical = AsyncMock(
        return_value=_services_api.FleetServiceActionResponse(
            action=action, service_name="redis.service", node_id="fleet", success=True, message="m"
        )
    )
    monkeypatch.setattr(_services_api, f"{action}_fleet_service", canonical)
    response = await env.post("redis.service", action)
    assert response.status_code == 200, response.text
    canonical.assert_awaited_once()
    name, db, principal = canonical.await_args.args
    assert (name, principal) == ("redis.service", _ADMIN)
    assert isinstance(db, FakeAsyncSession)
    assert response.json()["node_id"] == "fleet"


@pytest.mark.parametrize("action", _ACTIONS)
async def test_failure_diagnostics_survive_the_response_model_on_the_wire(env, action, monkeypatch):
    """The route's response_model must be the fleet one, or FastAPI strips ``diagnostics`` (#18714)."""
    diagnostics = {"n1": "systemctl status: failed\njournal: boom"}
    canonical = AsyncMock(
        return_value=_services_api.FleetServiceActionResponse(
            action=action,
            service_name="redis.service",
            node_id="fleet",
            success=False,
            message="m",
            diagnostics=diagnostics,
        )
    )
    monkeypatch.setattr(_services_api, f"{action}_fleet_service", canonical)
    response = await env.post("redis.service", action)
    assert response.status_code == 200, response.text
    assert response.json()["diagnostics"] == diagnostics


@pytest.mark.parametrize("action", _ACTIONS)
async def test_a_valid_name_runs_the_single_services_executor_path(env, action):
    response = await env.post("redis.service", action)
    assert response.status_code == 200, response.text
    env.ssh.assert_awaited_once()
    assert env.ssh.await_args.args[1:] == ("redis.service", action)
    env.executor.execute_playbook.assert_not_awaited()
    assert response.json()["success"] is True


@pytest.mark.parametrize("action", _ACTIONS)
async def test_a_caller_without_service_management_is_403_and_nothing_runs(env, action):
    env.app.dependency_overrides[_auth.get_current_user] = lambda: {"admin": False, "role": "user", "sub": "m"}
    response = await env.post("redis.service", action)
    assert response.status_code == 403
    env.ssh.assert_not_awaited()
    env.executor.execute_playbook.assert_not_awaited()
