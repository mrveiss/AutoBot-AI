#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Configuration loading and merging logic.
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

import yaml

from src.config.defaults import get_default_config
from src.constants.threshold_constants import StringParsingConstants

logger = logging.getLogger(__name__)

# Module-level constants for O(1) lookups (Issue #326)
YAML_FILE_EXTENSIONS = {".yaml", ".yml"}


def load_yaml_config(config_file: Path) -> Dict[str, Any]:
    """Load base configuration from YAML file"""
    if not config_file.exists():
        logger.info(f"Base configuration file not found: {config_file}, using defaults")
        return get_default_config()

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        logger.info(f"Base configuration loaded from {config_file}")
        return config
    except Exception as e:
        logger.error(f"Failed to load YAML configuration: {e}")
        return get_default_config()


def load_json_settings(settings_file: Path) -> Dict[str, Any]:
    """Load user settings from JSON file"""
    if not settings_file.exists():
        logger.debug(f"Settings file not found: {settings_file}")
        return {}

    try:
        with open(settings_file, "r", encoding="utf-8") as f:
            settings = json.load(f)
        logger.info(f"User settings loaded from {settings_file}")
        return settings
    except Exception as e:
        logger.warning(f"Failed to load JSON settings: {e}")
        return {}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries, with override taking precedence"""
    result = base.copy()

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value

    return result


def apply_env_overrides(config: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment variable overrides using AUTOBOT_ prefix"""
    env_overrides = {}

    # Environment variable mappings
    env_mappings = {
        # Backend configuration
        "AUTOBOT_BACKEND_HOST": ["backend", "server_host"],
        "AUTOBOT_BACKEND_PORT": ["backend", "server_port"],
        "AUTOBOT_BACKEND_TIMEOUT": ["backend", "timeout"],
        "AUTOBOT_BACKEND_MAX_RETRIES": ["backend", "max_retries"],
        "AUTOBOT_BACKEND_STREAMING": ["backend", "streaming"],
        # LLM configuration
        "AUTOBOT_OLLAMA_HOST": [
            "backend",
            "llm",
            "local",
            "providers",
            "ollama",
            "host",
        ],
        "AUTOBOT_DEFAULT_LLM_MODEL": [
            "backend",
            "llm",
            "local",
            "providers",
            "ollama",
            "selected_model",
        ],
        "AUTOBOT_OLLAMA_ENDPOINT": [
            "backend",
            "llm",
            "local",
            "providers",
            "ollama",
            "endpoint",
        ],
        # Redis configuration
        "AUTOBOT_REDIS_HOST": ["memory", "redis", "host"],
        "AUTOBOT_REDIS_PORT": ["memory", "redis", "port"],
        "AUTOBOT_REDIS_DB": ["memory", "redis", "db"],
        "AUTOBOT_REDIS_PASSWORD": ["memory", "redis", "password"],
        "AUTOBOT_REDIS_ENABLED": ["memory", "redis", "enabled"],
        # UI configuration
        "AUTOBOT_UI_THEME": ["ui", "theme"],
        "AUTOBOT_UI_FONT_SIZE": ["ui", "font_size"],
        "AUTOBOT_UI_LANGUAGE": ["ui", "language"],
        "AUTOBOT_UI_ANIMATIONS": ["ui", "animations"],
        # Chat configuration
        "AUTOBOT_CHAT_MAX_MESSAGES": ["chat", "max_messages"],
        "AUTOBOT_CHAT_AUTO_SCROLL": ["chat", "auto_scroll"],
        "AUTOBOT_CHAT_RETENTION_DAYS": ["chat", "message_retention_days"],
        # Logging configuration
        "AUTOBOT_LOG_LEVEL": ["logging", "log_level"],
        "AUTOBOT_LOG_TO_FILE": ["logging", "log_to_file"],
        "AUTOBOT_LOG_FILE_PATH": ["logging", "log_file_path"],
    }

    for env_var, config_path in env_mappings.items():
        env_value = os.getenv(env_var)
        if env_value is not None:
            # Convert string values to appropriate types
            if env_value.lower() in StringParsingConstants.BOOL_STRING_VALUES:
                env_value = env_value.lower() == "true"
            elif env_value.isdigit():
                env_value = int(env_value)

            # Set the value in the config
            set_nested_value(env_overrides, config_path, env_value)
            logger.info(f"Applied environment override: {env_var} = {env_value}")

    # Merge environment overrides
    if env_overrides:
        return deep_merge(config, env_overrides)

    return config


def set_nested_value(config: Dict[str, Any], path: List[str], value: Any) -> None:
    """Set a nested value in a dictionary using a path list"""
    current = config
    for key in path[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[path[-1]] = value


def load_configuration(
    config_dir: Path, base_config_file: Path, settings_file: Path
) -> Dict[str, Any]:
    """Load and merge all configuration sources (synchronous)

    IMPORTANT: Configuration precedence order:
    1. config.yaml (base configuration)
    2. settings.json (user settings override base config)
    3. Environment variables (override both)

    WARNING: settings.json completely overrides matching sections from config.yaml.
    For example, if config.yaml has 10 CORS origins and settings.json has 4,
    only the 4 from settings.json will be used.
    """
    try:
        # Load base configuration from YAML
        base_config = load_yaml_config(base_config_file)

        # Load user settings from JSON (if exists)
        user_settings = load_json_settings(settings_file)

        # Merge configurations (user settings override base config)
        config = deep_merge(base_config, user_settings)

        # Apply environment variable overrides
        config = apply_env_overrides(config)

        logger.info("Unified configuration loaded successfully")
        return config

    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        raise
