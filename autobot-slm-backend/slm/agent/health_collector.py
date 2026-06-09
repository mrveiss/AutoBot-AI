# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Health Collector for SLM Agent

Collects system and service health metrics for reporting to admin.
Publishes state-change events to Redis pub/sub (#3404).
"""

import json
import logging
import os
import platform
import socket
import subprocess  # nosec B404 - required for systemctl interaction
import time
from datetime import datetime, timezone
from typing import Dict, List

import psutil

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_STATE_CHANGE_CHANNEL_TEMPLATE = "autobot:services:{service}:state_change"

# Subprocess-heavy service sweep is cached this long to reduce system load (#9086)
_SERVICE_DISCOVERY_TTL = 300  # seconds


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
        services: List[str] | None = None,
        ports: List[Dict] | None = None,
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
        # Tracks the last known status per service name for state-change detection.
        # Populated on first collect(); events are only published on transitions.
        self._last_known_status: Dict[str, str] = {}
        # Cache for discover_all_services() — avoids spawning 100+ subprocesses
        # every heartbeat (#9086)
        self._service_cache: List[Dict] = []
        self._service_cache_ts: float = 0.0

    def collect(self) -> Dict:
        """Collect all health metrics."""
        health = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hostname": self.hostname,
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "load_avg": (list(os.getloadavg()) if hasattr(os, "getloadavg") else [0.0, 0.0, 0.0]),
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

        # Discover all systemd services (for Issue #728).
        # Result is cached for _SERVICE_DISCOVERY_TTL seconds — the sweep
        # spawns 100+ subprocesses and must not run every heartbeat (#9086).
        if self.discover_services:
            health["discovered_services"] = self._get_discovered_services()

        return health

    def _get_discovered_services(self) -> List[Dict]:
        """Return cached service list, refreshing when TTL has expired."""
        now = time.monotonic()
        if now - self._service_cache_ts >= _SERVICE_DISCOVERY_TTL:
            self._service_cache = self.discover_all_services()
            self._service_cache_ts = now
        return self._service_cache

    def check_service(self, service_name: str) -> Dict:
        """Check systemd service status."""
        try:
            result = subprocess.run(  # nosec B607 - systemctl is a trusted system binary
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
        except Exception:
            return {"active": False, "status": "health check failed"}

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
                        service_info.update(self._get_service_details(service_info["name"]))
                    elif service_info["status"] in ("failed", "crash-loop"):
                        # Issue #1019: Capture error context for failed services
                        # Issue #1604: Also capture for crash-looping services
                        service_info.update(self._get_service_details(service_info["name"]))
                        error_ctx = self._get_error_context(service_info["name"])
                        if error_ctx:
                            service_info["error_message"] = error_ctx
                    services.append(service_info)

        except subprocess.TimeoutExpired:
            logger.warning("Timeout discovering services")
            return services
        except FileNotFoundError:
            logger.warning("systemctl not found - not a systemd system")
            return services
        except Exception as e:
            logger.warning("Error discovering services: %s", e)
            return services

        self._detect_and_publish_state_changes(services)
        return services

    def _run_systemctl_list_units(self) -> str | None:
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

    def _parse_service_line(self, line: str) -> Dict | None:
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
        load_state = parts[1]
        # Skip phantom entries with no unit file (not-found/masked)
        if load_state in ("not-found", "masked"):
            return None
        active_state, sub_state = parts[2], parts[3]
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
        elif active_state == "activating" and sub_state == "auto-restart":
            return "crash-loop"  # Issue #1604
        elif active_state == "inactive":
            return "stopped"
        return "unknown"

    def _get_service_details(self, service_name: str) -> Dict:
        """Get detailed info for a specific service."""
        details = {}
        try:
            # Get service properties
            result = subprocess.run(  # nosec B607 - systemctl is a trusted system binary
                [
                    "systemctl",
                    "show",
                    service_name,
                    "--property=MainPID,MemoryCurrent,Description," "UnitFileState,NRestarts",
                ],
                capture_output=True,
                text=True,
                timeout=5,
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
                        elif key == "NRestarts" and value.isdigit():
                            details["n_restarts"] = int(value)

        except Exception as e:
            logger.debug("Could not get details for %s: %s", service_name, e)

        return details

    def _get_error_context(self, service_name: str, lines: int = 5) -> str:
        """Get last N lines of journalctl for a failed service.

        Issue #1019: Capture error context so the SLM dashboard
        can display why a service failed without requiring SSH.
        """
        try:
            result = subprocess.run(  # nosec B607 - journalctl is trusted
                [
                    "journalctl",
                    "-u",
                    service_name,
                    "-n",
                    str(lines),
                    "--no-pager",
                    "-q",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception as e:
            logger.debug("Could not get error context for %s: %s", service_name, e)
        return ""

    def _publish_state_change(
        self,
        service_name: str,
        prev_state: str,
        new_state: str,
        error_context: str,
    ) -> None:
        """Publish a service state-change event to Redis pub/sub.

        Channel: autobot:services:{service_name}:state_change
        Payload keys: service, hostname, prev_state, new_state, error_context.

        Failure is logged at WARNING level and never propagates — a Redis
        outage must not interrupt health collection (#3404).
        """
        try:
            client = get_redis_client(database="main")
            if client is None:
                logger.warning(
                    "Redis unavailable — state-change event not published " "(service=%s %s->%s)",
                    service_name,
                    prev_state,
                    new_state,
                )
                return
            channel = _STATE_CHANGE_CHANNEL_TEMPLATE.format(service=service_name)
            payload = json.dumps(
                {
                    "service": service_name,
                    "hostname": self.hostname,
                    "prev_state": prev_state,
                    "new_state": new_state,
                    "error_context": error_context,
                }
            )
            client.publish(channel, payload)
            logger.info(
                "Published state-change event: service=%s %s->%s",
                service_name,
                prev_state,
                new_state,
            )
        except Exception as exc:
            logger.warning("Failed to publish state-change event for %s: %s", service_name, exc)

    def _detect_and_publish_state_changes(self, services: List[Dict]) -> None:
        """Compare discovered service statuses against last known state.

        Publishes a Redis pub/sub event for each service whose status has
        changed since the previous call.  Updates ``_last_known_status`` so
        only real transitions trigger events (#3404).
        """
        for svc in services:
            name = svc.get("name")
            new_state = svc.get("status", "unknown")
            if name is None:
                continue
            prev_state = self._last_known_status.get(name)
            if prev_state is None:
                # First observation — record state but do not emit an event.
                self._last_known_status[name] = new_state
                continue
            if prev_state == new_state:
                continue
            self._last_known_status[name] = new_state
            self._publish_state_change(
                service_name=name,
                prev_state=prev_state,
                new_state=new_state,
                error_context=svc.get("error_message", ""),
            )

    def is_healthy(self, thresholds: Dict | None = None) -> bool:
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
