# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Centralized path management for backend API.
Ensures all log/data writes use consistent, configurable paths.
"""

from pathlib import Path

from autobot_shared.logging_manager import get_logger
from autobot_shared.security.path_validator import require_path_string
from autobot_shared.ssot_config import config as ssot_config
from config import unified_config_manager
from type_defs.common import Metadata

logger = get_logger(__name__)


def _resolve_directory(configured: object | None, canonical: Path, context: str) -> Path:
    """Resolve a configured directory spec to an ABSOLUTE path (#14113).

    Every accessor below used to end in ``Path("data")`` / ``Path("logs")`` —
    a *relative* literal, resolved by the OS against whatever working
    directory the process happened to be launched with. That never raised, so
    the divergence stayed invisible: `ssot_config` answered `/var/lib/autobot`
    for the data directory while this resolver answered `data`, and under the
    deployed unit (``WorkingDirectory=/opt/autobot/autobot-user-backend``) the
    files landed somewhere no operator setting ``AUTOBOT_DATA_DIR`` would look.

    The `paths:` key these accessors read has never existed in any
    ``config.yaml`` this repository's ``ConfigManager`` loads, so *every* call
    took the fallback. The fallback is therefore the real behaviour, and it is
    what changes here: an unconfigured directory now resolves through the SSOT
    (`AUTOBOT_DATA_DIR`/`AUTOBOT_LOG_DIR` relative to `AUTOBOT_BASE_DIR`), and
    a configured *relative* value resolves against the SSOT base rather than
    against CWD. Both answers are absolute, so neither depends on how the
    process was started.
    """
    if configured is None:
        return canonical
    value = require_path_string(configured, context=context)
    candidate = Path(value)
    return candidate if candidate.is_absolute() else ssot_config.path.resolve(value)


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

        return (time.time() - PathsManager._cache_timestamp) > PathsManager.CACHE_DURATION

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
        """Get path for a specific log file.

        Issue #14217: a config value that resolves to a non-string (a
        malformed setting, or an unconfigured mock in tests) is rejected
        loudly here rather than handed to ``Path()``, which never raises
        and would silently turn it into a real, creatable directory tree.
        """
        paths = PathsManager.get_paths()
        logs_config = paths.get("logs", {})

        # Check if specific log path is configured
        if log_name in logs_config:
            return _resolve_directory(logs_config[log_name], ssot_config.path.logs_path, f"paths.logs.{log_name}")

        # Fall back to logs directory + filename (#14113: absolute, never CWD-relative)
        return PathsManager.get_logs_directory() / f"{log_name}.log"

    @staticmethod
    def get_data_path(data_name: str) -> Path:
        """Get path for a specific data file.

        Issue #14217: same boundary check as :meth:`get_log_path` — reject
        a non-string config value instead of normalising it into a path.
        """
        paths = PathsManager.get_paths()
        data_config = paths.get("data", {})

        # Check if specific data path is configured
        if data_name in data_config:
            return _resolve_directory(data_config[data_name], ssot_config.path.data_path, f"paths.data.{data_name}")

        # Fall back to data directory + filename (#14113: absolute, never CWD-relative)
        return PathsManager.get_data_directory() / data_name

    @staticmethod
    def get_logs_directory() -> Path:
        """Get the main logs directory"""
        paths = PathsManager.get_paths()
        logs_config = paths.get("logs", {})
        return _resolve_directory(logs_config.get("directory"), ssot_config.path.logs_path, "paths.logs.directory")

    @staticmethod
    def get_data_directory() -> Path:
        """Get the main data directory"""
        paths = PathsManager.get_paths()
        data_config = paths.get("data", {})
        return _resolve_directory(data_config.get("directory"), ssot_config.path.data_path, "paths.data.directory")

    @staticmethod
    def get_static_directory() -> Path:
        """Get the static files directory"""
        paths = PathsManager.get_paths()
        static_config = paths.get("static", {})
        canonical = ssot_config.path.resolve("static")
        return _resolve_directory(static_config.get("directory"), canonical, "paths.static.directory")

    @staticmethod
    def get_config_directory() -> Path:
        """Get the configuration directory"""
        paths = PathsManager.get_paths()
        config_config = paths.get("config", {})
        canonical = ssot_config.path.resolve("config")
        return _resolve_directory(config_config.get("directory"), canonical, "paths.config.directory")

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
                return Path(require_path_string(audit_log_file, context="backend.audit_log_file"))

            # Fall back to paths configuration
            return PathsManager.get_log_path("audit")
        except Exception as e:
            logger.error("Error getting audit log path: %s", str(e))
            # #14113: absolute, not CWD-relative. This branch fires when config
            # lookup itself failed, which is exactly when a silently CWD-relative
            # audit log is least acceptable.
            return ssot_config.path.logs_path / "audit.log"

    @staticmethod
    def get_chat_data_dir() -> Path:
        """Get chat data directory from backend configuration"""
        try:
            # Try to get from backend config first
            backend_config = unified_config_manager.get("backend", {})
            chat_data_dir = backend_config.get("chat_data_dir")

            if chat_data_dir:
                return Path(require_path_string(chat_data_dir, context="backend.chat_data_dir"))

            # Fall back to paths configuration
            return PathsManager.get_data_path("chats")
        except Exception as e:
            logger.error("Error getting chat data directory: %s", str(e))
            # #14113: absolute, not CWD-relative.
            return ssot_config.path.data_path / "chats"

    @staticmethod
    def get_chat_history_file() -> Path:
        """Get chat history file path from backend configuration"""
        try:
            # Try to get from backend config first
            backend_config = unified_config_manager.get("backend", {})
            chat_history_file = backend_config.get("chat_history_file")

            if chat_history_file:
                return Path(require_path_string(chat_history_file, context="backend.chat_history_file"))

            # Fall back to paths configuration
            return PathsManager.get_data_path("chat_history.json")
        except Exception as e:
            logger.error("Error getting chat history file path: %s", str(e))
            # #14113: absolute, not CWD-relative.
            return ssot_config.path.data_path / "chat_history.json"

    @staticmethod
    def get_knowledge_base_db() -> Path:
        """Get knowledge base database path from backend configuration"""
        try:
            # Try to get from backend config first
            backend_config = unified_config_manager.get("backend", {})
            knowledge_base_db = backend_config.get("knowledge_base_db")

            if knowledge_base_db:
                return Path(require_path_string(knowledge_base_db, context="backend.knowledge_base_db"))

            # Fall back to paths configuration
            return PathsManager.get_data_path("knowledge_base.db")
        except Exception as e:
            logger.error("Error getting knowledge base database path: %s", str(e))
            # #14113: absolute, not CWD-relative.
            return ssot_config.path.data_path / "knowledge_base.db"

    @staticmethod
    def get_reliability_stats_file() -> Path:
        """Get reliability stats file path from backend configuration"""
        try:
            # Try to get from backend config first
            backend_config = unified_config_manager.get("backend", {})
            reliability_stats_file = backend_config.get("reliability_stats_file")

            if reliability_stats_file:
                return Path(require_path_string(reliability_stats_file, context="backend.reliability_stats_file"))

            # Fall back to paths configuration
            return PathsManager.get_data_path("reliability_stats.json")
        except Exception as e:
            logger.error("Error getting reliability stats file path: %s", str(e))
            # #14113: absolute, not CWD-relative.
            return ssot_config.path.data_path / "reliability_stats.json"

    @staticmethod
    def get_chromadb_path() -> Path:
        """Get ChromaDB path from memory configuration"""
        try:
            # Get from memory.chromadb configuration
            memory_config = unified_config_manager.get("memory", {})
            chromadb_config = memory_config.get("chromadb", {})
            chromadb_path = chromadb_config.get("path")

            if chromadb_path:
                return Path(require_path_string(chromadb_path, context="memory.chromadb.path"))

            # Fall back to paths configuration
            return PathsManager.get_data_path("chromadb")
        except Exception as e:
            logger.error("Error getting ChromaDB path: %s", str(e))
            # #14113: absolute, not CWD-relative.
            return ssot_config.path.data_path / "chromadb"


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
