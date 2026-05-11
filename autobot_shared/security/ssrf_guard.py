# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""SSRF guard: DNS-pinning resolver and SSRF-safe HTTP fetch (GH #6533).

Consolidates four previously independent SSRF guard implementations
(marketplace_sources, media/link/pipeline, a2a/capability_verifier,
api/knowledge) into a single hardened module.

Public API
----------
- :class:`SSRFError` — raised when a host is blocked
- :func:`resolve_safe_ip` — async DNS resolution with private-IP rejection
- :func:`safe_aiohttp_resolver` — pinned aiohttp resolver factory (prevents
  DNS rebinding between resolution and connection)
- :func:`fetch_safe_url` — SSRF-safe HTTP GET (DNS pin + no redirects)

Design notes
------------
- No FastAPI/HTTPException dependency. Callers that need HTTP 400 responses
  catch ``SSRFError`` and raise their own ``HTTPException``.
- Builds on :func:`autobot_shared.url_safety._ip_is_public` for the
  address-classification logic (single implementation).
- ``aiohttp`` is imported lazily inside functions that need it so this
  module is safely importable even where aiohttp is not installed.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from autobot_shared.url_safety import _ip_is_public

if TYPE_CHECKING:
    import aiohttp


class SSRFError(ValueError):
    """Raised when a URL or host is blocked by the SSRF guard.

    Callers in HTTP layers should catch this and raise an appropriate
    ``HTTPException(400)`` with the embedded message.
    """


async def resolve_safe_ip(host: str) -> str:
    """Resolve *host* to a single public IP address.

    Performs an async DNS lookup and validates every resolved address.
    Raises :exc:`SSRFError` if:

    * DNS resolution fails
    * any resolved address is loopback, private (RFC 1918), link-local
      (e.g. 169.254.169.254 AWS metadata), multicast, reserved, or
      unique-local IPv6
    * the IPv4-mapped form of an IPv6 address would be private
    * no addresses resolve at all

    Returns the first public IP string so the caller can create a
    :func:`safe_aiohttp_resolver` that pins the connection and prevents
    DNS-rebind attacks.
    """
    try:
        loop = asyncio.get_running_loop()
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError) as exc:
        raise SSRFError(f"Could not resolve host {host!r}: {exc}") from exc

    safe_ip: str | None = None
    for info in infos:
        ip_str = info[4][0]
        # Strip IPv6 scope id before parsing (e.g. "fe80::1%eth0").
        ip_str = ip_str.split("%", 1)[0]
        try:
            ip: ipaddress.IPv4Address | ipaddress.IPv6Address = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        # Unwrap IPv4-mapped IPv6 addresses (::ffff:192.168.x.x) — the mapped
        # IPv4 part may be private even when the outer IPv6 form is not flagged
        # as such on older Python versions.
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped

        if not _ip_is_public(ip):
            raise SSRFError(f"Host {host!r} resolves to non-public address {ip_str} — request blocked")
        if safe_ip is None:
            safe_ip = ip_str

    if safe_ip is None:
        raise SSRFError(f"Host {host!r} has no usable public IP address")
    return safe_ip


def safe_aiohttp_resolver(
    host: str,
    safe_ip: str,
    port: int,
) -> "aiohttp.abc.AbstractResolver":
    """Return an aiohttp resolver that always maps *host*:*port* to *safe_ip*.

    Pass this resolver to :class:`aiohttp.TCPConnector` with
    ``use_dns_cache=False`` to pin every outbound connection to the IP that
    was validated by :func:`resolve_safe_ip`.  This prevents DNS-rebind
    attacks where a hostname changes from a public IP to a private one
    between the resolution check and the actual connection.

    Example::

        safe_ip = await resolve_safe_ip(host)
        resolver = safe_aiohttp_resolver(host, safe_ip, port)
        connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, allow_redirects=False) as resp:
                ...
    """
    import aiohttp  # noqa: PLC0415

    entry = [
        {
            "hostname": host,
            "host": safe_ip,
            "port": port,
            "family": socket.AF_INET,
            "proto": 0,
            "flags": 0,
        }
    ]

    class _PinnedResolver(aiohttp.abc.AbstractResolver):
        async def resolve(
            self,
            hostname: str,
            port_: int = 0,
            family: int = socket.AF_INET,
        ) -> list:
            return entry if hostname == host else []

        async def close(self) -> None:
            return None

    return _PinnedResolver()


async def fetch_safe_url(
    url: str,
    *,
    timeout_s: float = 15.0,
    max_bytes: int | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    """SSRF-safe HTTP GET.

    Applies all four layers of the SSRF defence-in-depth strategy:

    1. **Scheme guard** — only ``http`` / ``https`` accepted.
    2. **DNS-resolving IP guard** — :func:`resolve_safe_ip` rejects any host
       that resolves to a private, loopback, link-local, or reserved address.
    3. **Resolver pinning** — :func:`safe_aiohttp_resolver` creates a
       connector that always connects to the pre-verified IP, closing the
       TOCTOU window between DNS check and connect.
    4. **Redirect guard** — ``allow_redirects=False`` prevents a server from
       bouncing the client to an internal address via a 3xx response.

    Parameters
    ----------
    url:
        Target URL (must be http or https).
    timeout_s:
        Total request timeout in seconds (default 15).
    max_bytes:
        If set, read at most *max_bytes* + 1 bytes so the caller can detect
        oversized responses without buffering everything.
    extra_headers:
        Optional additional HTTP request headers.

    Returns
    -------
    tuple[int, bytes]
        ``(http_status_code, body_bytes)``

    Raises
    ------
    SSRFError
        If the URL scheme is not allowed or the host resolves to a
        private/reserved address.
    aiohttp.ClientError
        On network-level errors (connection refused, TLS failure, etc.).
    """
    import aiohttp  # noqa: PLC0415

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFError(f"URL scheme {parsed.scheme!r} not allowed (only http/https)")
    host = parsed.hostname
    if not host:
        raise SSRFError("URL has no hostname")

    safe_ip = await resolve_safe_ip(host)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolver = safe_aiohttp_resolver(host, safe_ip, port)
    connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)
    timeout = aiohttp.ClientTimeout(total=timeout_s)

    headers = extra_headers or {}
    async with aiohttp.ClientSession(timeout=timeout, connector=connector, headers=headers) as session:
        async with session.get(url, allow_redirects=False) as response:
            if max_bytes is not None:
                body = await response.content.read(max_bytes + 1)
            else:
                body = await response.read()
            return response.status, body


__all__ = [
    "SSRFError",
    "resolve_safe_ip",
    "safe_aiohttp_resolver",
    "fetch_safe_url",
]
