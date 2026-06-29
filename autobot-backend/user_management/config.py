# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Deployment Mode Configuration for User Management System

AutoBot always runs full, Postgres-backed user management (#10636). Supports
3 deployment modes:
- single_company: One org with users and teams (default)
- multi_company: Multiple orgs (multi-tenant), isolated data
- provider: Full multi-tenant with billing, quotas, social login
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)


def _get_default_postgres_host() -> str:
    """Get default PostgreSQL host from SSOT config.

    PostgreSQL runs on the Redis VM in AutoBot architecture.
    Uses ConfigRegistry for consistent fallback chain (#639).
    """
    try:
        from config.registry import ConfigRegistry

        return ConfigRegistry.get("vm.redis")  # SSOT default via registry_defaults
    except Exception:
        from autobot_shared.ssot_config import get_config

        return get_config().vm.redis


class DeploymentMode(str, Enum):
    """Deployment mode enumeration."""

    SINGLE_COMPANY = "single_company"
    MULTI_COMPANY = "multi_company"
    PROVIDER = "provider"


@dataclass
class FeatureFlags:
    """Feature flags based on deployment mode."""

    user_management: bool = False
    team_management: bool = False
    organization_switcher: bool = False
    sso_configuration: bool = False
    social_login: bool = False
    tenant_admin_dashboard: bool = False
    api_key_management: bool = False
    audit_log: bool = False
    quota_management: bool = False
    billing: bool = False


@dataclass
class DeploymentConfig:
    """Configuration for the current deployment mode."""

    mode: DeploymentMode
    features: FeatureFlags
    postgres_enabled: bool = False
    postgres_host: str = field(default_factory=_get_default_postgres_host)
    postgres_port: int = 5432
    postgres_db: str = "autobot"
    postgres_user: str = "autobot"
    postgres_password: str = ""
    encryption_key: str | None = None

    @property
    def postgres_url(self) -> str:
        """Generate PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def postgres_sync_url(self) -> str:
        """Generate synchronous PostgreSQL connection URL (for Alembic)."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# Feature flags for each deployment mode
MODE_FEATURES: dict[DeploymentMode, FeatureFlags] = {
    DeploymentMode.SINGLE_COMPANY: FeatureFlags(
        user_management=True,
        team_management=True,
        organization_switcher=False,
        sso_configuration=True,
        social_login=False,
        tenant_admin_dashboard=False,
        api_key_management=True,
        audit_log=True,
        quota_management=False,
        billing=False,
    ),
    DeploymentMode.MULTI_COMPANY: FeatureFlags(
        user_management=True,
        team_management=True,
        organization_switcher=True,
        sso_configuration=True,
        social_login=False,
        tenant_admin_dashboard=False,
        api_key_management=True,
        audit_log=True,
        quota_management=True,
        billing=False,
    ),
    DeploymentMode.PROVIDER: FeatureFlags(
        user_management=True,
        team_management=True,
        organization_switcher=True,
        sso_configuration=True,
        social_login=True,
        tenant_admin_dashboard=True,
        api_key_management=True,
        audit_log=True,
        quota_management=True,
        billing=True,
    ),
}


# Singleton config instance
_deployment_config: DeploymentConfig | None = None


def get_deployment_config() -> DeploymentConfig:
    """
    Get the deployment configuration singleton.

    Configuration is loaded from environment variables with fallback to config file.
    """
    global _deployment_config

    if _deployment_config is not None:
        return _deployment_config

    # Get user management mode from environment or config
    # Note: AUTOBOT_USER_MODE is separate from AUTOBOT_DEPLOYMENT_MODE (infrastructure)
    # AUTOBOT_DEPLOYMENT_MODE = hybrid/local/distributed (infrastructure)
    # AUTOBOT_USER_MODE = single_company/multi_company/provider (user mgmt)
    mode_str = config.user_mode.lower()

    try:
        mode = DeploymentMode(mode_str)
    except ValueError:
        # AutoBot always runs full, Postgres-backed user management (#10636).
        # An unset/invalid AUTOBOT_USER_MODE defaults to single_company.
        if mode_str:
            logger.warning(
                "AUTOBOT_USER_MODE=%r is invalid; defaulting to single_company (full user management)",
                mode_str,
            )
        mode = DeploymentMode.SINGLE_COMPANY

    # Get feature flags for this mode
    features = MODE_FEATURES[mode]

    # PostgreSQL is always required for full user management (#10636).
    postgres_enabled = True

    # Load PostgreSQL configuration from environment (uses SSOT fallback)
    postgres_host = config.postgres_host
    postgres_port = int(config.postgres_port)
    postgres_db = config.postgres_db
    postgres_user = config.postgres_user
    postgres_password = config.postgres_password

    # Encryption key for secrets (MFA, SSO config)
    encryption_key = config.encryption_key

    _deployment_config = DeploymentConfig(
        mode=mode,
        features=features,
        postgres_enabled=postgres_enabled,
        postgres_host=postgres_host,
        postgres_port=postgres_port,
        postgres_db=postgres_db,
        postgres_user=postgres_user,
        postgres_password=postgres_password,
        encryption_key=encryption_key,
    )

    return _deployment_config


def is_feature_enabled(feature: str) -> bool:
    """Check if a specific feature is enabled for the current deployment mode."""
    config = get_deployment_config()
    return getattr(config.features, feature, False)


def requires_auth() -> bool:
    """Check if authentication is required for the current deployment mode.

    AutoBot always runs full, Postgres-backed user management (#10636), so
    authentication is always required.
    """
    return True
