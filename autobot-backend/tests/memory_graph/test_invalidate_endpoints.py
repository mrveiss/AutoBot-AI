# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for PATCH /memory/entities/{entity_id}/invalidate
and  PATCH /memory/relations/invalidate REST endpoints.

Issue #3810.
"""

import sys
import types
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from autobot_shared.time_utils import now_utc

# ---------------------------------------------------------------------------
# Stub heavy dependencies so api/memory.py imports without a real Redis
# ---------------------------------------------------------------------------


def _register_stub(name: str, attrs: dict | None = None) -> types.ModuleType:
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
    if attrs:
        for k, v in attrs.items():
            setattr(mod, k, v)
    sys.modules[name] = mod
    return mod


# autobot_shared package stubs
_autobot_shared = _register_stub("autobot_shared")
_autobot_shared.__path__ = []

_register_stub(
    "autobot_shared.redis_client",
    {"get_redis_client": MagicMock(return_value=None)},
)
_redis_mgmt = _register_stub("autobot_shared.redis_management")
_redis_mgmt.__path__ = []
_register_stub(
    "autobot_shared.redis_management.types",
    {"DATABASE_MAPPING": {"knowledge": 2}},
)
_cfg = MagicMock()
_cfg.vm.redis = "127.0.0.1"
_register_stub("autobot_shared.ssot_config", {"config": _cfg})


# error_boundaries stub — with_error_handling is a pass-through decorator
def _with_error_handling(**_kw):
    def decorator(fn):
        return fn

    return decorator


_eb_mod = _register_stub(
    "autobot_shared.error_boundaries",
    {
        "with_error_handling": _with_error_handling,
        "ErrorCategory": MagicMock(SERVER_ERROR="SERVER_ERROR"),
    },
)

# auth_middleware stub — always approves
_auth_mod = _register_stub("auth_middleware", {"check_admin_permission": MagicMock(return_value=True)})

# type_defs.common stub
_type_defs = _register_stub("type_defs")
_type_defs.__path__ = []
_register_stub("type_defs.common", {"Metadata": dict})

# utils.request_utils stub
_utils = _register_stub("utils")
_utils.__path__ = []
_utils_req = _register_stub("utils.request_utils")

_req_counter = 0


def _generate_request_id() -> str:
    global _req_counter
    _req_counter += 1
    return f"test-req-{_req_counter:04d}"


_utils_req.generate_request_id = _generate_request_id

# autobot_memory_graph stub — provide a minimal AutoBotMemoryGraph class
_mg_pkg = _register_stub("autobot_memory_graph")
_mg_pkg.__path__ = []


class _FakeMemoryGraph:
    initialized = True
    redis_client = MagicMock()
    knowledge_base = None


_mg_pkg.AutoBotMemoryGraph = _FakeMemoryGraph

# ---------------------------------------------------------------------------
# Import the router under test AFTER stubs are registered
# ---------------------------------------------------------------------------
from api.memory import router  # noqa: E402

# ---------------------------------------------------------------------------
# FastAPI test app
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(router, prefix="/memory")


def _make_client(fake_graph: _FakeMemoryGraph) -> TestClient:
    """Return a TestClient whose app.state.memory_graph is the fake graph."""

    async def override_memory_graph():
        return fake_graph

    from api.memory import get_memory_graph

    app.dependency_overrides[get_memory_graph] = override_memory_graph

    # Bypass admin check
    from auth_middleware import check_admin_permission

    app.dependency_overrides[check_admin_permission] = lambda: True

    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests — PATCH /memory/entities/{entity_id}/invalidate
# ---------------------------------------------------------------------------


class TestInvalidateEntityEndpoint:
    def _make_graph(self, invalidate_return: bool) -> _FakeMemoryGraph:
        graph = _FakeMemoryGraph()
        graph.invalidate_entity = AsyncMock(return_value=invalidate_return)
        return graph

    def test_returns_200_when_entity_found(self):
        graph = self._make_graph(True)
        client = _make_client(graph)
        resp = client.patch(
            "/memory/entities/aaaa-1111-2222-3333/invalidate",
            json={},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["entity_id"] == "aaaa-1111-2222-3333"
        assert body["data"]["invalidated"] is True
        assert body["data"]["valid_to"] is not None

    def test_returns_404_when_entity_not_found(self):
        graph = self._make_graph(False)
        client = _make_client(graph)
        resp = client.patch(
            "/memory/entities/nonexistent-uuid/invalidate",
            json={},
        )
        assert resp.status_code == 404

    def test_custom_ended_at_is_forwarded(self):
        graph = self._make_graph(True)
        client = _make_client(graph)
        custom_ts = "2025-06-01T00:00:00+00:00"
        resp = client.patch(
            "/memory/entities/aaaa-1111-2222-3333/invalidate",
            json={"ended_at": custom_ts},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["valid_to"] == custom_ts
        graph.invalidate_entity.assert_awaited_once_with(
            entity_id="aaaa-1111-2222-3333",
            ended_at=custom_ts,
        )

    def test_default_ended_at_is_utc_now(self):
        graph = self._make_graph(True)
        client = _make_client(graph)
        before = now_utc()
        resp = client.patch(
            "/memory/entities/aaaa-1111-2222-3333/invalidate",
            json={},
        )
        after = now_utc()
        assert resp.status_code == 200
        valid_to_str = resp.json()["data"]["valid_to"]
        valid_to = datetime.fromisoformat(valid_to_str)
        assert before <= valid_to <= after

    def test_empty_body_is_accepted(self):
        """Omitting the body entirely should still work (ended_at defaults to now)."""
        graph = self._make_graph(True)
        client = _make_client(graph)
        resp = client.patch("/memory/entities/aaaa-1111/invalidate")
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tests — PATCH /memory/relations/invalidate
# ---------------------------------------------------------------------------


class TestInvalidateRelationEndpoint:
    _VALID_BODY = {
        "from_id": "from-uuid-1111",
        "relation_type": "depends_on",
        "to_id": "to-uuid-2222",
    }

    def _make_graph(self, invalidate_return: bool) -> _FakeMemoryGraph:
        graph = _FakeMemoryGraph()
        graph.invalidate_relation = AsyncMock(return_value=invalidate_return)
        return graph

    def test_returns_200_when_relation_found(self):
        graph = self._make_graph(True)
        client = _make_client(graph)
        resp = client.patch("/memory/relations/invalidate", json=self._VALID_BODY)
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"]["from_id"] == self._VALID_BODY["from_id"]
        assert body["data"]["relation_type"] == self._VALID_BODY["relation_type"]
        assert body["data"]["to_id"] == self._VALID_BODY["to_id"]
        assert body["data"]["invalidated"] is True
        assert body["data"]["valid_to"] is not None

    def test_returns_404_when_relation_not_found(self):
        graph = self._make_graph(False)
        client = _make_client(graph)
        resp = client.patch("/memory/relations/invalidate", json=self._VALID_BODY)
        assert resp.status_code == 404

    def test_custom_ended_at_is_forwarded(self):
        graph = self._make_graph(True)
        client = _make_client(graph)
        custom_ts = "2025-07-01T09:00:00+00:00"
        body = {**self._VALID_BODY, "ended_at": custom_ts}
        resp = client.patch("/memory/relations/invalidate", json=body)
        assert resp.status_code == 200
        assert resp.json()["data"]["valid_to"] == custom_ts
        graph.invalidate_relation.assert_awaited_once_with(
            from_id=self._VALID_BODY["from_id"],
            relation_type=self._VALID_BODY["relation_type"],
            to_id=self._VALID_BODY["to_id"],
            ended_at=custom_ts,
        )

    def test_default_ended_at_is_utc_now(self):
        graph = self._make_graph(True)
        client = _make_client(graph)
        before = now_utc()
        resp = client.patch("/memory/relations/invalidate", json=self._VALID_BODY)
        after = now_utc()
        assert resp.status_code == 200
        valid_to_str = resp.json()["data"]["valid_to"]
        valid_to = datetime.fromisoformat(valid_to_str)
        assert before <= valid_to <= after

    def test_missing_required_fields_returns_422(self):
        graph = self._make_graph(True)
        client = _make_client(graph)
        resp = client.patch(
            "/memory/relations/invalidate",
            json={"from_id": "only-from-id"},
        )
        assert resp.status_code == 422
