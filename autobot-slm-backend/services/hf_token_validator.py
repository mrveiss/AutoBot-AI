# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HuggingFace token validation helper (#11718).

Probes a token against HF's ``whoami-v2`` endpoint at secret-save time so an
invalid/revoked ``hf_token`` is caught before it silently propagates to the
TTS worker (which falls back to an ungated model and still reports healthy).

Network failures never block the save — offline installs are supported.
The token value is never logged.
"""

import logging

import httpx

logger = logging.getLogger(__name__)

HF_WHOAMI_URL = "https://huggingface.co/api/whoami-v2"
HF_PROBE_TIMEOUT_SECONDS = 10.0

UNREACHABLE_WARNING = "Could not reach HuggingFace to validate the token; saved without verification."


async def probe_hf_token(token: str) -> tuple[bool | None, str | None]:
    """Probe a HuggingFace token against ``whoami-v2``.

    Returns ``(is_valid, warning)``:
      - ``(True, None)``: token confirmed valid.
      - ``(False, None)``: token confirmed invalid (HTTP 401) — caller rejects.
      - ``(None, warning)``: HF unreachable (network/timeout/unexpected status)
        — never blocks the save, but a warning is returned for the caller.
    """
    try:
        async with httpx.AsyncClient(timeout=HF_PROBE_TIMEOUT_SECONDS) as client:
            response = await client.get(
                HF_WHOAMI_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.HTTPError as exc:
        logger.warning("HuggingFace token probe failed (network error): %s", exc)
        return None, UNREACHABLE_WARNING

    if response.status_code == 401:
        return False, None
    if response.status_code >= 400:
        logger.warning("HuggingFace token probe returned unexpected status %d", response.status_code)
        return None, (
            f"HuggingFace returned unexpected status {response.status_code} "
            "while validating the token; saved without verification."
        )
    return True, None
