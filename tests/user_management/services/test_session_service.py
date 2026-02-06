# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Session Service Tests

Tests for session management and JWT token invalidation.
Issue #635.
"""

import pytest

from src.user_management.services.session_service import SessionService


@pytest.mark.asyncio
async def test_hash_token_creates_sha256():
    """Token hashing produces consistent SHA256 hashes."""
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

    hash1 = SessionService.hash_token(token)
    hash2 = SessionService.hash_token(token)

    assert hash1 == hash2  # Deterministic
    assert len(hash1) == 64  # SHA256 hex length
    assert hash1.isalnum()  # Hex string
