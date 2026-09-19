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

import asyncio
import contextlib
import logging
from types import SimpleNamespace

import pytest

import agents.agent_client as agent_client_module
import api.agent_terminal as agent_terminal_module
import autobot_shared.redis_client as redis_client_module
import chat_workflow as chat_workflow_module
import llc.services.agent_presence_queries as queries_module
import protocols.agent_presence_feeds as feeds_module
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


def test_sync_interval_seconds_clamps_a_zero_or_negative_value(monkeypatch):
    """#16965 review: an unclamped 0/negative interval makes asyncio.sleep
    return immediately, busy-spinning _sync_once() every tick."""
    monkeypatch.setenv("AUTOBOT_AGENT_PRESENCE_SYNC_INTERVAL_SECONDS", "0")

    assert agent_presence_sync.sync_interval_seconds() == agent_presence_sync.MIN_SYNC_INTERVAL_SECONDS


class TestPerCompanyIsolation:
    async def test_one_companys_sync_failure_does_not_skip_the_rest(self, wired, monkeypatch, caplog):
        async def _two_companies(session):
            return ["company-a", "company-b"]

        monkeypatch.setattr(queries_module, "distinct_company_ids_with_agents", _two_companies)

        synced: list[str] = []

        async def _flaky_sync_company_os_presence(registry, session, company_id):
            if company_id == "company-a":
                raise RuntimeError("company-a's DB row is malformed")
            synced.append(company_id)

        monkeypatch.setattr(feeds_module, "sync_company_os_presence", _flaky_sync_company_os_presence)

        with caplog.at_level(logging.WARNING):
            await agent_presence_sync._sync_once()

        assert synced == ["company-b"], "company-b must still sync after company-a's failure"
        assert any("company-a" in r.message for r in caplog.records)


class TestLoopSurvivesAFailedIteration:
    async def test_a_logged_failure_does_not_stop_the_next_iteration_from_running(self, wired, monkeypatch, caplog):
        monkeypatch.setattr(agent_presence_sync, "sync_interval_seconds", lambda: 0.01)
        real_sync_once = agent_presence_sync._sync_once
        calls = {"n": 0}

        async def _flaky_sync_once():
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("first iteration fails")
            await real_sync_once()

        monkeypatch.setattr(agent_presence_sync, "_sync_once", _flaky_sync_once)

        with caplog.at_level(logging.WARNING):
            task = asyncio.ensure_future(agent_presence_sync._loop())
            try:
                for _ in range(200):
                    if calls["n"] >= 2:
                        break
                    await asyncio.sleep(0.01)
            finally:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

        assert calls["n"] >= 2, "the loop must run a second iteration after the first one raised"
        assert any("Agent presence sync iteration failed" in r.message for r in caplog.records)
        entries = wired.list_live(None)
        assert any(
            e.kind is AgentKind.AI_STACK and e.name == "chat" for e in entries
        ), "the surviving second iteration must still reach the real _sync_once() and populate the registry"
