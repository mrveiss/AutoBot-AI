# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Empty Chroma collections: read-only report, admin-only route, removal only after approval (#19725)."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.knowledge_chroma_empty as route
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from models.approval import Approval, ApprovalComment
from services import approval_execution
from services import chroma_empty_collections as svc
from services.approval_gate_service import ApprovalGateService
from testkit.canonical_gate import canonical_resolver, real_admin_gate
from testkit.fake_approval_session import ApprovalClaimSession
from testkit.fake_async_session import FakeAsyncSession

_ADMIN = {"username": "admin", "role": "admin", "user_id": "admin-1"}
_URL = "/api/empty-collections"


class _Collection:
    def __init__(self, count):
        self._count = count

    async def count(self):
        if isinstance(self._count, Exception):
            raise self._count
        return self._count


class _Client:
    def __init__(self, counts):
        self.collections = {name: _Collection(c) for name, c in counts.items()}
        self.deleted = []

    async def list_collections(self):
        return list(self.collections)

    async def get_collection(self, name):
        return self.collections[name]

    async def get_collection_or_none(self, name):
        return self.collections.get(name)

    async def delete_collection(self, name):
        self.deleted.append(name)
        del self.collections[name]


@pytest.fixture
def chroma(monkeypatch):
    def build(counts):
        client = _Client(counts)

        async def _get():
            return client

        monkeypatch.setattr(svc, "get_async_chromadb_client", _get)
        return client

    return build


def _client(session=None) -> TestClient:
    app = FastAPI()
    app.include_router(route.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: _ADMIN
    app.dependency_overrides[get_db_session] = lambda: session or FakeAsyncSession(assign_ids=uuid.uuid4)
    return TestClient(app)


def _as_admin():
    auth = MagicMock()
    auth.get_user_from_request.return_value = _ADMIN
    return canonical_resolver("auth_rbac.resolve_human_user", auth)


def test_the_report_names_empty_collections_and_keeps_unreadable_ones_apart(chroma):
    client = chroma({"docs": 5, "work_item_a": 0, "broken": RuntimeError("down")})
    with _as_admin():
        response = _client().get(_URL)
    assert response.status_code == 200, response.text
    assert response.json() == {"total": 3, "empty": ["work_item_a"], "unreadable": ["broken"]}
    assert client.deleted == [], "the report is read-only"


def test_a_non_admin_is_refused_on_both_routes(chroma):
    chroma({"work_item_a": 0})
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"username": "u2", "role": "user", "user_id": "u2"}
    with real_admin_gate(auth) as wire:
        client = wire(_client())
        assert client.get(_URL).status_code in (401, 403)
        assert client.post(f"{_URL}/cleanup-requests", json={"collection": "work_item_a"}).status_code in (401, 403)


def test_a_proposal_is_pending_and_deletes_nothing(chroma, monkeypatch):
    client = chroma({"work_item_a": 0})
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, event, approval: _noop())
    session = FakeAsyncSession(assign_ids=uuid.uuid4)
    with _as_admin():
        response = _client(session).post(f"{_URL}/cleanup-requests", json={"collection": "work_item_a"})
    assert response.status_code == 201, response.text
    approval = next(o for o in session.added if isinstance(o, Approval))
    assert approval.status == "pending" and approval.approval_type == "destructive_action"
    assert approval.context == {"action": "chroma_empty_collection_delete", "collection": "work_item_a"}
    assert client.deleted == []


def test_a_collection_holding_vectors_cannot_be_proposed(chroma):
    chroma({"docs": 5})
    with _as_admin():
        response = _client().post(f"{_URL}/cleanup-requests", json={"collection": "docs"})
    assert response.status_code == 409


@pytest.fixture
def chain(monkeypatch):
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, event, approval: _noop())

    async def _audit_log(operation, **kwargs):
        return True

    monkeypatch.setattr(approval_execution, "audit_log", _audit_log)
    monkeypatch.setattr("services.kb_cleanup_proposals.audit_log", _audit_log)
    svc.register_empty_collection_delete()


async def _propose_and_decide(session, approve):
    proposal = await route.propose_empty_collection_cleanup(
        route.EmptyCollectionCleanupRequest(collection="work_item_a"), current_user=_ADMIN, session=session
    )
    gate = ApprovalGateService(session)
    decide = gate.approve if approve else gate.reject
    await decide(uuid.UUID(proposal.approval_id), decided_by="alice", author_type="human", comment=None)


@pytest.mark.asyncio
async def test_only_an_approved_proposal_deletes_the_collection(chroma, chain):
    client = chroma({"work_item_a": 0})
    session = ApprovalClaimSession()
    await _propose_and_decide(session, approve=True)
    assert client.deleted == ["work_item_a"]
    assert any(isinstance(o, ApprovalComment) and "done" in o.body for o in session.added)


@pytest.mark.asyncio
async def test_a_rejected_proposal_deletes_nothing(chroma, chain):
    client = chroma({"work_item_a": 0})
    await _propose_and_decide(ApprovalClaimSession(), approve=False)
    assert client.deleted == []


@pytest.mark.asyncio
async def test_a_collection_filled_after_the_proposal_is_not_deleted(chroma):
    client = chroma({"work_item_a": 3})
    done, reason = await svc.delete_empty_collection("work_item_a")
    assert done is False and "3 vector" in reason
    assert client.deleted == []


async def _noop():
    return None
