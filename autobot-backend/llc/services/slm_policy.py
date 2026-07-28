# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Canonical SLM-settings JSON policy reader (#11359).

Both ``disposal_policy.py`` and ``findings_policy.py`` independently defined
a structurally-identical ``_fetch_policy_json()``: GET the SLM settings API
for a given key, return ``None`` on any failure (missing client, non-200
response, malformed JSON) so callers fall back to safe defaults. This module
is the single, shared implementation; each policy module keeps only its
dataclass + coercion logic.
"""

import json
import logging

from services.slm_client import get_slm_client

logger = logging.getLogger(__name__)


async def fetch_slm_policy_json(key: str) -> dict | None:
    """GET the SLM setting ``key``'s JSON value; ``None`` on any failure.

    Best-effort read: no SLM client configured, a non-200 response, or a
    malformed/undecodable ``value`` all resolve to ``None`` rather than
    raising, so callers can apply safe defaults.
    """
    client = get_slm_client()
    if client is None:
        return None
    try:
        session = await client._get_session()
        url = f"{client.slm_url}/api/settings/{key}"
        async with session.get(url) as response:
            if response.status != 200:
                return None
            setting = await response.json()
            raw = setting.get("value")
            # ``value`` is stored as an escaped JSON string; if the SLM API is ever
            # changed to return it pre-decoded (a dict), json.loads raises TypeError
            # and the outer except returns None -> caller uses its safe defaults.
            return json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001 - policy read is best-effort
        logger.warning("SLM policy read failed for key=%s: %s", key, exc)
        return None
