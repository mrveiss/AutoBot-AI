# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Role Manifest Schema (Issue #926 Phase 2).

Pydantic models that define and validate role manifest.yml files.
Every autobot-infrastructure/autobot-<role>/manifest.yml must conform to this schema.
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class UpdatePolicy(str, Enum):
    """System update policy for apt packages."""

    FULL = "full"
    SECURITY = "security"
    MANUAL = "manual"


class RebootStrategy(str, Enum):
    """When to reboot after system updates."""

    IMMEDIATE = "immediate"
    SCHEDULED = "scheduled"
    MANUAL = "manual"
    NEVER = "never"


class ServiceType(str, Enum):
    """Systemd unit type."""

    SYSTEMD = "systemd"
    ONESHOT = "oneshot"
    TIMER = "timer"


class ProtocolType(str, Enum):
    """Network protocol for ports."""

    HTTP = "http"
    HTTPS = "https"
    TCP = "tcp"
    UDP = "udp"
    UNIX = "unix"


class ConflictSeverity(str, Enum):
    """Port/resource conflict severity."""

    HARD = "hard"  # SLM blocks assignment
    SOFT = "soft"  # SLM warns but allows


class ManifestDeploy(BaseModel):
    """Deployment configuration."""

    source: str = Field(description="Repo dir to sync (e.g. autobot-backend/)")
    destination: str = Field(
        description="Target path on node (e.g. /opt/autobot/autobot-backend/)"
    )
    shared: bool = Field(
        default=True, description="Also deploy autobot-shared/ to node"
    )
    infrastructure: bool = Field(
        default=True,
        description="Also deploy autobot-infrastructure/autobot-<role>/ to node",
    )
    extra_sources: List[str] = Field(
        default_factory=list,
        description="Additional source dirs to sync (e.g. autobot-ollama/)",
    )


class ManifestService(BaseModel):
    """A systemd service managed by this role."""

    name: str = Field(description="systemd unit name (without .service suffix)")
    type: ServiceType = Field(default=ServiceType.SYSTEMD)
    system_service: Optional[str] = Field(
        default=None, description="Underlying system service (e.g. nginx, postgresql)"
    )
    start_order: int = Field(
        default=1, description="Start order (lower = starts first)"
    )
    exec_start: Optional[str] = Field(
        default=None, description="Override ExecStart command"
    )
    user: Optional[str] = Field(
        default=None, description="Override service user (default: autobot-<role>)"
    )
    environment_file: Optional[str] = Field(
        default=None, description="Override environment file path"
    )


class ManifestPort(BaseModel):
    """A network port this role binds."""

    port: int
    protocol: ProtocolType = ProtocolType.HTTPS
    public: bool = Field(
        default=False, description="Exposed through firewall to external traffic"
    )
    loopback_only: bool = Field(
        default=False, description="Bind 127.0.0.1 only (no external access)"
    )
    description: Optional[str] = None


class ManifestHealth(BaseModel):
    """Health check configuration."""

    endpoint: str = Field(
        description="Full health URL (e.g. https://localhost:8443/api/health)"
    )
    interval: str = Field(default="30s")
    timeout: str = Field(default="10s")
    retries: int = Field(default=3)
    expected_status: int = Field(default=200)


class ManifestSecrets(BaseModel):
    """Secrets this role owns vs borrows."""

    own: List[str] = Field(
        default_factory=list,
        description="Secrets this role generates and owns (e.g. tls_cert, tls_key)",
    )
    shared: List[str] = Field(
        default_factory=list,
        description="Shared secrets this role reads (e.g. redis_password, service_auth_token)",
    )


class ManifestTLS(BaseModel):
    """TLS certificate configuration."""

    auto_rotate: bool = Field(default=True)
    rotate_days_before: int = Field(
        default=14, description="Rotate cert N days before expiry"
    )
    reload_command: str = Field(default="systemctl reload nginx")


class ManifestSystemUpdates(BaseModel):
    """System (apt) update policy."""

    policy: UpdatePolicy = UpdatePolicy.SECURITY
    reboot_strategy: RebootStrategy = RebootStrategy.SCHEDULED


