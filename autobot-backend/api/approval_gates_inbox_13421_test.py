# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /approval-gates/pending lists every source, with the risk tier in the schema (#13421 S1)."""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.approval_gates as route
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from services.approval_gate_service import ApprovalGateService

_USER = {"username": "u1", "role": "user", "user_id": "u1"}


def _row(source, tier, **over):
    base = dict(
        id=uuid.uuid4(), title="t", description=None, approval_type="workflow_gate", status="pending",
        requested_by_agent=None, decided_by_user=None, workflow_id=None, workflow_step=None, context={},
        decided_at=None, created_at=None, updated_at=None, source=source, risk_tier=tier,
        expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc), payload_hash="h" * 64, resume_ref="r",
        comments=[], task_links=[],
    )  # fmt: skip
    return SimpleNamespace(**{**base, **over})


@pytest.fixture
def client(monkeypatch):
    calls = []

    async def list_pending(self, **kwargs):
        calls.append(kwargs)
        return [_row("agent_tool", "high"), _row("plugin_capability", "low"), _row(None, None)]

    monkeypatch.setattr(ApprovalGateService, "list_pending", list_pending)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_db_session] = lambda: object()
    test_client = TestClient(app)
    test_client.app = app
    test_client.calls = calls
    return test_client


def test_pending_is_routed_before_the_uuid_route_and_returns_every_source(client):
    resp = client.get("/approval-gates/pending")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [(r["source"], r["risk_tier"]) for r in body] == [
        ("agent_tool", "high"),
        ("plugin_capability", "low"),
        (None, None),
    ]
    assert body[0]["expires_at"].startswith("2030-01-01") and body[0]["payload_hash"] == "h" * 64


def test_the_caller_identity_is_forwarded_so_the_service_can_scope_the_list(client):
    """#18413: the route passes the username and admin-ness; scoping itself is tested on Postgres."""
    assert client.get("/approval-gates/pending").status_code == 200
    assert (client.calls[-1]["viewer"], client.calls[-1]["is_admin"]) == ("u1", False)
    client.app.dependency_overrides[get_current_user] = lambda: {**_USER, "role": "admin"}
    assert client.get("/approval-gates/pending").status_code == 200
    assert client.calls[-1]["is_admin"] is True


def test_filters_are_forwarded_as_plain_values(client):
    assert client.get("/approval-gates/pending?source=agent_tool&risk_tier=critical").status_code == 200
    assert client.calls[-1]["source"] == "agent_tool" and client.calls[-1]["risk_tier"] == "critical"


@pytest.mark.parametrize("query", ["source=nope", "risk_tier=HIGH", "risk_tier=moderate"])
def test_values_outside_the_shared_vocabularies_are_a_422(client, query):
    assert client.get(f"/approval-gates/pending?{query}").status_code == 422


def test_the_response_schema_publishes_source_and_risk_tier():
    from api.schemas_approvals import ApprovalGateResponse

    schema = ApprovalGateResponse.model_json_schema()
    tier_ref = str(schema["properties"]["risk_tier"])
    assert "RiskTier" in tier_ref
    assert {"source", "expires_at", "payload_hash", "resume_ref"} <= set(schema["properties"])
    assert schema["$defs"]["RiskTier"]["enum"] == ["low", "medium", "high", "critical"]


def test_the_http_create_route_cannot_set_source_or_resume_ref(monkeypatch):
    seen = {}

    async def create_approval(self, **kwargs):
        seen.update(kwargs)
        return _row(None, None)

    monkeypatch.setattr(ApprovalGateService, "create_approval", create_approval)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[get_db_session] = lambda: object()
    resp = TestClient(app).post(
        "/approval-gates",
        json={
            "title": "t",
            "approval_type": "workflow_gate",
            "source": "terminal_command",
            "risk_tier": "low",
            "resume_ref": "x",
        },
    )
    assert resp.status_code == 201, resp.text
    assert not {"source", "risk_tier", "resume_ref", "expires_at", "payload_hash"} & set(seen)
