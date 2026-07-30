# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared httpx fetch helper for content_reach backends (#11078).

Encapsulates the injected-client-vs-async-with branch so backends stay DRY.
Error handling (httpx.HTTPError → BackendError) remains the caller's responsibility.

SSRF (#13017): the production (no injected client) path validates a URL with
``content_reach._url_guard.ensure_public_url`` and then connects separately —
classic TOCTOU, since DNS can change between the check and the connect. This
module closes that gap the same way ``pinned_connector`` does for aiohttp
call sites (``agent_loop/search/config_declared_provider.py``): resolve the
host to a public IP literal once, then connect directly to that IP (Host
header + TLS SNI preserved via httpx's ``extensions={"sni_hostname": ...}``)
so the address validated is the address connected to. The injected-client
test path is unaffected — tests bypass real network entirely.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

# Default HTTP timeout in seconds — shared across all httpx-backed backends.
_HTTP_TIMEOUT = 15.0


def _pin_host(url: str, safe_ip: str) -> str:
    """Return *url* with its host literal replaced by *safe_ip* (port preserved, IPv6 bracketed)."""
    parsed = urlparse(url)
    netloc = f"[{safe_ip}]" if ":" in safe_ip else safe_ip
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


async def _pinned_get(
    url: str,
    *,
    headers: dict[str, str] | None,
    params: dict[str, Any] | None,
    timeout: float,
) -> httpx.Response:
    """SSRF-safe GET: resolve *url*'s host to a public IP and connect to that literal address.

    Raises ``autobot_shared.security.ssrf_guard.SSRFError`` if the host is
    missing or resolves to a non-public address (defeats DNS-rebind TOCTOU
    between ``ensure_public_url`` and the fetch — #13017).
    """
    from autobot_shared.security.ssrf_guard import SSRFError, resolve_safe_ip

    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise SSRFError(f"URL has no hostname: {url!r}")

    safe_ip = await resolve_safe_ip(host)
    pinned_url = _pin_host(url, safe_ip)
    req_headers = dict(headers or {})
    req_headers.setdefault("Host", host)
    extensions = {"sni_hostname": host} if parsed.scheme == "https" else {}

    async with httpx.AsyncClient(timeout=timeout) as c:
        return await c.get(pinned_url, headers=req_headers, params=params, extensions=extensions)


async def http_get(
    url: str,
    *,
    client: httpx.AsyncClient | None,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    timeout: float = _HTTP_TIMEOUT,
) -> httpx.Response:
    """GET *url* with an optional injected client or a pinned short-lived AsyncClient.

    If *client* is not None, uses it directly (test injection path) — unchanged.
    Otherwise resolves the host to a safe IP and connects to that literal
    address (see :func:`_pinned_get`) so validation and connection cannot
    diverge (#13017). Callers must wrap this with ``try/except httpx.HTTPError``
    (network errors) and ``SSRFError`` (guard rejections) as appropriate.
    """
    if client is not None:
        kwargs: dict[str, Any] = {}
        if headers is not None:
            kwargs["headers"] = headers
        if params is not None:
            kwargs["params"] = params
        return await client.get(url, timeout=timeout, **kwargs)

    return await _pinned_get(url, headers=headers, params=params, timeout=timeout)
