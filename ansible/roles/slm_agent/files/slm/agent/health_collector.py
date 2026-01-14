# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Health Collector for SLM Agent

Collects system and service health metrics for reporting to admin.
"""

import logging
import platform
import socket
import subprocess
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
    """

    def __init__(
        self,
        services: Optional[List[str]] = None,
        ports: Optional[List[Dict]] = None,
    ):
        """
        Initialize health collector.

        Args:
            services: List of systemd service names to check
            ports: List of port checks [{"host": "localhost", "port": 6379}]
        """
        self.services = services or []
        self.ports = ports or []
        self.hostname = platform.node()

    def collect(self) -> Dict:
        """Collect all health metrics."""
        health = {
            "timestamp": datetime.utcnow().isoformat(),
            "hostname": self.hostname,
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "load_avg": list(psutil.getloadavg()),
            "uptime_seconds": int(
                datetime.now().timestamp() - psutil.boot_time()
            ),
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

        return health

    def check_service(self, service_name: str) -> Dict:
        """Check systemd service status."""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                timeout=5,
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
