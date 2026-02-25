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
from constants.path_constants import PATH

from autobot_shared.error_boundaries import ErrorCategory

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for metadata field filtering
_METADATA_FIELDS = frozenset({"version", "last_updated"})

# Issue #912: Builtin fallback — used when error_messages.yaml is not found on the VM.
# Mirrors infrastructure/shared/config/error_messages.yaml exactly.
_BUILTIN_FALLBACK_ERRORS: dict = {
    # AUTH errors
    "AUTH_0001": {
        "category": "authentication",
        "message": "Invalid or expired session",
        "status_code": 401,
        "retry": False,
        "details": "User session has expired or is invalid",
    },
    "AUTH_0002": {
        "category": "authentication",
        "message": "Authentication required",
        "status_code": 401,
        "retry": False,
        "details": "This endpoint requires authentication",
    },
    "AUTH_0003": {
        "category": "authorization",
        "message": "Insufficient permissions",
        "status_code": 403,
        "retry": False,
        "details": "User does not have required permissions",
    },
    "AUTH_0004": {
        "category": "authentication",
        "message": "Invalid credentials",
        "status_code": 401,
        "retry": False,
        "details": "Username or password is incorrect",
    },
    # API errors
    "API_0001": {
        "category": "validation",
        "message": "Invalid request parameters",
        "status_code": 400,
        "retry": False,
        "details": "Check request body and parameters",
    },
    "API_0002": {
        "category": "not_found",
        "message": "Endpoint not found",
        "status_code": 404,
        "retry": False,
        "details": "The requested API endpoint does not exist",
    },
    "API_0003": {
        "category": "server_error",
        "message": "Internal server error",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "An unexpected error occurred",
    },
    "API_0004": {
        "category": "rate_limit",
        "message": "Rate limit exceeded",
        "status_code": 429,
        "retry": True,
        "retry_after": 60,
        "details": "Too many requests from this client",
    },
    "API_0005": {
        "category": "service_unavailable",
        "message": "Service temporarily unavailable",
        "status_code": 503,
        "retry": True,
        "retry_after": 30,
        "details": "Service is under maintenance or overloaded",
    },
    # KB errors
    "KB_0001": {
        "category": "server_error",
        "message": "Failed to initialize knowledge base",
        "status_code": 500,
        "retry": True,
        "retry_after": 30,
        "details": "Check Redis connection and ChromaDB availability",
    },
    "KB_0002": {
        "category": "not_found",
        "message": "Knowledge base fact not found",
        "status_code": 404,
        "retry": False,
        "details": "The requested fact ID does not exist",
    },
    "KB_0003": {
        "category": "server_error",
        "message": "Failed to add fact to knowledge base",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "Error during fact vectorization or storage",
    },
    "KB_0004": {
        "category": "server_error",
        "message": "Failed to search knowledge base",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "Vector search operation failed",
    },
    "KB_0005": {
        "category": "server_error",
        "message": "Failed to delete fact from knowledge base",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "Could not remove fact from vector store",
    },
    "KB_0006": {
        "category": "validation",
        "message": "Invalid fact content or metadata",
        "status_code": 400,
        "retry": False,
        "details": "Fact content must be non-empty string",
    },
    "KB_0007": {
        "category": "server_error",
        "message": "ChromaDB connection failed",
        "status_code": 500,
        "retry": True,
        "retry_after": 10,
        "details": "Cannot connect to vector database",
    },
    "KB_0008": {
        "category": "server_error",
        "message": "Embedding generation failed",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "Ollama embedding service unavailable",
    },
    # LLM errors
    "LLM_0001": {
        "category": "service_unavailable",
        "message": "LLM service unavailable",
        "status_code": 503,
        "retry": True,
        "retry_after": 10,
        "details": "Ollama service is not responding",
    },
    "LLM_0002": {
        "category": "external_service",
        "message": "LLM request timeout",
        "status_code": 504,
        "retry": True,
        "retry_after": 5,
        "details": "LLM took too long to respond",
    },
    "LLM_0003": {
        "category": "validation",
        "message": "Invalid prompt or parameters",
        "status_code": 400,
        "retry": False,
        "details": "Check prompt format and model parameters",
    },
    "LLM_0004": {
        "category": "rate_limit",
        "message": "LLM rate limit exceeded",
        "status_code": 429,
        "retry": True,
        "retry_after": 60,
        "details": "Too many requests to LLM service",
    },
    "LLM_0005": {
        "category": "server_error",
        "message": "LLM generation failed",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "Error during text generation",
    },
    "LLM_0006": {
        "category": "not_found",
        "message": "LLM model not found",
        "status_code": 404,
        "retry": False,
        "details": "The requested model is not available",
    },
    # CHAT errors
    "CHAT_0001": {
        "category": "server_error",
        "message": "Failed to initialize chat workflow",
        "status_code": 500,
        "retry": True,
        "retry_after": 10,
        "details": "Could not initialize chat session",
    },
    "CHAT_0002": {
        "category": "not_found",
        "message": "Chat session not found",
        "status_code": 404,
        "retry": False,
        "details": "The requested session ID does not exist",
    },
    "CHAT_0003": {
        "category": "server_error",
        "message": "Failed to process chat message",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "Error during message processing",
    },
    "CHAT_0004": {
        "category": "server_error",
        "message": "Failed to load conversation history",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "Could not retrieve conversation from Redis",
    },
    "CHAT_0005": {
        "category": "server_error",
        "message": "Failed to save conversation history",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "Could not persist conversation to Redis",
    },
    "CHAT_0006": {
        "category": "validation",
        "message": "Invalid message format",
        "status_code": 400,
        "retry": False,
        "details": "Message must be non-empty string",
    },
    # DB errors
    "DB_0001": {
        "category": "database",
        "message": "Redis connection failed",
        "status_code": 500,
        "retry": True,
        "retry_after": 10,
        "details": "Cannot connect to Redis server",
    },
    "DB_0002": {
        "category": "database",
        "message": "Database operation timeout",
        "status_code": 504,
        "retry": True,
        "retry_after": 5,
        "details": "Database operation took too long",
    },
    "DB_0003": {
        "category": "database",
        "message": "Database query failed",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "Error executing database query",
    },
    "DB_0004": {
        "category": "conflict",
        "message": "Duplicate key violation",
        "status_code": 409,
        "retry": False,
        "details": "Record with this key already exists",
    },
    # MEM errors
    "MEM_0001": {
        "category": "server_error",
        "message": "Failed to initialize memory graph",
        "status_code": 500,
        "retry": True,
        "retry_after": 10,
        "details": "Could not initialize memory graph connections",
    },
    "MEM_0002": {
        "category": "server_error",
        "message": "Failed to create entity",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "Could not create memory graph entity",
    },
    "MEM_0003": {
        "category": "not_found",
        "message": "Entity not found",
        "status_code": 404,
        "retry": False,
        "details": "The requested entity does not exist",
    },
    "MEM_0004": {
        "category": "server_error",
        "message": "Failed to create relationship",
        "status_code": 500,
        "retry": True,
        "retry_after": 5,
        "details": "Could not create entity relationship",
    },
    "MEM_0005": {
        "category": "validation",
        "message": "Invalid entity type",
        "status_code": 400,
        "retry": False,
        "details": "Entity type must be one of the supported types",
    },
    # SYS errors
    "SYS_0001": {
        "category": "system",
        "message": "System initialization failed",
        "status_code": 500,
        "retry": True,
        "retry_after": 30,
        "details": "Critical system component failed to initialize",
    },
    "SYS_0002": {
        "category": "system",
        "message": "Configuration error",
        "status_code": 500,
        "retry": False,
        "details": "Invalid or missing configuration",
    },
    "SYS_0003": {
        "category": "system",
        "message": "Resource exhausted",
        "status_code": 503,
        "retry": True,
        "retry_after": 60,
        "details": "System resources (memory/CPU) exhausted",
    },
    "SYS_0004": {
        "category": "system",
        "message": "Dependency unavailable",
        "status_code": 503,
        "retry": True,
        "retry_after": 20,
        "details": "Required system dependency is unavailable",
    },
}


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
            logger.info("%s - Retry: %s", error.message, error.retry)
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

    def _resolve_catalog_path(self) -> Optional[Path]:
        """Find error_messages.yaml searching backend static dir then infrastructure.

        Helper for load_catalog (Issue #912).
        """
        # Try backend-bundled static dir first (always present when backend is synced)
        backend_local = PATH.STATIC_DIR / "error_messages.yaml"
        if backend_local.exists():
            return backend_local

        # Fall back to infrastructure path (works on dev machine / full-repo deploys)
        infra_path = PATH.CONFIG_DIR / "error_messages.yaml"
        if infra_path.exists():
            return infra_path

        return None

    def _load_builtin_fallback(self) -> None:
        """Populate catalog from hardcoded fallback when YAML is unavailable.

        Helper for load_catalog (Issue #912).
        """
        self._catalog.clear()
        for error_code, data in _BUILTIN_FALLBACK_ERRORS.items():
            category = _parse_error_category(data["category"], error_code)
            self._catalog[error_code] = ErrorDefinition(
                code=error_code,
                category=category,
                message=data["message"],
                status_code=data["status_code"],
                retry=data["retry"],
                retry_after=data.get("retry_after"),
                details=data.get("details"),
            )
        self._initialized = True
        logger.warning(
            "Error catalog YAML not found; using built-in fallback (%d errors)",
            len(self._catalog),
        )

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

        # Auto-detect catalog path (Issue #912: try multiple locations)
        if catalog_path is None:
            catalog_path = self._resolve_catalog_path()

        if catalog_path is None or not catalog_path.exists():
            # Issue #912: graceful fallback — prevents HTTP 500 when YAML is missing
            self._load_builtin_fallback()
            return True

        try:
            # Load YAML catalog
            with open(catalog_path, "r", encoding="utf-8") as f:
                self._raw_data = yaml.safe_load(f)

            self._catalog_path = catalog_path
            self._parse_catalog()
            self._initialized = True

            logger.info(
                "Loaded error catalog: %d errors from %s",
                len(self._catalog),
                catalog_path,
            )
            return True

        except Exception as e:
            logger.error("Failed to load error catalog: %s", e, exc_info=True)
            self._load_builtin_fallback()
            return True

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
            code for code in self._catalog if code.startswith(component_prefix + "_")
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
            logger.info("%s - Status: %s", error.message, error.status_code)
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
            logger.info("Valid error code")
    """
    catalog = ErrorCatalog.get_instance()
    return catalog.validate_code(error_code)


# Pre-load catalog on module import
_catalog_instance = ErrorCatalog.get_instance()
_catalog_instance.load_catalog()
