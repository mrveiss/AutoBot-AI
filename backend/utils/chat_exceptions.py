# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat Exceptions - Centralized exception classes for chat modules.

This module provides shared exception classes used across chat-related
API modules. Extracted to eliminate code duplication (Issue #292).
"""

import logging
from typing import Any, Dict, Optional, Tuple, Callable

logger = logging.getLogger(__name__)


class AutoBotError(Exception):
    """Base exception class for AutoBot errors."""
    pass


class InternalError(AutoBotError):
    """Internal server error with optional details."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(message)


class ResourceNotFoundError(AutoBotError):
    """Resource not found error."""
    pass


class ValidationError(AutoBotError):
    """Validation error."""
    pass


def get_error_code(error_type: str) -> str:
    """Get standardized error code for error type."""
    error_codes = {
        "INTERNAL_ERROR": "INTERNAL_ERROR",
        "VALIDATION_ERROR": "VALIDATION_ERROR",
        "NOT_FOUND": "NOT_FOUND",
    }
    return error_codes.get(error_type, "UNKNOWN_ERROR")


def get_exceptions_lazy() -> Tuple[
    type, type, type, type, Callable[[str], str]
]:
    """
    Lazy load exception classes to avoid import errors.

    This function is maintained for backward compatibility with code that
    expects the tuple pattern. New code should import the classes directly.

    Returns:
        Tuple of (AutoBotError, InternalError, ResourceNotFoundError,
                  ValidationError, get_error_code)
    """
    return (
        AutoBotError,
        InternalError,
        ResourceNotFoundError,
        ValidationError,
        get_error_code,
    )


def log_exception(error: Exception, context: str = "chat") -> None:
    """Simple exception logger replacement."""
    logger.error(f"[{context}] Exception: {str(error)}")
