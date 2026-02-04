# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Port Scanner Module (Issue #779).

Detects listening TCP ports on the local system.
"""

import logging
import subprocess  # nosec B404 - subprocess used with fixed commands for system inspection
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PortInfo:
    """Information about a listening port."""

    port: int
    process: Optional[str] = None
    pid: Optional[int] = None


def _parse_port_from_address(local_addr: str) -> Optional[int]:
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
    Remove duplicate ports from list, keeping first occurrence.

    Issue #620.

    Args:
        ports: List of PortInfo objects

    Returns:
        Deduplicated list of PortInfo objects
    """
    seen = set()
    unique_ports = []
    for p in ports:
        if p.port not in seen:
            seen.add(p.port)
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
        result = subprocess.run(  # nosec B607 - fixed command for port scanning
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
            ports.append(PortInfo(port=port, process=process, pid=pid))

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
        result = subprocess.run(  # nosec B607 - fixed command for port scanning
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
                ports.append(PortInfo(port=port))
            except ValueError:
                continue

    except Exception as e:
        logger.error("netstat fallback failed: %s", e)

    return ports
