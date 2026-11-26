# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the declarative agent capability manifest (GH#11139).

Acceptance criteria:
  - AgentProfile carries allowed_work / forbidden_work (default empty).
  - Default profiles declare a least-privilege forbidden_work boundary for
    non-executor agents; the system (executor) agent has none.
  - AgentCapabilityRegistry exposes the boundary via forbidden_tools() / work_boundary()
    as the single query point — unknown agents degrade to empty (no boundary).
"""

from orchestration.agent_registry import AgentCapabilityRegistry, get_default_agents
from orchestration.types import AgentCapability, AgentProfile


class TestAgentProfileManifest:
    def test_defaults_empty(self) -> None:
        profile = AgentProfile(
            agent_id="x",
            agent_type="test",
            capabilities={AgentCapability.ANALYSIS},
            specializations=[],
        )
        assert profile.allowed_work == []
        assert profile.forbidden_work == []

    def test_manifest_fields_are_independent_lists(self) -> None:
        a = AgentProfile(agent_id="a", agent_type="t", capabilities=set(), specializations=[])
        b = AgentProfile(agent_id="b", agent_type="t", capabilities=set(), specializations=[])
        a.forbidden_work.append("bash")
        assert b.forbidden_work == []  # no shared mutable default


class TestDefaultProfilesBoundary:
    def test_non_executor_agents_forbid_infra_and_shell(self) -> None:
        by_id = {p.agent_id: p for p in get_default_agents()}
        for agent_id in ("research_agent", "documentation_agent", "coordination_agent"):
            forbidden = by_id[agent_id].forbidden_work
            assert "bash" in forbidden
            assert "deploy" in forbidden
            assert "ansible" in forbidden

    def test_system_agent_is_the_executor_no_boundary(self) -> None:
        by_id = {p.agent_id: p for p in get_default_agents()}
        system = by_id["system_agent"]
        assert system.forbidden_work == []
        # It is allowed to run the very tools others are forbidden from.
        assert "bash" in system.allowed_work


class TestAgentRegistryAccessors:
    def test_forbidden_tools_reads_manifest(self) -> None:
        reg = AgentCapabilityRegistry(initialize_defaults=True)
        forbidden = reg.forbidden_tools("research_agent")
        assert isinstance(forbidden, frozenset)
        assert "bash" in forbidden and "terraform" in forbidden

    def test_work_boundary_returns_allowed_and_forbidden(self) -> None:
        reg = AgentCapabilityRegistry(initialize_defaults=True)
        allowed, forbidden = reg.work_boundary("documentation_agent")
        assert "write_file" in allowed
        assert "docker" in forbidden

    def test_unknown_agent_degrades_to_empty(self) -> None:
        """The raw accessor reports "no profile" as an empty manifest.

        Not a security property, and not what any enforcement seam sees: those go
        through ``resolve_forbidden_tools``, which turns this same miss into the
        default boundary plus a warning (GH#13588, ``test_agent_registry_fail_closed``).
        """
        reg = AgentCapabilityRegistry(initialize_defaults=True)
        assert reg.forbidden_tools("does-not-exist") == frozenset()
        assert reg.work_boundary("does-not-exist") == ([], [])


class TestRoutingOverlayNonRegressive:
    """GH#11139 1.2: profiles overlay the routing map without changing membership."""

    def test_overlay_adds_no_new_routing_keys_and_preserves_caps(self) -> None:
        # The routing literal from Orchestrator._init_strategy_components.
        agent_capabilities = {
            "research_agent": {AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
            "classification_agent": {AgentCapability.ANALYSIS, AgentCapability.VALIDATION},
            "kb_librarian": {AgentCapability.RESEARCH, AgentCapability.SYNTHESIS},
            "system_commands": {AgentCapability.EXECUTION, AgentCapability.MONITORING},
        }
        before_keys = set(agent_capabilities)
        before_research = set(agent_capabilities["research_agent"])

        reg = AgentCapabilityRegistry(initialize_defaults=True)
        for agent_id, profile in reg.get_all().items():
            if agent_id in agent_capabilities:
                agent_capabilities[agent_id] = set(profile.capabilities)

        # Overlay must not add/remove routing candidates ...
        assert set(agent_capabilities) == before_keys
        # ... and the overlapping agent's capabilities are unchanged (single source).
        assert set(agent_capabilities["research_agent"]) == before_research


class TestOneAgentRecord:
    """#22275: health and presence are attributes of one agent record, not separate registries."""

    async def test_record_joins_profile_health_and_presence(self, monkeypatch) -> None:
        from orchestration import agent_record

        async def no_stored() -> dict:
            return {}

        monkeypatch.setattr(agent_record, "_stored_agents", no_stored)
        records = await agent_record.agent_records()
        assert {r["name"] for r in records} >= {p.agent_id for p in get_default_agents()}
        for r in records:
            assert r["kind"] == "agent" and r["serving_service"] == "backend"
            assert {"capabilities", "health", "presence", "forbidden_work"} <= set(r["fields"])

    async def test_producers_write_attributes_and_stored_agents_join_by_id(self, monkeypatch) -> None:
        """Health and presence reach the record through the one store; DB and Company OS agents join by id."""
        from autobot_shared.agent_attributes import get_agent_attribute_store
        from orchestration import agent_record

        known = get_default_agents()[0]
        store = get_agent_attribute_store()
        store.set(known.agent_id, "presence", {"busy": True})
        store.set(known.agent_type, "health", {"status": "healthy"})

        async def stored() -> dict:
            return {known.agent_id: {"registered": {"status": "active"}}, "hired-1": {"company_os": {"title": "QA"}}}

        monkeypatch.setattr(agent_record, "_stored_agents", stored)
        by_name = {r["name"]: r["fields"] for r in await agent_record.agent_records()}
        assert by_name[known.agent_id]["presence"] == {"busy": True}
        assert by_name[known.agent_id]["health"] == {"status": "healthy"}
        assert by_name[known.agent_id]["registered"] == {"status": "active"}
        assert by_name["hired-1"]["company_os"] == {"title": "QA"} and by_name["hired-1"]["health"] is None
        store.clear(known.agent_id, "presence")
        store.clear(known.agent_type, "health")

    def test_presence_and_health_producers_write_the_store(self) -> None:
        """The presence registry's report/deregister are the producers of the ``presence`` attribute."""
        from autobot_shared.agent_attributes import get_agent_attribute_store
        from protocols.agent_kind import AgentKind
        from protocols.agent_presence import AgentPresenceRegistry

        reg = AgentPresenceRegistry(ttl_seconds=60)
        reg.report(kind=AgentKind.AI_STACK, tenant_id=None, name="gap-agent", instance_id="i1", busy=True)
        assert get_agent_attribute_store().snapshot()["gap-agent"]["presence"]["busy"] is True
        reg.deregister(kind=AgentKind.AI_STACK, tenant_id=None, name="gap-agent", instance_id="i1")
        assert "gap-agent" not in get_agent_attribute_store().snapshot()

    def test_no_further_agent_registry_class(self) -> None:
        """A new live-status registry must be an attribute of the record, not a class of its own."""
        import pathlib
        import re

        from autobot_shared.testfile_names import is_test_filename

        root = pathlib.Path(__file__).resolve().parents[2]
        found = set()
        for path in root.rglob("*.py"):
            if "tests" in path.parts or is_test_filename(path.name) or "venv" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            found.update(re.findall(r"^class (Agent\w*Registry)\b", text, re.MULTILINE))
        known = {"AgentCapabilityRegistry", "AgentHealthRegistry", "AgentPresenceRegistry", "AgentRegistryService"}
        assert (
            found - known <= set()
        ), f"#22275: new agent registry classes {sorted(found - known)}; add an attribute to the record"
