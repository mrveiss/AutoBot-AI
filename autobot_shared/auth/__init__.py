# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared authentication utilities for AutoBot (#3840, #6511).

Provides the JWT encode/decode core, bcrypt password helpers, and the
canonical Permission/Role/ROLE_PERMISSIONS definitions used by both
autobot-backend and autobot-slm-backend. Also provides typed connector auth
dataclasses for credential configuration (Issue #8145).

Usage:
    from autobot_shared.auth import decode_jwt, encode_jwt, hash_password, verify_password
    from autobot_shared.auth import Permission, Role, ROLE_PERMISSIONS
    from autobot_shared.auth import BearerAuth, ApiKeyAuth, BasicAuth, OAuthRefreshAuth, validate_config_against_schema
"""

from autobot_shared.auth.connector_auth import (
    ApiKeyAuth,
    BasicAuth,
    BearerAuth,
    OAuthRefreshAuth,
    validate_config_against_schema,
)
from autobot_shared.auth.jwt_core import (
    JWTDecodeError,
    JWTExpiredError,
    decode_jwt,
    decode_jwt_no_verify_exp,
    decode_jwt_or_none,
    encode_jwt,
    hash_password,
    verify_password,
)
from autobot_shared.auth.permissions import (
    ROLE_PERMISSIONS,
    SYSTEM_PERMISSIONS,
    SYSTEM_ROLES,
    Permission,
    Role,
)

__all__ = [
    "decode_jwt",
    "decode_jwt_no_verify_exp",
    "decode_jwt_or_none",
    "encode_jwt",
    "hash_password",
    "verify_password",
    "JWTDecodeError",
    "JWTExpiredError",
    "Permission",
    "Role",
    "ROLE_PERMISSIONS",
    "SYSTEM_PERMISSIONS",
    "SYSTEM_ROLES",
    "ApiKeyAuth",
    "BasicAuth",
    "BearerAuth",
    "OAuthRefreshAuth",
    "validate_config_against_schema",
]
