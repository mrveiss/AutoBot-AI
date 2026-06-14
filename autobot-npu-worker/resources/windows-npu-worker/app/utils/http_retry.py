# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared HTTP retry primitive for Windows NPU Worker.

Issue #5430: Extract aiohttp-session-with-backoff pattern duplicated across
config_bootstrap.py and backend_telemetry.py.

NOTE: This module is intentionally self-contained — it must NOT import from
autobot_shared/ because the NPU worker deploys as a standalone PyInstaller
executable.
"""

import asyncio
import logging
import aiohttp


async def aiohttp_with_backoff(
    url: str,
    method: str = "GET",
    *,
    json_body: dict | None = None,
    headers: dict | None = None,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
    timeout_s: float = 10.0,
    logger: logging.Logger | None = None,
) -> dict | None:
    """POST/GET via aiohttp with exponential backoff; returns JSON dict or None on failure.

    Each attempt opens a fresh ClientSession (appropriate for one-shot startup
    calls; long-lived connections should use a persistent session instead).

    Args:
        url: Full URL to request.
        method: HTTP verb (case-insensitive). Defaults to 'GET'.
        json_body: If provided, serialised as JSON request body.
        headers: Optional extra headers to send with every attempt.
        max_attempts: Total number of attempts before giving up.
        initial_delay: Seconds to wait before the second attempt.  Doubles on
            each subsequent attempt (exponential backoff).
        max_delay: Upper bound on inter-attempt delay.
        timeout_s: aiohttp ClientTimeout total for each attempt.
        logger: Logger to use; falls back to this module's logger.

    Returns:
        Parsed JSON dict on the first successful (2xx) response, or None if all
        attempts fail.
    """
    log = logger or logging.getLogger(__name__)
    delay = initial_delay
    req_kwargs: dict = {}
    if json_body is not None:
        req_kwargs["json"] = json_body
    if headers:
        req_kwargs["headers"] = headers

    for attempt in range(max_attempts):
        try:
            timeout = aiohttp.ClientTimeout(total=timeout_s)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with getattr(session, method.lower())(url, **req_kwargs) as resp:
                    resp.raise_for_status()
                    return await resp.json()
        except Exception as exc:
            log.warning(
                "HTTP %s %s attempt %d/%d failed: %s",
                method.upper(),
                url,
                attempt + 1,
                max_attempts,
                exc,
            )
            if attempt < max_attempts - 1:
                await asyncio.sleep(delay)
                delay = min(delay * 2, max_delay)

    return None
