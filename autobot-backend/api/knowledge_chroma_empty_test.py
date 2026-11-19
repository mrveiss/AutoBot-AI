# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Empty Chroma collections: read-only report, admin-only route, removal only after approval (#19725)."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import api.knowledge_chroma_empty as route
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from llc.kb.collections import KbCollectionManager
from models.approval import Approval, ApprovalComment
from services import approval_execution
from services import chroma_empty_collections as svc
from services.approval_gate_service import ApprovalGateService
from testkit.canonical_gate import canonical_resolver, real_admin_gate
from testkit.fake_approval_session import ApprovalClaimSession
from testkit.fake_async_session import FakeAsyncSession

_ADMIN = {"username": "admin", "role": "admin", "user_id": "admin-1"}
_URL = "/api/empty-collections"
_EMPTY = KbCollectionManager.collection_name(KbCollectionManager.WORK_ITEM_PREFIX, "a")
_DOCS = "autobot_docs"
_FOREIGN = "other_subsystem_vectors"


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

    async def delete_collection_if_empty(self, name):
        count = await self.collections[name].count()
        if count == 0:
            await self.delete_collection(name)
        return count


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
    client = chroma({_DOCS: 5, _EMPTY: 0, "autobot_lessons": RuntimeError("down")})
    with _as_admin():
        response = _client().get(_URL)
    assert response.status_code == 200, response.text
    assert response.json() == {"total": 3, "empty": [_EMPTY], "unreadable": ["autobot_lessons"]}
    assert client.deleted == [], "the report is read-only"


def test_a_non_admin_is_refused_on_both_routes(chroma):
    chroma({_EMPTY: 0})
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"username": "u2", "role": "user", "user_id": "u2"}
    with real_admin_gate(auth) as wire:
        client = wire(_client())
        assert client.get(_URL).status_code in (401, 403)
        assert client.post(f"{_URL}/cleanup-requests", json={"collection": _EMPTY}).status_code in (401, 403)


def test_a_proposal_is_pending_and_deletes_nothing(chroma, chain):
    client = chroma({_EMPTY: 0})
    session = FakeAsyncSession(assign_ids=uuid.uuid4)
    with _as_admin():
        response = _client(session).post(f"{_URL}/cleanup-requests", json={"collection": _EMPTY})
    assert response.status_code == 201, response.text
    approval = next(o for o in session.added if isinstance(o, Approval))
    assert approval.status == "pending" and approval.approval_type == "destructive_action"
    assert approval.context == {"action": "chroma_empty_collection_delete", "collection": _EMPTY}
    assert client.deleted == []


def test_a_collection_holding_vectors_cannot_be_proposed(chroma):
    chroma({_DOCS: 5})
    with _as_admin():
        response = _client().post(f"{_URL}/cleanup-requests", json={"collection": _DOCS})
    assert response.status_code == 409


@pytest.fixture
def chain(monkeypatch):
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, event, approval: _noop())

    audited = []

    async def _audit_log(operation, **kwargs):
        audited.append((operation, kwargs))
        return True

    monkeypatch.setattr(approval_execution, "audit_log", _audit_log)
    monkeypatch.setattr("services.kb_cleanup_proposals.audit_log", _audit_log)
    svc.register_empty_collection_delete()
    return audited


async def _propose(session):
    return await route.propose_empty_collection_cleanup(
        route.EmptyCollectionCleanupRequest(collection=_EMPTY), current_user=_ADMIN, session=session
    )


async def _propose_and_decide(session, approve):
    proposal = await _propose(session)
    gate = ApprovalGateService(session)
    decide = gate.approve if approve else gate.reject
    await decide(uuid.UUID(proposal.approval_id), decided_by="alice", author_type="human", comment=None)


@pytest.mark.asyncio
async def test_only_an_approved_proposal_deletes_the_collection(chroma, chain):
    client = chroma({_EMPTY: 0})
    session = ApprovalClaimSession()
    await _propose_and_decide(session, approve=True)
    assert client.deleted == [_EMPTY]
    assert any(isinstance(o, ApprovalComment) and "done" in o.body for o in session.added)


