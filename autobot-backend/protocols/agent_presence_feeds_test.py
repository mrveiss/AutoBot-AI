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
from protocols.agent_presence import UNKNOWN_TENANT, AgentPresenceRegistry, PresenceTask
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
    """Answers each execute() with the next result set: org rows first, then work-item titles."""

    def __init__(self, rows, *more):
        self._results = [rows, *more]
        self.calls = 0
        self.statements = []

    async def execute(self, statement, *_args, **_kwargs):
        self.calls += 1
        self.statements.append(statement)
        return _FakeResult(self._results[min(self.calls, len(self._results)) - 1])


def _org_node(*, agent_id: str, company_id, org_role: str = "worker") -> AgentOrgNode:
    return AgentOrgNode(agent_id=agent_id, name=agent_id, company_id=company_id, org_role=org_role)


def _run(status: str, work_item_id=None):
    return SimpleNamespace(status=status, work_item_id=work_item_id)


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
    async def test_a_running_agent_reports_its_runs_work_item_as_current_task(self):
        """#18391: the run that makes the agent busy names what it is working on."""
        company_id, item = uuid.uuid4(), uuid.uuid4()
        node = _org_node(agent_id="assistant-abc123", company_id=company_id)
        session = _FakeSession([(node, _run(LLCRunStatus.RUNNING.value, item))], [(item, "Draft the Q3 report")])
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_company_os_presence(registry, session, str(company_id))

        assert registry.list_live(str(company_id))[0].task == PresenceTask(id=str(item), title="Draft the Q3 report")

    @pytest.mark.asyncio
    async def test_the_title_query_is_scoped_to_the_agents_company(self):
        """A title is only ever read for the company whose presence is being synced (01's review of #18652)."""
        company_id, item = uuid.uuid4(), uuid.uuid4()
        node = _org_node(agent_id="assistant-abc123", company_id=company_id)
        session = _FakeSession([(node, _run(LLCRunStatus.RUNNING.value, item))], [(item, "t")])

        await sync_company_os_presence(AgentPresenceRegistry(ttl_seconds=60), session, str(company_id))

        where = str(session.statements[1].whereclause)
        assert "llc_work_items.company_id" in where and "llc_work_items.id IN" in where

    def test_the_latest_run_join_is_scoped_to_the_company(self):
        """Agent slugs repeat across companies; the run join must not pick another company's run."""
        from llc.services.agent_presence_queries import agent_org_nodes_with_latest_heartbeat

        sql = str(agent_org_nodes_with_latest_heartbeat(str(uuid.uuid4())))
        join_on = sql.split("LEFT OUTER JOIN llc_heartbeat_runs ON", 1)[1].split("WHERE", 1)[0]
        assert "llc_heartbeat_runs.company_id" in join_on

    @pytest.mark.asyncio
    async def test_an_idle_agent_has_no_current_task_and_no_title_query_runs(self):
        company_id, item = uuid.uuid4(), uuid.uuid4()
        node = _org_node(agent_id="assistant-abc123", company_id=company_id)
        session = _FakeSession([(node, _run(LLCRunStatus.COMPLETED.value, item))])
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_company_os_presence(registry, session, str(company_id))

        assert registry.list_live(str(company_id))[0].task is None
        assert session.calls == 1

    @pytest.mark.asyncio
    async def test_a_running_run_without_a_work_item_has_no_current_task(self):
        company_id = uuid.uuid4()
        node = _org_node(agent_id="assistant-abc123", company_id=company_id)
        session = _FakeSession([(node, _run(LLCRunStatus.RUNNING.value))])
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_company_os_presence(registry, session, str(company_id))

        entry = registry.list_live(str(company_id))[0]
        assert entry.busy is True and entry.task is None
        assert session.calls == 1

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

    @pytest.mark.asyncio
    async def test_every_role_is_busy_while_a_stream_is_in_flight(self):
        health_registry = SimpleNamespace(list_agents=lambda: ["chat", "rag"])
        chat_workflow_manager = SimpleNamespace(is_processing=lambda: True)
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_ai_stack_presence(registry, health_registry, chat_workflow_manager)

        assert all(e.busy is True for e in registry.list_live())

    @pytest.mark.asyncio
    async def test_omitting_the_manager_reports_idle_not_a_guess(self):
        health_registry = SimpleNamespace(list_agents=lambda: ["chat"])
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_ai_stack_presence(registry, health_registry)

        assert registry.list_live()[0].busy is False


def _fake_session(*, agent_id: str = "claude", busy: bool = False, tenant_id: str | None = None):
    return SimpleNamespace(agent_id=agent_id, has_running_task=lambda: busy, tenant_id=tenant_id)


class TestSyncSessionPresence:
    @pytest.mark.asyncio
    async def test_a_session_with_a_running_command_is_busy(self):
        session_manager = SimpleNamespace(
            sessions={
                "sess-1": _fake_session(busy=True, tenant_id="tenant-x"),
                "sess-2": _fake_session(busy=False, tenant_id="tenant-x"),
            }
        )
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_session_presence(registry, session_manager)

        entries = {e.name: e for e in registry.list_live("tenant-x")}
        assert entries["sess-1"].busy is True
        assert entries["sess-2"].busy is False

    @pytest.mark.asyncio
    async def test_a_session_with_a_known_tenant_is_discoverable_within_it_only(self):
        session_manager = SimpleNamespace(sessions={"sess-1": _fake_session(tenant_id="tenant-x")})
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_session_presence(registry, session_manager)

        assert {e.name for e in registry.list_live("tenant-x")} == {"sess-1"}
        assert registry.list_live("tenant-y") == []

    @pytest.mark.asyncio
    async def test_a_session_with_no_tenant_is_unknown_and_never_listed(self):
        session_manager = SimpleNamespace(sessions={"sess-1": _fake_session(tenant_id=None)})
        registry = AgentPresenceRegistry(ttl_seconds=60)

        await sync_session_presence(registry, session_manager)

        assert list(registry._entries)[0][1] == UNKNOWN_TENANT
        assert registry.list_live() == []
        assert registry.list_live("any-tenant") == []
