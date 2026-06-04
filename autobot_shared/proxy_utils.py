# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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


def get_client_ip(
    request: Request,
    trusted_proxies: Iterable[str] | None = None,
) -> str | None:
    """Extract the real client IP from a Starlette/FastAPI request.

    X-Forwarded-For is only honoured when the direct TCP connection
    originates from a trusted reverse proxy (Issue #2252, #2239).  If the
    connecting peer is not in the trusted set the header is ignored and the
    raw peer IP is returned, preventing IP spoofing by clients that connect
    directly.

    Args:
        request: Incoming Starlette request.
        trusted_proxies: Iterable of trusted proxy IP strings.  When
            ``None`` (the default) the module-level set is used, which
            is populated from the ``AUTOBOT_TRUSTED_PROXIES`` environment
            variable or the built-in fallback list.

    Returns:
        Client IP string, or ``None`` when no connection info is available.
    """
    peer_ip = request.client.host if request.client else None
    if peer_ip is None:
        return None

    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        normalized_peer = _normalize_ip(peer_ip)
        if trusted_proxies is None:
            trusted_set: frozenset = _DEFAULT_TRUSTED_PROXIES
        else:
            trusted_set = frozenset(_normalize_ip(p) for p in trusted_proxies)

        if normalized_peer in trusted_set:
            candidate = forwarded.split(",")[0].strip()
            if candidate:
                return candidate

    return peer_ip
