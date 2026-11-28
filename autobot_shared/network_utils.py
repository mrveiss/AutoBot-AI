# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Network utility helpers for local-node detection (Issue #2759).

Consolidates three separate implementations of 'is this the local machine?'
logic from sync_orchestrator, code_sync, and code_source into one place.

``get_local_ips`` enumerates interface addresses (``ip -o -4 addr show``) and the
``settings.external_url`` host. ``is_local_ip`` is the conservative question built on it:
local only when provable, remote when unknown or ambiguous (see its docstring for the rule).
"""

import ipaddress
import logging
import re
import socket
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


#: Interfaces whose addresses are shared with, or reachable from, other hosts: container
#: bridges, virtual ethernet pairs, CNI/overlay devices, VPN/tailnet tunnels. The same address
#: (``172.17.0.1`` on ``docker0``) exists on every Docker host, so matching it proves nothing.
_SHARED_IFACE_RE = re.compile(
    r"^(docker\d*|br-.*|veth.*|virbr.*|cni.*|flannel.*|cali.*|weave.*|tailscale.*|ts\d+|wg.*|tun.*|tap.*|zt.*)$"
)

#: Overlay / CGNAT space (Tailscale hands every node an address here): never proof of locality.
_SHARED_NETWORKS = (ipaddress.ip_network("100.64.0.0/10"),)

_IFACE_LINE_RE = re.compile(r"^\d+:\s+(\S+)\s+inet (\d+\.\d+\.\d+\.\d+)")


def _interfaces() -> list[tuple[str, str]]:
    """``(interface name, IPv4)`` pairs from ``ip -o -4 addr show``; empty if it cannot run."""
    try:
        result = subprocess.run(  # nosec B603 B607  # fixed ip argv for interface enumeration, no user input
            ["ip", "-o", "-4", "addr", "show"], capture_output=True, text=True, encoding="utf-8", timeout=5
        )
    except Exception:
        return []
    pairs = []
    for line in result.stdout.splitlines():
        match = _IFACE_LINE_RE.match(line.strip())
        if match:
            pairs.append((match.group(1).split("@", 1)[0], match.group(2)))
    return pairs


def get_local_ips() -> set:
    """Return all IP addresses (and aliases) that identify this machine.

    Includes loopback, every IPv4 interface address (container bridges and tunnels too, since
    callers use this to recognise the host's own fleet addresses) and the ``settings.external_url``
    host. Cached for ``_IP_CACHE_TTL`` seconds (Issue #2791). Not a locality PROOF -- use
    :func:`is_local_ip` for that.
    """
    global _ip_cache, _ip_cache_time

    now = time.monotonic()
    if _ip_cache is not None and (now - _ip_cache_time) < _IP_CACHE_TTL:
        return _ip_cache

    local_ips: set = set(_LOOPBACK)
    local_ips.update(ip for _, ip in _interfaces())
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


def _is_genuinely_local(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """One literal address: loopback, or an exact address of a NON-shared interface."""
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if ip.is_unspecified or ip.is_link_local:
        return False  # "any address" / per-link: ambiguous by definition
    if ip.is_loopback:
        return True
    if any(ip in net for net in _SHARED_NETWORKS if ip.version == net.version):
        return False
    text = str(ip)
    if any(addr == text and _SHARED_IFACE_RE.match(name) for name, addr in _interfaces()):
        return False
    return text in get_local_ips()


def is_local_ip(ip: str) -> bool:
    """Return True only when *ip* is PROVABLY this machine; anything unclear is remote.

    The result picks local execution over SSH, so a false "local" runs a command on the wrong
    host while a false "remote" merely costs an SSH hop. The rule, in order:

    * a literal IP is local if it is loopback (``::ffff:127.0.0.1`` included), or EXACTLY
      matches an interface address (``::ffff:a.b.c.d`` is unwrapped first);
    * never local: ``0.0.0.0`` / ``::``, link-local (``169.254/16``, ``fe80::/10``), the
      ``100.64/10`` overlay range, and any address on a container bridge, veth, CNI or
      VPN/tunnel interface (``docker0``, ``br-*``, ``tailscale0`` ...) -- those exist on many
      hosts at once;
    * a hostname is local only if it resolves and EVERY resolved address is local by the
      rules above (``localhost`` is local); an unresolvable name is remote.
    """
    text = (ip or "").strip().strip("[]")
    if not text:
        return False
    try:
        return _is_genuinely_local(ipaddress.ip_address(text.split("%", 1)[0]))
    except ValueError:
        pass
    if text.lower() == "localhost":
        return True
    try:
        infos = socket.getaddrinfo(text, None)
    except OSError:
        return False
    resolved = {str(info[4][0]).split("%", 1)[0] for info in infos}
    try:
        return bool(resolved) and all(_is_genuinely_local(ipaddress.ip_address(a)) for a in resolved)
    except ValueError:
        return False


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
