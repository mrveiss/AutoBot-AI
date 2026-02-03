# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Error Catalog Loader

Provides centralized error message retrieval from config/error_messages.yaml
with caching, validation, and integration with error_boundaries.py
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

import yaml

from src.constants.path_constants import PATH
from src.utils.error_boundaries import ErrorCategory

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for metadata field filtering
_METADATA_FIELDS = frozenset({"version", "last_updated"})


def _parse_error_category(category_str: str, error_code: str) -> ErrorCategory:
    """Parse error category string to enum. (Issue #315 - extracted)"""
    try:
        return ErrorCategory(category_str)
    except ValueError:
        logger.warning(
            f"Invalid category '{category_str}' for {error_code}, "
            f"defaulting to SERVER_ERROR"
        )
        return ErrorCategory.SERVER_ERROR


def _parse_single_error(
    error_code: str, error_data: dict
) -> Optional["ErrorDefinition"]:
    """Parse single error definition from catalog data. (Issue #315 - extracted)"""
    required_keys = ("category", "message", "status_code", "retry")
    if not all(key in error_data for key in required_keys):
        logger.warning("Skipping incomplete error definition: %s", error_code)
        return None

    try:
        category = _parse_error_category(error_data["category"], error_code)
        return ErrorDefinition(
            code=error_code,
            category=category,
            message=error_data["message"],
            status_code=error_data["status_code"],
            retry=error_data["retry"],
            retry_after=error_data.get("retry_after"),
            details=error_data.get("details"),
        )
    except Exception as e:
        logger.warning("Failed to parse error %s: %s", error_code, e, exc_info=True)
        return None


