# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Read the SLM-configured project disposal policy with safe defaults (#11129 P2)."""

from dataclasses import dataclass

from llc.services.slm_policy import fetch_slm_policy_json

POLICY_SETTING_KEY = "llc.project_disposal_policy"


@dataclass(frozen=True)
class DisposalPolicy:
    retention_days: int = 0
    require_approval: bool = False


async def _fetch_policy_json() -> dict | None:
    """GET the disposal policy setting from the SLM settings API; None on any failure."""
    return await fetch_slm_policy_json(POLICY_SETTING_KEY)


async def get_disposal_policy() -> DisposalPolicy:
    """Return the configured policy, or safe defaults (immediate/no-approval)."""
    data = await _fetch_policy_json()
    if not isinstance(data, dict):
        return DisposalPolicy()
    try:
        return DisposalPolicy(
            retention_days=max(0, int(data["retention_days"])),
            require_approval=bool(data["require_approval"]),
        )
    except (KeyError, TypeError, ValueError):
        return DisposalPolicy()
