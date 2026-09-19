# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /api/monitoring/gpu/nodes: the route, its three states, and its guards (#16281).

The state cases drive the real router through a TestClient, with the database
and the user dependency overridden. The guard comes from two places, and each
is pinned:

* the route's own ``get_current_user``. Here it is overridden with a dependency
  that needs real bearer credentials, so an anonymous request is refused. If
  the route ever dropped that dependency, the override would stop applying and
  the anonymous request would succeed -- failing the test.
* the mount. ``api/__init__.py`` mounts the GPU router on ``monitoring_router``,
  and ``main.py`` includes that router with ``dependencies=_SM``
  (``require_service_management``). Both are read from source, the way
  ``test_prometheus_scrape_is_unauthenticated_14339.py`` reads ``main.py``.
"""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from fastapi import Depends, FastAPI, status  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import gpu as gpu_api  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[2]
_PATH = "/api/monitoring/gpu/nodes"
_SIGNED_IN = {"Authorization": "Bearer test-token"}
_BEARER = HTTPBearer()

RTX = {
    "device_type": "nvidia-gpu",
    "index": 0,
    "name": "NVIDIA GeForce RTX 4070 Laptop GPU",
    "monitored": True,
    "utilization_percent": 12.0,
    "memory_used_mb": 2047.0,
    "memory_total_mb": 8188.0,
    "temperature_celsius": 51.0,
    "power_watts": 1.9,
}


def _node(hostname: str, **extra) -> SimpleNamespace:
    return SimpleNamespace(
        node_id=f"id-{hostname}",
        hostname=hostname,
        status="online",
        extra_data=extra,
        last_heartbeat=datetime(2026, 9, 11, tzinfo=timezone.utc),
    )


class _Db:
    def __init__(self, nodes):
        self._nodes = nodes

    async def execute(self, _statement):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: self._nodes))


async def _requires_bearer(credentials: HTTPAuthorizationCredentials = Depends(_BEARER)) -> dict:
    return {"sub": "tester"}


def _client(nodes) -> TestClient:
    app = FastAPI()
    app.include_router(gpu_api.router, prefix="/api/monitoring")

    async def _db():
        yield _Db(nodes)

    app.dependency_overrides[gpu_api.get_db] = _db
    app.dependency_overrides[gpu_api.get_current_user] = _requires_bearer
    return TestClient(app)


def _states(nodes) -> list[tuple[str, str]]:
    body = _client(nodes).get(_PATH, headers=_SIGNED_IN).json()
    assert body["total"] == len(nodes)
    return [(entry["hostname"], entry["state"]) for entry in body["nodes"]]


def test_a_node_reporting_devices_is_present_with_them():
    body = _client([_node("worker-1", gpu=[RTX])]).get(_PATH, headers=_SIGNED_IN).json()

    [entry] = body["nodes"]
    assert entry["state"] == "present"
    assert entry["devices"][0]["device_type"] == "nvidia-gpu"
    assert entry["devices"][0]["memory_total_mb"] == 8188.0


def test_an_empty_probe_is_none_present():
    assert _states([_node("worker-1", gpu=[])]) == [("worker-1", "none")]


def test_a_node_without_the_key_is_not_reported():
    assert _states([_node("worker-1")]) == [("worker-1", "not_reported")]


def test_an_anonymous_request_is_refused():
    """HTTPBearer refuses a missing Authorization header before the handler runs.

    FastAPI answered that with 403 for years and moved to 401 later; either is
    a refusal, which is what this pins -- a 200 here would mean the route lost
    its user dependency.
    """
    response = _client([_node("worker-1", gpu=[RTX])]).get(_PATH)

    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


def _include_router_calls(tree: ast.Module, receiver: str) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == receiver
    ]


def test_the_router_is_mounted_on_the_monitoring_router():
    tree = ast.parse((_BACKEND / "api" / "__init__.py").read_text(encoding="utf-8"))

    mounts = _include_router_calls(tree, "monitoring_router")

    assert [ast.unparse(call.args[0]) for call in mounts] == ["gpu_router"]


def test_main_includes_the_monitoring_router_behind_service_management():
    tree = ast.parse((_BACKEND / "main.py").read_text(encoding="utf-8"))

    [include] = [
        call for call in _include_router_calls(tree, "app") if ast.unparse(call.args[0]) == "monitoring_router"
    ]
    keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in include.keywords}
    [guard] = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_SM" for t in node.targets)
    ]

    assert keywords.get("dependencies") == "_SM"
    assert "require_service_management" in ast.unparse(guard.value)
