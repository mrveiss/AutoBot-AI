# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Integration test for run-scoped JWT lifecycle (SEC-2 #6473)

Tests:
  - mint_run_jwt() creates valid, signed tokens
  - validate_run_jwt() accepts valid tokens
  - validate_run_jwt() rejects expired tokens
  - revoke_run_jwt_async() adds JTI to denylist
  - validate_run_jwt() rejects denylisted tokens (after revocation, mock Redis)
  - validate_run_jwt() fail-open path when Redis unavailable
  - mint_run_jwt() rejects unknown scopes
  - mint_run_jwt() accepts all VALID_SCOPES
"""

import asyncio
import uuid

import pytest

from services.run_jwt import (
    VALID_SCOPES,
    mint_run_jwt,
    revoke_run_jwt_async,
    validate_run_jwt,
)


@pytest.fixture
def jwt_secret(monkeypatch):
    """Set a stable JWT secret for testing."""
    secret = "test-secret-for-integration-testing-only"
    monkeypatch.setenv("RUN_JWT_SECRET", secret)
    return secret


def test_mint_run_jwt_creates_valid_token(jwt_secret):
    """Verify mint_run_jwt() creates a properly signed token."""
    run_id = str(uuid.uuid4())
    task_id = "task-1"
    agent_id = "agent-1"
    tenant_id = "tenant-1"
    scope = ["task:read"]

    token = mint_run_jwt(run_id, task_id, agent_id, tenant_id, scope)
    assert isinstance(token, str)
    assert len(token) > 0
    # Token format: three parts separated by dots (header.payload.signature)
    assert token.count(".") == 2


@pytest.mark.asyncio
async def test_validate_run_jwt_accepts_valid_token(jwt_secret):
    """Verify validate_run_jwt() decodes and accepts a valid token."""
    run_id = str(uuid.uuid4())
    task_id = "task-1"
    agent_id = "agent-1"
    tenant_id = "tenant-1"
    scope = ["task:read", "task:write"]

    token = mint_run_jwt(run_id, task_id, agent_id, tenant_id, scope)
    claims = await validate_run_jwt(token)
    assert claims is not None
    assert claims["run_id"] == run_id
    assert claims["task_id"] == task_id
    assert claims["agent_id"] == agent_id
    assert claims["tenant_id"] == tenant_id
    assert set(claims["scope"]) == set(scope)
    assert "jti" in claims
    assert "exp" in claims


@pytest.mark.asyncio
async def test_validate_run_jwt_rejects_expired_token(jwt_secret, monkeypatch):
    """Verify validate_run_jwt() rejects expired tokens."""
    monkeypatch.setenv("RUN_JWT_TTL_SECONDS", "1")
    run_id = str(uuid.uuid4())
    task_id = "task-1"
    agent_id = "agent-1"
    tenant_id = "tenant-1"

    token = mint_run_jwt(run_id, task_id, agent_id, tenant_id, ["task:read"])
    await asyncio.sleep(2)

    with pytest.raises(Exception):
        # Token should be expired and raise JWTExpiredError
        await validate_run_jwt(token)


@pytest.mark.asyncio
async def test_denylist_rejection_with_mock_redis(jwt_secret, monkeypatch):
    """Verify validate_run_jwt() raises JWTDecodeError after revocation via Redis denylist."""
    from autobot_shared.auth.jwt_core import JWTDecodeError

    denylist: dict[str, str] = {}

    class FakeRedis:
        async def set(self, key, value, ex=None):
            denylist[key] = value

        async def exists(self, key):
            return 1 if key in denylist else 0

    async def fake_get_redis(*args, **kwargs):
        return FakeRedis()

    monkeypatch.setattr("services.run_jwt.get_async_redis_client", fake_get_redis)

    run_id = str(uuid.uuid4())
    token = mint_run_jwt(run_id, "task-1", "agent-1", "tenant-1", ["task:read"])

    # Pre-condition: token validates before revocation
    claims = await validate_run_jwt(token)
    assert claims["run_id"] == run_id

    # Revoke the token — JTI should land in denylist
    await revoke_run_jwt_async(token, agent_id="agent-1")

    # Validation must now raise JWTDecodeError (denylist hit)
    with pytest.raises(JWTDecodeError):
        await validate_run_jwt(token)


@pytest.mark.asyncio
async def test_revoke_fail_open_no_rejection(jwt_secret, monkeypatch):
    """Verify fail-open mode skips denylist check when Redis is unavailable.

    RUN_JWT_REDIS_FAIL_OPEN=1 means a revoked token still validates when Redis is down —
    fail-open trades revocation guarantee for availability. Tested by simulating Redis
    unavailability (get_async_redis_client returns None).
    """
    monkeypatch.setenv("RUN_JWT_REDIS_FAIL_OPEN", "1")
    # Simulate Redis unavailability so the denylist path is skipped
    monkeypatch.setattr("services.run_jwt.get_async_redis_client", lambda *a, **kw: _return_none())

    run_id = str(uuid.uuid4())
    task_id = "task-1"
    agent_id = "agent-1"
    tenant_id = "tenant-1"

    token = mint_run_jwt(run_id, task_id, agent_id, tenant_id, ["task:read"])

    # Pre-condition: token should be valid before revocation
    claims = await validate_run_jwt(token)
    assert claims is not None

    # Revoke path must not raise even when Redis is unavailable
    await revoke_run_jwt_async(token, agent_id=agent_id)

    # With fail-open + no Redis, the revoked token still validates (no denylist to hit)
    claims_after = await validate_run_jwt(token)
    assert claims_after is not None


async def _return_none():
    return None


def test_mint_run_jwt_rejects_invalid_scope(jwt_secret):
    """Verify mint_run_jwt() raises ValueError for unknown scopes."""
    run_id = str(uuid.uuid4())
    task_id = "task-1"
    agent_id = "agent-1"
    tenant_id = "tenant-1"
    invalid_scope = ["banana:peel"]  # Not in VALID_SCOPES

    with pytest.raises(ValueError):
        mint_run_jwt(run_id, task_id, agent_id, tenant_id, invalid_scope)


def test_mint_run_jwt_with_all_valid_scopes(jwt_secret):
    """Verify mint_run_jwt() accepts all VALID_SCOPES."""
    run_id = str(uuid.uuid4())
    task_id = "task-1"
    agent_id = "agent-1"
    tenant_id = "tenant-1"

    token = mint_run_jwt(run_id, task_id, agent_id, tenant_id, list(VALID_SCOPES))
    assert isinstance(token, str)
    assert len(token) > 0
