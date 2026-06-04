# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Backward-compatibility re-exports for typed auth dataclasses (Issue #8962).

All auth classes have been moved to autobot_shared.auth.connector_auth.
Import from there directly; this module is maintained for backward compatibility.
"""

from autobot_shared.auth import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    OAuthRefreshAuth,
    validate_config_against_schema,
)

__all__ = [
    "ApiKeyAuth",
    "BasicAuth",
    "BearerAuth",
    "OAuthRefreshAuth",
    "validate_config_against_schema",
]
