# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""Canonical SSRF guard utilities for AutoBot (#6533).

Consolidates four independent SSRF implementations into a single module.
All call sites that previously had inline guards or ad-hoc DNS checks
now delegate here.

Public API
----------
- :class:`SSRFError` — raised for unsafe URLs (subclass of ValueError for
  easy HTTPException conversion at call sites)
- :func:`resolve_safe_ip` — async DNS resolution that returns a safe IP
  literal, defeating DNS-rebind TOCTOU attacks
- :func:`safe_aiohttp_resolver` — returns a pinned aiohttp AbstractResolver
  that connects to the pre-resolved IP
- :func:`fetch_safe_url` — full SSRF-safe HTTP GET: resolve → pin → fetch,
  with allow_redirects=False enforced

Dependencies: stdlib + aiohttp only (no autobot-* imports).
"""

from __future__ import annotations

import socket

import aiohttp
import aiohttp.abc

from autobot_shared.url_safety import resolve_safe_ip_async


class SSRFError(ValueError):
    """Raised when a URL fails SSRF safety checks."""


async def resolve_safe_ip(host: str) -> str:
    """Resolve *host* to a globally-routable IP literal.

    Wraps :func:`autobot_shared.url_safety.resolve_safe_ip_async` and
    re-raises ``ValueError`` as :class:`SSRFError` so callers can handle
    unsafe URLs with a single except clause.

    Raises
    ------
    SSRFError
        If the hostname resolves to a private, loopback, link-local,
        multicast, reserved, or unspecified address, or if DNS fails.
    """
    try:
        return await resolve_safe_ip_async(host)
    except ValueError as exc:
        raise SSRFError(str(exc)) from exc


def safe_aiohttp_resolver(host: str, safe_ip: str, port: int) -> aiohttp.abc.AbstractResolver:
    """Return an aiohttp resolver that always maps *host* → *safe_ip*.

    Using this resolver for the aiohttp connector ensures the socket
    connects to the pre-verified IP rather than re-resolving the hostname,
    defeating DNS-rebind TOCTOU attacks where DNS re-resolves to a private
    address between the safety check and the actual connection.

    Parameters
    ----------
    host:
        The original hostname (preserved for TLS SNI / virtual hosting).
    safe_ip:
        The public IP returned by :func:`resolve_safe_ip`.
    port:
        The destination port (used to populate the resolver result).
    """

    class _PinnedResolver(aiohttp.abc.AbstractResolver):
        async def resolve(
            self,
            hostname: str,
            port_: int = 0,
            family: int = socket.AF_INET,
        ) -> list:
            return [
                {
                    "hostname": hostname,
                    "host": safe_ip,
                    "port": port_ or port,
                    "family": socket.AF_INET,
                    "proto": 0,
                    "flags": 0,
                }
            ]

        async def close(self) -> None:
            return None

    return _PinnedResolver()


async def fetch_safe_url(
    url: str,
    *,
    timeout: float = 15.0,
    max_bytes: int = 4 * 1024 * 1024,
    headers: dict | None = None,
) -> tuple[int, bytes, str]:
    """Fetch *url* with full SSRF protection.

    Protection layers:
    1. Scheme validation — only http/https allowed.
    2. DNS resolution via :func:`resolve_safe_ip` — rejects private,
       loopback, link-local, multicast, reserved addresses.
    3. Pinned resolver via :func:`safe_aiohttp_resolver` — connector
       bypasses DNS on the actual TCP connection, defeating rebind attacks.
    4. ``allow_redirects=False`` — prevents a 301/302 to an internal IP
       from bypassing the SSRF check.
    5. ``max_bytes`` cap — prevents memory exhaustion on oversized responses.

    Parameters
    ----------
    url:
        Absolute HTTP/HTTPS URL to fetch.
    timeout:
        Total request timeout in seconds (default 15).
    max_bytes:
        Maximum response body in bytes (default 4 MB). Bodies exceeding
        this limit are silently truncated.
    headers:
        Optional request headers dict.

    Returns
    -------
    tuple[int, bytes, str]
        ``(status_code, body_bytes, content_type)``

    Raises
    ------
    SSRFError
        If the URL fails SSRF safety checks (bad scheme, private IP, etc.).
    aiohttp.ClientError
        On network / connection errors.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"URL scheme '{parsed.scheme}' not allowed; only http/https permitted")
    host = parsed.hostname
    if not host:
        raise SSRFError("URL has no hostname")

    safe_ip = await resolve_safe_ip(host)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    resolver = safe_aiohttp_resolver(host, safe_ip, port)
    connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)
    client_timeout = aiohttp.ClientTimeout(total=timeout)

    async with aiohttp.ClientSession(
        timeout=client_timeout,
        connector=connector,
        headers=headers or {},
    ) as session:
        async with session.get(
            url, allow_redirects=False
        ) as response:  # codeql[py/full-ssrf] SSRF mitigated: scheme validated, host resolved to public IP via resolve_safe_ip(), connector uses pinned resolver defeating DNS-rebind, redirects disabled (#6533)  # noqa: E501
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            body = await response.content.read(max_bytes + 1)

    return status, body[:max_bytes], content_type


__all__ = ["SSRFError", "resolve_safe_ip", "safe_aiohttp_resolver", "fetch_safe_url"]
