# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every quality route requires its source, and its data is that source's alone (#20513)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api import analytics_quality as mod
from api.codebase_analytics.endpoints import shared

#: Not about one source: the remediation loop's own history (written with no source).
_NOT_SOURCE_SCOPED = {"/remediation-deltas"}
_SCOPED_READS = ("health-score", "metrics", "patterns", "complexity", "trends", "snapshot", "export")


def _client(real_access: bool = False):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth_middleware import check_admin_permission

    app = FastAPI()
    app.include_router(mod.router)
    app.dependency_overrides[check_admin_permission] = lambda: True
    if not real_access:
        app.dependency_overrides[shared.require_source_access] = lambda: None
    return TestClient(app, raise_server_exceptions=False)


def test_every_source_scoped_quality_route_requires_source_id():
    seen = 0
    for route in mod.router.routes:
        if route.path in _NOT_SOURCE_SCOPED or not getattr(route, "dependant", None):
            continue
        query = {q.name: q for q in route.dependant.query_params}
        assert "source_id" in query and query["source_id"].field_info.is_required(), route.path
        seen += 1
    assert seen >= 8  # health-score, metrics, patterns, complexity, trends, snapshot, drill-down, export, ws


@pytest.mark.parametrize("route", [*_SCOPED_READS, "drill-down/complexity"])
def test_a_request_without_source_id_is_a_422(route):
    assert _client().get(f"/{route}").status_code == 422


@pytest.mark.parametrize("route", [*_SCOPED_READS, "drill-down/complexity"])
def test_a_source_with_no_checkout_is_a_404(route):
    with patch.object(shared, "resolve_source_root", AsyncMock(return_value=None)):
        assert _client().get(f"/{route}", params={"source_id": "missing"}).status_code == 404


@pytest.mark.parametrize("route", [*_SCOPED_READS, "drill-down/complexity"])
def test_a_foreign_private_source_is_a_404_with_access_enforcement_left_real(route, tmp_path):
    from api.codebase_analytics.source_models import CodeSource, SourceAccess

    private = CodeSource(name="p", clone_path="/tmp/p", owner_id="alice", access=SourceAccess.PRIVATE)
    with (
        patch("auth_middleware.get_current_user", AsyncMock(return_value={"id": "mallory"})),
        patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=private)),
        patch.object(shared, "resolve_source_root", AsyncMock(return_value=tmp_path)),
    ):
        assert _client(real_access=True).get(f"/{route}", params={"source_id": "x"}).status_code == 404


class _FakeRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def setex(self, key, _ttl, value):
        self.values[key] = value


@pytest.mark.asyncio
async def test_source_a_cached_quality_is_not_served_to_source_b(tmp_path):
    fake = _FakeRedis()
    calc = AsyncMock(side_effect=lambda source_root, source_id: {"metrics": {"x": 1}, "who": source_id})
    with (
        patch("autobot_shared.redis_client.get_redis_client", return_value=fake),
        patch.object(mod, "calculate_real_quality_metrics", calc),
    ):
        a = await mod.get_quality_data_from_storage(tmp_path, "a")
        b = await mod.get_quality_data_from_storage(tmp_path, "b")
    assert (a["who"], b["who"]) == ("a", "b")
    assert calc.await_count == 2
    assert sorted(fake.values) == ["code_quality:latest:a", "code_quality:latest:b"]


@pytest.mark.asyncio
async def test_health_history_is_kept_per_source():
    redis = MagicMock()
    redis.zadd, redis.zremrangebyrank = AsyncMock(), AsyncMock()
    with patch("autobot_shared.redis_client.get_async_redis_client", AsyncMock(return_value=redis)):
        await mod._persist_health_snapshot(70.0, {"a": 1.0}, "a")
    assert redis.zadd.call_args.args[0] == mod._health_history_key("a")
    assert mod._health_history_key("a") != mod._health_history_key("b")
    with pytest.raises(ValueError):
        mod._health_history_key("")


