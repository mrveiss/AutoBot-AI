# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Common utility functions for AutoBot

This module provides centralized utility functions to consolidate duplicate
functionality across the codebase.
"""

import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)


def _is_path_in_allowed_dir(path_obj: Path, allowed_dirs: list) -> bool:
    """Check if path is within any allowed directory (Issue #315 - extracted)."""
    for allowed_dir in allowed_dirs:
        allowed_path = Path(allowed_dir).resolve()
        try:
            path_obj.relative_to(allowed_path)
            return True
        except ValueError:
            continue
    return False


def _parse_key_value_file(file_obj) -> Dict[str, str]:
    """Parse key=value format config file. (Issue #315 - extracted)"""
    config = {}
    for line in file_obj:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        config[key.strip()] = value.strip()
    return config


def _try_delete_old_file(file_path: Path, current_time: float, max_age_seconds: int) -> bool:
    """Try to delete file if older than max age (Issue #315 - extracted)."""
    if not file_path.is_file():
        return False

    file_age = current_time - file_path.stat().st_mtime
    if file_age <= max_age_seconds:
        return False

    try:
        file_path.unlink()
        return True
    except Exception as e:
        logging.warning(f"Failed to delete {file_path}: {e}")
        return False


class CommonUtils:
    """Common utility functions used across the codebase"""

    @staticmethod
    def load_config(
        config_path: Union[str, Path], default: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Centralized configuration loading utility

        Args:
            config_path: Path to configuration file
            default: Default configuration if file doesn't exist

        Returns:
            Configuration dictionary
        """
        if default is None:
            default = {}

        config_path = Path(config_path)

        if not config_path.exists():
            return default.copy()

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                if config_path.suffix.lower() == ".json":
                    return json.load(f)
                # Parse key=value format (Issue #315 - uses helper)
                return _parse_key_value_file(f)
        except Exception as e:
            logging.warning(f"Failed to load config from {config_path}: {e}")
            return default.copy()

    @staticmethod
    def save_config(config: Dict[str, Any], config_path: Union[str, Path]) -> bool:
        """
        Save configuration to file

        Args:
            config: Configuration dictionary to save
            config_path: Path to save configuration

        Returns:
            True if successful, False otherwise
        """
        config_path = Path(config_path)

        try:
            # Ensure parent directory exists
            config_path.parent.mkdir(parents=True, exist_ok=True)

            with open(config_path, "w", encoding="utf-8") as f:
                if config_path.suffix.lower() == ".json":
                    json.dump(config, f, indent=2, ensure_ascii=False)
                else:
                    # Save as key=value format
                    for key, value in config.items():
                        f.write(f"{key}={value}\n")
            return True
        except Exception as e:
            logging.error(f"Failed to save config to {config_path}: {e}")
            return False

    @staticmethod
    def init_logger(
        name: str, level: str = "INFO", format_str: Optional[str] = None
    ) -> logging.Logger:
        """
        Centralized logger initialization

        Args:
            name: Logger name
            level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            format_str: Custom format string

        Returns:
            Configured logger instance
        """
        logger = logging.getLogger(name)

        # Avoid duplicate handlers
        if logger.handlers:
            return logger

        logger.setLevel(getattr(logging, level.upper(), logging.INFO))

        if format_str is None:
            format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(format_str))
        logger.addHandler(handler)

        return logger

    @staticmethod
    def get_database_connection(
        db_path: Union[str, Path], create_if_missing: bool = True
    ) -> Optional[sqlite3.Connection]:
        """
        Get database connection with consistent error handling

        Args:
            db_path: Path to database file
            create_if_missing: Create database if it doesn't exist

        Returns:
            Database connection or None if failed
        """
        db_path = Path(db_path)

        try:
            # Ensure parent directory exists
            if create_if_missing:
                db_path.parent.mkdir(parents=True, exist_ok=True)

            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row  # Enable column access by name
            return conn
        except Exception as e:
            logging.error(f"Failed to connect to database {db_path}: {e}")
            return None

    @staticmethod
    def execute_sql_safely(
        conn: sqlite3.Connection, sql: str, params: Optional[tuple] = None
    ) -> bool:
        """
        Execute SQL with consistent error handling

        Args:
            conn: Database connection
            sql: SQL statement to execute
            params: Optional parameters for SQL statement

        Returns:
            True if successful, False otherwise
        """
        if params is None:
            params = ()

        try:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"SQL execution failed: {e}")
            conn.rollback()
            return False

    @staticmethod
    def ensure_directory(directory_path: Union[str, Path]) -> bool:
        """
        Ensure directory exists, create if necessary

        Args:
            directory_path: Path to directory

        Returns:
            True if directory exists or was created successfully
        """
        directory_path = Path(directory_path)

        try:
            directory_path.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logging.error(f"Failed to create directory {directory_path}: {e}")
            return False

    @staticmethod
    def safe_json_load(
        file_path: Union[str, Path], default: Optional[Any] = None
    ) -> Any:
        """
        Safely load JSON file with error handling

        Args:
            file_path: Path to JSON file
            default: Default value if loading fails

        Returns:
            Loaded data or default value
        """
        if default is None:
            default = {}

        file_path = Path(file_path)

        if not file_path.exists():
            return default

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load JSON from {file_path}: {e}")
            return default

    @staticmethod
    def safe_json_save(data: Any, file_path: Union[str, Path], indent: int = 2) -> bool:
        """
        Safely save data to JSON file

        Args:
            data: Data to save
            file_path: Path to save file
            indent: JSON indentation

        Returns:
            True if successful, False otherwise
        """
        file_path = Path(file_path)

        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            return True
        except Exception as e:
            logging.error(f"Failed to save JSON to {file_path}: {e}")
            return False

    @staticmethod
    def validate_file_path(
        file_path: Union[str, Path], must_exist: bool = False
    ) -> bool:
        """
        Validate file path

        Args:
            file_path: Path to validate
            must_exist: Whether file must exist

        Returns:
            True if valid, False otherwise
        """
        try:
            file_path = Path(file_path)

            if must_exist and not file_path.exists():
                return False

            # Check if parent directory is valid
            return file_path.parent.exists() or file_path.parent == file_path
        except Exception:
            return False

    @staticmethod
    def get_file_size_mb(file_path: Union[str, Path]) -> float:
        """
        Get file size in megabytes

        Args:
            file_path: Path to file

        Returns:
            File size in MB, 0 if file doesn't exist
        """
        try:
            file_path = Path(file_path)
            if file_path.exists():
                return file_path.stat().st_size / (1024 * 1024)
        except Exception as e:
            logger.debug("Could not get file size for %s: %s", file_path, e)
        return 0.0

    @staticmethod
    def cleanup_temp_files(temp_dir: Union[str, Path], max_age_hours: int = 24) -> int:
        """
        Clean up temporary files older than specified age (Issue #315 - refactored).

        Args:
            temp_dir: Directory containing temporary files
            max_age_hours: Maximum age in hours

        Returns:
            Number of files cleaned up
        """
        import time

        temp_dir = Path(temp_dir)
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600

        try:
            return sum(
                1 for file_path in temp_dir.iterdir()
                if _try_delete_old_file(file_path, current_time, max_age_seconds)
            )
        except Exception as e:
            logging.error(f"Failed to cleanup temp files in {temp_dir}: {e}")
            return 0


class DatabaseUtils:
    """Database-specific utility functions"""

    @staticmethod
    def create_table_if_not_exists(
        conn: sqlite3.Connection, table_name: str, schema: str
    ) -> bool:
        """
        Create table if it doesn't exist

        Args:
            conn: Database connection
            table_name: Name of table
            schema: Table schema SQL

        Returns:
            True if successful
        """
        sql = f"CREATE TABLE IF NOT EXISTS {table_name} ({schema})"
        return CommonUtils.execute_sql_safely(conn, sql)

    @staticmethod
    def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        """
        Check if table exists in database

        Args:
            conn: Database connection
            table_name: Name of table to check

        Returns:
            True if table exists
        """
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            )
            return cursor.fetchone() is not None
        except Exception:
            return False

    @staticmethod
    def get_table_row_count(conn: sqlite3.Connection, table_name: str) -> int:
        """
        Get number of rows in table

        Args:
            conn: Database connection
            table_name: Name of table

        Returns:
            Number of rows, 0 if error
        """
        try:
            cursor = conn.cursor()
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            result = cursor.fetchone()
            return result[0] if result else 0
        except Exception:
            return 0


class ConfigUtils:
    """Configuration-specific utility functions"""

    @staticmethod
    def merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge configuration dictionaries (deep merge)

        Args:
            base: Base configuration
            override: Configuration to merge in

        Returns:
            Merged configuration
        """
        result = base.copy()

        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = ConfigUtils.merge_configs(result[key], value)
            else:
                result[key] = value

        return result

    @staticmethod
    def get_nested_value(
        config: Dict[str, Any], key_path: str, default: Any = None
    ) -> Any:
        """
        Get nested configuration value using dot notation

        Args:
            config: Configuration dictionary
            key_path: Dot-separated key path (e.g., 'database.host')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key_path.split(".")
        current = config

        try:
            for key in keys:
                current = current[key]
            return current
        except (KeyError, TypeError):
            return default

    @staticmethod
    def set_nested_value(config: Dict[str, Any], key_path: str, value: Any) -> None:
        """
        Set nested configuration value using dot notation

        Args:
            config: Configuration dictionary
            key_path: Dot-separated key path
            value: Value to set
        """
        keys = key_path.split(".")
        current = config

        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[keys[-1]] = value


class PathUtils:
    """Path-related utility functions"""

    @staticmethod
    def resolve_path(path: str) -> str:
        """
        Resolve relative paths to absolute paths

        Args:
            path: Path to resolve (can be relative or absolute)

        Returns:
            Absolute path string
        """
        if not path:
            return ""

        path_obj = Path(path)

        if not path_obj.is_absolute():
            return str(path_obj.resolve())

        return str(path_obj)

    @staticmethod
    def ensure_path_exists(path: Union[str, Path], is_file: bool = False) -> bool:
        """
        Ensure path exists, creating directories as needed

        Args:
            path: Path to ensure exists
            is_file: Whether path is a file (will create parent directory)

        Returns:
            True if path exists or was created successfully
        """
        path_obj = Path(path)

        try:
            if is_file:
                # Create parent directory for file
                path_obj.parent.mkdir(parents=True, exist_ok=True)
                return True
            else:
                # Create directory
                path_obj.mkdir(parents=True, exist_ok=True)
                return True
        except Exception as e:
            logging.error(f"Failed to ensure path exists {path}: {e}")
            return False

    @staticmethod
    def normalize_path(path: Union[str, Path]) -> str:
        """
        Normalize path by resolving relative components and converting to string

        Args:
            path: Path to normalize

        Returns:
            Normalized path string
        """
        return str(Path(path).resolve())

    @staticmethod
    def get_relative_path(path: Union[str, Path], base: Union[str, Path]) -> str:
        """
        Get relative path from base directory

        Args:
            path: Target path
            base: Base directory

        Returns:
            Relative path string
        """
        try:
            path_obj = Path(path).resolve()
            base_obj = Path(base).resolve()
            return str(path_obj.relative_to(base_obj))
        except ValueError:
            # If path is not relative to base, return absolute path
            return str(Path(path).resolve())

    @staticmethod
    def is_safe_path(
        path: Union[str, Path], allowed_dirs: Optional[list] = None
    ) -> bool:
        """
        Check if path is safe (within allowed directories) (Issue #315 - refactored).

        Args:
            path: Path to check
            allowed_dirs: List of allowed base directories (optional)

        Returns:
            True if path is safe
        """
        try:
            path_obj = Path(path).resolve()

            # Basic safety checks
            if ".." in str(path_obj):
                return False

            if allowed_dirs:
                return _is_path_in_allowed_dir(path_obj, allowed_dirs)

            return True
        except Exception:
            return False
