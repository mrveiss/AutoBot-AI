# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Deployment Mode Configuration for User Management System

Supports 4 deployment modes:
- single_user: No auth required, personal/dev use
- single_company: One org with users and teams
- multi_company: Multiple orgs (multi-tenant), isolated data
- provider: Full multi-tenant with billing, quotas, social login
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.config import UnifiedConfigManager


def _get_default_postgres_host() -> str:
    """
    Get default PostgreSQL host from SSOT config.

    PostgreSQL runs on the Redis VM (172.16.168.23) in AutoBot architecture.
    Issue #694: Config consolidation - uses SSOT with proper fallback.
    """
    try:
        from src.config.ssot_config import get_config
        return get_config().vm.redis
    except Exception:
        # Fallback only if SSOT config completely unavailable
        import os
        return os.getenv("AUTOBOT_REDIS_HOST", "172.16.168.23")


class DeploymentMode(str, Enum):
    """Deployment mode enumeration."""

    SINGLE_USER = "single_user"
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
    encryption_key: Optional[str] = None

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
    DeploymentMode.SINGLE_USER: FeatureFlags(
        user_management=False,
        team_management=False,
        organization_switcher=False,
        sso_configuration=False,
        social_login=False,
        tenant_admin_dashboard=False,
        api_key_management=False,
        audit_log=False,
        quota_management=False,
        billing=False,
    ),
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
_deployment_config: Optional[DeploymentConfig] = None


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
    # AUTOBOT_USER_MODE = single_user/single_company/multi_company/provider (user mgmt)
    mode_str = os.getenv("AUTOBOT_USER_MODE", "single_user").lower()

    try:
        mode = DeploymentMode(mode_str)
    except ValueError:
        # Default to single_user for invalid values
        mode = DeploymentMode.SINGLE_USER

    # Get feature flags for this mode
    features = MODE_FEATURES[mode]

    # Check if PostgreSQL is enabled (required for non-single_user modes)
    postgres_enabled = mode != DeploymentMode.SINGLE_USER

    # Load PostgreSQL configuration from environment (uses SSOT fallback)
    postgres_host = os.getenv("AUTOBOT_POSTGRES_HOST", _get_default_postgres_host())
    postgres_port = int(os.getenv("AUTOBOT_POSTGRES_PORT", "5432"))
    postgres_db = os.getenv("AUTOBOT_POSTGRES_DB", "autobot")
    postgres_user = os.getenv("AUTOBOT_POSTGRES_USER", "autobot")
    postgres_password = os.getenv("AUTOBOT_POSTGRES_PASSWORD", "")

    # Encryption key for secrets (MFA, SSO config)
    encryption_key = os.getenv("AUTOBOT_ENCRYPTION_KEY")

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
    """Check if authentication is required for the current deployment mode."""
    config = get_deployment_config()
    return config.mode != DeploymentMode.SINGLE_USER
