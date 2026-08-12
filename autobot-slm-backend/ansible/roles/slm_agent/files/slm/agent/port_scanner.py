# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Port Scanner Module (Issue #779).

Detects listening TCP ports on the local system.
"""

import logging
import subprocess  # nosec B404  # subprocess used with fixed commands for system inspection
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class PortInfo:
    """Information about a listening port."""

    port: int
    process: str | None = None
    pid: int | None = None
    # GH#11224: bind interface ("0.0.0.0", "*", "::", "127.0.0.1", a concrete IP).
    # Lets the fleet security-posture audit distinguish public exposure from
    # loopback-only. None when the source line can't be parsed.
    address: str | None = None


def _parse_port_from_address(local_addr: str) -> int | None:
    """
    Parse port number from local address string.

    Handles formats: *:port, 0.0.0.0:port, :::port. Issue #620.

    Args:
        local_addr: Local address string from ss output

    Returns:
        Port number or None if parsing fails
    """
    if ":" not in local_addr:
        return None

    port_str = local_addr.rsplit(":", 1)[-1]
    try:
        return int(port_str)
    except ValueError:
        return None


def _parse_bind_address(local_addr: str) -> str | None:
    """
    Extract the bind interface from an ss/netstat local-address string (GH#11224).

    Handles ``*:port``, ``0.0.0.0:port``, ``:::port``, ``[::]:port``,
    ``127.0.0.1:port``, ``[::1]:port``. Returns the address with the port and any
    IPv6 brackets stripped, or None if it can't be parsed.
    """
    if ":" not in local_addr:
        return None
    addr = local_addr.rsplit(":", 1)[0].strip("[]")
    return addr or None


def _parse_process_info(parts: List[str]) -> tuple:
    """
    Parse process name and PID from ss output line parts.

    Extracts from format: users:(("process",pid,fd)). Issue #620.

    Args:
        parts: Split line parts from ss output

    Returns:
        Tuple of (process_name, pid) or (None, None)
    """
    process = None
    pid = None

    if len(parts) >= 6:
        proc_info = parts[5] if "users:" in parts[5] else ""
        if proc_info and '(("' in proc_info:
            try:
                process = proc_info.split('(("')[1].split('"')[0]
                pid_str = proc_info.split(",")[1]
                pid = int(pid_str.replace("pid=", ""))
            except (IndexError, ValueError):
                pass

    return process, pid


def _deduplicate_ports(ports: List[PortInfo]) -> List[PortInfo]:
    """
    Remove duplicate (port, address) pairs, keeping first occurrence.

    Issue #620; keyed on (port, address) since GH#11224 so a public bind is not
    collapsed into a loopback bind on the same port.

    Args:
        ports: List of PortInfo objects

    Returns:
        Deduplicated list of PortInfo objects
    """
    seen = set()
    unique_ports = []
    for p in ports:
        # GH#11224: key on (port, address) so a public bind is not masked by a
        # loopback bind on the same port for the security-posture audit.
        key = (p.port, p.address)
        if key not in seen:
            seen.add(key)
            unique_ports.append(p)
    return unique_ports


def get_listening_ports() -> List[PortInfo]:
    """
    Get all listening TCP ports.

    Uses `ss` command on Linux.
    """
    ports = []

    try:
        # ss -tlnp: TCP, listening, numeric, show process
        result = subprocess.run(  # nosec B603 B607  # fixed ss argv for port scanning, no user input
            ["ss", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode != 0:
            logger.warning("ss command failed: %s", result.stderr)
            return ports

        for line in result.stdout.splitlines()[1:]:  # Skip header
            parts = line.split()
            if len(parts) < 5:
                continue

            port = _parse_port_from_address(parts[3])
            if port is None:
                continue

            process, pid = _parse_process_info(parts)
            ports.append(PortInfo(port=port, process=process, pid=pid, address=_parse_bind_address(parts[3])))

    except subprocess.TimeoutExpired:
        logger.warning("Port scan timed out")
    except FileNotFoundError:
        logger.warning("ss command not found, trying netstat")
        ports = _get_ports_netstat()
    except Exception as e:
        logger.error("Port scan failed: %s", e)

    return _deduplicate_ports(ports)


def _get_ports_netstat() -> List[PortInfo]:
    """Fallback using netstat."""
    ports = []

    try:
        result = subprocess.run(  # nosec B603 B607  # fixed netstat argv for port scanning, no user input
            ["netstat", "-tlnp"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        for line in result.stdout.splitlines():
            if "LISTEN" not in line:
                continue

            parts = line.split()
            if len(parts) < 4:
                continue

            local_addr = parts[3]
            port_str = local_addr.rsplit(":", 1)[-1]

            try:
                port = int(port_str)
                ports.append(PortInfo(port=port, address=_parse_bind_address(local_addr)))
            except ValueError:
                continue

    except Exception as e:
        logger.error("netstat fallback failed: %s", e)

    return ports
