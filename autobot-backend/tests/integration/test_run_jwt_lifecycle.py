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
  - refresh_run_jwt() extends access for long-running tasks (SEC-2 Phase 3)
  - refresh_run_jwt() rejects expired JWTs (SEC-2 Phase 3)
  - backward-compat: user JWT still authenticates via auth middleware
"""

import asyncio
import uuid
from datetime import timedelta

import pytest

from autobot_shared.auth.jwt_core import JWTDecodeError, JWTExpiredError, encode_jwt
from services.run_jwt import (
    VALID_SCOPES,
    mint_run_jwt,
    refresh_run_jwt,
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


# ---------------------------------------------------------------------------
# Phase 3: refresh endpoint integration tests
# ---------------------------------------------------------------------------

_LONG_SIGNING_KEY = "a" * 40  # deterministic test key ≥32 chars
_ALT_SIGNING_KEY = "b" * 40  # different key to prove secret isolation


def _make_redis_store():
    """Return a (store dict, async factory) backed by that store."""
    store: dict = {}

    class FakeRedis:
        async def set(self, key, value, ex=None):
            store[key] = value

        async def exists(self, key):
            return 1 if key in store else 0

    async def factory(*args, **kwargs):
        return FakeRedis()

    return store, factory


@pytest.mark.asyncio
async def test_refresh_extends_access_for_long_running_task(jwt_secret, monkeypatch):
    """Integration: refresh grants a fresh JWT that validates after original is revoked.

    Simulates the heartbeat scheduler refreshing a JWT mid-run so the task
    continues to have valid credentials beyond the initial 5-min window.
    """
    store, factory = _make_redis_store()
    monkeypatch.setattr("services.run_jwt.get_async_redis_client", factory)

    run_id = str(uuid.uuid4())
    original = mint_run_jwt(run_id, "task-1", "agent-1", "tenant-1", ["task:read", "task:write"])

    # Refresh returns a new valid token
    refreshed = await refresh_run_jwt(original, run_id)
    assert refreshed != original

    # New token must validate successfully
    claims = await validate_run_jwt(refreshed)
    assert claims["run_id"] == run_id
    assert set(claims["scope"]) == {"task:read", "task:write"}

    # Original token must be revoked after refresh
    with pytest.raises(JWTDecodeError):
        await validate_run_jwt(original)


@pytest.mark.asyncio
async def test_expired_jwt_cannot_be_refreshed(jwt_secret, monkeypatch):
    """Integration: an expired JWT is rejected by refresh, not silently renewed.

    Verifies the blast-radius boundary — once a token has passed its exp
    timestamp there is no way to extend it; a new run JWT must be minted.
    """
    store, factory = _make_redis_store()
    monkeypatch.setattr("services.run_jwt.get_async_redis_client", factory)

    run_id = str(uuid.uuid4())
    expired_token = encode_jwt(
        {
            "jti": str(uuid.uuid4()),
            "run_id": run_id,
            "task_id": "task-1",
            "agent_id": "agent-1",
            "tenant_id": "tenant-1",
            "scope": ["task:read"],
        },
        secret=jwt_secret,
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(JWTExpiredError):
        await refresh_run_jwt(expired_token, run_id)


# ---------------------------------------------------------------------------
# Phase 3: backward-compat — user JWT auth unaffected by run JWT changes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_jwt_auth_unaffected_by_run_jwt_fallback(monkeypatch):
    """Integration: _extract_user_from_run_jwt returns None for a user JWT.

    A user JWT signed with a different key must not validate in the run JWT
    path — proving the two secrets remain isolated.
    """
    from unittest.mock import MagicMock

    from autobot_shared.auth.jwt_core import encode_jwt as _encode_jwt

    monkeypatch.setenv("RUN_JWT_SECRET", _LONG_SIGNING_KEY)
    monkeypatch.delenv("AUTOBOT_JWT_SECRET", raising=False)

    # Mint a user JWT signed with a completely different key
    user_token = _encode_jwt(
        {"username": "alice", "role": "admin"},
        secret=_ALT_SIGNING_KEY,
        expiry_hours=1,
    )

    request = MagicMock()
    request.headers.get = lambda k, d="": f"Bearer {user_token}" if k == "Authorization" else d

    from auth_middleware import AuthenticationMiddleware

    middleware = AuthenticationMiddleware.__new__(AuthenticationMiddleware)
    result = await middleware._extract_user_from_run_jwt(request)
    # A JWT signed with ALT_SIGNING_KEY must not validate against LONG_SIGNING_KEY
    assert result is None


# ---------------------------------------------------------------------------
# Phase 3: path-prefix guard — run JWT blocked on non-allowed paths (SEC-2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_jwt_blocked_on_non_allowed_path(jwt_secret, monkeypatch):
    """Integration: get_current_user raises 403 for run JWT on a non-allowed path.

    A run JWT must not be usable on arbitrary REST endpoints (e.g. /api/llm/chat).
    The path-prefix guard ensures that even a valid, non-revoked run JWT returns
    403 Forbidden when presented outside /api/runs/ and /api/mcp/.
    """
    from unittest.mock import MagicMock, patch

    from fastapi import HTTPException

    store, factory = _make_redis_store()
    monkeypatch.setattr("services.run_jwt.get_async_redis_client", factory)
    # Disable single-user mode so the run JWT fallback path is reached
    monkeypatch.setenv("AUTOBOT_SINGLE_USER_MODE", "false")

    run_id = str(uuid.uuid4())
    token = mint_run_jwt(run_id, "task-1", "agent-1", "tenant-1", ["task:read"])

    request = MagicMock()
    request.headers = MagicMock()
    request.headers.get = lambda k, d="": f"Bearer {token}" if k == "Authorization" else d
    request.url.path = "/api/llm/chat"
    request.cookies = {}
    request.state = MagicMock(spec=[])

    from auth_middleware import AuthenticationMiddleware, get_current_user

    middleware = AuthenticationMiddleware.__new__(AuthenticationMiddleware)

    with (
        patch("auth_middleware.get_auth_middleware", return_value=middleware),
        patch.object(middleware, "get_user_from_request", return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(request)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_run_jwt_allowed_on_refresh_path(jwt_secret, monkeypatch):
    """Integration: get_current_user accepts run JWT on /api/runs/ paths.

    The refresh endpoint lives under /api/runs/{run_id}/jwt/refresh — confirming
    the path-prefix guard allows the token through on this prefix.
    """
    from unittest.mock import MagicMock, patch

    store, factory = _make_redis_store()
    monkeypatch.setattr("services.run_jwt.get_async_redis_client", factory)

    run_id = str(uuid.uuid4())
    token = mint_run_jwt(run_id, "task-1", "agent-1", "tenant-1", ["task:read"])

    request = MagicMock()
    request.headers = MagicMock()
    request.headers.get = lambda k, d="": f"Bearer {token}" if k == "Authorization" else d
    request.url.path = f"/api/runs/{run_id}/jwt/refresh"
    request.cookies = {}
    request.state = MagicMock(spec=[])

    from auth_middleware import AuthenticationMiddleware, get_current_user

    middleware = AuthenticationMiddleware.__new__(AuthenticationMiddleware)

    with (
        patch("auth_middleware.get_auth_middleware", return_value=middleware),
        patch.object(middleware, "get_user_from_request", return_value=None),
    ):
        user = await get_current_user(request)
    assert user["auth_method"] == "run_jwt"
    assert user["run_id"] == run_id
