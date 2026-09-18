# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /agents/presence is tenant-scoped from the verified context (#16965 review).

Drives the real ``get_tenant_context`` chain (not an override of
``require_org_context`` itself) for the parameter-tenancy tests -- overriding
``require_org_context`` directly proved nothing about request parameters,
since the override ignores them and always returns the same tenant.
"""

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import agent_presence
from api.user_management import dependencies
from api.user_management.dependencies import get_current_user, require_org_context
from protocols.agent_kind import AgentKind
from protocols.agent_presence import AgentPresenceRegistry
from user_management.services import TenantContext


class _FakeMembershipSession:
    """Answers `_check_org_membership`'s one query without a real DB."""

    def __init__(self, *, is_member: bool) -> None:
        self._is_member = is_member

    async def execute(self, *_args, **_kwargs):
        is_member = self._is_member

        class _Result:
            def first(self):
                return ("row",) if is_member else None

        return _Result()


def _db_session_override(*, is_member: bool):
    """A `get_db_session`-shaped generator dependency override.

    A plain lambda would not do -- FastAPI's override resolution re-inspects
    the override callable's own generator-ness, not just its return value.
    """

    def _gen():
        yield _FakeMembershipSession(is_member=is_member)

    return _gen


def _client(monkeypatch, *, registry):
    monkeypatch.setattr(agent_presence, "get_presence_registry", lambda: registry)
    app = FastAPI()
    app.include_router(agent_presence.router)
    return app, TestClient(app, raise_server_exceptions=False)


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

        app, client = _client(monkeypatch, registry=registry)
        app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "role": "user"}
        app.dependency_overrides[require_org_context] = lambda: TenantContext(org_id=tenant_a)

        response = client.get("/agents/presence")

        assert response.status_code == 200
        names = {row["name"] for row in response.json()}
        assert names == {"a-agent", "chat"}


class TestParameterTenancyThroughTheRealChain:
    """#16965 review: drives get_tenant_context for real, not a stubbed context."""

    def test_a_non_member_requesting_another_tenant_by_header_is_refused(self, monkeypatch):
        tenant_b = uuid.uuid4()
        registry = AgentPresenceRegistry(ttl_seconds=60)
        registry.report(
            kind=AgentKind.COMPANY_OS, tenant_id=str(tenant_b), name="b-agent", instance_id="i1", busy=False
        )

        app, client = _client(monkeypatch, registry=registry)
        app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "role": "user"}
        app.dependency_overrides[dependencies.get_db_session] = _db_session_override(is_member=False)

        response = client.get("/agents/presence", headers={"X-Organization-Id": str(tenant_b)})

        assert response.status_code == 403

    def test_a_member_requesting_their_own_tenant_by_header_succeeds(self, monkeypatch):
        tenant_a = uuid.uuid4()
        registry = AgentPresenceRegistry(ttl_seconds=60)
        registry.report(
            kind=AgentKind.COMPANY_OS, tenant_id=str(tenant_a), name="a-agent", instance_id="i1", busy=False
        )

        app, client = _client(monkeypatch, registry=registry)
        app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "role": "user"}
        app.dependency_overrides[dependencies.get_db_session] = _db_session_override(is_member=True)

        response = client.get("/agents/presence", headers={"X-Organization-Id": str(tenant_a)})

        assert response.status_code == 200
        assert {row["name"] for row in response.json()} == {"a-agent"}

    def test_a_platform_admin_may_choose_a_tenant_by_header_the_documented_exception(self, monkeypatch):
        """get_tenant_context trusts an admin's request-supplied org outright --
        the docstring on the route names this exception explicitly."""
        tenant_b = uuid.uuid4()
        registry = AgentPresenceRegistry(ttl_seconds=60)
        registry.report(
            kind=AgentKind.COMPANY_OS, tenant_id=str(tenant_b), name="b-agent", instance_id="i1", busy=False
        )

        app, client = _client(monkeypatch, registry=registry)
        app.dependency_overrides[get_current_user] = lambda: {"id": str(uuid.uuid4()), "role": "admin"}
        # No membership row needed -- an admin is never checked against it.
        app.dependency_overrides[dependencies.get_db_session] = _db_session_override(is_member=False)

        response = client.get("/agents/presence", headers={"X-Organization-Id": str(tenant_b)})

        assert response.status_code == 200
        assert {row["name"] for row in response.json()} == {"b-agent"}
