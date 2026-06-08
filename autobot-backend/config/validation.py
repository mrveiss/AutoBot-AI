#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Configuration validation for unified config manager.

Issue #3398: enhanced validation — startup warnings, conflict detection,
             invalid-value fast-fail, and startup summary log.
"""

import logging  # stdlib: avoids deadlock — config is on the logging-manager init path (GH#7765 pattern)
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List

from config.loader import ENV_VAR_MAPPINGS

logger = logging.getLogger(__name__)

# Minimum/maximum valid port range.
_PORT_MIN = 1
_PORT_MAX = 65535

# Config keys that must resolve to a non-None value before serving requests.
# Each entry is a dot-notation path checked via get_nested().
# GH#9232: backend.server_host removed — defaults to 0.0.0.0 in config/defaults.py
_REQUIRED_CONFIG_KEYS: List[str] = []

# Config keys required only when a feature flag is enabled.
# Each tuple is (required_key, guard_path, guard_enabled_value).
# When the guard key is absent the default is to treat the feature as enabled
# (backward-compatible behaviour for configs that predate the flag).
_CONDITIONAL_REQUIRED_CONFIG_KEYS: List[tuple] = [
    ("memory.redis.host", ["memory", "redis", "enabled"], True),
]


@dataclass
class ConfigValidationResult:
    """Structured result of startup configuration validation.

    ``valid`` is False when at least one error is present.  Warnings do not
    cause ``valid`` to be False but are logged at WARNING level.
    """

    valid: bool = True
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    overrides: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str) -> None:
        """Record a fatal validation error and mark result as invalid."""
        self.errors.append(message)
        self.valid = False

    def add_warning(self, message: str) -> None:
        """Record a non-fatal validation warning."""
        self.warnings.append(message)

    def add_override(self, env_var: str, file_value: Any, env_value: Any) -> None:
        """Record that an env var overrides the file-based value."""
        self.overrides[env_var] = {"file_value": file_value, "env_value": env_value}


def _get_nested_value(config: Dict[str, Any], path: List[str]) -> Any:
    """Walk ``config`` following ``path`` list; return ``None`` if missing."""
    current: Any = config
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _validate_port(value: Any, label: str, result: ConfigValidationResult) -> None:
    """Fail fast when *value* is not a valid TCP port number."""
    try:
        port = int(value)
    except (TypeError, ValueError):
        result.add_error(f"Config key '{label}' is not a valid integer (got {value!r})")
        return
    if not (_PORT_MIN <= port <= _PORT_MAX):
        result.add_error(f"Config key '{label}' has invalid port value {port} " f"(must be {_PORT_MIN}–{_PORT_MAX})")


# Keys whose values must be valid TCP ports.
_PORT_CONFIG_PATHS: List[tuple] = [
    (["backend", "server_port"], "backend.server_port"),
    (["memory", "redis", "port"], "memory.redis.port"),
]


def validate_startup_config(raw_config: Dict[str, Any]) -> ConfigValidationResult:
    """Validate *raw_config* at startup and return a structured result.

    Checks performed (Issue #3398):
    1. Required keys are present and non-empty.
    2. Port values are in the valid TCP range (1–65535).
    3. Each env var in ``ENV_VAR_MAPPINGS`` that is set is compared against the
       file-based value; a WARNING is emitted for every override so operators
       can see at a glance which values were changed by the environment.

    The function never raises; callers decide how to act on the result.
    """
    result = ConfigValidationResult()

    # --- 1a. Unconditionally required keys ---
    for dotted_key in _REQUIRED_CONFIG_KEYS:
        path = dotted_key.split(".")
        value = _get_nested_value(raw_config, path)
        if value is None:
            result.add_error(f"Required config key '{dotted_key}' is missing")

    # --- 1b. Conditionally required keys (gated on a feature flag) ---
    for required_key, guard_path, guard_enabled_value in _CONDITIONAL_REQUIRED_CONFIG_KEYS:
        guard_value = _get_nested_value(raw_config, guard_path)
        # Default to enabled when the guard key is absent (backward compat).
        feature_enabled = guard_value if guard_value is not None else guard_enabled_value
        if feature_enabled == guard_enabled_value:
            path = required_key.split(".")
            value = _get_nested_value(raw_config, path)
            if value is None:
                result.add_error(
                    f"Required config key '{required_key}' is missing "
                    f"(required when {'.'.join(str(p) for p in guard_path)} "
                    f"is {guard_enabled_value!r})"
                )

    # --- 2. Port range validation ---
    for path, label in _PORT_CONFIG_PATHS:
        value = _get_nested_value(raw_config, path)
        if value is not None:
            _validate_port(value, label, result)

    # --- 3. Env-var override conflict detection ---
    # Build a snapshot of what the file-based config would look like *without*
    # applying env overrides so we can compare.
    for env_var, config_path in ENV_VAR_MAPPINGS.items():
        env_value_raw = os.getenv(env_var)  # ssot-config-exempt: dynamic config key mapped from ENV_VAR_MAPPINGS
        if env_value_raw is None:
            continue  # env var not set — no override

        file_value = _get_nested_value(raw_config, config_path)
        # Convert the raw env string to a comparable Python type.
        if env_value_raw.lower() in ("true", "false"):
            env_value: Any = env_value_raw.lower() == "true"
        elif env_value_raw.isdigit():
            env_value = int(env_value_raw)
        else:
            env_value = env_value_raw

        if file_value is not None and file_value != env_value:
            key_label = ".".join(config_path)
            result.add_warning(
                f"Config override: env var {env_var} overrides file value for "
                f"'{key_label}' (file={file_value!r}, env={env_value!r})"
            )
            result.add_override(env_var, file_value, env_value)

    return result


def log_startup_config_summary(raw_config: Dict[str, Any]) -> None:
    """Emit a concise startup log of active configuration values.

    Logs at INFO level so operators have a single, scannable record of what
    the backend is actually using (Issue #3398).
    """
    redis_host = _get_nested_value(raw_config, ["memory", "redis", "host"])
    redis_port = _get_nested_value(raw_config, ["memory", "redis", "port"])
    backend_host = _get_nested_value(raw_config, ["backend", "server_host"])
    backend_port = _get_nested_value(raw_config, ["backend", "server_port"])
    ollama_host = _get_nested_value(
        raw_config,
        ["backend", "llm", "local", "providers", "ollama", "host"],
    )
    selected_model = _get_nested_value(
        raw_config,
        ["backend", "llm", "local", "providers", "ollama", "selected_model"],
    )
    log_level = _get_nested_value(raw_config, ["logging", "log_level"])

    logger.info(
        "Config summary — backend=%s:%s  redis=%s:%s  ollama=%s  " "model=%s  log_level=%s",
        backend_host,
        backend_port,
        redis_host,
        redis_port,
        ollama_host,
        selected_model,
        log_level,
    )


class ValidationMixin:
    """Mixin providing configuration validation"""

    def is_feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return self.get_nested(f"features.{feature}", False)

    def get_security_config(self) -> Dict[str, Any]:
        """Get security configuration"""
        return self.get_nested(
            "security",
            {"session": {"timeout_minutes": 30}, "encryption": {"enabled": False}},
        )

    def validate_config(self) -> Dict[str, Any]:
        """Validate configuration and return status"""
        status = {
            "config_loaded": True,
            "llm_config": self.get_llm_config(),
            "redis_config": self.get_redis_config(),
            "issues": [],
        }

        # Validate LLM configuration
        llm_config = status["llm_config"]
        if not llm_config.get("ollama", {}).get("selected_model"):
            status["issues"].append("No selected_model specified in LLM config")

        # Validate Redis configuration
        redis_config = status["redis_config"]
        if redis_config.get("enabled", True) and not redis_config.get("host"):
            status["issues"].append("Redis enabled but no host specified")

        return status

    def validate_startup(self) -> ConfigValidationResult:
        """Run full startup validation and log the results.

        Returns the structured result so callers can decide whether to abort.
        Issue #3398.
        """
        raw = self._config if hasattr(self, "_config") else {}
        result = validate_startup_config(raw)

        # Log override warnings so operators see them at startup.
        for warning in result.warnings:
            logger.warning("Config warning: %s", warning)

        if result.errors:
            for error in result.errors:
                logger.error("Config error: %s", error)
        else:
            log_startup_config_summary(raw)

        return result
