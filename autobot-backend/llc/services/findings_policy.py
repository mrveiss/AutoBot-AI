# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Read the SLM-configured findings policy with safe defaults (#11271)."""

from dataclasses import dataclass

from llc.services.slm_policy import fetch_slm_policy_json

POLICY_SETTING_KEY = "llc.findings_policy"

_VALID_SEVERITIES = frozenset({"high", "medium", "low"})


@dataclass(frozen=True)
class FindingsPolicy:
    enabled: bool = False
    min_severity: str = "medium"
    require_approval_to_promote: bool = False
    run_on_index: bool = False
    verify_batch_size: int = 10


async def _fetch_policy_json() -> dict | None:
    """GET the findings policy setting from the SLM settings API; None on any failure."""
    return await fetch_slm_policy_json(POLICY_SETTING_KEY)


async def get_findings_policy() -> FindingsPolicy:
    """Return the configured policy, or safe defaults (feature OFF)."""
    data = await _fetch_policy_json()
    if not isinstance(data, dict):
        return FindingsPolicy()
    try:
        raw_severity = str(data.get("min_severity", "medium"))
        min_severity = raw_severity if raw_severity in _VALID_SEVERITIES else "medium"
        return FindingsPolicy(
            enabled=bool(data["enabled"]),
            min_severity=min_severity,
            require_approval_to_promote=bool(data["require_approval_to_promote"]),
            run_on_index=bool(data["run_on_index"]),
            verify_batch_size=max(1, int(data["verify_batch_size"])),
        )
    except (KeyError, TypeError, ValueError):
        return FindingsPolicy()
