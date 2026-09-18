#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the presence feed adapters (#16947).

Each adapter is tested against a fake of its own single source, not a real
DB/Redis/BaseAgent -- what's under test is the adapter's own translation
into `registry.report()` calls, not the source's own correctness.
"""

import uuid
from types import SimpleNamespace

import pytest

from llc.models.enums import LLCRunStatus
from models.agent_org import AgentOrgNode
from protocols.agent_kind import AgentKind
from protocols.agent_presence import UNKNOWN_TENANT, AgentPresenceRegistry
from protocols.agent_presence_feeds import (
    sync_ai_stack_presence,
    sync_company_os_presence,
    sync_session_presence,
)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_args, **_kwargs):
        return _FakeResult(self._rows)


def _org_node(*, agent_id: str, company_id, org_role: str = "worker") -> AgentOrgNode:
    return AgentOrgNode(agent_id=agent_id, name=agent_id, company_id=company_id, org_role=org_role)


def _run(status: str):
    return SimpleNamespace(status=status)


class TestSyncCompanyOsPresence:
    @pytest.mark.asyncio
    async def test_an_agent_with_a_running_heartbeat_is_busy(self):
        company_id = uuid.uuid4()
        node = _org_node(agent_id="assistant-abc123", company_id=company_id)
        session = _FakeSession([(node, _run(LLCRunStatus.RUNNING.value))])
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_company_os_presence(registry, session, str(company_id))

        entries = registry.list_live(str(company_id))
        assert len(entries) == 1
        assert entries[0].kind == AgentKind.COMPANY_OS
        assert entries[0].name == "assistant-abc123"
        assert entries[0].tenant_id == str(company_id)
        assert entries[0].busy is True

    @pytest.mark.asyncio
    async def test_an_agent_with_a_completed_heartbeat_is_idle(self):
        company_id = uuid.uuid4()
        node = _org_node(agent_id="assistant-abc123", company_id=company_id)
        session = _FakeSession([(node, _run(LLCRunStatus.COMPLETED.value))])
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_company_os_presence(registry, session, str(company_id))

        assert registry.list_live(str(company_id))[0].busy is False

    @pytest.mark.asyncio
    async def test_an_agent_with_no_heartbeat_run_yet_is_idle_not_dropped(self):
        company_id = uuid.uuid4()
        node = _org_node(agent_id="fresh-agent", company_id=company_id)
        session = _FakeSession([(node, None)])
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_company_os_presence(registry, session, str(company_id))

        entries = registry.list_live(str(company_id))
        assert len(entries) == 1
        assert entries[0].busy is False

    @pytest.mark.asyncio
    async def test_a_node_with_no_company_id_is_unknown_tenant_not_shared(self):
        node = _org_node(agent_id="orphan-agent", company_id=None)
        session = _FakeSession([(node, None)])
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_company_os_presence(registry, session, "some-company")

        # Fails closed: not visible to a specific tenant's query...
        assert registry.list_live("some-company") == []
        # ...nor treated as shared infrastructure, visible to every tenant.
        assert registry.list_live("a-different-company") == []


class TestSyncAiStackPresence:
    @pytest.mark.asyncio
    async def test_every_registered_agent_type_is_reported_idle(self):
        health_registry = SimpleNamespace(list_agents=lambda: ["chat", "rag"])
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_ai_stack_presence(registry, health_registry)

        entries = {e.name: e for e in registry.list_live()}
        assert set(entries) == {"chat", "rag"}
        assert all(e.kind == AgentKind.AI_STACK for e in entries.values())
        assert all(e.tenant_id is None for e in entries.values())
        assert all(e.busy is False for e in entries.values())


class TestSyncSessionPresence:
    @pytest.mark.asyncio
    async def test_a_session_with_a_running_command_is_busy(self):
        session_manager = SimpleNamespace(
            sessions={
                "sess-1": SimpleNamespace(agent_id="claude", has_running_task=lambda: True),
                "sess-2": SimpleNamespace(agent_id="claude", has_running_task=lambda: False),
            }
        )
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_session_presence(registry, session_manager)

        # Sessions carry UNKNOWN_TENANT (#16947 review): never listable via
        # list_live(), by design -- inspect the stored record directly.
        stored = {name: rec for (_, _, name), rec in registry._entries.items()}
        assert stored["sess-1"].busy is True
        assert stored["sess-2"].busy is False

    @pytest.mark.asyncio
    async def test_sessions_are_reported_with_unknown_tenant_and_never_listed(self):
        session_manager = SimpleNamespace(
            sessions={"sess-1": SimpleNamespace(agent_id="claude", has_running_task=lambda: False)}
        )
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_session_presence(registry, session_manager)

        assert list(registry._entries)[0][1] == UNKNOWN_TENANT
        assert registry.list_live() == []
        assert registry.list_live("any-tenant") == []
