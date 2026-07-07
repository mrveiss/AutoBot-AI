# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared httpx fetch helper for content_reach backends (#11078).

Encapsulates the injected-client-vs-async-with branch so backends stay DRY.
Error handling (httpx.HTTPError → BackendError) remains the caller's responsibility.
"""

from __future__ import annotations

from typing import Any

import httpx

# Default HTTP timeout in seconds — shared across all httpx-backed backends.
_HTTP_TIMEOUT = 15.0


async def http_get(
    url: str,
    *,
    client: httpx.AsyncClient | None,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = _HTTP_TIMEOUT,
) -> httpx.Response:
    """GET *url* with an optional injected client or a short-lived AsyncClient.

    If *client* is not None, uses it directly (test injection path).
    Otherwise opens a fresh AsyncClient, issues the request, and closes it.
    Callers must wrap this with ``try/except httpx.HTTPError`` as appropriate.
    """
    kwargs: dict[str, Any] = {}
    if headers is not None:
        kwargs["headers"] = headers
    if params is not None:
        kwargs["params"] = params

    if client is not None:
        return await client.get(url, **kwargs)

    async with httpx.AsyncClient(timeout=timeout) as c:
        return await c.get(url, **kwargs)
