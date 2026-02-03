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

            # Parse local address (format: *:port or 0.0.0.0:port or :::port)
            local_addr = parts[3]
            if ":" not in local_addr:
                continue

            port_str = local_addr.rsplit(":", 1)[-1]
            try:
                port = int(port_str)
            except ValueError:
                continue

            # Parse process info if available (format: users:(("process",pid,fd)))
            process = None
            pid = None
            if len(parts) >= 6:
                proc_info = parts[5] if "users:" in parts[5] else ""
                if proc_info:
                    # Extract process name
                    if '(("' in proc_info:
                        try:
                            process = proc_info.split('(("')[1].split('"')[0]
                            pid_str = proc_info.split(",")[1]
                            pid = int(pid_str.replace("pid=", ""))
                        except (IndexError, ValueError):
                            pass

            ports.append(PortInfo(port=port, process=process, pid=pid))

    except subprocess.TimeoutExpired:
        logger.warning("Port scan timed out")
    except FileNotFoundError:
        logger.warning("ss command not found, trying netstat")
        ports = _get_ports_netstat()
    except Exception as e:
        logger.error("Port scan failed: %s", e)

    # Deduplicate by port
    seen = set()
    unique_ports = []
    for p in ports:
        if p.port not in seen:
            seen.add(p.port)
            unique_ports.append(p)

    return unique_ports


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
