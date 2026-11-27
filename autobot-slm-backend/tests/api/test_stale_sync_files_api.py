# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The stale code-sync file routes through a real FastAPI app: who may call them and what they answer (#22033).

``api/stale_sync_files.py`` and ``api/stale_sync_files_internal.py`` are loaded by path with the service layer
stubbed; FastAPI, pydantic, the response schemas and the real internal-key check are real.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[2]
_KEY = "k" * 40  # pragma: allowlist secret
_APPROVAL = "00000000-0000-4000-8000-000000000055"


class _Refused(Exception):
    def __init__(self, status_code: int, reason: str):
        super().__init__(reason)
        self.status_code, self.reason = status_code, reason


class _Unavailable(Exception):
    def __init__(self, status_code: int = 503, detail: str = "backend down"):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


def _module(monkeypatch, name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


def _load(monkeypatch, name: str, relative: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, _BACKEND / relative)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, name, mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)
    state = SimpleNamespace(admin=True, calls=[], refuse=None, unavailable=False)

    async def get_current_user() -> dict:
        if not state.admin:
            raise HTTPException(status_code=403, detail="This console is for administrators.")
        return {"sub": "alice"}

    async def get_db():
        yield object()

    async def list_stale_files(_db, node_id):
        state.calls.append(("list", node_id))
        item = SimpleNamespace(
            old_target="/srv",
            role="backend",
            path="a.py",
            size_bytes=3,
            modified_at="2026-01-02T00:00:00Z",
            blob="a" * 40,
        )
        return SimpleNamespace(commit="c0ffee1", stale=[item], kept=[], error=None)

    async def propose_cleanup(_db, node_id, actor):
        state.calls.append(("propose", node_id, actor))
        if state.unavailable:
            raise _Unavailable()
        return [
            {
                "old_target": "/srv",
                "approval_id": "ap1",
                "status": "pending",
                "created": True,
                "proposed": 1,
                "total_found": 1,
            }
        ]

    async def remove_approved(_db, node_id, approval_id):
        state.calls.append(("remove", node_id, approval_id))
        if state.refuse:
            raise _Refused(state.refuse, "the approval does not authorize this removal")
        return [{"old_target": "/srv", "path": "a.py", "result": "removed"}]

    _module(monkeypatch, "sqlalchemy.ext.asyncio", AsyncSession=type("AsyncSession", (), {}))
    _module(monkeypatch, "services.auth", get_current_user=get_current_user)
    _module(monkeypatch, "services.database", get_db=get_db)
    _module(monkeypatch, "services.main_backend_client", MainBackendUnavailable=_Unavailable)
    _module(
        monkeypatch,
        "services.stale_sync_files",
        StaleRefused=_Refused,
        list_stale_files=list_stale_files,
        propose_cleanup=propose_cleanup,
        remove_approved=remove_approved,
    )
    _load(monkeypatch, "models.schemas_stale_sync_files", "models/schemas_stale_sync_files.py")
    admin = _load(monkeypatch, "_stale_sync_files_api_under_test", "api/stale_sync_files.py")
    internal = _load(monkeypatch, "_stale_sync_files_internal_under_test", "api/stale_sync_files_internal.py")
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/code-sync")
    app.include_router(internal.router, prefix="/api")
    state.client = TestClient(app, raise_server_exceptions=False)
    return state


def test_an_admin_lists_the_files_read_only(env) -> None:
    response = env.client.get("/api/code-sync/stale-files/n1")
    assert response.status_code == 200 and response.json()["total_stale"] == 1
    assert response.json()["stale"][0]["path"] == "a.py" and env.calls == [("list", "n1")]


def test_a_non_admin_can_neither_list_nor_propose_and_nothing_runs(env) -> None:
    env.admin = False
    assert env.client.get("/api/code-sync/stale-files/n1").status_code == 403
    assert env.client.post("/api/code-sync/stale-files/n1/proposal").status_code == 403
    assert env.calls == []


def test_the_admin_trigger_proposes_once_per_location_and_names_the_admin(env) -> None:
    response = env.client.post("/api/code-sync/stale-files/n1/proposal")
    assert response.status_code == 200 and response.json()["proposals"][0]["approval_id"] == "ap1"
    assert env.calls == [("propose", "n1", "alice")]


def test_an_unavailable_backend_is_a_503_and_not_a_proposal(env) -> None:
    env.unavailable = True
    response = env.client.post("/api/code-sync/stale-files/n1/proposal")
    assert response.status_code == 503 and "proposals" not in response.json()


def _remove(env, headers: dict | None = None):
    return env.client.post(
        f"/api/internal/nodes/n1/stale-sync-files/removal?approval_id={_APPROVAL}", headers=headers or {}
    )


def test_the_removal_route_needs_the_internal_key(env) -> None:
    assert _remove(env).status_code == 403
    assert _remove(env, {"X-Internal-API-Key": "wrong"}).status_code == 403
    assert env.calls == []
    ok = _remove(env, {"X-Internal-API-Key": _KEY})
    assert ok.status_code == 200 and ok.json()["removed"] == 1 and env.calls == [("remove", "n1", _APPROVAL)]


def test_a_refused_claim_surfaces_as_403_with_nothing_reported_removed(env) -> None:
    env.refuse = 403
    response = _remove(env, {"X-Internal-API-Key": _KEY})
    assert response.status_code == 403 and "removed" not in response.json()


def test_a_user_jwt_without_the_internal_key_is_refused_on_the_removal_route(env) -> None:
    response = _remove(env, {"Authorization": "Bearer eyJhbGciOiJSUzI1NiJ9.e30.sig"})  # pragma: allowlist secret
    assert response.status_code == 403 and env.calls == []
