# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import functools
import ipaddress
import os
import socket
from collections.abc import Collection
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# OAuth provider allowlist — single source of truth for SSRF-safe OAuth hosts.
# Shared by api/provider_auth.py and llm_shared/provider_auth.py so neither
# duplicates the list.  Override at runtime via AUTOBOT_PROVIDER_OAUTH_ALLOWED_HOSTS.
# ---------------------------------------------------------------------------

_DEFAULT_OAUTH_ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "accounts.google.com",
        "oauth2.googleapis.com",
        "github.com",
        "api.github.com",
        "huggingface.co",
        "login.microsoftonline.com",
        "api.openai.com",
        "auth.openai.com",
        "api.anthropic.com",
        "api.mistral.ai",
    }
)


def get_oauth_allowed_hosts() -> frozenset[str]:
    """Return the OAuth provider SSRF allowlist.

    Uses AUTOBOT_PROVIDER_OAUTH_ALLOWED_HOSTS (comma-separated hostnames) when
    set and non-empty; falls back to ``_DEFAULT_OAUTH_ALLOWED_HOSTS`` otherwise.
    Evaluated at call time so runtime env-var changes are reflected without restart.
    """
    raw = os.environ.get("AUTOBOT_PROVIDER_OAUTH_ALLOWED_HOSTS", "")
    if raw.strip():
        return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())
    return _DEFAULT_OAUTH_ALLOWED_HOSTS


# TLDs that are never public — rejected before DNS resolution.
_PRIVATE_TLDS = (".onion", ".internal", ".local", ".localhost", ".lan", ".home", ".corp")

# IPv6 Unique Local Address block — ``ipaddress.is_private`` already covers
# this on modern Python, but we check explicitly as defence-in-depth.
_IPV6_ULA = ipaddress.ip_network("fc00::/7")

# Short DNS timeout to prevent the SSRF check itself from becoming a DoS vector.
_DNS_TIMEOUT_SECONDS = 2.0


def _ip_is_hard_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True for addresses that are never a legitimate egress target (#13625).

    Loopback, link-local (which covers the 169.254.169.254 cloud-metadata
    endpoint), multicast, reserved and unspecified. These stay blocked even when
    a deployment opts into private-network egress: an operator hosting Confluence
    on an RFC-1918 address is a real deployment, whereas an operator hosting it
    on the metadata endpoint is not.
    """
    return bool(ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified)


def _ip_is_private(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Return True for RFC-1918 / ULA addresses — separable from the hard blocks (#13625)."""
    if ip.is_private and not _ip_is_hard_blocked(ip):
        return True
    # IPv6 Unique Local Addresses (fc00::/7) — redundant with is_private on
    # modern Python but kept explicit as defence-in-depth.
    return isinstance(ip, ipaddress.IPv6Address) and ip in _IPV6_ULA


def _ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, *, allow_private: bool = False) -> bool:
    """Return True if an IP is an acceptable egress target.

    With *allow_private* the RFC-1918/ULA range is permitted — self-hosted
    Confluence/GitLab/Nextcloud instances legitimately live there — while the
    hard blocks above still apply. Default is unchanged: public only.
    """
    if _ip_is_hard_blocked(ip):
        return False
    if _ip_is_private(ip):
        return allow_private
    return True


def is_public_url(url: str, *, allow_private: bool = False) -> bool:
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
        if host == "localhost":
            return False  # loopback is hard-blocked in both states (#13625)
        if any(host.endswith(tld) for tld in _PRIVATE_TLDS) and not allow_private:
            return False
        # If host is a literal IP, check directly without DNS.
        try:
            return _ip_is_public(ipaddress.ip_address(host), allow_private=allow_private)
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
            if not _ip_is_public(ipaddress.ip_address(addr), allow_private=allow_private):
                return False
        return True
    except (socket.gaierror, socket.timeout, ValueError, OSError):
        # Fail closed — any failure to verify means "not public".
        return False


async def is_public_url_async(url: str, *, allow_private: bool = False) -> bool:
    """Async wrapper: run the blocking DNS check in the default executor."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, functools.partial(is_public_url, url, allow_private=allow_private))


async def resolve_safe_ip_async(
    host: str, *, timeout: float = _DNS_TIMEOUT_SECONDS, allow_private: bool = False
) -> str:
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
        if not _ip_is_public(ip, allow_private=allow_private):
            raise ValueError(f"Host '{host}' resolves to a non-public address: {ip_str}")
        if safe_ip is None:
            safe_ip = ip_str

    if safe_ip is None:
        raise ValueError(f"Host '{host}' has no usable public IP address")
    return safe_ip


def require_allowlisted_https(url: str, allowed_hosts: Collection[str]) -> None:
    """Validate *url* as a safe outbound endpoint or raise ``ValueError`` (#11091).

    A superset SSRF guard for *server-configured* outbound endpoints (e.g. provider
    OAuth / token URLs). Unlike :func:`is_public_url` — which DNS-resolves an
    arbitrary user-supplied URL — this pins the request to an explicit host
    allowlist and the standard https port, so an allowlisted name can't be pivoted
    to reach another service or port. Consolidated here (per #11091 item 3) so the
    https / IP-literal / allowlist / port-pinning rules live in one SSRF module
    instead of being reimplemented at each caller.

    Raises ``ValueError`` with a human-readable reason (stdlib only, no transport
    dependency); callers translate it to their own error type (e.g. HTTP 400).

    Rules — any violation raises:
    - scheme must be ``https``
    - host must be present and not an IP literal (blocks 127.0.0.1, 10.x,
      169.254.169.254, ``::1``, …)
    - host (lowercased) must be in *allowed_hosts*
    - port must be the standard https port (``None`` or 443); a malformed port raises
    """
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("Invalid URL")

    if parsed.scheme != "https":
        raise ValueError("Only https URLs are permitted")

    host = parsed.hostname or ""
    if not host:
        raise ValueError("URL has no host")

    # ip_address() raises ValueError when host is NOT an IP; use a flag so the
    # "is a literal" rejection isn't swallowed by the same except clause.
    try:
        ipaddress.ip_address(host)
        is_ip_literal = True
    except ValueError:
        is_ip_literal = False
    if is_ip_literal:
        raise ValueError("IP-literal hosts are not permitted")

    if host.lower() not in allowed_hosts:
        raise ValueError(f"Host '{host}' is not in the allowlist")

    # urlparse defers port parsing to attribute access, so a malformed port
    # (e.g. ``:99999``) raises ValueError here — surface it as a clear reason
    # rather than letting it escape unhandled (#11066).
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("URL has an invalid port")
    if port not in (None, 443):
        raise ValueError("Only the standard https port (443) is permitted")


def host_matches(host: str, domain: str) -> bool:
    """Return True iff *host* is exactly *domain* or a subdomain of it (#11226).

    Domain-boundary-aware trust check. Unlike a substring test (``domain in host``)
    or an unanchored ``host.endswith(domain)``, this cannot be fooled by an
    attacker-controlled name that merely *contains* or *ends with* a trusted label:
    ``evilgithub.com`` does NOT match ``github.com``, while ``github.com`` and
    ``sub.github.com`` do. Case-insensitive and tolerant of a trailing FQDN dot.
    """
    host = host.lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


__all__ = [
    "is_public_url",
    "is_public_url_async",
    "resolve_safe_ip_async",
    "require_allowlisted_https",
    "get_oauth_allowed_hosts",
    "host_matches",
]
