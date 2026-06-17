# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Network utility helpers for local-node detection (Issue #2759).

Consolidates three separate implementations of 'is this the local machine?'
logic from sync_orchestrator, code_sync, and code_source into one place.

The most robust implementation (from code_source.py, hardened in #2721) is
used as the base: it runs ``ip -4 addr show`` to enumerate all interface IPs
and also includes the hostname resolved from ``settings.external_url`` so the
check works even when the process is behind a reverse proxy.
"""

import logging
import re
import subprocess
import time
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Loopback / well-known local aliases always considered local
_LOOPBACK: frozenset = frozenset({"127.0.0.1", "::1", "localhost"})

# Cache for get_local_ips() — IPs change rarely; avoid repeated subprocess calls (Issue #2791)
_IP_CACHE_TTL: float = 60.0  # seconds
_ip_cache: set | None = None
_ip_cache_time: float = 0.0


def get_local_ips() -> set:
    """Return all IP addresses (and aliases) that identify this machine.

    Results are cached for ``_IP_CACHE_TTL`` seconds so that repeated calls
    (e.g., per-request is_local_ip checks) do not spawn a subprocess on every
    invocation (Issue #2791).

    Includes:
    - Loopback addresses (127.0.0.1, localhost, ::1)
    - All IPv4 addresses reported by ``ip -4 addr show``
    - The hostname extracted from ``settings.external_url`` (SSOT config)

    Returns:
        A set of strings that are considered local identifiers.
    """
    global _ip_cache, _ip_cache_time

    now = time.monotonic()
    if _ip_cache is not None and (now - _ip_cache_time) < _IP_CACHE_TTL:
        return _ip_cache

    local_ips: set = set(_LOOPBACK)

    # Enumerate all interface IPs via ``ip addr``
    try:
        result = subprocess.run(  # nosec B603 B607 - fixed ip argv for interface enumeration, no user input
            ["ip", "-4", "addr", "show"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
        for match in re.finditer(r"inet (\d+\.\d+\.\d+\.\d+)", result.stdout):
            local_ips.add(match.group(1))
    except Exception:
        pass

    # Also include the IP/hostname from the configured external_url
    try:
        from config import settings  # type: ignore[attr-defined]  # GH#7105: local backend import  # noqa: PLC0415

        own_host = urlparse(settings.external_url).hostname or ""
        if own_host:
            local_ips.add(own_host)
    except Exception:
        pass

    _ip_cache = local_ips
    _ip_cache_time = now
    return local_ips


def is_local_ip(ip: str) -> bool:
    """Return True if *ip* resolves to this machine.

    Args:
        ip: An IPv4 address string (or ``localhost`` / ``127.0.0.1``).

    Returns:
        True when the given address is one of the local IPs for this host.
    """
    return ip in get_local_ips()


def is_local_host(hostname_or_url: str) -> bool:
    """Return True if *hostname_or_url* identifies this machine.

    Accepts either a bare hostname / IP or a full URL.  If a URL is given
    the hostname is extracted first via ``urlparse``.

    Args:
        hostname_or_url: A bare IP / hostname, or a URL such as
            ``https://<slm-host>:8443``.

    Returns:
        True when the extracted host is one of the local addresses.
    """
    # Try as URL first; fall back to treating the whole string as a host
    parsed = urlparse(hostname_or_url)
    host = parsed.hostname or hostname_or_url
    return is_local_ip(host)
