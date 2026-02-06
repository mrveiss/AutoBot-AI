# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Centralized Logging Manager for AutoBot
Standardizes logging configuration across all components
"""

import logging
import logging.handlers
import os
import threading
from pathlib import Path
from typing import Optional

from src.config import config_manager

# Module-level logger for logging_manager itself
_logger = logging.getLogger(__name__)

# Issue #380: Module-level tuple for log types
_LOG_TYPES = ("backend", "frontend", "llm", "debug", "audit")


class LoggingManager:
    """
    Centralized logging manager that standardizes logging across all components
    """

    _initialized = False
    _loggers = {}
    _lock = threading.Lock()

    @classmethod
    def get_logger(cls, name: str, log_type: str = "backend") -> logging.Logger:
        """
        Get a configured logger instance (thread-safe)

        Args:
            name: Logger name (usually __name__)
            log_type: Type of log (backend, frontend, llm, debug, audit)

        Returns:
            Configured logger instance
        """
        logger_key = f"{log_type}:{name}"

        # Fast path: check cache without lock
        with cls._lock:
            if logger_key in cls._loggers:
                return cls._loggers[logger_key]

            # Initialize if needed
            if not cls._initialized:
                cls._setup_logging_internal()

        # Create and configure logger under lock
        with cls._lock:
            # Double-check after acquiring lock
            if logger_key in cls._loggers:
                return cls._loggers[logger_key]

            logger = logging.getLogger(name)

            # Don't add handlers if already configured
            if not logger.handlers:
                handler = cls._get_file_handler(log_type)
                if handler:
                    logger.addHandler(handler)

                # Add console handler for development
                if config_manager.get("deployment.mode", "local") == "local":
                    console_handler = logging.StreamHandler()
                    console_handler.setFormatter(cls._get_formatter())
                    logger.addHandler(console_handler)

            # Set log level
            log_level = getattr(
                logging, config_manager.get("logging.level", "INFO").upper()
            )
            logger.setLevel(log_level)

            cls._loggers[logger_key] = logger
            return logger

    @classmethod
    def _setup_logging_internal(cls):
        """Setup basic logging configuration (internal, called under lock)"""
        # Create logs directory if it doesn't exist
        logs_dir_path = os.getenv("AUTOBOT_LOGS_DIR", "logs")
        logs_dir = Path(logs_dir_path)
        logs_dir.mkdir(exist_ok=True)

        # Create backup directory
        backup_dir_name = os.getenv("AUTOBOT_LOGS_BACKUP_DIR", "backup")
        backup_dir = logs_dir / backup_dir_name
        backup_dir.mkdir(exist_ok=True)

        cls._initialized = True

    @classmethod
    def _setup_logging(cls):
        """Setup basic logging configuration (thread-safe public method)"""
        with cls._lock:
            if not cls._initialized:
                cls._setup_logging_internal()

    @classmethod
    def _get_file_handler(cls, log_type: str) -> Optional[logging.Handler]:
        """Get file handler for specific log type"""
        log_file = config_manager.get(f"logging.file_handlers.{log_type}")
        if not log_file:
            # Fallback to default path using environment-configurable logs directory
            logs_dir = os.getenv("AUTOBOT_LOGS_DIR", "logs")
            log_file = f"{logs_dir}/{log_type}.log"

        # Create directory if needed
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Use rotating file handler to prevent large log files
        max_bytes = config_manager.get("logging.rotation.max_bytes", 10485760)  # 10MB
        backup_count = config_manager.get("logging.rotation.backup_count", 5)

        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count
        )
        handler.setFormatter(cls._get_formatter())

        return handler

    @classmethod
    def _get_formatter(cls) -> logging.Formatter:
        """Get log formatter"""
        log_format = config_manager.get(
            "logging.format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        return logging.Formatter(log_format)

    @classmethod
    def setup_component_logging(
        cls, component_name: str, log_type: str = "backend"
    ) -> logging.Logger:
        """
        Setup logging for a specific component

        Args:
            component_name: Name of the component
            log_type: Type of logging (backend, frontend, llm, etc.)

        Returns:
            Configured logger
        """
        return cls.get_logger(component_name, log_type)

    @classmethod
    def rotate_logs(cls, log_type: Optional[str] = None):
        """
        Manually rotate log files

        Args:
            log_type: Specific log type to rotate, or None for all
        """
        # Issue #380: Use module-level constant
        log_types_to_rotate = list(_LOG_TYPES) if not log_type else [log_type]

        for lt in log_types_to_rotate:
            log_file = config_manager.get(f"logging.file_handlers.{lt}")
            if log_file and os.path.exists(log_file):
                # Create backup using environment-configurable paths
                logs_dir = os.getenv("AUTOBOT_LOGS_DIR", "logs")
                backup_dir = os.getenv("AUTOBOT_LOGS_BACKUP_DIR", "backup")
                backup_path = (
                    f"{logs_dir}/{backup_dir}/{lt}_{int(__import__('time').time())}.log"
                )
                try:
                    os.rename(log_file, backup_path)
                    _logger.info("Rotated %s to %s", log_file, backup_path)
                except OSError as e:
                    _logger.error("Failed to rotate %s: %s", log_file, e)


# Convenience functions for common logging patterns
def get_logger(name: str, category: str = "backend") -> logging.Logger:
    """
    Get a logger instance - REUSABLE general-purpose logger function.

    This is the canonical way to get loggers across the codebase.
    Use specific functions below for clarity, or call this directly.

    Args:
        name: Logger name (usually __name__)
        category: Logger category (backend, frontend, llm, debug, audit)

    Returns:
        Configured logger instance

    Examples:
        >>> logger = get_logger(__name__)  # Default: backend
        >>> logger = get_logger(__name__, "llm")  # LLM logger
        >>> logger = get_logger(__name__, "debug")  # Debug logger
    """
    return LoggingManager.get_logger(name, category)


def get_backend_logger(name: str) -> logging.Logger:
    """Get backend logger"""
    return get_logger(name, "backend")


def get_frontend_logger(name: str) -> logging.Logger:
    """Get frontend logger"""
    return get_logger(name, "frontend")


def get_llm_logger(name: str) -> logging.Logger:
    """Get LLM logger"""
    return get_logger(name, "llm")


def get_debug_logger(name: str) -> logging.Logger:
    """Get debug logger"""
    return get_logger(name, "debug")


def get_audit_logger(name: str) -> logging.Logger:
    """Get audit logger"""
    return get_logger(name, "audit")


# Maintain backward compatibility with existing logging setup
def setup_logging():
    """Setup logging - backward compatibility function"""
    LoggingManager._setup_logging()
