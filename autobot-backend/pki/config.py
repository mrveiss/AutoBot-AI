# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
PKI Configuration Models
========================

Pydantic models for TLS/PKI configuration, integrated with SSOT config system.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from autobot_shared.ssot_config import TLSMode  # noqa: F401 — canonical enum


def _find_project_root() -> Path:
    """Find the project root directory containing .env file."""
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / ".env").exists():
            return parent
    return Path(os.environ.get("AUTOBOT_BASE_DIR", "/opt/autobot"))


PROJECT_ROOT = _find_project_root()


class CertificateType(str, Enum):
    """Types of certificates managed."""

    CA = "ca"
    SERVER = "server"
    CLIENT = "client"


@dataclass
class VMCertificateInfo:
    """Certificate information for a single VM."""

    name: str
    ip: str
    cert_path: Path
    key_path: Path
    common_name: str
    san_entries: List[str] = field(default_factory=list)


@dataclass
class CertificateStatus:
    """Status of a certificate."""

    exists: bool
    valid: bool
    expires_at: Optional[str] = None
    days_until_expiry: Optional[int] = None
    subject: Optional[str] = None
    issuer: Optional[str] = None
    needs_renewal: bool = False


class TLSConfig(BaseSettings):
    """
    TLS/PKI Configuration - Part of SSOT system.

    Manages all TLS-related settings for the AutoBot distributed architecture.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # TLS mode
    mode: TLSMode = Field(
        default=TLSMode.DISABLED,
        alias="AUTOBOT_TLS_MODE",
        description="TLS operation mode (disabled, optional, required)",
    )

    # Certificate paths (relative to project root)
    cert_dir: str = Field(
        default="certs",
        alias="AUTOBOT_TLS_CERT_DIR",
        description="Directory containing certificates",
    )

    ca_cert: str = Field(
        default="certs/ca/ca-cert.pem",
        alias="AUTOBOT_TLS_CA_CERT",
        description="Path to CA certificate",
    )

    ca_key: str = Field(
        default="certs/ca/ca-key.pem",
        alias="AUTOBOT_TLS_CA_KEY",
        description="Path to CA private key",
    )

    # Certificate validity
    ca_validity_days: int = Field(
        default=3650,
        alias="AUTOBOT_TLS_CA_VALIDITY_DAYS",
        description="CA certificate validity in days (default: 10 years)",
    )

    cert_validity_days: int = Field(
        default=365,
        alias="AUTOBOT_TLS_CERT_VALIDITY_DAYS",
        description="Service certificate validity in days",
    )

    renewal_threshold_days: int = Field(
        default=30,
        alias="AUTOBOT_TLS_RENEWAL_THRESHOLD_DAYS",
        description="Days before expiry to trigger renewal warning",
    )

    # Key configuration
    key_size: int = Field(
        default=4096,
        alias="AUTOBOT_TLS_KEY_SIZE",
        description="RSA key size in bits",
    )

    # Remote paths on VMs
    remote_cert_dir: str = Field(
        default="/etc/autobot/certs",
        alias="AUTOBOT_TLS_REMOTE_CERT_DIR",
        description="Certificate directory on remote VMs",
    )

    # SSH configuration for distribution
    ssh_key: str = Field(
        default="~/.ssh/autobot_key",
        alias="AUTOBOT_SSH_KEY",
        description="SSH key for VM access",
    )

    ssh_user: str = Field(
        default="autobot",
        alias="AUTOBOT_SSH_USER",
        description="SSH user for VM access",
    )

    # Redis TLS
    redis_tls_enabled: bool = Field(
        default=False,
        alias="AUTOBOT_REDIS_TLS_ENABLED",
        description="Enable TLS for Redis connections",
    )

    # Backend TLS
    backend_tls_enabled: bool = Field(
        default=False,
        alias="AUTOBOT_BACKEND_TLS_ENABLED",
        description="Enable TLS for backend API",
    )

    # Certificate subject fields
    country: str = Field(
        default="US",
        alias="AUTOBOT_TLS_COUNTRY",
        description="Certificate country code",
    )

    organization: str = Field(
        default="AutoBot",
        alias="AUTOBOT_TLS_ORGANIZATION",
        description="Certificate organization",
    )

    @property
    def cert_dir_path(self) -> Path:
        """Get absolute path to certificate directory."""
        return PROJECT_ROOT / self.cert_dir

    @property
    def ca_cert_path(self) -> Path:
        """Get absolute path to CA certificate."""
        return PROJECT_ROOT / self.ca_cert

    @property
    def ca_key_path(self) -> Path:
        """Get absolute path to CA key."""
        return PROJECT_ROOT / self.ca_key

    @property
    def ssh_key_path(self) -> Path:
        """Get absolute path to SSH key."""
        return Path(os.path.expanduser(self.ssh_key))

    @property
    def is_enabled(self) -> bool:
        """Check if TLS is enabled (not disabled)."""
        return self.mode != TLSMode.DISABLED

    @property
    def is_required(self) -> bool:
        """Check if TLS is required."""
        return self.mode == TLSMode.REQUIRED

    def get_vm_cert_info(self, vm_name: str, vm_ip: str) -> VMCertificateInfo:
        """Get certificate info for a specific VM."""
        vm_cert_dir = self.cert_dir_path / vm_name
        return VMCertificateInfo(
            name=vm_name,
            ip=vm_ip,
            cert_path=vm_cert_dir / "server-cert.pem",
            key_path=vm_cert_dir / "server-key.pem",
            common_name=f"autobot-{vm_name}",
            san_entries=[
                f"DNS:autobot-{vm_name}",
                f"DNS:{vm_name}",
                "DNS:localhost",
                f"IP:{vm_ip}",
                "IP:127.0.0.1",
            ],
        )


# VM definitions for certificate generation - imported from SSOT
# Issue #694: Centralized config consolidation
def _get_vm_definitions() -> Dict[str, str]:
    """Get VM definitions from SSOT config with fallback."""
    try:
        from autobot_shared.ssot_config import get_config

        return get_config().vm_definitions
    except Exception:
        # Fallback for standalone PKI tool usage - use SSOT defaults
        from autobot_shared.ssot_config import VMConfig

        vm = VMConfig()
        return {
            "main-host": vm.main,
            "frontend": vm.frontend,
            "npu-worker": vm.npu,
            "redis": vm.redis,
            "ai-stack": vm.aistack,
            "browser": vm.browser,
        }


VM_DEFINITIONS: Dict[str, str] = _get_vm_definitions()
