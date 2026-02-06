# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralized configuration service for backend API.
Eliminates duplication across settings.py, llm.py, and redis.py

SSOT Migration (Issue #602):
    This service now integrates with the SSOT configuration system.
    Network constants and other values are sourced from ssot_config.py.

UPDATED: Now uses unified_config_manager for consistent model selection
"""

import fcntl
import logging
import threading
from typing import Dict

import yaml

from backend.type_defs.common import Metadata

# SSOT Migration (Issue #602): Import SSOT config as primary source
from autobot_shared.ssot_config import get_config as get_ssot_config

# Legacy import for backward compatibility - these now read from SSOT
from constants.network_constants import NetworkConstants

# Get SSOT config
_ssot = get_ssot_config()

# Extract constants from SSOT (with fallback to NetworkConstants for safety)
BACKEND_HOST_IP = _ssot.vm.main if _ssot else NetworkConstants.MAIN_MACHINE_IP
BACKEND_PORT = _ssot.port.backend if _ssot else NetworkConstants.BACKEND_PORT
HTTP_PROTOCOL = "http"
REDIS_HOST_IP = _ssot.vm.redis if _ssot else NetworkConstants.REDIS_VM_IP
from config import unified_config_manager

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for LLM provider keys
_LLM_PROVIDER_KEYS = frozenset({"ollama", "local", "cloud"})


class ConfigService:
    """Centralized configuration management service"""

    _cached_config = None
    _cache_timestamp = None
    CACHE_DURATION = 30  # Cache for 30 seconds
    # Issue #481: Thread-safe lock for config file writes
    _config_write_lock = threading.Lock()

    @staticmethod
    def _should_refresh_cache() -> bool:
        """Check if cache should be refreshed"""
        import time

        if ConfigService._cached_config is None:
            return True

        if ConfigService._cache_timestamp is None:
            return True

        return (
            time.time() - ConfigService._cache_timestamp
        ) > ConfigService.CACHE_DURATION

    @staticmethod
    def clear_cache():
        """Force clear the configuration cache"""
        ConfigService._cached_config = None
        ConfigService._cache_timestamp = None
        logger.info("Configuration cache cleared")

    @staticmethod
    def _get_nested_from_dict(data: dict, path: str, default=None):
        """Get nested value from dict by dot-separated path (Issue #372 - helper)."""
        keys = path.split(".")
        value = data
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    @staticmethod
    def _build_backend_config(get, llm_config: Metadata) -> Metadata:
        """
        Build backend configuration section.

        SSOT Migration (Issue #602):
            Now uses SSOT config for default values.

        Issue #281: Extracted helper for backend config building.

        Args:
            get: Config getter function
            llm_config: LLM configuration dict

        Returns:
            Backend configuration dict
        """
        # Use SSOT for default backend URL
        default_api_endpoint = (
            _ssot.backend_url if _ssot else f"{HTTP_PROTOCOL}://{BACKEND_HOST_IP}:{BACKEND_PORT}"
        )
        default_port = _ssot.port.backend if _ssot else BACKEND_PORT

        return {
            "api_endpoint": get("backend.api_endpoint", default_api_endpoint),
            "server_host": get(
                "backend.server_host", NetworkConstants.BIND_ALL_INTERFACES
            ),
            "server_port": get("backend.server_port", default_port),
            "chat_data_dir": get("backend.chat_data_dir", "data/chats"),
            "chat_history_file": get(
                "backend.chat_history_file", "data/chat_history.json"
            ),
            "knowledge_base_db": get(
                "backend.knowledge_base_db", "data/knowledge_base.db"
            ),
            "reliability_stats_file": get(
                "backend.reliability_stats_file", "data/reliability_stats.json"
            ),
            "audit_log_file": get("backend.audit_log_file", "data/audit.log"),
            "cors_origins": get("backend.cors_origins", []),
            "timeout": get("backend.timeout", 60),
            "max_retries": get("backend.max_retries", 3),
            "streaming": get("backend.streaming", False),
            "llm": llm_config,
        }

    @staticmethod
    def _build_memory_config(get) -> Metadata:
        """
        Build memory configuration section.

        SSOT Migration (Issue #602):
            Redis host/port now sourced from SSOT config.

        Issue #281: Extracted helper for memory config building.

        Args:
            get: Config getter function

        Returns:
            Memory configuration dict
        """
        # Use SSOT for Redis defaults
        default_redis_host = _ssot.vm.redis if _ssot else REDIS_HOST_IP
        default_redis_port = _ssot.port.redis if _ssot else NetworkConstants.REDIS_PORT

        return {
            "long_term": {
                "enabled": get("memory.long_term.enabled", True),
                "retention_days": get("memory.long_term.retention_days", 30),
            },
            "short_term": {
                "enabled": get("memory.short_term.enabled", True),
                "duration_minutes": get(
                    "memory.short_term.duration_minutes", 30
                ),
            },
            "vector_storage": {
                "enabled": get("memory.vector_storage.enabled", True),
                "update_frequency_days": get(
                    "memory.vector_storage.update_frequency_days", 7
                ),
            },
            "chromadb": {
                "enabled": get("memory.chromadb.enabled", True),
                "path": get("memory.chromadb.path", "data/chromadb"),
                "collection_name": get(
                    "memory.chromadb.collection_name", "autobot_memory"
                ),
            },
            "redis": {
                "enabled": get("memory.redis.enabled", False),
                "host": get("memory.redis.host", default_redis_host),
                "port": get("memory.redis.port", default_redis_port),
            },
        }

    @staticmethod
    def _build_ui_and_security_config(get) -> Metadata:
        """
        Build UI and security configuration sections.

        Issue #665: Extracted helper for UI/security config building.

        Args:
            get: Config getter function

        Returns:
            Dict with ui and security configuration sections
        """
        return {
            "ui": {
                "theme": get("ui.theme", "light"),
                "font_size": get("ui.font_size", "medium"),
                "language": get("ui.language", "en"),
                "animations": get("ui.animations", True),
                "developer_mode": get("ui.developer_mode", False),
            },
            "security": {
                "enable_encryption": get("security.enable_encryption", False),
                "session_timeout_minutes": get(
                    "security.session_timeout_minutes", 30
                ),
            },
        }

    @staticmethod
    def _build_logging_config(get) -> Metadata:
        """
        Build logging configuration section.

        Issue #665: Extracted helper for logging config building.
        Issue #594: Match frontend LoggingSettings interface field names.

        Args:
            get: Config getter function

        Returns:
            Logging configuration dict
        """
        return {
            "level": get("logging.log_level", "info"),
            "log_levels": ["debug", "info", "warning", "error", "critical"],
            "console": get("logging.console", True),
            "file": get("logging.log_to_file", True),
            "max_file_size": get("logging.max_file_size", 10),
            "log_requests": get("logging.log_requests", False),
            "log_sql": get("logging.log_sql", False),
            "log_file_path": get("logging.log_file_path", "logs/autobot.log"),
        }

    @staticmethod
    def _build_other_config_sections(get) -> Metadata:
        """
        Build remaining configuration sections (knowledge_base, voice_interface, developer).

        Issue #665: Extracted helper for miscellaneous config building.

        Args:
            get: Config getter function

        Returns:
            Dict with knowledge_base, voice_interface, and developer config sections
        """
        return {
            "knowledge_base": {
                "enabled": get("knowledge_base.enabled", True),
                "update_frequency_days": get(
                    "knowledge_base.update_frequency_days", 7
                ),
            },
            "voice_interface": {
                "enabled": get("voice_interface.enabled", False),
                "voice": get("voice_interface.voice", "default"),
                "speech_rate": get("voice_interface.speech_rate", 1.0),
            },
            "developer": {
                "enabled": get("developer.enabled", False),
                "enhanced_errors": get("developer.enhanced_errors", True),
                "endpoint_suggestions": get("developer.endpoint_suggestions", True),
                "debug_logging": get("developer.debug_logging", False),
            },
        }

    @staticmethod
    def get_full_config() -> Metadata:
        """
        Get complete application configuration.

        Issue #281: Refactored from 145 lines to use extracted helper methods.
        Issue #665: Further refactored to reduce from 103 lines to below 65 lines.

        Returns:
            Complete configuration dictionary
        """
        import time

        # Return cached config if still valid
        if not ConfigService._should_refresh_cache():
            logger.debug("Returning cached configuration")
            return ConfigService._cached_config

        logger.debug("Refreshing configuration cache")

        try:
            # Get the complete config once to avoid repeated calls (Issue #372)
            full_config = unified_config_manager.to_dict()
            llm_config = unified_config_manager.get_llm_config()

            # Use local helper to access already-fetched config (Issue #372 fix)
            def get(path, default=None):
                return ConfigService._get_nested_from_dict(full_config, path, default)

            # Build comprehensive config structure matching frontend expectations
            # Note: Prompts section is excluded as it's managed separately
            # Issue #665: Uses extracted helpers for all config sections
            ui_security = ConfigService._build_ui_and_security_config(get)
            other_sections = ConfigService._build_other_config_sections(get)

            config_data = {
                "message_display": {
                    "show_thoughts": get("message_display.show_thoughts", True),
                    "show_json": get("message_display.show_json", False),
                    "show_utility": get("message_display.show_utility", False),
                    "show_planning": get("message_display.show_planning", True),
                    "show_debug": get("message_display.show_debug", False),
                },
                "chat": {
                    "auto_scroll": get("chat.auto_scroll", True),
                    "max_messages": get("chat.max_messages", 100),
                    "message_retention_days": get("chat.message_retention_days", 30),
                },
                "backend": ConfigService._build_backend_config(get, llm_config),
                "ui": ui_security["ui"],
                "security": ui_security["security"],
                "logging": ConfigService._build_logging_config(get),
                "knowledge_base": other_sections["knowledge_base"],
                "voice_interface": other_sections["voice_interface"],
                "memory": ConfigService._build_memory_config(get),
                "developer": other_sections["developer"],
            }

            # Cache the configuration
            ConfigService._cached_config = config_data
            ConfigService._cache_timestamp = time.time()
            logger.debug(
                f"Configuration cached for {ConfigService.CACHE_DURATION} seconds"
            )

            return config_data
        except Exception as e:
            logger.error("Error getting full config: %s", str(e))
            # Return cached config if available, even if refresh failed
            if ConfigService._cached_config is not None:
                logger.warning("Returning cached config due to refresh failure")
                return ConfigService._cached_config
            raise

    @staticmethod
    def get_llm_config() -> Metadata:
        """Get current LLM configuration using unified config system"""
        try:
            logger.info("UNIFIED CONFIG SERVICE: Getting LLM configuration")
            return unified_config_manager.get_llm_config()
        except Exception as e:
            logger.error("Error getting LLM config: %s", str(e))
            raise

    @staticmethod
    def get_redis_config() -> Metadata:
        """
        Get current Redis configuration.

        SSOT Migration (Issue #602):
            Host and port now default to SSOT config values.
        """
        try:
            task_transport_config = unified_config_manager.get("task_transport", {})
            redis_config = task_transport_config.get("redis", {})

            # Use SSOT for defaults
            default_host = _ssot.vm.redis if _ssot else REDIS_HOST_IP
            default_port = _ssot.port.redis if _ssot else NetworkConstants.REDIS_PORT

            return {
                "type": task_transport_config.get("type", "local"),
                "host": redis_config.get("host", default_host),
                "port": redis_config.get("port", default_port),
                "channels": redis_config.get("channels", {}),
                "priority": redis_config.get("priority", 10),
            }
        except Exception as e:
            logger.error("Error getting Redis config: %s", str(e))
            raise

    @staticmethod
    def update_llm_config(config_data: Metadata) -> Dict[str, str]:
        """Update LLM configuration using unified config system"""
        try:
            logger.info(
                f"UNIFIED CONFIG SERVICE: Updating LLM configuration with: {config_data}"
            )

            # Handle Ollama model updates through unified config
            if "ollama" in config_data and "model" in config_data["ollama"]:
                model_name = config_data["ollama"]["model"]
                logger.info(
                    f"UNIFIED CONFIG SERVICE: Updating Ollama model to: {model_name}"
                )
                unified_config_manager.update_llm_model(model_name)

            # Handle other LLM configuration updates
            if "local" in config_data and "selected_model" in config_data["local"]:
                model_name = config_data["local"]["selected_model"]
                logger.info(
                    f"UNIFIED CONFIG SERVICE: Updating local model to: {model_name}"
                )
                unified_config_manager.update_llm_model(model_name)

            # Handle legacy format updates (Issue #380: use module-level frozenset)
            for key, value in config_data.items():
                if key not in _LLM_PROVIDER_KEYS:
                    unified_config_manager.set_nested(f"llm_config.{key}", value)

            # Save all changes
            unified_config_manager.save_settings()

            # Clear cache to force fresh load on next access
            ConfigService.clear_cache()

            logger.info(
                "UNIFIED CONFIG SERVICE: LLM configuration updated successfully and cache cleared"
            )
            return {
                "status": "success",
                "message": (
                    "LLM configuration updated successfully using unified config system"
                ),
            }
        except Exception as e:
            logger.error("Error updating LLM config: %s", str(e))
            raise

    @staticmethod
    def update_redis_config(config_data: Metadata) -> Dict[str, str]:
        """Update Redis configuration"""
        try:
            # Load current config
            current_config = unified_config_manager.to_dict()

            # Update task transport configuration
            if "task_transport" not in current_config:
                current_config["task_transport"] = {}

            # Update transport type
            if "type" in config_data:
                current_config["task_transport"]["type"] = config_data["type"]

            # Update Redis-specific settings
            if "redis" not in current_config["task_transport"]:
                current_config["task_transport"]["redis"] = {}

            redis_config = current_config["task_transport"]["redis"]

            if "host" in config_data:
                redis_config["host"] = config_data["host"]
            if "port" in config_data:
                redis_config["port"] = int(config_data["port"])
            if "channels" in config_data:
                redis_config["channels"] = config_data["channels"]
            if "priority" in config_data:
                redis_config["priority"] = int(config_data["priority"])

            # Filter out prompts before saving (prompts are managed separately)
            import copy

            filtered_config = copy.deepcopy(current_config)
            if "prompts" in filtered_config:
                logger.info(
                    "Removing prompts section from Redis config save - prompts are managed in prompts/ directory"
                )
                del filtered_config["prompts"]

            # Save updated config to file
            ConfigService._save_config_to_file(filtered_config)

            # Reload the global config manager
            unified_config_manager.reload()

            logger.info("Updated Redis configuration: %s", config_data)
            return {
                "status": "success",
                "message": "Redis configuration updated successfully",
            }
        except Exception as e:
            logger.error("Error updating Redis config: %s", str(e))
            raise

    @staticmethod
    def save_full_config(config_data: Metadata) -> Dict[str, str]:
        """Save complete application configuration to config.yaml and reload"""
        try:
            # Create a copy of the config data to avoid modifying the original
            filtered_config = config_data.copy()

            # Remove prompts section - prompts are managed separately
            # in prompts/ directory
            if "prompts" in filtered_config:
                logger.info(
                    "Removing prompts section from config - "
                    "prompts are managed in prompts/ directory"
                )
                del filtered_config["prompts"]

            # Issue #594: Normalize logging field names from frontend to config format
            if "logging" in filtered_config:
                logging_cfg = filtered_config["logging"]
                normalized_logging = {}
                # Map frontend field names to config.yaml field names
                field_mapping = {"level": "log_level", "file": "log_to_file"}
                passthrough = {"console", "max_file_size", "log_requests", "log_sql", "log_file_path"}
                for key, value in logging_cfg.items():
                    if key == "log_levels":
                        continue  # Drop - generated at runtime
                    elif key in field_mapping:
                        normalized_logging[field_mapping[key]] = value
                    elif key in passthrough or key not in field_mapping:
                        normalized_logging[key] = value
                filtered_config["logging"] = normalized_logging

            # Save filtered configuration to config.yaml
            ConfigService._save_config_to_file(filtered_config)

            # Reload the global config manager to pick up changes
            unified_config_manager.reload()

            # Clear cache to force fresh load on next access
            ConfigService.clear_cache()

            logger.info(
                "Full configuration saved and reloaded successfully (prompts excluded)"
            )
            return {
                "status": "success",
                "message": "Configuration saved and reloaded successfully",
            }
        except Exception as e:
            logger.error("Error saving full config: %s", str(e))
            raise

    @staticmethod
    def get_backend_settings() -> Metadata:
        """Get backend-specific settings from config.yaml"""
        try:
            return unified_config_manager.get("backend", {})
        except Exception as e:
            logger.error("Error loading backend settings: %s", str(e))
            raise

    @staticmethod
    def update_backend_settings(backend_settings: Metadata) -> Dict[str, str]:
        """Update backend-specific settings in config.yaml"""
        try:
            # Load current config
            current_config = unified_config_manager.to_dict()

            # Update backend settings
            current_config["backend"] = backend_settings

            # Filter out prompts before saving (prompts are managed separately)
            import copy

            filtered_config = copy.deepcopy(current_config)
            if "prompts" in filtered_config:
                logger.info(
                    "Removing prompts section from backend settings save - prompts are managed in prompts/ directory"
                )
                del filtered_config["prompts"]

            # Save updated config to file
            ConfigService._save_config_to_file(filtered_config)

            # Reload the global config manager
            unified_config_manager.reload()

            # Clear cache to force fresh load on next access
            ConfigService.clear_cache()

            logger.info("Updated backend settings in config.yaml")
            return {
                "status": "success",
                "message": "Backend settings updated successfully",
            }
        except Exception as e:
            logger.error("Error updating backend settings: %s", str(e))
            raise

    @staticmethod
    def _save_config_to_file(config: Metadata) -> None:
        """Save configuration to config.yaml file (thread-safe with file locking)"""
        # SAFETY NET: Always filter out prompts before saving (prompts are managed separately)
        import copy

        filtered_config = copy.deepcopy(config)
        if "prompts" in filtered_config:
            logger.info(
                "SAFETY NET: Removing prompts section from config save - prompts are managed in prompts/ directory"
            )
            del filtered_config["prompts"]

        # Use the same dynamic path resolution as the config manager
        config_file_path = unified_config_manager.base_config_file
        config_file_path.parent.mkdir(parents=True, exist_ok=True)

        # Issue #481: Use thread lock + file lock for safe concurrent writes
        with ConfigService._config_write_lock:
            with open(config_file_path, "w", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    yaml.dump(filtered_config, f, default_flow_style=False)
                    f.flush()
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
