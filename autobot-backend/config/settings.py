#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Configuration settings for the config manager.
"""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigSettings(BaseSettings):
    """Configuration settings for the config manager"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="allow",
    )

    # File paths
    config_dir: Path = Field(default=Path("config"), validation_alias="CONFIG_DIR")
    config_file: str = Field(default="config.yaml", validation_alias="CONFIG_FILE")
    settings_file: str = Field(default="settings.json", validation_alias="SETTINGS_FILE")

    # Cache settings
    cache_ttl: int = Field(default=300, validation_alias="CONFIG_CACHE_TTL")  # 5 minutes
    auto_reload: bool = Field(default=True, validation_alias="CONFIG_AUTO_RELOAD")

    # Redis settings for distributed config
    use_redis_cache: bool = Field(default=True, validation_alias="USE_REDIS_CONFIG_CACHE")
    redis_key_prefix: str = Field(default="config:", validation_alias="CONFIG_REDIS_PREFIX")


# Deprecated: use ConfigSettings instead
UnifiedConfigSettings = ConfigSettings
