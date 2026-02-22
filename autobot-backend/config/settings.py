#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Configuration settings for the config manager.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class ConfigSettings(BaseSettings):
    """Configuration settings for the config manager"""

    # File paths
    config_dir: Path = Field(default=Path("config"), env="CONFIG_DIR")
    config_file: str = Field(default="config.yaml", env="CONFIG_FILE")
    settings_file: str = Field(default="settings.json", env="SETTINGS_FILE")

    # Cache settings
    cache_ttl: int = Field(default=300, env="CONFIG_CACHE_TTL")  # 5 minutes
    auto_reload: bool = Field(default=True, env="CONFIG_AUTO_RELOAD")

    # Redis settings for distributed config
    use_redis_cache: bool = Field(default=True, env="USE_REDIS_CONFIG_CACHE")
    redis_key_prefix: str = Field(default="config:", env="CONFIG_REDIS_PREFIX")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "allow"


# Deprecated: use ConfigSettings instead
UnifiedConfigSettings = ConfigSettings
