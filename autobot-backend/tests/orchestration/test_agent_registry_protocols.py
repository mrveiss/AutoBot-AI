# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the AgentRegistry consolidation (#6828).

Acceptance criteria under test:
  - AgentCapabilityRegistry is the canonical implementer of both shared
    protocols (AgentCapabilityLookup + AgentRegistryProtocol).
  - update_specializations persists discovered specializations onto profiles.
  - get_default_capability_registry() is a process-wide singleton shared by
    resolve_forbidden_tools and the API fallbacks.
  - AgentEvolutionTracker works end-to-end against the canonical registry
    (the Protocol has a real concrete implementer, not just mocks).
"""

from unittest.mock import AsyncMock

from autobot_shared.agent_registry_protocol import (
    AgentCapabilityLookup,
    AgentRegistryProtocol,
)
from orchestration.agent_registry import (
    AgentCapabilityRegistry,
    get_default_capability_registry,
    resolve_forbidden_tools,
)
from services.mesh_brain.agent_evolution import AgentEvolutionTracker


class TestProtocolConformance:
    def test_capability_registry_implements_lookup_protocol(self) -> None:
        reg = AgentCapabilityRegistry(initialize_defaults=True)
        assert isinstance(reg, AgentCapabilityLookup)

    def test_capability_registry_implements_registry_protocol(self) -> None:
        reg = AgentCapabilityRegistry(initialize_defaults=True)
        assert isinstance(reg, AgentRegistryProtocol)

    def test_find_by_capability_answers_can_do_x(self) -> None:
        from orchestration.types import AgentCapability

        reg = AgentCapabilityRegistry(initialize_defaults=True)
        researchers = reg.find_by_capability(AgentCapability.RESEARCH)
        assert any(p.agent_id == "research_agent" for p in researchers)


class TestUpdateSpecializations:
    async def test_promotes_discovered_types_and_records_rates(self) -> None:
        reg = AgentCapabilityRegistry(initialize_defaults=True)
        before = list(reg.get("research_agent").specializations)
        assert "code_review" not in before

        await reg.update_specializations("research_agent", ["code_review"], {"code_review": 0.9})

        profile = reg.get("research_agent")
        assert profile.specializations[0] == "code_review"
        # Existing specializations retained (no data loss), no duplicates.
        assert set(before).issubset(set(profile.specializations))
        assert len(profile.specializations) == len(set(profile.specializations))
        assert profile.performance_metrics["specialization:code_review"] == 0.9

    async def test_existing_top_type_is_deduplicated(self) -> None:
        reg = AgentCapabilityRegistry(initialize_defaults=True)
        existing = reg.get("research_agent").specializations[0]

        await reg.update_specializations("research_agent", [existing], {existing: 1.0})

        specs = reg.get("research_agent").specializations
        assert specs.count(existing) == 1
        assert specs[0] == existing

    async def test_unknown_agent_is_ignored(self) -> None:
        reg = AgentCapabilityRegistry(initialize_defaults=True)
        await reg.update_specializations("does-not-exist", ["x"], {"x": 1.0})  # no raise


class TestDefaultRegistrySingleton:
    def test_accessor_returns_same_instance(self) -> None:
        assert get_default_capability_registry() is get_default_capability_registry()

    def test_resolve_forbidden_tools_reads_the_shared_instance(self) -> None:
        # The tool-dispatch boundary and the API fallbacks share one registry.
        forbidden = resolve_forbidden_tools("research_agent")
        assert forbidden == get_default_capability_registry().forbidden_tools("research_agent")
        assert "bash" in forbidden


class TestEvolutionTrackerAgainstCanonicalRegistry:
    async def test_tracker_updates_real_registry(self) -> None:
        """End-to-end: the Protocol's consumer works with its concrete implementer."""
        db = AsyncMock()
        db.get_agent_specializations = AsyncMock(
            return_value=[{"task_type": "vuln_triage", "success_rate": 0.95, "task_count": 8}]
        )
        reg = AgentCapabilityRegistry(initialize_defaults=True)
        tracker = AgentEvolutionTracker(db=db, registry=reg)

        specs = await tracker.evaluate("security_scanner")

        assert specs and specs[0].task_type == "vuln_triage"
        profile = reg.get("security_scanner")
        assert profile.specializations[0] == "vuln_triage"
        assert profile.performance_metrics["specialization:vuln_triage"] == 0.95