@pytest.mark.asyncio
async def test_a_rejected_proposal_deletes_nothing(chroma, chain):
    client = chroma({_EMPTY: 0})
    await _propose_and_decide(ApprovalClaimSession(), approve=False)
    assert client.deleted == []


@pytest.mark.asyncio
async def test_a_collection_filled_after_the_proposal_is_not_deleted(chroma):
    client = chroma({_EMPTY: 3})
    done, reason = await svc.delete_empty_collection(_EMPTY)
    assert done is False and "3 vector" in reason
    assert client.deleted == []


def test_the_scan_is_limited_to_knowledge_base_collections(chroma):
    chroma({_EMPTY: 0, _FOREIGN: 0, "semantic_query_cache": 0, _DOCS: 5})
    with _as_admin():
        body = _client().get(_URL).json()
    assert body == {"total": 2, "empty": [_EMPTY], "unreadable": []}


def test_a_foreign_empty_collection_cannot_be_proposed(chroma):
    chroma({_FOREIGN: 0})
    with _as_admin():
        response = _client().post(f"{_URL}/cleanup-requests", json={"collection": _FOREIGN})
    assert response.status_code == 409


def test_the_deletion_is_admin_decided(chain):
    assert approval_execution.is_server_only_action(svc.ACTION)
    assert approval_execution.action_needs_elevated_approver(svc.ACTION)


@pytest.mark.asyncio
async def test_a_proposal_is_audit_logged_when_created(chroma, chain):
    chroma({_EMPTY: 0})
    session = ApprovalClaimSession()
    proposal = await route.propose_empty_collection_cleanup(
        route.EmptyCollectionCleanupRequest(collection=_EMPTY), current_user=_ADMIN, session=session
    )
    operation, kwargs = chain[0]
    assert operation == "chroma.empty_collection_delete_proposed"
    assert kwargs["details"] == {"approval_id": proposal.approval_id} and kwargs["durable"] is True
    assert kwargs["resource"] == f"chroma:{_EMPTY}"


@pytest.mark.asyncio
async def test_no_audit_row_means_no_proposal(chroma, chain, monkeypatch):
    chroma({_EMPTY: 0})

    async def _refused(operation, **kwargs):
        return False

    monkeypatch.setattr("services.kb_cleanup_proposals.audit_log", _refused)
    session = ApprovalClaimSession()
    with pytest.raises(HTTPException) as caught:
        await route.propose_empty_collection_cleanup(
            route.EmptyCollectionCleanupRequest(collection=_EMPTY), current_user=_ADMIN, session=session
        )
    assert caught.value.status_code == 503
    assert not [o for o in session.added if isinstance(o, Approval)]


@pytest.mark.asyncio
async def test_a_second_proposal_for_the_same_collection_returns_the_pending_one(chroma, chain):
    chroma({_EMPTY: 0})
    session = ApprovalClaimSession()
    first = await _propose(session)
    second = await _propose(session)
    assert second.approval_id == first.approval_id
    assert len([c for c in chain if c[0].endswith("_proposed")]) == 1


@pytest.mark.asyncio
async def test_a_failed_outcome_audit_is_logged_and_shown_on_the_approval(chroma, chain, monkeypatch):
    chroma({_EMPTY: 0})

    async def _raises(operation, **kwargs):
        if operation == "chroma.empty_collection_delete":
            raise OSError("audit store down")
        return True

    monkeypatch.setattr("services.kb_cleanup_proposals.audit_log", _raises)
    session = ApprovalClaimSession()
    await _propose_and_decide(session, approve=True)
    assert any(isinstance(o, ApprovalComment) and "audit entry" in o.body for o in session.added)


async def _noop():
    return None


@pytest.mark.asyncio
async def test_a_foreign_collection_named_in_an_approval_is_never_deleted(chroma):
    """Defence in depth (#20992): the deletion re-checks the registry, whatever the approval's context says."""
    client = chroma({_FOREIGN: 0})
    done, reason = await svc.delete_empty_collection(_FOREIGN)
    assert done is False and "not a knowledge-base collection" in reason
    assert client.deleted == [] and _FOREIGN in client.collections
