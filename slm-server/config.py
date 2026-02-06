# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Server Configuration

Centralized configuration for the standalone SLM backend.
PostgreSQL replaces SQLite for all database operations (Issue #786).
"""

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings


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
        "SLM_DATABASE_URL", "postgresql+asyncpg://slm_app@127.0.0.1:5432/slm"
    )

    # SLM admin users database (fleet administrators)
    slm_users_database_url: str = os.getenv(
        "SLM_USERS_DATABASE_URL",
        "postgresql+asyncpg://slm_app@127.0.0.1:5432/slm_users",
    )

    # AutoBot application users database (on Redis VM)
    autobot_users_database_url: str = os.getenv(
        "AUTOBOT_USERS_DATABASE_URL",
        "postgresql+asyncpg://autobot_app@172.16.168.23:5432/autobot_users",
    )

    # Database connection pool settings
    db_pool_size: int = int(os.getenv("SLM_DB_POOL_SIZE", "20"))
    db_pool_max_overflow: int = int(os.getenv("SLM_DB_POOL_MAX_OVERFLOW", "10"))
    db_pool_recycle: int = int(os.getenv("SLM_DB_POOL_RECYCLE", "3600"))

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Authentication
    secret_key: str = os.getenv("SLM_SECRET_KEY", "")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Encryption for sensitive data (credentials, etc.)
    encryption_key: str = os.getenv("SLM_ENCRYPTION_KEY", "")

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
    cors_origins: list = ["*"]

    # External URL - the address remote nodes use to reach the SLM backend
    # Backend binds to 127.0.0.1:8000, so remote agents use nginx reverse proxy
    external_url: str = os.getenv("SLM_EXTERNAL_URL", "https://172.16.168.19")

    class Config:
        env_prefix = "SLM_"
        env_file = ".env"


settings = Settings()

# Ensure directories exist
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.config_dir.mkdir(parents=True, exist_ok=True)
