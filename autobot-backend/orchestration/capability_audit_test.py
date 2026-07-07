# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the capability-manifest consistency audit (GH#11165)."""

from orchestration.agent_registry import get_default_agents
from orchestration.capability_audit import (
    audit_agent_manifests,
    run_capability_audit,
)
from orchestration.types import AgentCapability, AgentProfile


def _profile(agent_id: str, allowed=None, forbidden=None) -> AgentProfile:
    return AgentProfile(
        agent_id=agent_id,
        agent_type="test",
        capabilities={AgentCapability.RESEARCH},
        specializations=[],
        allowed_work=allowed or [],
        forbidden_work=forbidden or [],
    )


def _codes(findings) -> set[str]:
    return {f.code for f in findings}


def test_default_profiles_have_no_errors():
    """The shipped default manifests must be internally consistent."""
    findings = audit_agent_manifests(get_default_agents())
    errors = [f for f in findings if f.severity == "error"]
    assert errors == [], f"default profiles produced errors: {errors}"


def test_detects_allowed_forbidden_overlap():
    findings = audit_agent_manifests([_profile("a", allowed=["bash"], forbidden=["bash"])])
    assert "manifest_overlap" in _codes(findings)
    overlap = next(f for f in findings if f.code == "manifest_overlap")
    assert overlap.severity == "error"
    assert overlap.agent_id == "a"


def test_detects_allowed_blocked_by_forbidden_prefix():
    # allowed "deploy_service" is prefix-blocked by forbidden "deploy".
    findings = audit_agent_manifests([_profile("a", allowed=["deploy_service"], forbidden=["deploy"])])
    assert "allowed_blocked_by_forbidden" in _codes(findings)
    assert all(f.severity == "error" for f in findings if f.code == "allowed_blocked_by_forbidden")


def test_detects_duplicate_entries():
    findings = audit_agent_manifests([_profile("a", allowed=["read_file", "read_file"], forbidden=["bash"])])
    assert "duplicate_entries" in _codes(findings)


def test_detects_unbounded_non_executor():
    findings = audit_agent_manifests([_profile("a", allowed=["web_search"], forbidden=[])])
    assert "unbounded_non_executor" in _codes(findings)


def test_executor_agent_not_flagged_unbounded():
    # An agent granted shell/infra tools is an intended executor — empty
    # forbidden_work is expected, not a posture gap.
    findings = audit_agent_manifests([_profile("sys", allowed=["bash", "deploy"], forbidden=[])])
    assert "unbounded_non_executor" not in _codes(findings)


def test_run_capability_audit_report_shape():
    report = run_capability_audit()
    assert report["agent_count"] >= 4
    assert report["error_count"] == 0
    assert isinstance(report["findings"], list)
