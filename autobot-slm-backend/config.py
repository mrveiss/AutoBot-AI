# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Server Configuration

Centralized configuration for the standalone SLM backend.
PostgreSQL replaces SQLite for all database operations (Issue #786).
"""

import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


def _get_cors_origins() -> list:
    """Build CORS origins from env var or infrastructure SSOT.

    Override with SLM_CORS_ORIGINS (comma-separated).
    Otherwise, generates origins from all known infrastructure VMs.
    """
    env_origins = os.getenv("SLM_CORS_ORIGINS", "")
    if env_origins:
        return [o.strip() for o in env_origins.split(",") if o.strip()]

    try:
        from autobot_shared.network_constants import NetworkConstants

        origins: set[str] = set()
        for host in NetworkConstants.get_host_configs():
            ip = host["ip"]
            port = host["port"]
            origins.add(f"http://{ip}:{port}")
            origins.add(f"https://{ip}")
        origins.add("https://172.16.168.19")
        origins.add("https://172.16.168.21")
        return sorted(origins)
    except ImportError:
        logger.warning("autobot_shared not available; using SLM-only CORS")
        return [
            "https://172.16.168.19",
            "https://172.16.168.21",
        ]


class Settings(BaseSettings):
    """SLM Server Settings."""

    # Paths - relative to slm-server directory (where config.py lives)
    base_dir: Path = Path(__file__).parent
    data_dir: Path = Path(__file__).parent / "data"
    config_dir: Path = Path(__file__).parent / "config"
    ansible_dir: Path = Path(__file__).parent / "ansible"
    backup_dir: Path = Path(
        os.getenv("SLM_BACKUP_DIR", str(Path.home() / "slm-backups"))
    )

    # ==========================================================================
    # PostgreSQL Database Configuration (Issue #786)
    # ==========================================================================
    # Main SLM operational database (nodes, deployments, backups, etc.)
    database_url: str = os.getenv(
        "SLM_DATABASE_URL",
        "postgresql+asyncpg://slm_app@127.0.0.1:5432/slm",
    )

    # SLM admin users database (fleet administrators)
    slm_users_database_url: str = os.getenv(
        "SLM_USERS_DATABASE_URL",
        "postgresql+asyncpg://slm_app@127.0.0.1:5432/slm_users",
    )

    # AutoBot application users database (colocated on SLM server)
    autobot_users_database_url: str = os.getenv(
        "AUTOBOT_USERS_DATABASE_URL",
        "postgresql+asyncpg://slm_app@127.0.0.1:5432/autobot_users",
    )

    # Database connection pool settings
    db_pool_size: int = int(os.getenv("SLM_DB_POOL_SIZE", "20"))
    db_pool_max_overflow: int = int(os.getenv("SLM_DB_POOL_MAX_OVERFLOW", "10"))
    db_pool_recycle: int = int(os.getenv("SLM_DB_POOL_RECYCLE", "3600"))

    # Server
    host: str = "0.0.0.0"  # nosec B104 — bound behind nginx reverse proxy
    port: int = 8000
    debug: bool = False

    # Authentication
    secret_key: str = os.getenv("SLM_SECRET_KEY", "")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Encryption for sensitive data (credentials, etc.)
    encryption_key: str = os.getenv("SLM_ENCRYPTION_KEY", "")

    def validate_secrets(self) -> None:
        """Generate random keys if not configured.

        Logs CRITICAL warnings — keys won't persist across restarts.
        """
        if not self.secret_key:
            self.secret_key = secrets.token_urlsafe(32)
            logger.critical(
                "SLM_SECRET_KEY not set - using random key. "
                "Tokens invalidate on restart. "
                "Set SLM_SECRET_KEY in environment."
            )
        if not self.encryption_key:
            self.encryption_key = secrets.token_urlsafe(32)
            logger.critical(
                "SLM_ENCRYPTION_KEY not set - using random key. "
                "Encrypted data unreadable after restart. "
                "Set SLM_ENCRYPTION_KEY in environment."
            )

    # VNC defaults (configurable via env vars)
    vnc_default_port: int = int(os.getenv("SLM_VNC_DEFAULT_PORT", "6080"))
    vnc_default_display: int = int(os.getenv("SLM_VNC_DEFAULT_DISPLAY", "1"))

    # Monitoring
    monitoring_mode: str = "local"  # local or remote
    monitoring_host: Optional[str] = None
    grafana_url: str = "http://127.0.0.1:3000"
    prometheus_url: str = "http://127.0.0.1:9090"

    # Health checks
    heartbeat_interval: int = 30  # seconds
    health_check_timeout: int = 10  # seconds
    unhealthy_threshold: int = 3  # missed heartbeats

    # Reconciliation
    reconcile_interval: int = 60  # seconds

    # CORS settings
    cors_origins: list = _get_cors_origins()

    # External URL - remote nodes use nginx reverse proxy
    external_url: str = os.getenv("SLM_EXTERNAL_URL", "https://172.16.168.19")

    class Config:
        env_prefix = "SLM_"
        env_file = ".env"


settings = Settings()

# Validate secrets on import (generate random if not set)
settings.validate_secrets()

# Ensure directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.config_dir.mkdir(parents=True, exist_ok=True)
