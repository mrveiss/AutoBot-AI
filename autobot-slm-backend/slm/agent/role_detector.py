# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import subprocess  # nosec B404  # subprocess used for systemctl status checks
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .port_scanner import get_listening_ports

logger = logging.getLogger(__name__)


@dataclass
class RoleDefinition:
    """Definition of a role for detection."""

    name: str
    target_path: str
    systemd_service: List[str] | None = None  # #16025: a role can own >1 unit
    health_check_port: int | None = None


@dataclass
class RoleDetection:
    """Detection status for a role."""

    path_exists: bool = False
    # #19076: False when the role names units and the node has none of them.
    units_installed: bool = True
    path: str | None = None
    service_running: bool = False
    service_name: str | None = None
    ports: List[int] = field(default_factory=list)
    version: str | None = None

    @property
    def status(self) -> str:
        """Determine overall status.

        - active: path exists and service running (or no service required)
        - inactive: path exists but service is down
        - not_installed: path absent, or none of the role's units exists
        """
        if not self.path_exists or not self.units_installed:
            return "not_installed"
        # No service name means it's a library/passive role — path = active
        if not self.service_name:
            return "active"
        return "active" if self.service_running else "inactive"


class RoleDetector:
    """Detects installed roles on this node."""

    def __init__(self, role_definitions: List[Dict] | None = None):
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

    def detect_all(self) -> Dict[str, RoleDetection]:
        """Detect all known roles on this system."""
        results = {}
        listening_ports = {p.port for p in get_listening_ports()}

        for name, role in self.roles.items():
            results[name] = self._detect_role(role, listening_ports)

        return results

    def _detect_role(self, role: RoleDefinition, listening_ports: set) -> RoleDetection:
        """Detect a single role."""
        status = RoleDetection()

        # Check path (service-only roles have no target_path — always pass)
        if role.target_path:
            target_path = Path(role.target_path)
            status.path_exists = target_path.exists()
            status.path = str(target_path) if status.path_exists else None
        else:
            status.path_exists = True  # no path requirement

        # Check service. #16025: a role can own >1 unit; "running" means all of them are.
        if role.systemd_service:
            status.service_name = ", ".join(role.systemd_service)
            status.service_running = all(self._check_service(unit) for unit in role.systemd_service)
            # #19076: a service-only role has no path to disprove it, so a unit the
            # node does not have would otherwise read as "inactive" -- present.
            status.units_installed = any(self._unit_installed(unit) for unit in role.systemd_service)

        # Check port
        if role.health_check_port:
            if role.health_check_port in listening_ports:
                status.ports.append(role.health_check_port)

        # Read version if path exists and path was specified
        if status.path_exists and role.target_path:
            status.version = self._read_version(Path(role.target_path))

        return status

    def _systemctl(self, *args: str) -> str | None:
        """stdout of one ``systemctl`` query, or None when it failed to run or exited non-zero."""
        try:
            result = subprocess.run(  # nosec B603 B607  # fixed systemctl argv; unit names are configured role names
                ["systemctl", *args],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception as e:
            logger.debug("systemctl %s failed: %s", " ".join(args), e)
            return None
        return result.stdout.strip() if result.returncode == 0 else None

    def _check_service(self, service_name: str) -> bool:
        """Check if a systemd service is running."""
        return self._systemctl("is-active", service_name) == "active"

    def _unit_installed(self, service_name: str) -> bool:
        """Whether systemd knows the unit at all (#19076).

        ``LoadState=not-found`` means the node never had it; a stopped or masked
        unit is still installed. A failed probe counts as not installed: detection
        only ever ADDS groups to a node's declared roles, so "cannot tell" must
        add nothing.
        """
        state = self._systemctl("show", "--property=LoadState", "--value", service_name)
        return bool(state) and state != "not-found"

    def _read_version(self, target_path: Path) -> str | None:
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
