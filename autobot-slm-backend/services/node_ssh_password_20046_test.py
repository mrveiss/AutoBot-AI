# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20046: enrollment proposes deleting the stored SSH password; only the internal route deletes it.

The package conftest stubs ``services.*``, so the real modules are loaded from disk by path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_KEY = "k" * 40  # pragma: allowlist secret
_SECRET = "hunter2-fake"  # pragma: allowlist secret


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load("models.schemas_node_ssh_password", "models/schemas_node_ssh_password.py")  # `models` is a conftest stub
ssh = _load("node_ssh_password_under_20046_test", "services/node_ssh_password.py")
route = _load("node_ssh_password_internal_under_20046_test", "api/node_ssh_password_internal.py")


def _node(extra: dict | None) -> SimpleNamespace:
    return SimpleNamespace(node_id="node-a", extra_data=extra)


class _Client:
    """Stands in for the node client; records the call, never touches the network."""

    def __init__(self, response=None, error: Exception | None = None):
        self.post = AsyncMock(side_effect=error, return_value=response)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _configure(monkeypatch, client: _Client) -> None:
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)
    monkeypatch.setattr(ssh.node_proxy, "resolve_node_url", lambda fallback="": "https://backend.invalid")
    monkeypatch.setattr(ssh.node_proxy, "node_client", lambda **_: client)


def _ok() -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    return response


async def test_a_node_with_a_stored_password_proposes_by_name_never_by_value(monkeypatch) -> None:
    client = _Client(_ok())
    _configure(monkeypatch, client)
    assert await ssh.propose_password_deletion(_node({"ssh_password": _SECRET, "ssh_password_encrypted": True})) is True
    assert client.post.await_count == 1
    kwargs = client.post.await_args.kwargs
    assert kwargs["json"] == {"node_id": "node-a", "credential_kind": "ssh_password"}
    assert kwargs["headers"]["X-Internal-API-Key"] == _KEY
    assert _SECRET not in str(client.post.await_args)


@pytest.mark.parametrize("extra", [None, {}, {"ssh_password": ""}, {"other": 1}])
async def test_a_node_without_a_stored_password_proposes_nothing(monkeypatch, extra) -> None:
    client = _Client(_ok())
    _configure(monkeypatch, client)
    assert await ssh.propose_password_deletion(_node(extra)) is False
    client.post.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")],
    ids=["backend-down", "backend-slow"],
)
async def test_an_unreachable_backend_does_not_fail_enrollment(monkeypatch, caplog, error) -> None:
    _configure(monkeypatch, _Client(error=error))
    with caplog.at_level("ERROR"):
        assert await ssh.propose_password_deletion(_node({"ssh_password": _SECRET})) is False
    assert "not proposed" in caplog.text and _SECRET not in caplog.text


async def test_a_backend_refusal_is_logged_not_raised(monkeypatch, caplog) -> None:
    response = _ok()
    request = httpx.Request("POST", "https://backend.invalid/x")
    response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "no", request=request, response=httpx.Response(403, request=request)
    )
    _configure(monkeypatch, _Client(response))
    with caplog.at_level("ERROR"):
        assert await ssh.propose_password_deletion(_node({"ssh_password": _SECRET})) is False
    assert "HTTP 403" in caplog.text


async def test_an_unset_key_proposes_nothing_and_says_so(monkeypatch, caplog) -> None:
    client = _Client(_ok())
    _configure(monkeypatch, client)
    monkeypatch.delenv("AUTOBOT_INTERNAL_API_KEY")
    with caplog.at_level("WARNING"):
        assert await ssh.propose_password_deletion(_node({"ssh_password": _SECRET})) is False
    client.post.assert_not_awaited()
    assert "not proposed" in caplog.text


# --- deletion -------------------------------------------------------------


def _db(node) -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: node))
    return db


async def test_delete_removes_only_the_password_fields_of_that_node() -> None:
    node = _node({"ssh_password": _SECRET, "ssh_password_encrypted": True, "keep": "me"})
    db = _db(node)
    assert await ssh.delete_stored_password(db, "node-a") is True
    assert node.extra_data == {"keep": "me"}
    db.commit.assert_awaited_once()


async def test_delete_with_nothing_stored_changes_nothing() -> None:
    node, db = _node({"keep": "me"}), _db(_node({"keep": "me"}))
    db = _db(node)
    assert await ssh.delete_stored_password(db, "node-a") is False
    db.commit.assert_not_awaited()


async def test_delete_for_an_unknown_node_is_none() -> None:
    assert await ssh.delete_stored_password(_db(None), "ghost") is None


# --- the internal route -----------------------------------------------------


def _app(monkeypatch, node) -> TestClient:
    monkeypatch.setenv("AUTOBOT_INTERNAL_API_KEY", _KEY)
    app = FastAPI()
    app.include_router(route.router, prefix="/api")
    app.dependency_overrides[route.get_db] = lambda: _db(node)
    return TestClient(app)


def test_the_route_is_refused_without_the_key(monkeypatch) -> None:
    node = _node({"ssh_password": _SECRET})
    client = _app(monkeypatch, node)
    for headers in ({}, {"X-Internal-API-Key": "wrong"}, {"Authorization": "Bearer user-token"}):
        assert client.delete("/api/internal/nodes/node-a/ssh-password", headers=headers).status_code == 403
    assert node.extra_data == {"ssh_password": _SECRET}


def test_the_route_refuses_everyone_when_no_key_is_configured(monkeypatch) -> None:
    client = _app(monkeypatch, _node({"ssh_password": _SECRET}))
    monkeypatch.delenv("AUTOBOT_INTERNAL_API_KEY")
    assert (
        client.delete("/api/internal/nodes/node-a/ssh-password", headers={"X-Internal-API-Key": ""}).status_code == 403
    )


def test_the_route_deletes_and_returns_no_value(monkeypatch) -> None:
    node = _node({"ssh_password": _SECRET, "ssh_password_encrypted": True})
    response = _app(monkeypatch, node).delete(
        "/api/internal/nodes/node-a/ssh-password", headers={"X-Internal-API-Key": _KEY}
    )
    assert response.status_code == 200 and response.json() == {"node_id": "node-a", "deleted": True}
    assert _SECRET not in response.text and node.extra_data == {}


def test_the_route_answers_404_for_an_unknown_node(monkeypatch) -> None:
    response = _app(monkeypatch, None).delete(
        "/api/internal/nodes/ghost/ssh-password", headers={"X-Internal-API-Key": _KEY}
    )
    assert response.status_code == 404


# --- wiring -------------------------------------------------------------------


def test_the_stored_password_is_deleted_only_in_the_one_module_the_route_calls() -> None:
    """The deleting module is named; nothing else in api/ or services/ may call it but the route."""
    callers = {
        path.name
        for tree in ("api", "services")
        for path in (_ROOT / tree).rglob("*.py")
        if not path.name.endswith("_test.py") and "delete_stored_password" in path.read_text(encoding="utf-8")
    }
    assert callers == {"node_ssh_password.py", "node_ssh_password_internal.py"}


def test_enrollment_success_proposes_after_the_commit_and_never_deletes() -> None:
    source = (_ROOT / "services" / "deployment.py").read_text(encoding="utf-8")
    body = source[source.index("async def _handle_enrollment_success") :].split("\n    async def ")[0]
    assert body.index("await db.commit()") < body.index("await propose_password_deletion(node)")
    assert "delete_stored_password" not in source
