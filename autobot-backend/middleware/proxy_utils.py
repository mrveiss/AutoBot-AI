# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Trusted-proxy utilities for IP extraction (Issue #2252).

Provides get_client_ip() — the canonical function for extracting the real
client IP from a FastAPI/Starlette request.  X-Forwarded-For is only
trusted when the direct TCP peer is a known reverse proxy; an attacker
connecting directly cannot spoof their IP via that header.

Configuration
-------------
Set AUTOBOT_TRUSTED_PROXIES (comma-separated) to override the default
list.  Defaults include localhost addresses and the nginx frontend VM
(172.16.168.21).  The comment ``# noqa: ssot-proxy`` suppresses the
hardcoding pre-commit check for the fallback string only.

Usage
-----
    from middleware.proxy_utils import get_client_ip

    ip = get_client_ip(request)           # returns str | None
"""

import ipaddress
import logging
import os
from typing import Optional

from starlette.requests import Request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Trusted-proxy list — read once at import time.
# Override via AUTOBOT_TRUSTED_PROXIES env var (comma-separated IPs).
# Defaults: localhost (IPv4 + IPv6) and the nginx frontend VM (.21).
# ---------------------------------------------------------------------------
_RAW_TRUSTED = os.getenv(
    "AUTOBOT_TRUSTED_PROXIES",
    "127.0.0.1,::1,172.16.168.21",  # noqa: ssot-proxy
)
_TRUSTED_PROXIES: frozenset = frozenset(
    ip.strip() for ip in _RAW_TRUSTED.split(",") if ip.strip()
)


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


def get_client_ip(request: Request) -> Optional[str]:
    """Extract the real client IP from a Starlette/FastAPI request.

    X-Forwarded-For is only honoured when the direct TCP connection
    originates from a trusted reverse proxy (Issue #2252).  If the
    connecting peer is not in AUTOBOT_TRUSTED_PROXIES the header is
    ignored and the raw peer IP is returned, preventing IP spoofing by
    clients that connect directly.

    Args:
        request: Incoming Starlette request.

    Returns:
        Client IP string, or ``None`` when no connection info is available.
    """
    peer_ip = request.client.host if request.client else None
    if peer_ip is None:
        return None

    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        normalized_peer = _normalize_ip(peer_ip)
        if normalized_peer in _TRUSTED_PROXIES:
            candidate = forwarded.split(",")[0].strip()
            if candidate:
                return candidate

    return peer_ip
