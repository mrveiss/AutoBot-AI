# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralized path management for backend API.
Ensures all log/data writes use consistent, configurable paths.
"""

import logging
from pathlib import Path

from backend.type_defs.common import Metadata

from src.config import unified_config_manager

logger = logging.getLogger(__name__)


class PathsManager:
    """Centralized path management service"""

    _paths_cache = None
    _cache_timestamp = None
    CACHE_DURATION = 60  # Cache for 60 seconds

    @staticmethod
    def _should_refresh_cache() -> bool:
        """Check if paths cache should be refreshed"""
        import time

        if PathsManager._paths_cache is None:
            return True

        if PathsManager._cache_timestamp is None:
            return True

        return (
            time.time() - PathsManager._cache_timestamp
        ) > PathsManager.CACHE_DURATION

    @staticmethod
    def clear_cache():
        """Force clear the paths cache"""
        PathsManager._paths_cache = None
        PathsManager._cache_timestamp = None
        logger.debug("Paths cache cleared")

    @staticmethod
    def get_paths() -> Metadata:
        """Get all configured paths"""
        import time

        # Return cached paths if still valid
        if not PathsManager._should_refresh_cache():
            logger.debug("Returning cached paths configuration")
            return PathsManager._paths_cache

        logger.debug("Refreshing paths cache")

        try:
            # Get paths configuration from unified config
            paths_config = unified_config_manager.get("paths", {})

            # Cache the paths
            PathsManager._paths_cache = paths_config
            PathsManager._cache_timestamp = time.time()
            logger.debug("Paths cached for %s seconds", PathsManager.CACHE_DURATION)

            return paths_config
        except Exception as e:
            logger.error("Error getting paths config: %s", str(e))
            # Return cached paths if available, even if refresh failed
            if PathsManager._paths_cache is not None:
                logger.warning("Returning cached paths due to refresh failure")
                return PathsManager._paths_cache
            raise

    @staticmethod
    def get_log_path(log_name: str) -> Path:
        """Get path for a specific log file"""
        paths = PathsManager.get_paths()
        logs_config = paths.get("logs", {})

        # Check if specific log path is configured
        if log_name in logs_config:
            return Path(logs_config[log_name])

        # Fall back to logs directory + filename
        logs_dir = logs_config.get("directory", "logs")
        return Path(logs_dir) / f"{log_name}.log"

    @staticmethod
    def get_data_path(data_name: str) -> Path:
        """Get path for a specific data file"""
        paths = PathsManager.get_paths()
        data_config = paths.get("data", {})

        # Check if specific data path is configured
        if data_name in data_config:
            return Path(data_config[data_name])

        # Fall back to data directory + filename
        data_dir = data_config.get("directory", "data")
        return Path(data_dir) / data_name

    @staticmethod
    def get_logs_directory() -> Path:
        """Get the main logs directory"""
        paths = PathsManager.get_paths()
        logs_config = paths.get("logs", {})
        logs_dir = logs_config.get("directory", "logs")
        return Path(logs_dir)

    @staticmethod
    def get_data_directory() -> Path:
        """Get the main data directory"""
        paths = PathsManager.get_paths()
        data_config = paths.get("data", {})
        data_dir = data_config.get("directory", "data")
        return Path(data_dir)

    @staticmethod
    def get_static_directory() -> Path:
        """Get the static files directory"""
        paths = PathsManager.get_paths()
        static_config = paths.get("static", {})
        static_dir = static_config.get("directory", "static")
        return Path(static_dir)

    @staticmethod
    def get_config_directory() -> Path:
        """Get the configuration directory"""
        paths = PathsManager.get_paths()
        config_config = paths.get("config", {})
        config_dir = config_config.get("directory", "config")
        return Path(config_dir)

    @staticmethod
    def ensure_directory_exists(path: Path) -> Path:
        """Ensure a directory exists, creating it if necessary"""
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except Exception as e:
            logger.error("Failed to create directory %s: %s", path, str(e))
            raise

    @staticmethod
    def get_audit_log_path() -> Path:
        """Get audit log path from backend configuration"""
        try:
            # Try to get from backend config first
            backend_config = unified_config_manager.get("backend", {})
            audit_log_file = backend_config.get("audit_log_file")

            if audit_log_file:
                return Path(audit_log_file)

            # Fall back to paths configuration
            return PathsManager.get_log_path("audit")
        except Exception as e:
            logger.error("Error getting audit log path: %s", str(e))
            # Ultimate fallback
            return Path("logs/audit.log")

    @staticmethod
    def get_chat_data_dir() -> Path:
        """Get chat data directory from backend configuration"""
        try:
            # Try to get from backend config first
            backend_config = unified_config_manager.get("backend", {})
            chat_data_dir = backend_config.get("chat_data_dir")

            if chat_data_dir:
                return Path(chat_data_dir)

            # Fall back to paths configuration
            return PathsManager.get_data_path("chats")
        except Exception as e:
            logger.error("Error getting chat data directory: %s", str(e))
            # Ultimate fallback
            return Path("data/chats")

    @staticmethod
    def get_chat_history_file() -> Path:
        """Get chat history file path from backend configuration"""
        try:
            # Try to get from backend config first
            backend_config = unified_config_manager.get("backend", {})
            chat_history_file = backend_config.get("chat_history_file")

            if chat_history_file:
                return Path(chat_history_file)

            # Fall back to paths configuration
            return PathsManager.get_data_path("chat_history.json")
        except Exception as e:
            logger.error("Error getting chat history file path: %s", str(e))
            # Ultimate fallback
            return Path("data/chat_history.json")

    @staticmethod
    def get_knowledge_base_db() -> Path:
        """Get knowledge base database path from backend configuration"""
        try:
            # Try to get from backend config first
            backend_config = unified_config_manager.get("backend", {})
            knowledge_base_db = backend_config.get("knowledge_base_db")

            if knowledge_base_db:
                return Path(knowledge_base_db)

            # Fall back to paths configuration
            return PathsManager.get_data_path("knowledge_base.db")
        except Exception as e:
            logger.error("Error getting knowledge base database path: %s", str(e))
            # Ultimate fallback
            return Path("data/knowledge_base.db")

    @staticmethod
    def get_reliability_stats_file() -> Path:
        """Get reliability stats file path from backend configuration"""
        try:
            # Try to get from backend config first
            backend_config = unified_config_manager.get("backend", {})
            reliability_stats_file = backend_config.get("reliability_stats_file")

            if reliability_stats_file:
                return Path(reliability_stats_file)

            # Fall back to paths configuration
            return PathsManager.get_data_path("reliability_stats.json")
        except Exception as e:
            logger.error("Error getting reliability stats file path: %s", str(e))
            # Ultimate fallback
            return Path("data/reliability_stats.json")

    @staticmethod
    def get_chromadb_path() -> Path:
        """Get ChromaDB path from memory configuration"""
        try:
            # Get from memory.chromadb configuration
            memory_config = unified_config_manager.get("memory", {})
            chromadb_config = memory_config.get("chromadb", {})
            chromadb_path = chromadb_config.get("path")

            if chromadb_path:
                return Path(chromadb_path)

            # Fall back to paths configuration
            return PathsManager.get_data_path("chromadb")
        except Exception as e:
            logger.error("Error getting ChromaDB path: %s", str(e))
            # Ultimate fallback
            return Path("data/chromadb")


# Convenience functions for common paths
def get_log_path(log_name: str) -> Path:
    """Convenience function to get a log path"""
    return PathsManager.get_log_path(log_name)


def get_data_path(data_name: str) -> Path:
    """Convenience function to get a data path"""
    return PathsManager.get_data_path(data_name)


def ensure_log_directory() -> Path:
    """Ensure logs directory exists"""
    logs_dir = PathsManager.get_logs_directory()
    return PathsManager.ensure_directory_exists(logs_dir)


def ensure_data_directory() -> Path:
    """Ensure data directory exists"""
    data_dir = PathsManager.get_data_directory()
    return PathsManager.ensure_directory_exists(data_dir)


def get_rum_log_path() -> Path:
    """Get RUM log path"""
    return PathsManager.get_log_path("rum")


def get_backend_log_path() -> Path:
    """Get backend log path"""
    return PathsManager.get_log_path("backend")


def get_frontend_log_path() -> Path:
    """Get frontend log path"""
    return PathsManager.get_log_path("frontend")


def get_system_log_path() -> Path:
    """Get system log path"""
    return PathsManager.get_log_path("system")


def get_error_log_path() -> Path:
    """Get error log path"""
    return PathsManager.get_log_path("error")


def get_debug_log_path() -> Path:
    """Get debug log path"""
    return PathsManager.get_log_path("debug")
