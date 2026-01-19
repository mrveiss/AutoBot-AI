# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SLM Server Configuration

Centralized configuration for the standalone SLM backend.
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

    # Database
    database_url: str = "sqlite+aiosqlite:///./data/slm.db"
    database_path: str = "./data/slm.db"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Authentication
    secret_key: str = os.getenv("SLM_SECRET_KEY", "change-me-in-production")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

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
