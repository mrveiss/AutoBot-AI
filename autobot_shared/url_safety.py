# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""SSRF (Server-Side Request Forgery) guards for URL safety checks.

Extracted from ``autobot-backend/media/link/pipeline.py`` (#7477) so that
``web_fetch.fetcher`` can call the SSRF check directly instead of reaching
into ``LinkPipeline`` via a ``__new__`` hack + lazy import (which was the
last leg of the ``pipeline.py ↔ fetcher.py`` circular dependency).

Consolidated per #6533: ``marketplace_sources._resolve_safe_ip`` and
``services/url_validator.URLValidator.is_safe_url`` both reimplemented the
same RFC-range checks; they now delegate here.

The functions here are pure-Python — only stdlib (``ipaddress``, ``socket``,
``asyncio``, ``urllib.parse``) — and have zero autobot-* dependencies, so
they're safely importable from any layer.

Public API
----------
- :func:`is_public_url` — sync DNS-resolving check
- :func:`is_public_url_async` — async wrapper that runs the blocking
  ``getaddrinfo`` in the default executor
- :func:`resolve_safe_ip_async` — async DNS resolution that *returns* the
  safe IP literal, enabling callers to connect directly to the resolved
  address (defeats DNS-rebind TOCTOU attacks)

The ``LinkPipeline._is_public_url`` / ``_is_public_url_async`` methods are
preserved as backward-compat thin wrappers that delegate here.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse

# TLDs that are never public — rejected before DNS resolution.
_PRIVATE_TLDS = (".onion", ".internal", ".local", ".localhost", ".lan", ".home", ".corp")

# IPv6 Unique Local Address block — ``ipaddress.is_private`` already covers
# this on modern Python, but we check explicitly as defence-in-depth.
_IPV6_ULA = ipaddress.ip_network("fc00::/7")

# Short DNS timeout to prevent the SSRF check itself from becoming a DoS vector.
_DNS_TIMEOUT_SECONDS = 2.0


def _ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True only if an IP address is routable on the public internet."""
    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
        return False
    # IPv6 Unique Local Addresses (fc00::/7) — redundant with is_private on
    # modern Python but kept explicit as defence-in-depth.
    if isinstance(ip, ipaddress.IPv6Address) and ip in _IPV6_ULA:
        return False
    return True


def is_public_url(url: str) -> bool:
    """Return True only for public HTTP/HTTPS URLs.

    Resolves the hostname via DNS and rejects if *any* resolved address is
    private, loopback, link-local, multicast, reserved, or unspecified. This
    closes the SSRF hole where an internal hostname like
    ``intranet-db.company`` or a DNS-rebinding label like
    ``10-0-0-1.my-domain.com`` would otherwise be proxied via Jina Reader
    or other URL-fetching surfaces.

    **Note:** this performs a blocking DNS lookup; callers on the async
    path must use :func:`is_public_url_async` instead.
    """
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = (parsed.hostname or "").lower()
        if not host:
            return False
        # Reject bare private names and private TLDs outright — no DNS needed.
        if host in ("localhost",) or any(host.endswith(tld) for tld in _PRIVATE_TLDS):
            return False
        # If host is a literal IP, check directly without DNS.
        try:
            return _ip_is_public(ipaddress.ip_address(host))
        except ValueError:
            pass
        # Resolve hostname and reject if *any* A/AAAA record is non-public.
        prev_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(_DNS_TIMEOUT_SECONDS)
        try:
            infos = socket.getaddrinfo(host, None)
        finally:
            socket.setdefaulttimeout(prev_timeout)
        if not infos:
            return False
        for info in infos:
            addr = info[4][0]
            # Strip IPv6 scope id (e.g. "fe80::1%eth0") before parsing.
            addr = addr.split("%", 1)[0]  # type: ignore[union-attr]  # GH#7105: info[4] is always (str,...) for TCP/UDP
            if not _ip_is_public(ipaddress.ip_address(addr)):
                return False
        return True
    except (socket.gaierror, socket.timeout, ValueError, OSError):
        # Fail closed — any failure to verify means "not public".
        return False


async def is_public_url_async(url: str) -> bool:
    """Async wrapper: run the blocking DNS check in the default executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, is_public_url, url)


async def resolve_safe_ip_async(host: str, *, timeout: float = _DNS_TIMEOUT_SECONDS) -> str:
    """Resolve *host* and return the first globally-routable IP literal.

    Raises ``ValueError`` if the hostname resolves to any private, loopback,
    link-local, multicast, reserved, or unspecified address, or if DNS
    resolution fails. Callers should connect to the returned IP directly
    (bypassing DNS on the actual connection) to defeat DNS-rebind TOCTOU
    attacks.

    Parameters
    ----------
    host:
        Raw hostname or IP literal — not a full URL.
    timeout:
        DNS resolution timeout in seconds (default 2.0).
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError) as exc:
        raise ValueError(f"Could not resolve host '{host}': {exc}") from exc

    safe_ip: str | None = None
    for info in infos:
        ip_str = info[4][0].split("%", 1)[0]  # strip IPv6 scope id
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if not _ip_is_public(ip):
            raise ValueError(f"Host '{host}' resolves to a non-public address: {ip_str}")
        if safe_ip is None:
            safe_ip = ip_str

    if safe_ip is None:
        raise ValueError(f"Host '{host}' has no usable public IP address")
    return safe_ip


__all__ = ["is_public_url", "is_public_url_async", "resolve_safe_ip_async"]
