# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for run-scoped short-lived JWT service (#6473).

Integration test coverage:
- mint_run_jwt returns a verifiable token with correct claims
- validate_run_jwt accepts a valid token
- validate_run_jwt raises JWTExpiredError on an expired token (blast radius test)
- revoke_run_jwt + validate_run_jwt raises JWTDecodeError after revocation
- mint_run_jwt raises ValueError on unknown scope
- _ttl() respects RUN_JWT_TTL_SECONDS env override
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.auth.jwt_core import JWTDecodeError, JWTExpiredError, encode_jwt
from services.run_jwt import VALID_SCOPES, mint_run_jwt, revoke_run_jwt, validate_run_jwt

_SECRET = "test-secret-for-run-jwt-at-least-32-chars-long"
_RUN_ID = str(uuid.uuid4())
_TASK_ID = str(uuid.uuid4())
_AGENT_ID = str(uuid.uuid4())
_TENANT_ID = "tenant-test"
_SCOPE = ["mcp:knowledge", "task:read"]


@pytest.fixture(autouse=True)
def _inject_secret(monkeypatch):
    """Inject a deterministic signing secret so tests are self-contained."""
    monkeypatch.setenv("RUN_JWT_SECRET", _SECRET)


@pytest.fixture()
def _no_redis():
    """Stub out Redis so tests run without a live Redis instance."""
    with patch("services.run_jwt.get_async_redis_client", new=AsyncMock(return_value=None)):
        yield


@pytest.fixture()
def _no_audit():
    """Suppress audit_record fire-and-forget so tests stay synchronous."""
    with patch("services.run_jwt.audit_record"):
        yield


# ---------------------------------------------------------------------------
# mint_run_jwt
# ---------------------------------------------------------------------------


class TestMintRunJwt:
    def test_returns_string(self, _no_audit):
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        assert isinstance(token, str)
        assert token.count(".") == 2  # header.payload.signature

    def test_claims_present(self, _no_audit):
        from autobot_shared.auth.jwt_core import decode_jwt

        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        claims = decode_jwt(token, _SECRET)
        assert claims["run_id"] == _RUN_ID
        assert claims["task_id"] == _TASK_ID
        assert claims["agent_id"] == _AGENT_ID
        assert claims["tenant_id"] == _TENANT_ID
        assert claims["scope"] == _SCOPE
        assert "jti" in claims
        assert "exp" in claims

    def test_raises_on_unknown_scope(self, _no_audit):
        with pytest.raises(ValueError, match="Unknown scopes"):
            mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, ["mcp:knowledge", "bad:scope"])

    def test_ttl_env_override(self, monkeypatch, _no_audit):
        monkeypatch.setenv("RUN_JWT_TTL_SECONDS", "60")
        from autobot_shared.auth.jwt_core import decode_jwt

        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        claims = decode_jwt(token, _SECRET)
        remaining = claims["exp"] - time.time()
        assert 55 <= remaining <= 65, f"expected ~60s TTL, got {remaining:.0f}s"


# ---------------------------------------------------------------------------
# validate_run_jwt — valid token
# ---------------------------------------------------------------------------


class TestValidateRunJwtValid:
    @pytest.mark.asyncio
    async def test_accepts_valid_token(self, _no_audit, _no_redis):
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        claims = await validate_run_jwt(token)
        assert claims["run_id"] == _RUN_ID
        assert claims["agent_id"] == _AGENT_ID

    @pytest.mark.asyncio
    async def test_raises_when_jti_missing(self, _no_audit, _no_redis):
        """Token without jti claim must be rejected."""
        bad_token = encode_jwt(
            {"run_id": _RUN_ID, "agent_id": _AGENT_ID},
            secret=_SECRET,
            expires_delta=timedelta(seconds=300),
        )
        with pytest.raises(JWTDecodeError, match="missing jti"):
            await validate_run_jwt(bad_token)


# ---------------------------------------------------------------------------
# Blast radius test: expired JWT → access denied
# ---------------------------------------------------------------------------


class TestBlastRadiusExpiry:
    @pytest.mark.asyncio
    async def test_expired_jwt_raises(self, _no_audit, _no_redis):
        """Core blast-radius scenario: a leaked token auto-expires.

        We mint a token with 1-second TTL, wait for it to expire, then
        confirm validate_run_jwt raises JWTExpiredError — proving that a
        leaked credential becomes useless without any action from the operator.
        """
        expired_token = encode_jwt(
            {
                "jti": str(uuid.uuid4()),
                "run_id": _RUN_ID,
                "task_id": _TASK_ID,
                "agent_id": _AGENT_ID,
                "tenant_id": _TENANT_ID,
                "scope": _SCOPE,
            },
            secret=_SECRET,
            expires_delta=timedelta(seconds=-1),  # already expired
        )
        with pytest.raises(JWTExpiredError):
            await validate_run_jwt(expired_token)


# ---------------------------------------------------------------------------
# revoke_run_jwt → validate_run_jwt raises after revocation
# ---------------------------------------------------------------------------


class TestRevokeRunJwt:
    @pytest.mark.asyncio
    async def test_revoked_jwt_rejected(self, _no_audit):
        """Revoked JTI must be rejected even if the token has not expired yet."""
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)

        # Redis mock: set stores the key, exists returns True after set
        store: dict[str, str] = {}

        async def _mock_redis_client(**_kwargs):
            mock = AsyncMock()
            mock.set = AsyncMock(side_effect=lambda k, v, ex=None: store.update({k: v}))
            mock.exists = AsyncMock(side_effect=lambda k: int(k in store))
            return mock

        with patch("services.run_jwt.get_async_redis_client", side_effect=_mock_redis_client):
            revoke_run_jwt(token)
            # Allow the fire-and-forget coroutine to complete
            await asyncio.sleep(0.05)
            with pytest.raises(JWTDecodeError, match="revoked"):
                await validate_run_jwt(token)

    def test_revoke_noop_on_expired_token(self, _no_audit, _no_redis):
        """Calling revoke on an already-expired token must not raise."""
        expired = encode_jwt(
            {
                "jti": str(uuid.uuid4()),
                "run_id": _RUN_ID,
                "agent_id": _AGENT_ID,
                "tenant_id": _TENANT_ID,
                "scope": _SCOPE,
            },
            secret=_SECRET,
            expires_delta=timedelta(seconds=-1),
        )
        revoke_run_jwt(expired)  # must not raise

    def test_revoke_noop_on_invalid_token(self, _no_audit, _no_redis):
        """Calling revoke on a garbage token must not raise."""
        revoke_run_jwt("not.a.token")  # must not raise


# ---------------------------------------------------------------------------
# VALID_SCOPES completeness check
# ---------------------------------------------------------------------------


class TestValidScopes:
    def test_minimum_required_scopes_present(self):
        required = {"mcp:knowledge", "task:read"}
        assert required.issubset(VALID_SCOPES)
