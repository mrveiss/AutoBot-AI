# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Dual Database Configuration for SLM User Management

Two PostgreSQL databases, both colocated on the SLM server:
1. slm_users - SLM admin users
2. autobot_users - AutoBot application users

Credentials are injected via /etc/autobot/db-credentials.env (Ansible-managed).
"""

import os
from dataclasses import dataclass

from autobot_shared import postgres_identity as pg
from autobot_shared.logging_manager import get_logger
from autobot_shared.secret_redaction import redact_value

logger = get_logger(__name__)


@dataclass(repr=False)
class DatabaseConfig:
    """Database connection configuration."""

    url: str

    def __repr__(self) -> str:
        """Mask the DSN password via the shared redactor (``RedactedReprMixin`` is pydantic-only)."""
        return f"{type(self).__name__}(url={redact_value('url', self.url)!r})"

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
            host=os.getenv("SLM_POSTGRES_HOST", pg.SLM_DB_HOST),
            port=os.getenv("SLM_POSTGRES_PORT", str(pg.DB_PORT)),
            database=os.getenv("SLM_POSTGRES_DB", pg.SLM_USERS_DB_NAME),
            user=os.getenv("SLM_POSTGRES_USER", pg.SLM_DB_ROLE),
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
            host=os.getenv("AUTOBOT_POSTGRES_HOST", pg.USERS_DB_HOST),
            port=os.getenv("AUTOBOT_POSTGRES_PORT", str(pg.DB_PORT)),
            database=os.getenv("AUTOBOT_POSTGRES_DB", pg.USERS_DB_NAME),
            user=_slm_role_on_users_db(),
            password=os.getenv("AUTOBOT_POSTGRES_PASSWORD", ""),
        )
    )


def _slm_role_on_users_db() -> str:
    """The SLM's OWN login role on the user-management DB (#19320).

    ``AUTOBOT_POSTGRES_USER`` names the BACKEND's role (``autobot_app``); the SLM
    connects as ``slm_app`` (the Ansible postgresql role writes that into
    ``AUTOBOT_USERS_DATABASE_URL``). Reading the backend's variable here gave one
    name two meanings, so the canonical source is ``SLM_POSTGRES_USER`` and the
    old name is honoured only as a deprecated alias -- an environment that set
    it keeps connecting exactly as before.
    """
    role, legacy = os.getenv("SLM_POSTGRES_USER") or "", os.getenv("AUTOBOT_POSTGRES_USER") or ""
    if role and legacy and role != legacy:
        _warn_once("conflict", "SLM_POSTGRES_USER and AUTOBOT_POSTGRES_USER differ; SLM_POSTGRES_USER wins (#19320)")
    if role:
        return role
    if legacy:
        _warn_once("deprecated", "AUTOBOT_POSTGRES_USER as the SLM's user-DB role is deprecated; set SLM_POSTGRES_USER")
        return legacy
    return pg.SLM_DB_ROLE


#: Warnings already logged by this process (each fires once, never per connection).
_WARNED: set[str] = set()


def _warn_once(key: str, message: str) -> None:
    """Log *message* once per process. Names variables only, never their values."""
    if key not in _WARNED:
        _WARNED.add(key)
        logger.warning(message)


def _build_url(host: str, port: str, database: str, user: str, password: str) -> str:
    """Build async PostgreSQL connection URL from components."""
    credentials = f"{user}:{password}" if password else user
    return f"postgresql+asyncpg://{credentials}@{host}:{port}/{database}"


@dataclass
class RbacDeploymentConfig:
    """Deployment configuration for RBAC middleware."""

    postgres_enabled: bool = True


def get_rbac_deployment_config() -> RbacDeploymentConfig:
    """Get deployment configuration. SLM always uses PostgreSQL."""
    return RbacDeploymentConfig(postgres_enabled=True)
