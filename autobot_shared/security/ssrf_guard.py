# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
- :func:`pinned_request_with_redirects` — like :func:`pinned_connector` but
  follows redirects, independently re-resolving + re-pinning EACH hop, for
  callers (``web_fetch``, ``media/link/pipeline``, #13019) that genuinely
  need redirect-following and cannot accept ``allow_redirects=False``

Dependencies: stdlib + aiohttp only (no autobot-* imports).
"""

from __future__ import annotations

import socket
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from urllib.parse import urljoin, urlparse

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


async def pinned_connector(url: str) -> aiohttp.TCPConnector:
    """Return an aiohttp connector pinned to *url*'s pre-resolved public IP.

    Resolves the host once via :func:`resolve_safe_ip` (asserting a public
    address), then returns a :class:`aiohttp.TCPConnector` whose resolver always
    maps the host to that IP. Callers pass the connector to a ``ClientSession``
    for their outbound POST/GET so the TCP connection cannot be re-resolved to a
    private address between the safety check and the socket connect
    (DNS-rebind TOCTOU). The original hostname is preserved for TLS SNI.

    Raises
    ------
    SSRFError
        If the host is missing or resolves to a non-public address.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise SSRFError("URL has no hostname")
    safe_ip = await resolve_safe_ip(host)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolver = safe_aiohttp_resolver(host, safe_ip, port)
    return aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)


@asynccontextmanager
async def pinned_request_with_redirects(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    timeout: aiohttp.ClientTimeout | None = None,
    max_redirects: int = 5,
    ssl: Any = None,
) -> AsyncIterator[aiohttp.ClientResponse]:
    """SSRF-safe request that follows redirects, re-pinning EACH hop (#13019).

    A single ``pinned_connector(url)`` + ``allow_redirects=True`` would be
    unsafe: :func:`safe_aiohttp_resolver` returns a resolver that maps ANY
    hostname to the *first* hop's pinned IP, so a cross-host redirect would
    either connect to the wrong server or (worse) silently reuse the original
    IP for a hostname it was never resolved for. This function instead issues
    each hop with ``allow_redirects=False`` through its OWN fresh
    :func:`pinned_connector`, so a redirect ``Location`` is independently
    resolved and safety-checked before it is ever connected to — a redirect
    to a private/loopback/link-local/rebound address raises
    :class:`SSRFError` instead of being followed, exactly like the initial
    URL would be.

    Bounded by *max_redirects*: an exhausted chain raises :class:`SSRFError`
    (distinguishable from a natural network failure) rather than silently
    truncating.

    Yields the terminal response with its body still open for the caller to
    stream; the owning session for that final hop is closed when the
    ``async with`` block exits (including on error). Intermediate hops close
    their own sessions immediately after reading the ``Location`` header.
    """
    current_url = url
    for _ in range(max_redirects + 1):
        connector = await pinned_connector(current_url)
        session = aiohttp.ClientSession(connector=connector, timeout=timeout)
        try:
            resp = await session.request(method, current_url, headers=headers, allow_redirects=False, ssl=ssl)
        except Exception:
            await session.close()
            raise

        location = resp.headers.get("Location") if 300 <= resp.status < 400 else None
        if location is None:
            try:
                yield resp
            finally:
                await session.close()
            return

        await resp.release()
        await session.close()
        current_url = urljoin(current_url, location)

    raise SSRFError(f"exceeded max_redirects={max_redirects} while fetching {url!r}")


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
        ) as response:  # SSRF mitigated: scheme validated, host resolved to public IP via resolve_safe_ip(), connector uses pinned resolver defeating DNS-rebind, redirects disabled (#6533)  # noqa: E501
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            body = await response.content.read(max_bytes + 1)

    return status, body[:max_bytes], content_type


__all__ = [
    "SSRFError",
    "resolve_safe_ip",
    "safe_aiohttp_resolver",
    "pinned_connector",
    "pinned_request_with_redirects",
    "fetch_safe_url",
]