class ManifestCoexistence(BaseModel):
    """Port/resource conflict declarations."""

    conflicts_with: List[str] = Field(
        default_factory=list,
        description="Roles that CANNOT coexist on the same node (hard block)",
    )
    warns_with: List[str] = Field(
        default_factory=list,
        description="Roles that trigger a warning if assigned to same node",
    )
    compatible_with: List[str] = Field(
        default_factory=list,
        description="Roles explicitly known to coexist safely",
    )


class RoleManifest(BaseModel):
    """Complete role manifest — single source of truth for SLM deployment."""

    role: str = Field(description="Role identifier (e.g. autobot-backend)")
    description: str
    version: str = Field(default="1.0.0")

    # Node targeting
    target_node: Optional[str] = Field(
        default=None,
        description="Canonical target node name. None means 'all nodes' (e.g. slm-agent, shared).",
    )
    deploy_to_all: bool = Field(
        default=False,
        description="Deploy this role to every node in the fleet (used for slm-agent, shared).",
    )

    # Deployment
    deploy: ManifestDeploy

    # System requirements
    system_dependencies: List[str] = Field(
        default_factory=list, description="apt packages required on the node"
    )
    python_version: Optional[str] = Field(
        default=None, description="Required Python version (e.g. 3.10)"
    )

    # Services
    services: List[ManifestService] = Field(default_factory=list)

    # Network
    ports: List[ManifestPort] = Field(default_factory=list)

    # Health
    health: Optional[ManifestHealth] = None

    # Secrets
    secrets: ManifestSecrets = Field(default_factory=ManifestSecrets)

    # Security
    tls: Optional[ManifestTLS] = None
    service_account: Optional[str] = Field(
        default=None,
        description="Linux service account. Defaults to autobot-<role> if unset.",
    )

    # Updates
    system_updates: ManifestSystemUpdates = Field(default_factory=ManifestSystemUpdates)

    # Coexistence
    coexistence: ManifestCoexistence = Field(default_factory=ManifestCoexistence)

    # Dependencies
    depends_on: List[str] = Field(
        default_factory=list,
        description="Roles this role needs to be healthy before starting",
    )

    # Extra metadata
    ansible_role: Optional[str] = Field(
        default=None,
        description="Ansible role name (defaults to last segment of role, e.g. 'backend')",
    )
    notes: Optional[str] = None

    @field_validator("role")
    @classmethod
    def role_must_have_prefix(cls, v: str) -> str:
        """Validate role follows autobot-<name> convention."""
        if not v.startswith("autobot-"):
            raise ValueError(f"Role name must start with 'autobot-': {v!r}")
        return v

    def get_service_account(self) -> str:
        """Return the Linux service account for this role."""
        if self.service_account:
            return self.service_account
        return self.role  # e.g. autobot-backend

    def get_ansible_role(self) -> str:
        """Return the Ansible role name for this role."""
        if self.ansible_role:
            return self.ansible_role
        # Strip 'autobot-' prefix: autobot-browser-worker → browser-worker → browser
        name = self.role.removeprefix("autobot-")
        # Map compound names
        _map = {
            "browser-worker": "browser",
            "npu-worker": "npu-worker",
            "slm-backend": "slm_manager",
            "slm-agent": "slm_agent",
            "slm-database": "postgresql",
            "ai-stack": "ai-stack",
        }
        return _map.get(name, name)

    def get_env_file(self) -> str:
        """Return the expected environment file path on the node."""
        return f"/etc/autobot/{self.role}.env"

    def port_numbers(self) -> List[int]:
        """Return list of port numbers this role binds."""
        return [p.port for p in self.ports]

    def hard_conflicts(self) -> List[str]:
        """Return roles that cannot coexist with this role."""
        return self.coexistence.conflicts_with

    def metadata(self) -> Dict[str, Any]:
        """Return lightweight metadata for SLM DB storage."""
        return {
            "role": self.role,
            "description": self.description,
            "target_node": self.target_node,
            "deploy_to_all": self.deploy_to_all,
            "ports": self.port_numbers(),
            "services": [s.name for s in self.services],
            "health_endpoint": self.health.endpoint if self.health else None,
            "conflicts_with": self.coexistence.conflicts_with,
            "depends_on": self.depends_on,
        }
