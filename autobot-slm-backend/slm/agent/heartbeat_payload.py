# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Heartbeat payload assembly for the SLM agent (#620, #779).

Split out of agent.py because agent.py sat at exactly its recorded size ceiling
(739/739), and ``scripts/python_file_size_known_large.py`` says that mapping
ONLY SHRINKS -- "never add an entry to make a new file pass; split the file
instead". Any future heartbeat field therefore needs the builders out here
rather than a raised ceiling. This is a pure move: no behaviour change.

Free functions rather than methods: none of them needed agent state beyond
what is now passed explicitly, which is what made the split safe.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .port_scanner import get_listening_ports


def build_role_report(role_detector: Any, definitions_loaded: bool) -> Dict:
    """
    Build role detection report for heartbeat payload.

    Returns a dictionary mapping role names to their status details.
    Issue #620.
    """
    if not definitions_loaded:
        return {}

    role_statuses = role_detector.detect_all()
    return {
        name: {
            "path_exists": status.path_exists,
            "path": status.path,
            "service_running": status.service_running,
            "service_name": status.service_name,
            "ports": status.ports,
            "version": status.version,
            "status": status.status,
        }
        for name, status in role_statuses.items()
    }


def build_listening_ports_list() -> List[Dict]:
    """
    Build list of listening ports for heartbeat payload.

    Returns a list of dictionaries with port, process, pid, and bind address.
    Issue #620; ``address`` added for the security-posture audit (GH#11224).
    """
    return [{"port": p.port, "process": p.process, "pid": p.pid, "address": p.address} for p in get_listening_ports()]


def build_heartbeat_payload(
    health: Dict,
    os_info: str,
    code_version: str | None,
    role_detector: Any,
    definitions_loaded: bool,
) -> Dict:
    """
    Build the complete heartbeat payload.

    Args:
        health: Health data from collector.
        os_info: Operating system information string.
        code_version: Current code version hash.
        role_detector: Detector used to build the role report.
        definitions_loaded: Whether role definitions have been fetched yet.

    Returns:
        Dictionary payload matching HeartbeatRequest schema.
    Issue #620.
    """
    return {
        "cpu_percent": health.get("cpu_percent", 0.0),
        "memory_percent": health.get("memory_percent", 0.0),
        "disk_percent": health.get("disk_percent", 0.0),
        "agent_version": "1.0.0",
        "os_info": os_info,
        "code_version": code_version,  # Issue #741: Add code version
        "role_report": build_role_report(role_detector, definitions_loaded),  # Issue #779
        "listening_ports": build_listening_ports_list(),  # Issue #779
        "extra_data": {
            "services": health.get("services", {}),
            "discovered_services": health.get("discovered_services", []),
            "load_avg": health.get("load_avg", []),
            "uptime_seconds": health.get("uptime_seconds", 0),
            "hostname": health.get("hostname"),
        },
    }
