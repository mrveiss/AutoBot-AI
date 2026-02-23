# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Role Detector Module (Issue #779).

Detects installed roles on the local system based on:
- Path existence
- Service status
- Port availability
"""

import json
import logging
import subprocess  # nosec B404 - subprocess used for systemctl status checks
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .port_scanner import get_listening_ports

logger = logging.getLogger(__name__)


@dataclass
class RoleDefinition:
    """Definition of a role for detection."""

    name: str
    target_path: str
    systemd_service: Optional[str] = None
    health_check_port: Optional[int] = None


@dataclass
class RoleStatus:
    """Detection status for a role."""

    path_exists: bool = False
    path: Optional[str] = None
    service_running: bool = False
    service_name: Optional[str] = None
    ports: List[int] = field(default_factory=list)
    version: Optional[str] = None

    @property
    def status(self) -> str:
        """Determine overall status.

        - active: path exists and service running (or no service required)
        - inactive: path exists but service is down
        - not_installed: path absent
        """
        if not self.path_exists:
            return "not_installed"
        # No service name means it's a library/passive role — path = active
        if not self.service_name:
            return "active"
        return "active" if self.service_running else "inactive"


class RoleDetector:
    """Detects installed roles on this node."""

    def __init__(self, role_definitions: Optional[List[Dict]] = None):
        """
        Initialize role detector.

        Args:
            role_definitions: List of role definitions from SLM server.
                             If None, uses empty list until fetched.
        """
        self.roles: Dict[str, RoleDefinition] = {}
        if role_definitions:
            self.load_definitions(role_definitions)

    def load_definitions(self, definitions: List[Dict]) -> None:
        """Load role definitions from SLM server response."""
        self.roles = {}
        for defn in definitions:
            if not defn.get("target_path") and not defn.get("systemd_service"):
                continue  # Skip roles with neither path nor service

            self.roles[defn["name"]] = RoleDefinition(
                name=defn["name"],
                target_path=defn["target_path"],
                systemd_service=defn.get("systemd_service"),
                health_check_port=defn.get("health_check_port"),
            )

        logger.debug("Loaded %d role definitions", len(self.roles))

    def detect_all(self) -> Dict[str, RoleStatus]:
        """Detect all known roles on this system."""
        results = {}
        listening_ports = {p.port for p in get_listening_ports()}

        for name, role in self.roles.items():
            results[name] = self._detect_role(role, listening_ports)

        return results

    def _detect_role(self, role: RoleDefinition, listening_ports: set) -> RoleStatus:
        """Detect a single role."""
        status = RoleStatus()

        # Check path (service-only roles have no target_path — always pass)
        if role.target_path:
            target_path = Path(role.target_path)
            status.path_exists = target_path.exists()
            status.path = str(target_path) if status.path_exists else None
        else:
            status.path_exists = True  # no path requirement

        # Check service
        if role.systemd_service:
            status.service_name = role.systemd_service
            status.service_running = self._check_service(role.systemd_service)

        # Check port
        if role.health_check_port:
            if role.health_check_port in listening_ports:
                status.ports.append(role.health_check_port)

        # Read version if path exists and path was specified
        if status.path_exists and role.target_path:
            status.version = self._read_version(Path(role.target_path))

        return status

    def _check_service(self, service_name: str) -> bool:
        """Check if a systemd service is running."""
        try:
            result = subprocess.run(  # nosec B607 - fixed systemctl command
                ["systemctl", "is-active", service_name],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return result.stdout.strip() == "active"
        except Exception as e:
            logger.debug("Service check failed for %s: %s", service_name, e)
            return False

    def _read_version(self, target_path: Path) -> Optional[str]:
        """Read version from version.json if present."""
        version_file = target_path / "version.json"

        # Also check parent's version.json for nested paths
        if not version_file.exists():
            version_file = target_path.parent / "version.json"

        # Check /var/lib/slm-agent for slm-agent
        if not version_file.exists() and "slm-agent" in str(target_path):
            version_file = Path("/var/lib/slm-agent/version.json")

        if not version_file.exists():
            return None

        try:
            data = json.loads(version_file.read_text(encoding="utf-8"))
            return data.get("commit") or data.get("version")
        except Exception as e:
            logger.debug("Failed to read version from %s: %s", version_file, e)
            return None
