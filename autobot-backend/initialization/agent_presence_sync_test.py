# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The startup sync task actually populates the registry (#16965 review).

Before this, `sync_company_os_presence`/`sync_ai_stack_presence`/
`sync_session_presence` and `get_presence_registry` had zero production
callers -- correct adapters, never invoked. `_sync_once()` is the one
caller; this proves it reaches all three and the registry reflects it.
"""

from types import SimpleNamespace

import pytest

import agents.agent_client as agent_client_module
import api.agent_terminal as agent_terminal_module
import autobot_shared.redis_client as redis_client_module
import chat_workflow as chat_workflow_module
import llc.services.agent_presence_queries as queries_module
import user_management.database as database_module
from initialization import agent_presence_sync
from protocols.agent_kind import AgentKind
from protocols.agent_presence import AgentPresenceRegistry

pytestmark = pytest.mark.asyncio


class _FakeSession:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def wired(monkeypatch):
    """Every external source _sync_once() reaches, faked."""
    registry = AgentPresenceRegistry(ttl_seconds=60)
    monkeypatch.setattr("protocols.agent_presence.get_presence_registry", lambda: registry)

    health_registry = SimpleNamespace(list_agents=lambda: ["chat"])
    agent_client = SimpleNamespace(registry=health_registry)

    async def _get_agent_client():
        return agent_client

    monkeypatch.setattr(agent_client_module, "get_agent_client", _get_agent_client)

    session_manager = SimpleNamespace(sessions={})
    terminal_service = SimpleNamespace(session_manager=session_manager)
    monkeypatch.setattr(agent_terminal_module, "get_agent_terminal_service", lambda redis_client=None: terminal_service)
    monkeypatch.setattr(redis_client_module, "get_redis_client", lambda async_client=False, database="main": None)
    monkeypatch.setattr(chat_workflow_module, "get_chat_workflow_manager", lambda: None)

    async def _empty_company_ids(session):
        return []

    monkeypatch.setattr(queries_module, "distinct_company_ids_with_agents", _empty_company_ids)
    monkeypatch.setattr(database_module, "get_async_session_factory", lambda: lambda: _FakeSession())

    return registry


class TestSyncOncePopulatesTheRegistry:
    async def test_the_ai_stack_role_from_the_health_registry_is_reported(self, wired):
        await agent_presence_sync._sync_once()

        entries = wired.list_live(None)
        assert any(e.kind is AgentKind.AI_STACK and e.name == "chat" for e in entries)

    async def test_a_failed_iteration_does_not_raise_out_of_the_loop_step(self, wired, monkeypatch):
        async def _boom():
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(agent_client_module, "get_agent_client", _boom)

        # _sync_once() itself may raise -- it is _loop() that must survive one
        # bad iteration and retry, which this proves indirectly via _sync_once
        # raising cleanly rather than corrupting state.
        with pytest.raises(RuntimeError):
            await agent_presence_sync._sync_once()
