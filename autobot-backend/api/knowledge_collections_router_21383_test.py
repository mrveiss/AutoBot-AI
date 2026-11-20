# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#21383: the two collection delete routes sit behind the REAL admin gate and the real ``get_current_user``.

The handler tests call the functions directly, so the router dependencies never run there. Here the REAL auth stack
answers through a ``TestClient``; only the identity it reads, the knowledge base and the database are stood in
(auth is under test, not transactions). An unapproved call deletes nothing and files exactly one proposal.
"""

from __future__ import annotations

import importlib
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services import kb_collection_delete_action as action
from services.approval_gate_service import ApprovalGateService
from testkit.fake_async_session import FakeAsyncSession
from tests.conftest import load_real_auth_middleware

_INTERNAL_KEY = {"X-Internal-API-Key": "internal-service-key-for-tests"}
_APPROVAL_ID = uuid.UUID("00000000-0000-4000-8000-000000021383")
_ROUTES = {
    "delete": ("DELETE", "/api/knowledge_base/collections/c1?delete_facts=true", "kb_collection_delete"),
    "bulk": ("POST", "/api/knowledge_base/collections/c1/bulk-delete?confirm=true", "kb_collection_bulk_delete"),
}


class _KB:
    """One collection; every delete is recorded, reads are not."""

    def __init__(self) -> None:
        self.mutations: list = []

    async def get_collection(self, collection_id):
        return {"success": True, "collection": {"name": "Notes", "created_at": "t1"}}

    async def bulk_delete_collection_facts(self, collection_id, confirm=False, approved=None):
        if confirm:
            self.mutations.append(("bulk", collection_id))
        return {"success": True, "facts_to_delete": 3, "deleted_count": 3 if confirm else 0}

    async def delete_collection(self, collection_id, delete_facts=False, approved=None):
        self.mutations.append(("delete", collection_id))
        return {"success": True}


def _person(role: str, user_id: str | None = None) -> dict:
    uid = user_id or str(uuid.uuid4())
    return {"username": role, "role": role, "user_id": uid, "id": uid, "auth_method": "jwt"}


@pytest.fixture
def client(monkeypatch):
    """A client whose gate is the production code; ``identity.user`` is the human it resolves."""
    real = load_real_auth_middleware()
    monkeypatch.setitem(sys.modules, "auth_middleware", real)
    monkeypatch.delitem(sys.modules, "api.knowledge_collections", raising=False)
    routes = importlib.import_module("api.knowledge_collections")
    identity = SimpleNamespace(user=None)
    monkeypatch.setattr(real, "resolve_human_user", AsyncMock(side_effect=lambda _request: identity.user))
    monkeypatch.setattr(
        real, "verify_internal_api_key", lambda provided: provided == _INTERNAL_KEY["X-Internal-API-Key"]
    )
    kb = _KB()
    monkeypatch.setattr(routes, "get_or_create_knowledge_base", AsyncMock(return_value=kb))
    monkeypatch.setattr(action, "_pending_proposal", AsyncMock(return_value=None))
    created = SimpleNamespace(id=_APPROVAL_ID, status="pending")
    create = AsyncMock(return_value=created)
    monkeypatch.setattr(ApprovalGateService, "create_approval", create)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/knowledge_base")
    app.dependency_overrides[routes.get_db_session] = lambda: FakeAsyncSession()
    yield TestClient(app, raise_server_exceptions=False), identity, kb, create
    sys.modules.pop("api.knowledge_collections", None)


@pytest.mark.parametrize(("method", "path", "_action"), _ROUTES.values(), ids=list(_ROUTES))
def test_an_anonymous_caller_is_401_and_nothing_happens(client, method, path, _action) -> None:
    test_client, _, kb, create = client
    assert test_client.request(method, path).status_code == 401
    assert kb.mutations == [] and create.await_count == 0


@pytest.mark.parametrize(("method", "path", "_action"), _ROUTES.values(), ids=list(_ROUTES))
def test_a_non_admin_is_403_and_nothing_happens(client, method, path, _action) -> None:
    test_client, identity, kb, create = client
    identity.user = _person("user")
    assert test_client.request(method, path).status_code == 403
    assert kb.mutations == [] and create.await_count == 0


@pytest.mark.parametrize(("method", "path", "_action"), _ROUTES.values(), ids=list(_ROUTES))
def test_the_internal_key_alone_is_refused(client, method, path, _action) -> None:
    test_client, _, kb, create = client
    # not opted in (service_opt_in) and no human behind it: AUTH_0002, which the error catalogue maps to 401
    assert test_client.request(method, path, headers=_INTERNAL_KEY).status_code == 401
    assert kb.mutations == [] and create.await_count == 0


@pytest.mark.parametrize(("method", "path", "name"), _ROUTES.values(), ids=list(_ROUTES))
def test_an_admin_call_deletes_nothing_and_files_exactly_one_proposal(client, method, path, name) -> None:
    test_client, identity, kb, create = client
    identity.user = _person("admin")
    reply = test_client.request(method, path)
    assert reply.status_code == 200, reply.text
    assert reply.json()["approval_id"] == str(_APPROVAL_ID) and reply.json()["action"] == name
    assert kb.mutations == [] and create.await_count == 1
    assert create.await_args.kwargs["context"]["action"] == name
    assert create.await_args.kwargs["approval_type"] == "destructive_action"


@pytest.mark.parametrize(("method", "path", "_action"), _ROUTES.values(), ids=list(_ROUTES))
def test_an_admin_service_key_user_id_that_is_not_a_user_is_403_and_files_nothing(
    client, method, path, _action
) -> None:
    test_client, identity, kb, create = client
    identity.user = _person("admin", user_id="svc-key")
    assert test_client.request(method, path).status_code == 403
    assert kb.mutations == [] and create.await_count == 0
