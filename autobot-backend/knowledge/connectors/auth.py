# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Backward-compatibility re-exports of connector auth objects (Issue #8145, MVA-1664).

The canonical implementations have been moved to autobot_shared.auth.connector_auth
to allow cross-module reuse without circular dependency risk. This module re-exports
them for backward compatibility with existing connector imports.

New code should import directly from autobot_shared.auth:
    from autobot_shared.auth import BearerAuth, ApiKeyAuth, BasicAuth, OAuthRefreshAuth, validate_config_against_schema
"""

from autobot_shared.auth import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    OAuthRefreshAuth,
    validate_config_against_schema,
)

__all__ = [
    "BearerAuth",
    "ApiKeyAuth",
    "BasicAuth",
    "OAuthRefreshAuth",
    "validate_config_against_schema",
]
