# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Health Collector for SLM Agent

Collects system and service health metrics for reporting to admin.
"""

import logging
import os
import platform
import socket
import subprocess  # nosec B404 - required for systemctl interaction
from datetime import datetime
from typing import Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


class HealthCollector:
    """
    Collects health metrics from the local node.

    Gathers:
    - System metrics (CPU, memory, disk)
    - Service status (systemd)
    - Port connectivity
    - Service discovery (all systemd services)
    """

    def __init__(
        self,
        services: Optional[List[str]] = None,
        ports: Optional[List[Dict]] = None,
        discover_services: bool = True,
    ):
        """
        Initialize health collector.

        Args:
            services: List of systemd service names to check
            ports: List of port checks [{"host": "localhost", "port": 6379}]
            discover_services: Whether to discover all systemd services
        """
        self.services = services or []
        self.ports = ports or []
        self.hostname = platform.node()
        self.discover_services = discover_services

    def collect(self) -> Dict:
        """Collect all health metrics."""
        health = {
            "timestamp": datetime.utcnow().isoformat(),
            "hostname": self.hostname,
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "load_avg": list(os.getloadavg())
            if hasattr(os, "getloadavg")
            else [0.0, 0.0, 0.0],
            "uptime_seconds": int(datetime.now().timestamp() - psutil.boot_time()),
        }

        # Collect service statuses
        if self.services:
            health["services"] = {}
            for service in self.services:
                health["services"][service] = self.check_service(service)

        # Collect port checks
        if self.ports:
            health["ports"] = {}
            for port_check in self.ports:
                host = port_check.get("host", "localhost")
                port = port_check["port"]
                key = f"{host}:{port}"
                health["ports"][key] = self.check_port(host, port)

        # Discover all systemd services (for Issue #728)
        if self.discover_services:
            health["discovered_services"] = self.discover_all_services()

        return health

    def check_service(self, service_name: str) -> Dict:
        """Check systemd service status."""
        try:
            result = (
                subprocess.run(  # nosec B607 - systemctl is a trusted system binary
                    ["systemctl", "is-active", service_name],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            )
            is_active = result.returncode == 0
            status = result.stdout.strip()

            return {
                "active": is_active,
                "status": status,
            }
        except subprocess.TimeoutExpired:
            return {"active": False, "status": "timeout"}
        except Exception as e:
            return {"active": False, "status": str(e)}

    def check_port(self, host: str, port: int, timeout: float = 2.0) -> bool:
        """Check if a port is open and accepting connections."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(timeout)
                result = sock.connect_ex((host, port))
                return result == 0
        except Exception:
            return False

    def discover_all_services(self) -> List[Dict]:
        """
        Discover all systemd services on the node.

        Issue #620: Refactored to use helper functions.
        Issue #728: Related implementation.

        Returns list of service info dicts with status, enabled state, etc.
        """
        services = []
        try:
            output = self._run_systemctl_list_units()
            if output is None:
                return services

            for line in output.strip().split("\n"):
                service_info = self._parse_service_line(line)
                if service_info:
                    if service_info["status"] == "running":
                        service_info.update(
                            self._get_service_details(service_info["name"])
                        )
                    services.append(service_info)

        except subprocess.TimeoutExpired:
            logger.warning("Timeout discovering services")
        except FileNotFoundError:
            logger.warning("systemctl not found - not a systemd system")
        except Exception as e:
            logger.warning("Error discovering services: %s", e)

        return services

    def _run_systemctl_list_units(self) -> Optional[str]:
        """Run systemctl list-units command. Issue #620."""
        result = subprocess.run(  # nosec B607 - systemctl is trusted
            [
                "systemctl",
                "list-units",
                "--type=service",
                "--all",
                "--no-pager",
                "--no-legend",
                "--plain",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.warning("Failed to list services: %s", result.stderr)
            return None
        return result.stdout

    def _parse_service_line(self, line: str) -> Optional[Dict]:
        """Parse a single line of systemctl output. Issue #620."""
        if not line.strip():
            return None
        parts = line.split(None, 4)
        if len(parts) < 4:
            return None
        unit_name = parts[0]
        if "@" in unit_name or not unit_name.endswith(".service"):
            return None

        service_name = unit_name.replace(".service", "")
        active_state, sub_state, load_state = parts[2], parts[3], parts[1]
        status = self._map_status_from_states(active_state, sub_state)

        return {
            "name": service_name,
            "status": status,
            "active_state": active_state,
            "sub_state": sub_state,
            "load_state": load_state,
        }

    def _map_status_from_states(self, active_state: str, sub_state: str) -> str:
        """Map systemd active/sub states to our status enum. Issue #620."""
        if active_state == "active" and sub_state == "running":
            return "running"
        elif active_state == "failed" or sub_state == "failed":
            return "failed"
        elif active_state == "inactive":
            return "stopped"
        return "unknown"

    def _get_service_details(self, service_name: str) -> Dict:
        """Get detailed info for a specific service."""
        details = {}
        try:
            # Get service properties
            result = (
                subprocess.run(  # nosec B607 - systemctl is a trusted system binary
                    [
                        "systemctl",
                        "show",
                        service_name,
                        "--property=MainPID,MemoryCurrent,Description,UnitFileState",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        if key == "MainPID" and value.isdigit():
                            details["main_pid"] = int(value)
                        elif key == "MemoryCurrent" and value.isdigit():
                            details["memory_bytes"] = int(value)
                        elif key == "Description":
                            details["description"] = value[:500]
                        elif key == "UnitFileState":
                            details["enabled"] = value == "enabled"

        except Exception as e:
            logger.debug("Could not get details for %s: %s", service_name, e)

        return details

    def is_healthy(self, thresholds: Optional[Dict] = None) -> bool:
        """Quick health check against thresholds."""
        defaults = {
            "cpu_percent": 90,
            "memory_percent": 90,
            "disk_percent": 90,
        }
        thresholds = {**defaults, **(thresholds or {})}

        health = self.collect()

        if health["cpu_percent"] > thresholds["cpu_percent"]:
            return False
        if health["memory_percent"] > thresholds["memory_percent"]:
            return False
        if health["disk_percent"] > thresholds["disk_percent"]:
            return False

        # Check all services are active
        for service_status in health.get("services", {}).values():
            if not service_status.get("active"):
                return False

        return True
