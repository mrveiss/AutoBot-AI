# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dual Database Configuration for SLM User Management

Two PostgreSQL databases:
1. slm_users (local on 172.16.168.19) - SLM admin users
2. autobot_users (remote on 172.16.168.23) - AutoBot application users
"""

import os
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    """Database connection configuration."""

    host: str
    port: int
    database: str
    user: str
    password: str

    @property
    def url(self) -> str:
        """Generate async PostgreSQL connection URL."""
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )

    @property
    def sync_url(self) -> str:
        """Generate sync PostgreSQL connection URL (for Alembic)."""
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
        )


def get_slm_db_config() -> DatabaseConfig:
    """Get SLM local database configuration."""
    return DatabaseConfig(
        host=os.getenv("SLM_POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("SLM_POSTGRES_PORT", "5432")),
        database=os.getenv("SLM_POSTGRES_DB", "slm_users"),
        user=os.getenv("SLM_POSTGRES_USER", "slm_admin"),
        password=os.getenv("SLM_POSTGRES_PASSWORD", ""),
    )


def get_autobot_db_config() -> DatabaseConfig:
    """Get AutoBot remote database configuration (on Redis VM)."""
    return DatabaseConfig(
        host=os.getenv("AUTOBOT_POSTGRES_HOST", "172.16.168.23"),
        port=int(os.getenv("AUTOBOT_POSTGRES_PORT", "5432")),
        database=os.getenv("AUTOBOT_POSTGRES_DB", "autobot_users"),
        user=os.getenv("AUTOBOT_POSTGRES_USER", "autobot_user_admin"),
        password=os.getenv("AUTOBOT_POSTGRES_PASSWORD", ""),
    )


@dataclass
class DeploymentConfig:
    """Deployment configuration for RBAC middleware."""

    postgres_enabled: bool = True


def get_deployment_config() -> DeploymentConfig:
    """Get deployment configuration. SLM always uses PostgreSQL."""
    return DeploymentConfig(postgres_enabled=True)
