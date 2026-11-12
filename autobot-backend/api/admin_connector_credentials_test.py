# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Clear-text connector credentials: read-only scan, admin-only route, rewrite only after approval (#20701)."""

import json
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.admin_connector_credentials as route
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from models.approval import Approval, ApprovalComment
from services import approval_execution
from services import connector_credential_cleanup_action as action
from services import connector_credential_scan as scan
from services.approval_gate_service import ApprovalGateService
from testkit.canonical_gate import canonical_resolver, real_admin_gate
from testkit.fake_approval_session import ApprovalClaimSession
from testkit.fake_async_session import FakeAsyncSession
from testkit.fake_redis_pipeline import FakePipeline

_ADMIN = {"username": "admin", "role": "admin", "user_id": "admin-1"}
_SECRET_VALUE = "clear-text-sentinel"  # pragma: allowlist secret
_URL = "/api/knowledge_base/connector_credentials"


class _Auth:
    __sensitive_fields__ = frozenset({"token"})


class _Connector:
    @classmethod
    def auth_schema(cls):
        return _Auth


class _Redis:
    def __init__(self, records):
        self.data = {f"connector:{cid}": json.dumps(rec) for cid, rec in records.items()}
        self.data["connector:c1:history"] = "[]"

    def scan_iter(self, match=None):
        return iter(list(self.data))

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value

    def pipeline(self):
        return FakePipeline(self)


class _Store:
    def __init__(self, held=True):
        self.held = held

    async def load(self, secret_id, sanitized, auth_cls, owner_id):
        if not self.held:
            raise LookupError("gone")
        return {**sanitized, "token": "from-secrets-store"}


def _record(connector_type="gitea", **overrides):
    base = {
        "connector_id": "c1",
        "connector_type": connector_type,
        "name": "n",
        "config": {"base_url": "https://git.example.org", "token": _SECRET_VALUE},
        "secret_id": "s1",
        "owner_id": "o1",
    }
    return {**base, **overrides}


@pytest.fixture
def world(monkeypatch):
    def build(records, held=True):
        redis = _Redis(records)
        monkeypatch.setattr(scan, "get_redis_client", lambda database=None: redis)
        monkeypatch.setattr(scan, "get_credential_store", lambda: _Store(held))
        monkeypatch.setattr(
            scan.ConnectorRegistry,
            "get_registered_class",
            lambda name: _Connector if name == "gitea" else None,
        )
        return redis

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


def test_the_scan_reports_counts_and_field_names_never_a_value(world):
    redis = world({"c1": _record(), "c2": _record(config={"token": ""}), "c3": _record("mystery")})
    before = dict(redis.data)

    with _as_admin():
        response = _client().get(f"{_URL}/scan")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["scanned"], body["affected"], body["with_secret_copy"]) == (3, 1, 1)
    assert body["findings"] == [
        {"connector_id": "c1", "connector_type": "gitea", "fields": ["token"], "secret_backed": True}
    ]
    assert body["unscannable_ids"] == ["c3"], "an unregistered type is reported as unchecked, not as clean"
    assert _SECRET_VALUE not in response.text
    assert redis.data == before, "the scan is read-only"


def test_a_non_admin_is_refused_on_both_routes(world):
    world({"c1": _record()})
    auth = MagicMock()
    auth.get_user_from_request.return_value = {"username": "u2", "role": "user", "user_id": "u2"}

    with real_admin_gate(auth) as wire:
        client = wire(_client())
        assert client.get(f"{_URL}/scan").status_code in (401, 403)
        assert client.post(f"{_URL}/cleanup-requests", json={"connector_id": "c1"}).status_code in (401, 403)


def test_a_proposal_is_pending_names_rotation_and_rewrites_nothing(world, monkeypatch):
    redis = world({"c1": _record()})
    before = dict(redis.data)
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, event, approval: _noop())
    session = FakeAsyncSession(assign_ids=uuid.uuid4)

    with _as_admin():
        response = _client(session).post(f"{_URL}/cleanup-requests", json={"connector_id": "c1"})

    assert response.status_code == 201, response.text
    approval = next(o for o in session.added if isinstance(o, Approval))
    assert approval.status == "pending" and approval.approval_type == "destructive_action"
    assert approval.context == {"action": "connector_credential_strip", "connector_id": "c1"}
    assert "rotate" in approval.description and _SECRET_VALUE not in approval.description
    assert redis.data == before, "proposing must not rewrite -- only an approved gate may (#17038)"


def test_a_record_without_a_secrets_store_copy_cannot_be_proposed(world):
    world({"c1": _record(secret_id=None)})
    with _as_admin():
        response = _client().post(f"{_URL}/cleanup-requests", json={"connector_id": "c1"})
    assert response.status_code == 409


def test_the_action_is_server_only_and_admin_decided():
    action.register_connector_credential_strip()
    assert approval_execution.is_server_only_action(action.ACTION)
    assert approval_execution.action_needs_elevated_approver(action.ACTION)


@pytest.fixture
def chain(monkeypatch):
    monkeypatch.setattr(approval_execution, "_REGISTRY", {})
    monkeypatch.setattr(approval_execution, "_PROPOSERS", {})
    monkeypatch.setattr(ApprovalGateService, "_notify", lambda self, event, approval: _noop())
    audited = []

    async def _audit_log(operation, **kwargs):
        audited.append(operation)
        return True

    monkeypatch.setattr(approval_execution, "audit_log", _audit_log)
    monkeypatch.setattr("services.kb_cleanup_proposals.audit_log", _audit_log)
    action.register_connector_credential_strip()
    return audited


async def _propose(session):
    return await route.propose_connector_credential_cleanup(
        route.ConnectorCredentialCleanupRequest(connector_id="c1"), current_user=_ADMIN, session=session
    )


async def _decide(session, proposal, approve):
    gate = ApprovalGateService(session)
    decide = gate.approve if approve else gate.reject
    await decide(uuid.UUID(proposal.approval_id), decided_by="alice", author_type="human", comment=None)


@pytest.mark.asyncio
async def test_only_an_approved_proposal_rewrites_the_record(world, chain):
    redis = world({"c1": _record()})
    session = ApprovalClaimSession()
    proposal = await _propose(session)
    assert _SECRET_VALUE in redis.data["connector:c1"], "pending: untouched"

    await _decide(session, proposal, approve=True)

    stored = json.loads(redis.data["connector:c1"])
    assert "token" not in stored["config"] and stored["config"]["base_url"] == "https://git.example.org"
    assert stored["secret_id"] == "s1"
    assert any(isinstance(o, ApprovalComment) and "done" in o.body for o in session.added)
    assert "connector_credentials.strip" in chain


@pytest.mark.asyncio
async def test_a_rejected_proposal_rewrites_nothing(world, chain):
    redis = world({"c1": _record()})
    session = ApprovalClaimSession()
    proposal = await _propose(session)

    await _decide(session, proposal, approve=False)

    assert _SECRET_VALUE in redis.data["connector:c1"]


@pytest.mark.asyncio
async def test_an_approved_strip_is_refused_when_the_secrets_store_lost_the_credential(world, chain):
    redis = world({"c1": _record()}, held=False)
    done, reason = await scan.strip_sensitive_fields("c1")
    assert done is False and "secrets store" in reason
    assert _SECRET_VALUE in redis.data["connector:c1"], "the only remaining copy is never removed"


async def _noop():
    return None
