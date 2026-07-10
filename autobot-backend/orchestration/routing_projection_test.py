# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11251 Part 1: orchestrator routing capabilities are a projection of the
profile registry (routing ids win) — with NO routing-candidate regression."""

from orchestration.agent_registry import ROUTING_AGENT_IDS, get_default_agents
from orchestration.types import AgentCapability

# The exact routing map that lived as a hardcoded dict in orchestrator.py before
# #11251 P1. The projection MUST reproduce this verbatim (no routing regression).
_LEGACY_ROUTING_MAP = {
    "research_agent": {AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
    "classification_agent": {AgentCapability.ANALYSIS, AgentCapability.VALIDATION},
    "kb_librarian": {AgentCapability.RESEARCH, AgentCapability.SYNTHESIS},
    "system_commands": {AgentCapability.EXECUTION, AgentCapability.MONITORING},
    "security_scanner": {AgentCapability.SECURITY, AgentCapability.VALIDATION},
    "npu_code_search": {AgentCapability.ANALYSIS, AgentCapability.OPTIMIZATION},
    "development_speedup": {AgentCapability.ANALYSIS, AgentCapability.OPTIMIZATION},
    "json_formatter": {AgentCapability.VALIDATION, AgentCapability.SYNTHESIS},
    "llm_failsafe": {AgentCapability.SYNTHESIS},
}


def _project() -> dict:
    return {p.agent_id: set(p.capabilities) for p in get_default_agents() if p.agent_id in ROUTING_AGENT_IDS}


def test_projection_equals_legacy_routing_map_exactly():
    """No routing-candidate regression: the profile projection == the old literal."""
    assert _project() == _LEGACY_ROUTING_MAP


def test_every_routing_id_has_a_profile():
    ids = {p.agent_id for p in get_default_agents()}
    assert ROUTING_AGENT_IDS <= ids, f"missing routing profiles: {ROUTING_AGENT_IDS - ids}"


def test_non_routing_profiles_excluded_from_projection():
    """Orphan profiles (documentation/system/coordination) must NOT enter routing."""
    projected = set(_project())
    assert projected == set(ROUTING_AGENT_IDS)
    assert "documentation_agent" not in projected
    assert "coordination_agent" not in projected
    assert "system_agent" not in projected


def test_routing_profiles_carry_forbidden_boundaries():
    """Decision: proper hardening. Read/analysis/synthesis routing agents forbid
    infra+shell; the executor (system_commands) is allowed infra/shell."""
    by_id = {p.agent_id: p for p in get_default_agents()}
    # bounded agents
    for aid in (
        "kb_librarian",
        "classification_agent",
        "security_scanner",
        "npu_code_search",
        "development_speedup",
        "json_formatter",
        "llm_failsafe",
    ):
        assert by_id[aid].forbidden_work, f"{aid} must carry a forbidden_work boundary"
    # the executor is deliberately unbounded (allowed infra/shell), like system_agent
    assert not by_id["system_commands"].forbidden_work
    assert by_id["system_commands"].allowed_work
