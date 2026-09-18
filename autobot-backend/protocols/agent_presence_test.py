#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for AgentPresenceRegistry (#16947)."""

import time

import pytest

from protocols.agent_kind import AgentKind
from protocols.agent_presence import (
    UNKNOWN_TENANT,
    AgentPresenceRegistry,
    ExternalIdentityExcludedError,
    PresenceNameCollisionError,
)


def _registry(ttl: float = 60.0) -> AgentPresenceRegistry:
    return AgentPresenceRegistry(ttl_seconds=ttl)


class TestReportAndList:
    def test_a_reported_agent_appears_in_list_live(self):
        reg = _registry()
        reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)

        entries = reg.list_live()

        assert len(entries) == 1
        assert entries[0].kind == AgentKind.SESSION
        assert entries[0].name == "sess-1"
        assert entries[0].busy is False

    def test_all_three_kinds_appear_in_one_query(self):
        reg = _registry()
        reg.report(kind=AgentKind.COMPANY_OS, tenant_id="co-1", name="assistant-abc", instance_id="a", busy=True)
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="b", busy=False)
        reg.report(kind=AgentKind.SESSION, tenant_id="co-1", name="sess-1", instance_id="c", busy=True)

        kinds = {e.kind for e in reg.list_live("co-1")}

        assert kinds == {AgentKind.COMPANY_OS, AgentKind.AI_STACK, AgentKind.SESSION}

    def test_same_instance_reporting_again_is_a_heartbeat_not_a_collision(self):
        reg = _registry()
        reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)

        reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=True)

        entries = reg.list_live()
        assert len(entries) == 1
        assert entries[0].busy is True

    def test_different_kinds_with_the_same_name_do_not_collide(self):
        reg = _registry()
        reg.report(kind=AgentKind.COMPANY_OS, tenant_id=None, name="dup", instance_id="a", busy=False)

        reg.report(kind=AgentKind.SESSION, tenant_id=None, name="dup", instance_id="b", busy=False)

        assert len(reg.list_live()) == 2

    def test_different_tenants_with_the_same_name_do_not_collide(self):
        reg = _registry()
        reg.report(kind=AgentKind.COMPANY_OS, tenant_id="co-1", name="dup", instance_id="a", busy=False)

        reg.report(kind=AgentKind.COMPANY_OS, tenant_id="co-2", name="dup", instance_id="b", busy=False)

        assert len(reg.list_live("co-1")) == 1
        assert len(reg.list_live("co-2")) == 1


class TestTenantScoping:
    def test_a_tenant_query_does_not_see_a_different_tenants_entries(self):
        """Negative control (#16947 review): tenant X must not see tenant Y."""
        reg = _registry()
        reg.report(kind=AgentKind.COMPANY_OS, tenant_id="tenant-x", name="agent-x", instance_id="a", busy=False)
        reg.report(kind=AgentKind.COMPANY_OS, tenant_id="tenant-y", name="agent-y", instance_id="b", busy=False)

        names = {e.name for e in reg.list_live("tenant-x")}

        assert names == {"agent-x"}

    def test_a_tenant_query_includes_shared_entries(self):
        reg = _registry()
        reg.report(kind=AgentKind.COMPANY_OS, tenant_id="tenant-x", name="agent-x", instance_id="a", busy=False)
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="b", busy=False)

        names = {e.name for e in reg.list_live("tenant-x")}

        assert names == {"agent-x", "rag"}

    def test_no_tenant_argument_returns_shared_entries_only(self):
        reg = _registry()
        reg.report(kind=AgentKind.COMPANY_OS, tenant_id="tenant-x", name="agent-x", instance_id="a", busy=False)
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="rag", instance_id="b", busy=False)

        assert {e.name for e in reg.list_live()} == {"rag"}

    def test_an_unknown_tenant_entry_is_never_returned_by_any_query(self):
        reg = _registry()
        reg.report(kind=AgentKind.SESSION, tenant_id=UNKNOWN_TENANT, name="sess-1", instance_id="a", busy=False)

        assert reg.list_live() == []
        assert reg.list_live("tenant-x") == []
        # Querying the sentinel directly must not become a backdoor to it either.
        assert reg.list_live(UNKNOWN_TENANT) == []


class TestCollisionRejection:
    def test_a_different_instance_claiming_a_live_name_is_rejected(self):
        reg = _registry()
        reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)

        with pytest.raises(PresenceNameCollisionError):
            reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i2", busy=False)

        # The original holder's entry must survive the rejected attempt.
        entries = reg.list_live()
        assert len(entries) == 1
        assert entries[0].instance_id == "i1"

    def test_a_name_can_be_reclaimed_by_a_new_instance_once_the_old_one_goes_stale(self):
        reg = _registry(ttl=0.05)
        reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)
        time.sleep(0.06)

        reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i2", busy=False)

        entries = reg.list_live()
        assert len(entries) == 1
        assert entries[0].instance_id == "i2"

    def test_external_kind_is_refused_outright(self):
        reg = _registry()

        with pytest.raises(ExternalIdentityExcludedError):
            reg.report(kind=AgentKind.EXTERNAL, tenant_id=None, name="peer-1", instance_id="i1", busy=False)

        assert reg.list_live() == []


class TestStaleness:
    def test_an_agent_that_stops_reporting_leaves_the_list_within_the_ttl(self):
        reg = _registry(ttl=0.05)
        reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)
        assert len(reg.list_live()) == 1

        time.sleep(0.06)

        assert reg.list_live() == []

    def test_repeated_heartbeats_keep_an_entry_alive_past_a_single_ttl_window(self):
        reg = _registry(ttl=0.1)
        reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)

        for _ in range(3):
            time.sleep(0.05)
            reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)

        assert len(reg.list_live()) == 1


class TestDeregister:
    def test_deregister_by_the_reporting_instance_removes_the_entry(self):
        reg = _registry()
        reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)

        reg.deregister(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1")

        assert reg.list_live() == []

    def test_deregister_by_a_different_instance_does_not_remove_someone_elses_entry(self):
        reg = _registry()
        reg.report(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i1", busy=False)

        reg.deregister(kind=AgentKind.SESSION, tenant_id=None, name="sess-1", instance_id="i2")

        assert len(reg.list_live()) == 1

    def test_deregister_of_an_unknown_entry_is_a_silent_no_op(self):
        reg = _registry()

        reg.deregister(kind=AgentKind.SESSION, tenant_id=None, name="never-existed", instance_id="i1")

        assert reg.list_live() == []


def test_presence_ttl_seconds_falls_back_on_an_unparseable_env_value(monkeypatch):
    from protocols.agent_presence import DEFAULT_PRESENCE_TTL_SECONDS, presence_ttl_seconds

    monkeypatch.setenv("AUTOBOT_AGENT_PRESENCE_TTL_SECONDS", "not-a-number")

    assert presence_ttl_seconds() == DEFAULT_PRESENCE_TTL_SECONDS
