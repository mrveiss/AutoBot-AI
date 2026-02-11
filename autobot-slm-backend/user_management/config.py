# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Dual Database Configuration for SLM User Management

Two PostgreSQL databases, both colocated on the SLM server (172.16.168.19):
1. slm_users - SLM admin users
2. autobot_users - AutoBot application users

Credentials are injected via /etc/autobot/db-credentials.env (Ansible-managed).
"""

import os
from dataclasses import dataclass


@dataclass
class DatabaseConfig:
    """Database connection configuration."""

    url: str

    @property
    def sync_url(self) -> str:
        """Generate sync PostgreSQL connection URL (for Alembic)."""
        return self.url.replace("postgresql+asyncpg://", "postgresql://")


def get_slm_db_config() -> DatabaseConfig:
    """Get SLM local database configuration.

    Reads SLM_USERS_DATABASE_URL (set by Ansible credential template).
    Falls back to component env vars for backward compatibility.
    """
    url = os.getenv("SLM_USERS_DATABASE_URL")
    if url:
        return DatabaseConfig(url=url)
    return DatabaseConfig(
        url=_build_url(
            host=os.getenv("SLM_POSTGRES_HOST", "127.0.0.1"),
            port=os.getenv("SLM_POSTGRES_PORT", "5432"),
            database=os.getenv("SLM_POSTGRES_DB", "slm_users"),
            user=os.getenv("SLM_POSTGRES_USER", "slm_app"),
            password=os.getenv("SLM_POSTGRES_PASSWORD", ""),
        )
    )


def get_autobot_db_config() -> DatabaseConfig:
    """Get AutoBot database configuration (colocated on SLM server).

    Reads AUTOBOT_USERS_DATABASE_URL (set by Ansible credential template).
    Falls back to component env vars for backward compatibility.
    """
    url = os.getenv("AUTOBOT_USERS_DATABASE_URL")
    if url:
        return DatabaseConfig(url=url)
    return DatabaseConfig(
        url=_build_url(
            host=os.getenv("AUTOBOT_POSTGRES_HOST", "127.0.0.1"),
            port=os.getenv("AUTOBOT_POSTGRES_PORT", "5432"),
            database=os.getenv("AUTOBOT_POSTGRES_DB", "autobot_users"),
            user=os.getenv("AUTOBOT_POSTGRES_USER", "slm_app"),
            password=os.getenv("AUTOBOT_POSTGRES_PASSWORD", ""),
        )
    )


def _build_url(host: str, port: str, database: str, user: str, password: str) -> str:
    """Build async PostgreSQL connection URL from components."""
    return f"postgresql+asyncpg://{user}:{password}" f"@{host}:{port}/{database}"


@dataclass
class DeploymentConfig:
    """Deployment configuration for RBAC middleware."""

    postgres_enabled: bool = True


def get_deployment_config() -> DeploymentConfig:
    """Get deployment configuration. SLM always uses PostgreSQL."""
    return DeploymentConfig(postgres_enabled=True)
