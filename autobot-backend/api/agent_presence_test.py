# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /agents/presence is tenant-scoped from the verified context (#16965 review)."""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import agent_presence
from api.user_management.dependencies import get_current_user, require_org_context
from protocols.agent_kind import AgentKind
from protocols.agent_presence import AgentPresenceRegistry
from user_management.services import TenantContext


def _client(monkeypatch, *, org_id, registry):
    monkeypatch.setattr(agent_presence, "get_presence_registry", lambda: registry)
    app = FastAPI()
    app.include_router(agent_presence.router)
    app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "role": "admin"}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(org_id=org_id)
    return TestClient(app, raise_server_exceptions=False)


class TestListAgentPresence:
    def test_returns_the_callers_own_tenant_and_shared_but_not_another_tenant(self, monkeypatch):
        tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
        registry = AgentPresenceRegistry(ttl_seconds=60)
        registry.report(
            kind=AgentKind.COMPANY_OS, tenant_id=str(tenant_a), name="a-agent", instance_id="i1", busy=False
        )
        registry.report(
            kind=AgentKind.COMPANY_OS, tenant_id=str(tenant_b), name="b-agent", instance_id="i2", busy=False
        )
        registry.report(kind=AgentKind.AI_STACK, tenant_id=None, name="chat", instance_id="chat", busy=True)

        client = _client(monkeypatch, org_id=tenant_a, registry=registry)
        response = client.get("/agents/presence")

        assert response.status_code == 200
        names = {row["name"] for row in response.json()}
        assert names == {"a-agent", "chat"}

    def test_a_request_cannot_ask_for_another_tenant_via_a_parameter(self, monkeypatch):
        tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
        registry = AgentPresenceRegistry(ttl_seconds=60)
        registry.report(
            kind=AgentKind.COMPANY_OS, tenant_id=str(tenant_b), name="b-agent", instance_id="i1", busy=False
        )

        client = _client(monkeypatch, org_id=tenant_a, registry=registry)
        response = client.get("/agents/presence", params={"tenant_id": str(tenant_b), "org_id": str(tenant_b)})

        assert response.status_code == 200
        assert response.json() == []
