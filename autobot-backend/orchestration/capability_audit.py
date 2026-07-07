# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Capability-manifest consistency audit (GH#11165).

Governance-visibility companion to the enforcement wired in GH#11145: verifies
each agent's declarative ``allowed_work``/``forbidden_work`` manifest is
internally consistent and catches silent drift (a tool declared both allowed and
forbidden, an allowed tool its own ``forbidden_work`` prefix-blocks, duplicate
entries, or a non-executor agent with no boundary at all).

Reuses the single ``match_forbidden_tool`` matcher and ``_INFRA_AND_SHELL_TOOLS``
catalogue so audit and enforcement can never disagree on what "forbidden" means.
"""

from dataclasses import dataclass
from typing import List

from autobot_shared.logging_manager import get_logger
from orchestration.agent_registry import (
    _INFRA_AND_SHELL_TOOLS,
    AgentRegistry,
    get_default_agents,
    match_forbidden_tool,
)
from orchestration.types import AgentProfile

logger = get_logger(__name__)

_INFRA_TOOLS = frozenset(t.lower() for t in _INFRA_AND_SHELL_TOOLS)


@dataclass(frozen=True)
class AuditFinding:
    """A single manifest issue for one agent."""

    agent_id: str
    severity: str  # "error" | "warning"
    code: str
    message: str


def _duplicates(items: List[str]) -> List[str]:
    seen: set[str] = set()
    dupes: set[str] = set()
    for item in items:
        key = item.lower()
        if key in seen:
            dupes.add(key)
        seen.add(key)
    return sorted(dupes)


def _audit_profile(profile: AgentProfile) -> List[AuditFinding]:
    """Return all manifest findings for a single agent profile."""
    findings: List[AuditFinding] = []
    allowed = list(profile.allowed_work or [])
    forbidden = frozenset(t.lower() for t in (profile.forbidden_work or []))

    overlap = sorted({a.lower() for a in allowed} & forbidden)
    if overlap:
        findings.append(
            AuditFinding(
                profile.agent_id,
                "error",
                "manifest_overlap",
                f"tools in both allowed_work and forbidden_work: {overlap}",
            )
        )

    # An allowed tool the agent's own forbidden_work prefix-blocks is a dead
    # grant — reuses the enforcement matcher so the rule matches runtime exactly.
    for tool in allowed:
        matched = match_forbidden_tool(tool, forbidden)
        if matched is not None and tool.lower() not in overlap:
            findings.append(
                AuditFinding(
                    profile.agent_id,
                    "error",
                    "allowed_blocked_by_forbidden",
                    f"allowed tool '{tool}' is blocked by forbidden_work pattern '{matched}'",
                )
            )

    for field, values in (("allowed_work", allowed), ("forbidden_work", list(profile.forbidden_work or []))):
        dupes = _duplicates(values)
        if dupes:
            findings.append(
                AuditFinding(profile.agent_id, "warning", "duplicate_entries", f"{field} has duplicates: {dupes}")
            )

    # A non-executor agent (one not granted shell/infra tools) with no boundary
    # at all is a posture gap — it can invoke anything.
    is_executor = any(a.lower() in _INFRA_TOOLS for a in allowed)
    if not forbidden and not is_executor:
        findings.append(
            AuditFinding(
                profile.agent_id,
                "warning",
                "unbounded_non_executor",
                "empty forbidden_work on a non-executor agent — no capability boundary",
            )
        )
    return findings


def audit_agent_manifests(profiles: List[AgentProfile]) -> List[AuditFinding]:
    """Audit every profile's capability manifest for consistency and drift."""
    findings: List[AuditFinding] = []
    for profile in profiles:
        findings.extend(_audit_profile(profile))
    return findings


def audit_registry(registry: AgentRegistry) -> List[AuditFinding]:
    """Audit every profile in a live registry (incl. dynamically-registered agents)."""
    return audit_agent_manifests(list(registry.get_all().values()))


def run_capability_audit() -> dict:
    """Scan the default agent registry, log findings by severity, return a report.

    Callable from a scheduled job or an admin endpoint. Returns a report dict with
    the finding list plus error/warning counts for monitoring.
    """
    profiles = get_default_agents()
    findings = audit_agent_manifests(profiles)
    errors = [f for f in findings if f.severity == "error"]
    warnings = [f for f in findings if f.severity == "warning"]
    for finding in errors:
        logger.error("Capability audit [%s] %s: %s", finding.agent_id, finding.code, finding.message)
    for finding in warnings:
        logger.warning("Capability audit [%s] %s: %s", finding.agent_id, finding.code, finding.message)
    logger.info(
        "Capability audit complete: %d agents, %d error(s), %d warning(s)",
        len(profiles),
        len(errors),
        len(warnings),
    )
    return {
        "agent_count": len(profiles),
        "error_count": len(errors),
        "warning_count": len(warnings),
        "findings": [
            {"agent_id": f.agent_id, "severity": f.severity, "code": f.code, "message": f.message} for f in findings
        ],
    }
