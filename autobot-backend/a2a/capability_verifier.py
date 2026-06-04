# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Capability Verifier

Issue #968: Addresses the unsolved capability negotiation problem identified
in A2A research — agents claim skills but there is no mechanism to verify
those claims at runtime.

This module verifies that a remote agent's advertised skills are reachable
and responsive before a task is delegated to them.  For the local AutoBot
agent card it confirms claimed skills match the live registered agent types.

Verification strategy
---------------------
1. **Local card** (no HTTP call needed):
   Compare AgentCard.skills[].id against the set of active AgentType values.
   Any skill claimed but not backed by a real agent is flagged.

2. **Remote card** (external agent):
   a. Fetch /.well-known/agent.json from the remote URL.
   b. Check that each claimed skill has at least one example or tag
      (syntactic sanity check — deeper verification requires task execution).
   c. Optionally verify the security card signature if present.

Results are cached for CAPABILITY_CACHE_TTL seconds to avoid hammering
remote endpoints on every request.
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Cache TTL in seconds for remote capability checks.
_CACHE_TTL = int(
    os.environ.get("AUTOBOT_A2A_CAPABILITY_TTL", "300")
)  # ssot-config-exempt: int-wrapping type conversion per GH#7743


@dataclass
class CapabilityReport:
    """Result of a capability verification check."""

    verified: bool
    claimed_skills: List[str] = field(default_factory=list)
    verified_skills: List[str] = field(default_factory=list)
    unverified_skills: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    checked_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "claimed_skills": self.claimed_skills,
            "verified_skills": self.verified_skills,
            "unverified_skills": self.unverified_skills,
            "warnings": self.warnings,
            "checked_at": self.checked_at,
        }


# Simple in-process cache: remote_url → (CapabilityReport, expiry_epoch)
_cache: Dict[str, tuple] = {}


def verify_local_card() -> CapabilityReport:
    """
    Verify that every skill in the local Agent Card is backed by a live agent.

    Compares AgentCard.skills against DEFAULT_AGENT_CAPABILITIES keys.
    Returns a CapabilityReport with any discrepancies flagged as warnings.
    """
    try:
        from agents.agent_orchestration.types import DEFAULT_AGENT_CAPABILITIES

        live_ids = {at.value for at in DEFAULT_AGENT_CAPABILITIES}
    except ImportError:
        return CapabilityReport(
            verified=False,
            warnings=["Cannot import DEFAULT_AGENT_CAPABILITIES — agent stack not loaded"],
        )

    try:
        from a2a.agent_card import build_agent_card

        card = build_agent_card("http://localhost")
        claimed = [s.id for s in card.skills]
    except Exception as exc:
        return CapabilityReport(
            verified=False,
            warnings=[f"Cannot build agent card: {exc}"],
        )

    verified = [s for s in claimed if s in live_ids]
    unverified = [s for s in claimed if s not in live_ids]
    warnings = [f"Claimed skill '{s}' has no backing agent" for s in unverified]

    return CapabilityReport(
        verified=len(unverified) == 0,
        claimed_skills=claimed,
        verified_skills=verified,
        unverified_skills=unverified,
        warnings=warnings,
    )


async def verify_remote_card(remote_url: str) -> CapabilityReport:
    """
    Fetch and verify a remote agent's capability claims.

    Performs a lightweight sanity check: every claimed skill must have
    at least an id and either tags or examples.  Results are cached for
    _CACHE_TTL seconds.

    Args:
        remote_url: Base URL of the remote agent (e.g. "https://agent.example.com")

    Returns:
        CapabilityReport with verification results.
    """
    cached = _cache.get(remote_url)
    if cached:
        report, expiry = cached
        if time.time() < expiry:
            logger.debug("A2A capability cache hit for %s", remote_url)
            return report

    report = await _fetch_and_verify(remote_url)
    _cache[remote_url] = (report, time.time() + _CACHE_TTL)
    return report


async def _fetch_and_verify(remote_url: str) -> CapabilityReport:
    """Perform the actual HTTP fetch and verification."""
    import json

    import aiohttp

    from autobot_shared.security.ssrf_guard import SSRFError, fetch_safe_url

    well_known = remote_url.rstrip("/") + "/.well-known/agent.json"

    try:
        # fetch_safe_url enforces: scheme validation, DNS resolution to public IPs,
        # pinned resolver (defeats DNS-rebind), allow_redirects=False (#1721, #6533).
        status, body_bytes, _ = await fetch_safe_url(well_known, timeout=5.0)
    except SSRFError as exc:
        return CapabilityReport(verified=False, warnings=[f"Invalid agent URL: {exc}"])
    except aiohttp.ClientError as exc:
        return CapabilityReport(verified=False, warnings=[f"Agent card fetch error: {exc}"])

    if status != 200:
        return CapabilityReport(
            verified=False,
            warnings=[f"Agent card fetch failed: HTTP {status}"],
        )

    try:
        data = json.loads(body_bytes)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return CapabilityReport(verified=False, warnings=[f"Agent card is not valid JSON: {exc}"])

    if status_code != 200:
        return CapabilityReport(
            verified=False,
            warnings=[f"Agent card fetch failed: HTTP {status_code}"],
        )

    try:
        data = _json.loads(body)
    except _json.JSONDecodeError as exc:
        return CapabilityReport(
            verified=False,
            warnings=[f"Agent card is not valid JSON: {exc}"],
        )

    return _check_card_skills(data)


def _check_card_skills(card_data: Dict[str, Any]) -> CapabilityReport:
    """Validate skill entries in a fetched agent card dict."""
    skills = card_data.get("skills", [])
    claimed: List[str] = []
    verified: List[str] = []
    unverified: List[str] = []
    warnings: List[str] = []

    for skill in skills:
        skill_id = skill.get("id", "")
        claimed.append(skill_id)
        has_content = bool(skill.get("tags")) or bool(skill.get("examples"))
        has_description = bool(skill.get("description", "").strip())
        if has_content and has_description and skill_id:
            verified.append(skill_id)
        else:
            unverified.append(skill_id)
            warnings.append(
                f"Skill '{skill_id}' has insufficient metadata " "(missing id, description, tags, or examples)"
            )

    return CapabilityReport(
        verified=len(unverified) == 0,
        claimed_skills=claimed,
        verified_skills=verified,
        unverified_skills=unverified,
        warnings=warnings,
    )
