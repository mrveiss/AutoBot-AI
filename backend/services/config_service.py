"""
Centralized configuration service for backend API.
Eliminates duplication across settings.py, llm.py, and redis.py
"""

import logging
from typing import Any, Dict

import yaml

from src.config import (
    BACKEND_HOST_IP,
    BACKEND_PORT,
    HTTP_PROTOCOL,
    REDIS_HOST_IP,
    global_config_manager,
)

logger = logging.getLogger(__name__)


class ConfigService:
    """Centralized configuration management service"""

    _cached_config = None
    _cache_timestamp = None
    CACHE_DURATION = 30  # Cache for 30 seconds

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
    def get_full_config() -> Dict[str, Any]:
        """Get complete application configuration"""
        import time

        # Return cached config if still valid
        if not ConfigService._should_refresh_cache():
            logger.debug("Returning cached configuration")
            return ConfigService._cached_config

        logger.debug("Refreshing configuration cache")

        try:
            # Get the complete config once to avoid repeated calls
            full_config = global_config_manager.to_dict()
            llm_config = global_config_manager.get_llm_config()

            # Helper function to get nested values with default
            def get_nested(path: str, default=None):
                keys = path.split(".")
                value = full_config
                for key in keys:
                    if isinstance(value, dict) and key in value:
                        value = value[key]
                    else:
                        return default
                return value

            # Build comprehensive config structure matching frontend expectations
            # Note: Prompts section is excluded as it's managed separately
            config_data = {
                "message_display": {
                    "show_thoughts": global_config_manager.get_nested(
                        "message_display.show_thoughts", True
                    ),
                    "show_json": global_config_manager.get_nested(
                        "message_display.show_json", False
                    ),
                    "show_utility": global_config_manager.get_nested(
                        "message_display.show_utility", False
                    ),
                    "show_planning": global_config_manager.get_nested(
                        "message_display.show_planning", True
                    ),
                    "show_debug": global_config_manager.get_nested(
                        "message_display.show_debug", False
                    ),
                },
                "chat": {
                    "auto_scroll": global_config_manager.get_nested(
                        "chat.auto_scroll", True
                    ),
                    "max_messages": global_config_manager.get_nested(
                        "chat.max_messages", 100
                    ),
                    "message_retention_days": global_config_manager.get_nested(
                        "chat.message_retention_days", 30
                    ),
                },
                "backend": {
                    "api_endpoint": global_config_manager.get_nested(
                        "backend.api_endpoint",
                        f"{HTTP_PROTOCOL}://{BACKEND_HOST_IP}:{BACKEND_PORT}",
                    ),
                    "server_host": global_config_manager.get_nested(
                        "backend.server_host", "0.0.0.0"
                    ),
                    "server_port": global_config_manager.get_nested(
                        "backend.server_port", BACKEND_PORT
                    ),
                    "chat_data_dir": global_config_manager.get_nested(
                        "backend.chat_data_dir", "data/chats"
                    ),
                    "chat_history_file": global_config_manager.get_nested(
                        "backend.chat_history_file", "data/chat_history.json"
                    ),
                    "knowledge_base_db": global_config_manager.get_nested(
                        "backend.knowledge_base_db", "data/knowledge_base.db"
                    ),
                    "reliability_stats_file": global_config_manager.get_nested(
                        "backend.reliability_stats_file", "data/reliability_stats.json"
                    ),
                    "audit_log_file": global_config_manager.get_nested(
                        "backend.audit_log_file", "data/audit.log"
                    ),
                    "cors_origins": global_config_manager.get_nested(
                        "backend.cors_origins", []
                    ),
                    "timeout": global_config_manager.get_nested("backend.timeout", 60),
                    "max_retries": global_config_manager.get_nested(
                        "backend.max_retries", 3
                    ),
                    "streaming": global_config_manager.get_nested(
                        "backend.streaming", False
                    ),
                    # Use unified LLM configuration
                    "llm": global_config_manager.get_llm_config().get("unified", {}),
                },
                "ui": {
                    "theme": global_config_manager.get_nested("ui.theme", "light"),
                    "font_size": global_config_manager.get_nested(
                        "ui.font_size", "medium"
                    ),
                    "language": global_config_manager.get_nested("ui.language", "en"),
                    "animations": global_config_manager.get_nested(
                        "ui.animations", True
                    ),
                    "developer_mode": global_config_manager.get_nested(
                        "ui.developer_mode", False
                    ),
                },
                "security": {
                    "enable_encryption": global_config_manager.get_nested(
                        "security.enable_encryption", False
                    ),
                    "session_timeout_minutes": global_config_manager.get_nested(
                        "security.session_timeout_minutes", 30
                    ),
                },
                "logging": {
                    "log_level": global_config_manager.get_nested(
                        "logging.log_level", "info"
                    ),
                    "log_to_file": global_config_manager.get_nested(
                        "logging.log_to_file", True
                    ),
                    "log_file_path": global_config_manager.get_nested(
                        "logging.log_file_path", "logs/autobot.log"
                    ),
                },
                "knowledge_base": {
                    "enabled": global_config_manager.get_nested(
                        "knowledge_base.enabled", True
                    ),
                    "update_frequency_days": global_config_manager.get_nested(
                        "knowledge_base.update_frequency_days", 7
                    ),
                },
                "voice_interface": {
                    "enabled": global_config_manager.get_nested(
                        "voice_interface.enabled", False
                    ),
                    "voice": global_config_manager.get_nested(
                        "voice_interface.voice", "default"
                    ),
                    "speech_rate": global_config_manager.get_nested(
                        "voice_interface.speech_rate", 1.0
                    ),
                },
                "memory": {
                    "long_term": {
                        "enabled": global_config_manager.get_nested(
                            "memory.long_term.enabled", True
                        ),
                        "retention_days": global_config_manager.get_nested(
                            "memory.long_term.retention_days", 30
                        ),
                    },
                    "short_term": {
                        "enabled": global_config_manager.get_nested(
                            "memory.short_term.enabled", True
                        ),
                        "duration_minutes": global_config_manager.get_nested(
                            "memory.short_term.duration_minutes", 30
                        ),
                    },
                    "vector_storage": {
                        "enabled": global_config_manager.get_nested(
                            "memory.vector_storage.enabled", True
                        ),
                        "update_frequency_days": global_config_manager.get_nested(
                            "memory.vector_storage.update_frequency_days", 7
                        ),
                    },
                    "chromadb": {
                        "enabled": global_config_manager.get_nested(
                            "memory.chromadb.enabled", True
                        ),
                        "path": global_config_manager.get_nested(
                            "memory.chromadb.path", "data/chromadb"
                        ),
                        "collection_name": global_config_manager.get_nested(
                            "memory.chromadb.collection_name", "autobot_memory"
                        ),
                    },
                    "redis": {
                        "enabled": global_config_manager.get_nested(
                            "memory.redis.enabled", False
                        ),
                        "host": global_config_manager.get_nested(
                            "memory.redis.host", REDIS_HOST_IP
                        ),
                        "port": global_config_manager.get_nested(
                            "memory.redis.port", 6379
                        ),
                    },
                },
                "developer": {
                    "enabled": global_config_manager.get_nested(
                        "developer.enabled", False
                    ),
                    "enhanced_errors": global_config_manager.get_nested(
                        "developer.enhanced_errors", True
                    ),
                    "endpoint_suggestions": global_config_manager.get_nested(
                        "developer.endpoint_suggestions", True
                    ),
                    "debug_logging": global_config_manager.get_nested(
                        "developer.debug_logging", False
                    ),
                },
            }

            # Cache the configuration
            ConfigService._cached_config = config_data
            ConfigService._cache_timestamp = time.time()
            logger.debug(
                f"Configuration cached for {ConfigService.CACHE_DURATION} seconds"
            )

            return config_data
        except Exception as e:
            logger.error(f"Error getting full config: {str(e)}")
            # Return cached config if available, even if refresh failed
            if ConfigService._cached_config is not None:
                logger.warning("Returning cached config due to refresh failure")
                return ConfigService._cached_config
            raise

    @staticmethod
    def clear_cache():
        """Clear the configuration cache to force refresh on next access"""
        ConfigService._cached_config = None
        ConfigService._cache_timestamp = None
        logger.debug("Configuration cache cleared")

    @staticmethod
    def get_llm_config() -> Dict[str, Any]:
        """Get current LLM configuration using unified config system"""
        try:
            logger.info("UNIFIED CONFIG SERVICE: Getting LLM configuration")
            return global_config_manager.get_llm_config()
        except Exception as e:
            logger.error(f"Error getting LLM config: {str(e)}")
            raise

    @staticmethod
    def get_redis_config() -> Dict[str, Any]:
        """Get current Redis configuration"""
        try:
            task_transport_config = global_config_manager.get("task_transport", {})
            redis_config = task_transport_config.get("redis", {})

            return {
                "type": task_transport_config.get("type", "local"),
                "host": redis_config.get("host", REDIS_HOST_IP),
                "port": redis_config.get("port", 6379),
                "channels": redis_config.get("channels", {}),
                "priority": redis_config.get("priority", 10),
            }
        except Exception as e:
            logger.error(f"Error getting Redis config: {str(e)}")
            raise

    @staticmethod
    def update_llm_config(config_data: Dict[str, Any]) -> Dict[str, str]:
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
                global_config_manager.update_llm_model(model_name)

            # Handle other LLM configuration updates
            if "local" in config_data and "selected_model" in config_data["local"]:
                model_name = config_data["local"]["selected_model"]
                logger.info(
                    f"UNIFIED CONFIG SERVICE: Updating local model to: {model_name}"
                )
                global_config_manager.update_llm_model(model_name)

            # Handle legacy format updates
            for key, value in config_data.items():
                if key not in ["ollama", "local", "cloud"]:
                    global_config_manager.set_nested(f"llm_config.{key}", value)

            # Save all changes
            global_config_manager.save_settings()

            logger.info(
                "UNIFIED CONFIG SERVICE: LLM configuration updated successfully"
            )
            return {
                "status": "success",
                "message": "LLM configuration updated successfully using unified config system",
            }
        except Exception as e:
            logger.error(f"Error updating LLM config: {str(e)}")
            raise

    @staticmethod
    def update_redis_config(config_data: Dict[str, Any]) -> Dict[str, str]:
        """Update Redis configuration"""
        try:
            # Load current config
            current_config = global_config_manager.to_dict()

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
            global_config_manager.reload()

            logger.info(f"Updated Redis configuration: {config_data}")
            return {
                "status": "success",
                "message": "Redis configuration updated successfully",
            }
        except Exception as e:
            logger.error(f"Error updating Redis config: {str(e)}")
            raise

    @staticmethod
    def save_full_config(config_data: Dict[str, Any]) -> Dict[str, str]:
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

            # Save filtered configuration to config.yaml
            ConfigService._save_config_to_file(filtered_config)

            # Reload the global config manager to pick up changes
            global_config_manager.reload()

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
            logger.error(f"Error saving full config: {str(e)}")
            raise

    @staticmethod
    def get_backend_settings() -> Dict[str, Any]:
        """Get backend-specific settings from config.yaml"""
        try:
            return global_config_manager.get("backend", {})
        except Exception as e:
            logger.error(f"Error loading backend settings: {str(e)}")
            raise

    @staticmethod
    def update_backend_settings(backend_settings: Dict[str, Any]) -> Dict[str, str]:
        """Update backend-specific settings in config.yaml"""
        try:
            # Load current config
            current_config = global_config_manager.to_dict()

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
            global_config_manager.reload()

            # Clear cache to force fresh load on next access
            ConfigService.clear_cache()

            logger.info("Updated backend settings in config.yaml")
            return {
                "status": "success",
                "message": "Backend settings updated successfully",
            }
        except Exception as e:
            logger.error(f"Error updating backend settings: {str(e)}")
            raise

    @staticmethod
    def _save_config_to_file(config: Dict[str, Any]) -> None:
        """Save configuration to config.yaml file"""
        # SAFETY NET: Always filter out prompts before saving (prompts are managed separately)
        import copy

        filtered_config = copy.deepcopy(config)
        if "prompts" in filtered_config:
            logger.info(
                "SAFETY NET: Removing prompts section from config save - prompts are managed in prompts/ directory"
            )
            del filtered_config["prompts"]

        # Use the same dynamic path resolution as the config manager
        config_file_path = global_config_manager.base_config_file
        config_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file_path, "w") as f:
            yaml.dump(filtered_config, f, default_flow_style=False)
