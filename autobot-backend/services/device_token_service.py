# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Device Token JWT Service (GH#4463)

Generates and validates scoped JWTs for mobile device authentication.
Device tokens have limited scope (read-only by default) and are used
for push notification registration and offline sync.
"""

import datetime
from datetime import timezone
from typing import Dict

from autobot_shared.auth.jwt_core import decode_jwt_or_none, encode_jwt
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Device JWTs expire after 90 days to match device expiry policy
_DEVICE_JWT_EXPIRY_DAYS = 90


def create_device_jwt(
    device_id: str,
    user_id: str,
    scope: str = "read",
    platform: str = "unknown",
) -> str:
    """Create a scoped JWT for mobile device authentication.

    Args:
        device_id: UUID of the paired device
        user_id: User ID that owns this device
        scope: Token scope (default: "read")
        platform: Device platform (ios/android/pwa)

    Returns:
        Signed JWT token string
    """
    payload = {
        "device_id": str(device_id),
        "user_id": str(user_id),
        "scope": scope,
        "platform": platform,
        "token_type": "device",  # nosec B105 - JWT claim type value, not a credential
        "iat": datetime.datetime.now(tz=timezone.utc).isoformat(),
    }

    # Use the same JWT secret as the main auth system
    jwt_secret = _get_jwt_secret()
    expiry_hours = _DEVICE_JWT_EXPIRY_DAYS * 24

    return encode_jwt(payload, secret=jwt_secret, expiry_hours=expiry_hours)


def verify_device_jwt(token: str) -> Dict | None:
    """Verify and decode a device JWT token.

    Args:
        token: JWT token string

    Returns:
        Decoded payload if valid, None otherwise
    """
    jwt_secret = _get_jwt_secret()
    payload = decode_jwt_or_none(token, jwt_secret)

    if payload is None:
        return None

    # Verify it's a device token
    if payload.get("token_type") != "device":
        logger.warning("Non-device token presented to device auth endpoint")
        return None

    # Verify required fields are present
    required_fields = ["device_id", "user_id", "scope"]
    if not all(field in payload for field in required_fields):
        logger.warning("Device token missing required fields")
        return None

    return payload


def _get_jwt_secret() -> str:
    """Get JWT secret from config (shared with main auth system)."""
    from config.manager import get_config_manager

    config_manager = get_config_manager()
    security_config = config_manager.get("security_config", {})

    # Priority order: AUTOBOT_JWT_SECRET -> SECRET_KEY -> Config file
    secret = config_manager.jwt_secret
    if secret:
        return secret

    secret = config_manager.secret_key
    if secret:
        return secret

    secret = security_config.get("jwt_secret")
    if secret and len(secret) >= 32:
        return secret

    raise ValueError("No JWT secret configured. Set AUTOBOT_JWT_SECRET or SECRET_KEY environment variable.")
