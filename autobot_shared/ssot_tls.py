# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""TLS/PKI settings: the one ``TLSConfig`` for the SSOT and the PKI tooling (#17312).

``autobot_shared.ssot_config`` re-exports ``TLSMode``/``TLSConfig`` (``config.tls``) and
``autobot-backend/pki/config.py`` re-exports them for the certificate tooling, so a
field added here is seen by both. It lives in its own module so ``ssot_config`` does not
grow past its size ceiling.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import ClassVar, FrozenSet, List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# The TLS cert-dir defaults' one home (#19317), read by the Field defaults below.
from autobot_shared.env_registry_tls import DEFAULT_TLS_CERT_DIR, DEFAULT_TLS_REMOTE_CERT_DIR
from autobot_shared.paths import project_root
from autobot_shared.secret_redaction import RedactedReprMixin

PROJECT_ROOT = project_root()


class TLSMode(str, Enum):
    """TLS operation modes."""

    DISABLED = "disabled"
    OPTIONAL = "optional"
    REQUIRED = "required"


@dataclass
class VMCertificateInfo:
    """Certificate information for a single VM."""

    name: str
    ip: str
    cert_path: Path
    key_path: Path
    common_name: str
    san_entries: List[str] = field(default_factory=list)


class TLSConfig(RedactedReprMixin, BaseSettings):
    """TLS/PKI configuration for secure communications (Issue #164).

    Manages all TLS-related settings for the AutoBot distributed architecture.
    TLS certificates are managed and deployed via SLM (AUTOBOT_SLM_HOST).
    """

    # Paths to key material / the public CA certificate, not the material itself. Derived
    # after the class body from the field descriptions ("Path to ..."), not listed here, so
    # the module declares no credential key-name vocabulary of its own (#17337).
    NON_CREDENTIAL_FIELDS: ClassVar[FrozenSet[str]] = frozenset()

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
        default=DEFAULT_TLS_CERT_DIR,
        alias="AUTOBOT_TLS_CERT_DIR",
        description="Directory containing certificates",
    )

    ca_cert: str = Field(
        default=f"{DEFAULT_TLS_CERT_DIR}/ca/ca-cert.pem",
        alias="AUTOBOT_TLS_CA_CERT",
        description="Path to CA certificate",
    )

    ca_key: str = Field(
        default=f"{DEFAULT_TLS_CERT_DIR}/ca/ca-key.pem",
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
        default=DEFAULT_TLS_REMOTE_CERT_DIR,
        alias="AUTOBOT_TLS_REMOTE_CERT_DIR",
        description="Certificate directory on remote VMs",
    )

    # SSH configuration for distribution
    ssh_key: str = Field(
        default="~/.ssh/autobot_key",
        alias="AUTOBOT_SSH_KEY",
        description="Path to SSH key for VM access",
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

    # Service-specific TLS ports and per-service switches
    redis_tls_port: int = Field(default=6380, alias="AUTOBOT_REDIS_TLS_PORT")
    backend_tls_port: int = Field(default=8443, alias="AUTOBOT_BACKEND_TLS_PORT")
    # Issue #164: Frontend TLS (HTTPS) support
    frontend_tls_enabled: bool = Field(default=False, alias="AUTOBOT_FRONTEND_TLS_ENABLED")
    frontend_tls_port: int = Field(default=443, alias="AUTOBOT_FRONTEND_TLS_PORT")
    # SLM TLS settings (admin server)
    slm_tls_enabled: bool = Field(default=False, alias="AUTOBOT_SLM_TLS_ENABLED")
    slm_tls_port: int = Field(default=443, alias="AUTOBOT_SLM_TLS_PORT")

    @property
    def any_service_tls_enabled(self) -> bool:
        """Check if any service has TLS enabled."""
        return self.redis_tls_enabled or self.backend_tls_enabled or self.frontend_tls_enabled or self.slm_tls_enabled

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


#: Fields whose declared description says they hold a filesystem path stay visible in ``repr()``.
TLSConfig.NON_CREDENTIAL_FIELDS = frozenset(
    name for name, info in TLSConfig.model_fields.items() if (info.description or "").startswith("Path to")
)