@pytest.mark.asyncio
async def test_the_problem_query_names_the_source():
    collection = MagicMock()
    collection.get = AsyncMock(return_value={"metadatas": []})
    with patch("api.codebase_analytics.storage.get_code_collection_async", AsyncMock(return_value=collection)):
        await mod._get_problems_from_chromadb(Path("/tmp/p"), "src-1")
    where = collection.get.await_args_list[0].kwargs["where"]
    assert {"source_id": "src-1"} in where["$and"] and {"type": "problem"} in where["$and"]


# --- review (#22090): the socket with the real dependency, refresh scope, and the runtime-risk map ---------


def _ws_app():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(mod.router)  # require_source_access is NOT overridden
    return app


def _ws_connect(user, source, source_id="x"):
    from starlette.testclient import TestClient

    with (
        patch("api.ws_security._resolve_ws_user", new=AsyncMock(return_value=user)),
        patch("api.codebase_analytics.source_storage.get_source", AsyncMock(return_value=source)),
        patch.object(mod, "get_quality_snapshot", AsyncMock(return_value={"marker": source_id})),
    ):
        session = TestClient(_ws_app()).websocket_connect(f"/ws?source_id={source_id}")
        with session as socket:
            return socket.receive_json()


def test_the_socket_connects_for_the_owner_with_the_real_dependency():
    admin_alice = {"username": "alice", "user_id": "alice", "role": "admin"}
    assert _ws_connect(admin_alice, _private_source())["type"] == "snapshot"


def test_the_socket_refuses_a_foreign_source_with_the_real_dependency():
    from starlette.websockets import WebSocketDisconnect

    admin_mallory = {"username": "mallory", "user_id": "mallory", "role": "admin"}
    with pytest.raises(WebSocketDisconnect) as closed:
        _ws_connect(admin_mallory, _private_source())
    assert closed.value.code == 1008


def test_the_socket_needs_a_source_id():
    from starlette.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    with patch("api.ws_security._resolve_ws_user", new=AsyncMock(return_value={"role": "admin", "user_id": "a"})):
        with pytest.raises(WebSocketDisconnect):
            with TestClient(_ws_app()).websocket_connect("/ws"):
                pass


def _private_source():
    from api.codebase_analytics.source_models import CodeSource, SourceAccess

    return CodeSource(name="p", clone_path="/tmp/p", owner_id="alice", access=SourceAccess.PRIVATE)


@pytest.mark.asyncio
async def test_a_refresh_reauthorizes_and_scopes_to_the_sockets_source():
    from fastapi import HTTPException

    socket = MagicMock(send_json=AsyncMock(), close=AsyncMock())
    data = {"_source_id": "x", "_user": {"user_id": "alice"}}
    with (
        patch.object(mod, "authorize_source_access", AsyncMock()) as authorize,
        patch.object(mod, "get_quality_snapshot", AsyncMock(return_value={"ok": 1})) as snapshot,
    ):
        await mod._handle_ws_refresh(socket, data)
    authorize.assert_awaited_once_with("x", data["_user"])
    snapshot.assert_awaited_once_with(source_id="x")
    with patch.object(mod, "authorize_source_access", AsyncMock(side_effect=HTTPException(404))):
        await mod._handle_ws_refresh(socket, data)
    socket.close.assert_awaited_once_with(code=1008)


def _build_checkout(tmp_path):
    (tmp_path / "in.py").write_text("x = 1\n", encoding="utf-8")
    outside = tmp_path.parent / "elsewhere.py"
    outside.write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "link.py").symlink_to(outside)


@pytest.mark.asyncio
async def test_the_runtime_risk_map_keeps_only_files_of_the_sources_checkout(tmp_path):
    from api.analytics_quality_runtime import runtime_risk_for_source

    _build_checkout(tmp_path)
    risk = {"in.py": 0.5, "absent.py": 0.9, "../elsewhere.py": 0.7, "link.py": 0.6}
    with patch("code_analysis.src.runtime_risk.build_runtime_risk_map", new=AsyncMock(return_value=risk)):
        assert await runtime_risk_for_source(tmp_path) == {"in.py": 0.5}
