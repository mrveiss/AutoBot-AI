#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Synchronous operations for unified config manager.
"""

import json
import logging
import time
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)


class SyncOperationsMixin:
    """Mixin providing synchronous config operations"""

    def _get_sync_lock(self):
        """Get or create synchronous lock"""
        if self._sync_lock is None:
            import threading

            self._sync_lock = threading.Lock()
        return self._sync_lock

    def _should_refresh_sync_cache(self) -> bool:
        """Check if synchronous cache should be refreshed"""
        if self._sync_cache_timestamp is None:
            return True
        return (time.time() - self._sync_cache_timestamp) > self.CACHE_DURATION

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key (synchronous)"""
        with self._get_sync_lock():
            if self._should_refresh_sync_cache():
                self._reload_config()
            return self._config.get(key, default)

    def get_nested(self, path: str, default: Any = None) -> Any:
        """Get nested config value using dot notation (synchronous)"""
        with self._get_sync_lock():
            if self._should_refresh_sync_cache():
                self._reload_config()

            keys = path.split(".")
            current = self._config

            try:
                for key in keys:
                    current = current[key]
                return current
            except (KeyError, TypeError):
                return default

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value (synchronous)"""
        with self._get_sync_lock():
            self._config[key] = value

    def set_nested(self, path: str, value: Any) -> None:
        """Set a nested configuration value using dot notation (synchronous)"""
        with self._get_sync_lock():
            keys = path.split(".")
            current = self._config

            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]

            current[keys[-1]] = value

    def save_settings(self) -> None:
        """Save current configuration to settings.json (synchronous, thread-safe)"""
        with self._get_sync_lock():
            try:
                # Filter out prompts before saving
                import copy

                filtered_config = copy.deepcopy(self._config)
                if "prompts" in filtered_config:
                    logger.info("Removing prompts section from settings save")
                    del filtered_config["prompts"]

                self.settings_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.settings_file, "w", encoding="utf-8") as f:
                    json.dump(filtered_config, f, indent=2, ensure_ascii=False)

                # Clear cache to force fresh load on next access
                self._sync_cache_timestamp = None
                logger.info("Settings saved to %s and cache cleared", self.settings_file)
            except Exception as e:
                logger.error("Failed to save settings: %s", e)
                raise

    def save_config_to_yaml(self) -> None:
        """Save configuration to config.yaml file (synchronous, thread-safe)"""
        with self._get_sync_lock():
            try:
                # Filter out prompts and legacy fields before saving
                import copy

                filtered_config = copy.deepcopy(self._config)

                if "prompts" in filtered_config:
                    logger.info("Removing prompts section from YAML save")
                    del filtered_config["prompts"]

                self.base_config_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.base_config_file, "w", encoding="utf-8") as f:
                    yaml.dump(filtered_config, f, default_flow_style=False, indent=2)

                # Clear cache to force fresh load on next access
                self._sync_cache_timestamp = None
                logger.info(
                    "Configuration saved to %s and cache cleared",
                    self.base_config_file,
                )
            except Exception as e:
                logger.error("Failed to save YAML configuration: %s", e)
                raise

    def reload(self) -> None:
        """Reload configuration from files (synchronous)"""
        with self._get_sync_lock():
            self._reload_config()

    def to_dict(self) -> Dict[str, Any]:
        """Return the complete configuration as a dictionary (synchronous)"""
        with self._get_sync_lock():
            if self._should_refresh_sync_cache():
                self._reload_config()
            return self._config.copy()