@dataclass
class ErrorDefinition:
    """Structured error definition from catalog"""

    code: str
    category: ErrorCategory
    message: str
    status_code: int
    retry: bool
    retry_after: Optional[int] = None
    details: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses"""
        return {
            "code": self.code,
            "category": self.category.value,
            "message": self.message,
            "status_code": self.status_code,
            "retry": self.retry,
            "retry_after": self.retry_after,
            "details": self.details,
        }


class ErrorCatalog:
    """
    Singleton error catalog loader with caching and validation

    Usage:
        catalog = ErrorCatalog.get_instance()
        error = catalog.get_error("KB_0001")
        if error:
            print(f"{error.message} - Retry: {error.retry}")
    """

    _instance: Optional["ErrorCatalog"] = None
    _initialized: bool = False

    def __init__(self):
        """Initialize error catalog (use get_instance() instead)"""
        self._catalog: Dict[str, ErrorDefinition] = {}
        self._raw_data: Optional[dict] = None
        self._catalog_path: Optional[Path] = None

    @classmethod
    def get_instance(cls) -> "ErrorCatalog":
        """Get singleton instance of error catalog"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load_catalog(self, catalog_path: Optional[Path] = None) -> bool:
        """
        Load error catalog from YAML file

        Args:
            catalog_path: Path to error_messages.yaml (auto-detected if None)

        Returns:
            True if loaded successfully, False otherwise
        """
        if self._initialized and catalog_path is None:
            # Already loaded from default path
            return True

        # Auto-detect catalog path using centralized PathConstants (Issue #380)
        if catalog_path is None:
            catalog_path = PATH.CONFIG_DIR / "error_messages.yaml"

        if not catalog_path.exists():
            logger.error("Error catalog not found: %s", catalog_path)
            return False

        try:
            # Load YAML catalog
            with open(catalog_path, "r", encoding="utf-8") as f:
                self._raw_data = yaml.safe_load(f)

            self._catalog_path = catalog_path
            self._parse_catalog()
            self._initialized = True

            logger.info(
                f"Loaded error catalog: {len(self._catalog)} errors from {catalog_path}"
            )
            return True

        except Exception as e:
            logger.error("Failed to load error catalog: %s", e, exc_info=True)
            return False

    def _parse_catalog(self):
        """Parse raw YAML data into ErrorDefinition objects (Issue #315 - uses helpers)"""
        if not self._raw_data:
            return

        self._catalog.clear()

        # Iterate through component sections (knowledge_base, authentication, etc.)
        for component_name, errors in self._raw_data.items():
            # Skip metadata fields
            if component_name in _METADATA_FIELDS:
                continue
            if not isinstance(errors, dict):
                continue
            # Parse each error code using helper
            for error_code, error_data in errors.items():
                error_def = _parse_single_error(error_code, error_data)
                if error_def:
                    self._catalog[error_code] = error_def

    def get_error(self, error_code: str) -> Optional[ErrorDefinition]:
        """
        Retrieve error definition by code

        Args:
            error_code: Error code (e.g., "KB_0001", "LLM_0002")

        Returns:
            ErrorDefinition if found, None otherwise
        """
        # Lazy load catalog on first access
        if not self._initialized:
            self.load_catalog()

        return self._catalog.get(error_code)

    def get_error_message(self, error_code: str, default: str = "Unknown error") -> str:
        """
        Get error message by code with fallback

        Args:
            error_code: Error code to lookup
            default: Default message if code not found

        Returns:
            Error message string
        """
        error = self.get_error(error_code)
        return error.message if error else default

    def validate_code(self, error_code: str) -> bool:
        """
        Check if error code exists in catalog

        Args:
            error_code: Error code to validate

        Returns:
            True if code exists, False otherwise
        """
        if not self._initialized:
            self.load_catalog()

        return error_code in self._catalog

    def list_codes_by_component(self, component_prefix: str) -> list[str]:
        """
        List all error codes for a component

        Args:
            component_prefix: Component prefix (e.g., "KB", "LLM", "AUTH")

        Returns:
            List of error codes matching prefix
        """
        if not self._initialized:
            self.load_catalog()

        return [
            code
            for code in self._catalog
            if code.startswith(component_prefix + "_")
        ]

    def get_catalog_stats(self) -> dict:
        """
        Get statistics about loaded catalog

        Returns:
            Dictionary with catalog statistics
        """
        if not self._initialized:
            self.load_catalog()

        # Count errors by category
        category_counts: Dict[str, int] = {}
        for error in self._catalog.values():
            cat_name = error.category.value
            category_counts[cat_name] = category_counts.get(cat_name, 0) + 1

        # Count errors by component
        component_counts: Dict[str, int] = {}
        for code in self._catalog:
            component = code.split("_")[0]
            component_counts[component] = component_counts.get(component, 0) + 1

        return {
            "total_errors": len(self._catalog),
            "catalog_path": str(self._catalog_path) if self._catalog_path else None,
            "version": self._raw_data.get("version") if self._raw_data else None,
            "last_updated": (
                self._raw_data.get("last_updated") if self._raw_data else None
            ),
            "by_category": category_counts,
            "by_component": component_counts,
        }

    def reload_catalog(self) -> bool:
        """
        Force reload catalog from disk

        Returns:
            True if reloaded successfully
        """
        self._initialized = False
        return self.load_catalog(self._catalog_path)


# Convenience functions for direct access
def get_error(error_code: str) -> Optional[ErrorDefinition]:
    """
    Get error definition by code (convenience function)

    Args:
        error_code: Error code (e.g., "KB_0001")

    Returns:
        ErrorDefinition if found, None otherwise

    Example:
        error = get_error("KB_0001")
        if error:
            print(f"{error.message} - Status: {error.status_code}")
    """
    catalog = ErrorCatalog.get_instance()
    return catalog.get_error(error_code)


def get_error_message(error_code: str, default: str = "Unknown error") -> str:
    """
    Get error message by code with fallback (convenience function)

    Args:
        error_code: Error code to lookup
        default: Default message if not found

    Returns:
        Error message string

    Example:
        message = get_error_message("LLM_0001", "LLM service unavailable")
    """
    catalog = ErrorCatalog.get_instance()
    return catalog.get_error_message(error_code, default)


def validate_error_code(error_code: str) -> bool:
    """
    Validate error code exists in catalog (convenience function)

    Args:
        error_code: Error code to validate

    Returns:
        True if code exists

    Example:
        if validate_error_code("AUTH_0001"):
            print("Valid error code")
    """
    catalog = ErrorCatalog.get_instance()
    return catalog.validate_code(error_code)


# Pre-load catalog on module import
_catalog_instance = ErrorCatalog.get_instance()
_catalog_instance.load_catalog()
