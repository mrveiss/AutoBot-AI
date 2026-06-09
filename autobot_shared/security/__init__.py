# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Security utilities for AutoBot (#1721).

Shared path validation, safe error responses, input sanitization, and
SSRF protection used across all backend services.
"""

from autobot_shared.security.input_sanitizer import (
    escape_regex,
    sanitize_ldap_dn,
    sanitize_ldap_filter,
    sanitize_shell_arg,
    validate_url,
)
from autobot_shared.security.path_validator import validate_path, validate_relative_path
from autobot_shared.security.safe_response import safe_error_response
from autobot_shared.security.ssrf_guard import (
    SSRFError,
    fetch_safe_url,
    resolve_safe_ip,
    safe_aiohttp_resolver,
)

__all__ = [
    "validate_path",
    "validate_relative_path",
    "safe_error_response",
    "sanitize_shell_arg",
    "sanitize_ldap_dn",
    "sanitize_ldap_filter",
    "escape_regex",
    "validate_url",
    "SSRFError",
    "resolve_safe_ip",
    "safe_aiohttp_resolver",
    "fetch_safe_url",
]
