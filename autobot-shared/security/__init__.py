# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Security utilities for AutoBot (#1721).

Shared path validation, safe error responses, and input sanitization
used across all backend services to resolve CodeQL alerts.
"""

from autobot_shared.security.input_sanitizer import (
    escape_regex,
    sanitize_ldap_filter,
    sanitize_shell_arg,
    validate_url,
)
from autobot_shared.security.path_validator import validate_path, validate_relative_path
from autobot_shared.security.safe_response import safe_error_response

__all__ = [
    "validate_path",
    "validate_relative_path",
    "safe_error_response",
    "sanitize_shell_arg",
    "sanitize_ldap_filter",
    "escape_regex",
    "validate_url",
]
