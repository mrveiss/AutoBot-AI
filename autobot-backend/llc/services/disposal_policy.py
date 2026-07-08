# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Read the SLM-configured project disposal policy with safe defaults (#11129 P2)."""
import json
import logging
from dataclasses import dataclass
from typing import Optional

from services.slm_client import get_slm_client

logger = logging.getLogger(__name__)

POLICY_SETTING_KEY = "llc.project_disposal_policy"


@dataclass(frozen=True)
class DisposalPolicy:
    retention_days: int = 0
    require_approval: bool = False


async def _fetch_policy_json() -> Optional[dict]:
    """GET the policy setting from the SLM settings API; None on any failure."""
    client = get_slm_client()
    if client is None:
        return None
    try:
        session = await client._get_session()
        url = f"{client.slm_url}/api/settings/{POLICY_SETTING_KEY}"
        async with session.get(url) as response:
            if response.status != 200:
                return None
            setting = await response.json()
            raw = setting.get("value")
            return json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001 — policy read is best-effort
        logger.warning("Disposal policy read failed: %s", exc)
        return None


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
