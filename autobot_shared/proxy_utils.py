# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Trusted-proxy utilities for IP extraction (Issue #2408).

Provides get_client_ip() — the canonical shared function for extracting the
real client IP from a FastAPI/Starlette request.  X-Forwarded-For is only
trusted when the direct TCP peer is a known reverse proxy; an attacker
connecting directly cannot spoof their IP via that header.

Both autobot-backend and autobot-slm-backend import from this module so the
trusted-proxy logic has a single source of truth and cannot diverge.

Configuration
-------------
Two calling conventions are supported:

1. Environment-driven (autobot-backend style):
   Set AUTOBOT_TRUSTED_PROXIES (comma-separated) to override the default
   list.  Defaults include localhost addresses and the nginx frontend VM IP
   derived from NetworkConstants (ConfigRegistry SSOT).
   Issue #2862 — removed hardcoded IP fallback; values flow through SSOT.

       ip = get_client_ip(request)  # uses module-level default set

2. Caller-supplied (autobot-slm-backend style):
   Pass an explicit iterable of trusted proxy IPs:

       ip = get_client_ip(request, trusted_proxies=settings.trusted_proxies)

Usage
-----
    from autobot_shared.proxy_utils import get_client_ip

    # Default (uses AUTOBOT_TRUSTED_PROXIES env var or built-in fallback)
    ip = get_client_ip(request)

    # Explicit proxy list
    ip = get_client_ip(request, trusted_proxies=["127.0.0.1", "::1"])
"""

import ipaddress
import logging
import os
from typing import Iterable

from starlette.requests import Request

logger = logging.getLogger(__name__)


def _build_default_trusted_proxies() -> frozenset:
    """Build the default trusted-proxy frozenset.

    Priority:
    1. AUTOBOT_TRUSTED_PROXIES environment variable (comma-separated IPs).
    2. Localhost addresses plus the frontend VM IP from NetworkConstants
       (backed by ConfigRegistry SSOT).

    Issue #2862 — replaces the hardcoded IP string with SSOT-derived values.
    The lazy import of NetworkConstants avoids circular import issues because
    autobot_shared/network_constants.py itself depends on autobot-backend's
    config.registry at runtime.
    """
    # Registered in env_registry (AUTOBOT_TRUSTED_PROXIES); read directly because
    # importing the registry here pulls logging_manager into every SLM test harness.
    raw = os.getenv("AUTOBOT_TRUSTED_PROXIES", "")  # ssot-config-exempt: pre-ssot shim
    if raw:
        return frozenset(ip.strip() for ip in raw.split(",") if ip.strip())

    proxies = {"127.0.0.1", "::1"}
    try:
        from autobot_shared.network_constants import NetworkConstants  # lazy import

        proxies.add(NetworkConstants.FRONTEND_VM_IP)
    except Exception:  # pragma: no cover — ImportError or AttributeError at startup
        logger.warning(
            "NetworkConstants unavailable; AUTOBOT_TRUSTED_PROXIES limited to localhost. "
            "Set AUTOBOT_TRUSTED_PROXIES explicitly to include nginx proxy IPs."
        )
    return frozenset(proxies)


# ---------------------------------------------------------------------------
# Default trusted-proxy set — built once at import time.
# Override via AUTOBOT_TRUSTED_PROXIES env var (comma-separated IPs).
# ---------------------------------------------------------------------------
_DEFAULT_TRUSTED_PROXIES: frozenset = _build_default_trusted_proxies()


def _normalize_ip(ip_str: str) -> str:
    """Normalize an IP string, mapping ::ffff:x.x.x.x to x.x.x.x.

    This handles dual-stack sockets that present IPv4 addresses as
    IPv6-mapped addresses (e.g. ``::ffff:127.0.0.1``).

    Args:
        ip_str: Raw IP string from socket or header.

    Returns:
        Canonical IP string.
    """
    try:
        addr = ipaddress.ip_address(ip_str)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(addr)
    except ValueError:
        return ip_str


def _trusted_networks(entries: Iterable[str]) -> tuple:
    """Parse trusted-proxy entries (single addresses or CIDR ranges); skip malformed ones."""
    networks = []
    for entry in entries:
        if not str(entry).strip():
            continue
        try:
            networks.append(ipaddress.ip_network(_normalize_ip(entry.strip()), strict=False))
        except ValueError:
            logger.warning("Ignoring malformed trusted-proxy entry (%d chars)", len(entry))
    return tuple(networks)


def _is_trusted(ip_str: str, networks: tuple) -> bool:
    """True when *ip_str* is an address inside one of *networks*."""
    try:
        address = ipaddress.ip_address(_normalize_ip(ip_str))
    except ValueError:
        return False
    return any(address in network for network in networks)


def client_from_forwarded_chain(forwarded: str, networks: tuple) -> str | None:
    """The client in an appended ``X-Forwarded-For`` chain, walked from the RIGHT (#17848).

    Each proxy APPENDS the address it received from (nginx
    ``$proxy_add_x_forwarded_for``), so the right-hand entries were written by
    our proxies and everything left of the first untrusted entry was written by
    the client. The first entry, from the right, that is not a trusted proxy is
    therefore the client; with one trusted hop that is the rightmost entry. How
    many hops to skip comes from the configured trusted set, never from the
    chain's length, which the client controls. ``None`` for an empty chain.
    """
    hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
    for hop in reversed(hops):
        if not _is_trusted(hop, networks):
            return hop
    return hops[0] if hops else None


def get_client_ip(
    request: Request,
    trusted_proxies: Iterable[str] | None = None,
) -> str | None:
    """Extract the real client IP from a Starlette/FastAPI request.

    What this prevents (#17848, #2252, #2239):

    * a client connecting DIRECTLY cannot choose its address: unless the TCP
      peer is a trusted proxy, ``X-Forwarded-For`` is ignored entirely;
    * a client connecting THROUGH a trusted proxy cannot either: the chain is
      read from the right, skipping trusted proxies, so a forged leftmost entry
      is never selected.

    What it does not prevent: a trusted proxy that forwards a client-supplied
    header unchanged instead of appending (every nginx config here appends), and
    an untrusted proxy in front of a trusted one -- its address is what you get,
    which is the correct answer for a rate-limit key but not the end user.

    Args:
        request: Incoming Starlette request.
        trusted_proxies: Iterable of trusted proxy addresses or CIDR ranges.
            ``None`` uses the module default from ``AUTOBOT_TRUSTED_PROXIES``
            or the built-in fallback list.

    Returns:
        Client IP string, or ``None`` when no connection info is available.
    """
    peer_ip = request.client.host if request.client else None
    if peer_ip is None:
        return None
    networks = _DEFAULT_TRUSTED_NETWORKS if trusted_proxies is None else _trusted_networks(trusted_proxies)
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded and _is_trusted(peer_ip, networks):
        return client_from_forwarded_chain(forwarded, networks) or peer_ip
    return peer_ip


#: The default trusted set, parsed once (#17848).
_DEFAULT_TRUSTED_NETWORKS: tuple = _trusted_networks(_DEFAULT_TRUSTED_PROXIES)
