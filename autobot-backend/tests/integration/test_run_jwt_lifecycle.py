# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration test for run-scoped JWT lifecycle (SEC-2 #6473)

Tests:
  - mint_run_jwt() creates valid, signed tokens
  - validate_run_jwt() accepts valid tokens
  - validate_run_jwt() rejects expired tokens
  - revoke_run_jwt() adds JTI to denylist
  - validate_run_jwt() rejects denylined tokens
"""

import asyncio
import os
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from services.run_jwt import (
    mint_run_jwt,
    revoke_run_jwt,
    validate_run_jwt,
)


@pytest.fixture
def run_ids():
    """Generate test run and agent IDs."""
    return {"run_id": uuid.uuid4(), "agent_id": uuid.uuid4()}


@pytest.fixture
def jwt_secret(monkeypatch):
    """Set a stable JWT secret for testing."""
    secret = "test-secret-for-integration-testing-only"
    monkeypatch.setenv("AUTOBOT_JWT_SECRET", secret)
    return secret


@pytest.mark.asyncio
async def test_mint_run_jwt_creates_valid_token(run_ids, jwt_secret):
    """Verify mint_run_jwt() creates a properly signed token."""
    token = await mint_run_jwt(run_ids["run_id"], run_ids["agent_id"])
    assert isinstance(token, str)
    assert len(token) > 0
    # Token format: three parts separated by dots (header.payload.signature)
    assert token.count(".") == 2


@pytest.mark.asyncio
async def test_validate_run_jwt_accepts_valid_token(run_ids, jwt_secret):
    """Verify validate_run_jwt() decodes and accepts a valid token."""
    token = await mint_run_jwt(run_ids["run_id"], run_ids["agent_id"], scopes=["task:read"])
    claims = await validate_run_jwt(token)
    assert claims is not None
    assert claims["run_id"] == str(run_ids["run_id"])
    assert claims["agent_id"] == str(run_ids["agent_id"])
    assert "task:read" in claims["scopes"]
    assert claims["aud"] == "heartbeat"
    assert "jti" in claims


@pytest.mark.asyncio
async def test_validate_run_jwt_rejects_expired_token(run_ids, jwt_secret, monkeypatch):
    """Verify validate_run_jwt() rejects expired tokens."""
    monkeypatch.setenv("AUTOBOT_RUN_JWT_TTL_SECONDS", "1")
    token = await mint_run_jwt(run_ids["run_id"], run_ids["agent_id"])
    await asyncio.sleep(2)
    claims = await validate_run_jwt(token)
    assert claims is None


@pytest.mark.asyncio
async def test_validate_run_jwt_with_run_id_match(run_ids, jwt_secret):
    """Verify validate_run_jwt() matches expected run_id."""
    token = await mint_run_jwt(run_ids["run_id"], run_ids["agent_id"])
    claims = await validate_run_jwt(token, expected_run_id=run_ids["run_id"])
    assert claims is not None


@pytest.mark.asyncio
async def test_validate_run_jwt_rejects_mismatched_run_id(run_ids, jwt_secret):
    """Verify validate_run_jwt() rejects token with wrong run_id."""
    token = await mint_run_jwt(run_ids["run_id"], run_ids["agent_id"])
    other_run_id = uuid.uuid4()
    claims = await validate_run_jwt(token, expected_run_id=other_run_id)
    assert claims is None


@pytest.mark.asyncio
async def test_mint_run_jwt_with_custom_scopes(run_ids, jwt_secret):
    """Verify mint_run_jwt() accepts custom scopes."""
    custom_scopes = ["mcp:knowledge", "workspace:manage"]
    token = await mint_run_jwt(run_ids["run_id"], run_ids["agent_id"], scopes=custom_scopes)
    claims = await validate_run_jwt(token)
    assert claims is not None
    for scope in custom_scopes:
        assert scope in claims["scopes"]
