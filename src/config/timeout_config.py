#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Timeout configuration management for unified config manager.
"""

import logging
import os
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for required timeout categories
_REQUIRED_TIMEOUT_CATEGORIES = ("redis", "llamaindex", "documents", "http", "llm")

# Issue #380: Module-level tuple for numeric types
_NUMERIC_TYPES = (int, float)


def _validate_timeout_value(
    value: Any, path: str, issues: list, warnings: list
) -> None:
    """Validate a single timeout value (Issue #315: extracted).

    Args:
        value: The timeout value to validate
        path: The configuration path for error messages
        issues: List to append validation errors
        warnings: List to append validation warnings
    """
    if not isinstance(value, _NUMERIC_TYPES):  # Issue #380
        return

    if value <= 0:
        issues.append(f"Invalid timeout '{path}': {value} (must be > 0)")
    elif value > 600:
        warnings.append(f"Very long timeout '{path}': {value}s (> 10 minutes)")


def _check_timeout_values_recursive(
    config: dict, issues: list, warnings: list, path: str = ""
) -> None:
    """Recursively check timeout values in config (Issue #315: extracted).

    Args:
        config: Configuration dictionary to check
        issues: List to append validation errors
        warnings: List to append validation warnings
        path: Current path prefix for nested keys
    """
    for key, value in config.items():
        current_path = f"{path}.{key}" if path else key
        if isinstance(value, dict):
            _check_timeout_values_recursive(value, issues, warnings, current_path)
        else:
            _validate_timeout_value(value, current_path, issues, warnings)


class TimeoutConfigMixin:
    """Mixin providing timeout configuration management"""

    def get_timeout(self, category: str, timeout_type: str = "default") -> float:
        """
        Get timeout value for a category.

        Provides compatibility with config_helper.cfg.get_timeout()
        for config consolidation (Issue #63).

        Args:
            category: Timeout category (e.g., 'llm', 'http', 'redis')
            timeout_type: Type of timeout (default: 'default')

        Returns:
            Timeout in seconds
        """
        timeout = self.get_nested(f"timeouts.{category}.{timeout_type}")
        if timeout is not None:
            return float(timeout)

        # Fallback defaults
        defaults = {
            "llm": {"default": 120.0, "streaming": 180.0},
            "http": {"default": 30.0, "long": 60.0},
            "redis": {"default": 5.0, "connection": 10.0},
            "database": {"default": 30.0, "query": 60.0},
        }
        return defaults.get(category, {}).get(timeout_type, 30.0)

    def get_timeout_for_env(
        self,
        category: str,
        timeout_type: str,
        environment: str = None,
        default: float = 60.0,
    ) -> float:
        """
        Get environment-aware timeout value.

        Args:
            category: Category path (e.g., 'redis.operations')
            timeout_type: Specific timeout type (e.g., 'get')
            environment: Environment name ('development', 'production')
            default: Fallback value if not found

        Returns:
            Timeout value in seconds
        """
        if environment is None:
            environment = os.getenv("AUTOBOT_ENVIRONMENT", "production")

        # Try environment-specific override first
        env_path = f"environments.{environment}.timeouts.{category}.{timeout_type}"
        env_timeout = self.get_nested(env_path)
        if env_timeout is not None:
            return float(env_timeout)

        # Fall back to base configuration
        base_path = f"timeouts.{category}.{timeout_type}"
        base_timeout = self.get_nested(base_path, default)
        return float(base_timeout)

    def get_timeout_group(
        self, category: str, environment: str = None
    ) -> Dict[str, float]:
        """
        Get all timeouts for a category as a dictionary.

        Args:
            category: Category path (e.g., 'redis.operations')
            environment: Environment name (optional)

        Returns:
            Dictionary of timeout names to values
        """
        base_path = f"timeouts.{category}"
        base_config = self.get_nested(base_path, {})

        if not isinstance(base_config, dict):
            return {}

        # Apply environment overrides if specified
        if environment:
            env_path = f"environments.{environment}.timeouts.{category}"
            env_overrides = self.get_nested(env_path, {})
            if isinstance(env_overrides, dict):
                base_config = {**base_config, **env_overrides}

        # Convert all values to float
        result = {}
        for k, v in base_config.items():
            if isinstance(v, _NUMERIC_TYPES):  # Issue #380
                result[k] = float(v)

        return result

    def validate_timeouts(self) -> Dict[str, Any]:
        """Validate all timeout configurations.

        Issue #315: Refactored to use helper functions for reduced nesting.

        Returns:
            Validation report with issues and warnings
        """
        issues = []
        warnings = []

        # Check required timeout categories - Issue #380: Use module-level tuple
        for category in _REQUIRED_TIMEOUT_CATEGORIES:
            timeout_config = self.get_nested(f"timeouts.{category}")
            if timeout_config is None:
                issues.append(f"Missing timeout configuration for '{category}'")

        # Validate timeout ranges using extracted helper
        all_timeouts = self.get_nested("timeouts", {})
        _check_timeout_values_recursive(all_timeouts, issues, warnings)

        return {"valid": len(issues) == 0, "issues": issues, "warnings": warnings}
