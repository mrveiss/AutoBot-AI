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
  - AgentRegistry exposes the boundary via forbidden_tools() / work_boundary()
    as the single query point — unknown agents degrade to empty (no boundary).
"""

from orchestration.agent_registry import AgentRegistry, get_default_agents
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
        reg = AgentRegistry(initialize_defaults=True)
        forbidden = reg.forbidden_tools("research_agent")
        assert isinstance(forbidden, frozenset)
        assert "bash" in forbidden and "terraform" in forbidden

    def test_work_boundary_returns_allowed_and_forbidden(self) -> None:
        reg = AgentRegistry(initialize_defaults=True)
        allowed, forbidden = reg.work_boundary("documentation_agent")
        assert "write_file" in allowed
        assert "docker" in forbidden

    def test_unknown_agent_degrades_to_empty(self) -> None:
        reg = AgentRegistry(initialize_defaults=True)
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

        reg = AgentRegistry(initialize_defaults=True)
        for agent_id, profile in reg.get_all().items():
            if agent_id in agent_capabilities:
                agent_capabilities[agent_id] = set(profile.capabilities)

        # Overlay must not add/remove routing candidates ...
        assert set(agent_capabilities) == before_keys
        # ... and the overlapping agent's capabilities are unchanged (single source).
        assert set(agent_capabilities["research_agent"]) == before_research
