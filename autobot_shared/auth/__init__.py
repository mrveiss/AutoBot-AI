# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Shared authentication utilities for AutoBot (#3840).

Provides the JWT encode/decode core and bcrypt password helpers used by
both autobot-backend and autobot-slm-backend to eliminate duplication.

Usage:
    from autobot_shared.auth import decode_jwt, encode_jwt, hash_password, verify_password
"""

from autobot_shared.auth.jwt_core import (
    JWTDecodeError,
    JWTExpiredError,
    decode_jwt,
    encode_jwt,
    hash_password,
    verify_password,
)

__all__ = [
    "decode_jwt",
    "encode_jwt",
    "hash_password",
    "verify_password",
    "JWTDecodeError",
    "JWTExpiredError",
]
