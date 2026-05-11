# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Integration tests for run-scoped JWT lifecycle (SEC-2 #6473).

Tests:
  - mint_run_jwt() creates valid, signed tokens (sync, 5-arg)
  - validate_run_jwt() accepts valid tokens (raises on failure)
  - validate_run_jwt() raises JWTExpiredError on expired tokens
  - revoke_run_jwt() adds JTI to denylist; validate raises after revocation
  - validate_run_jwt() raises JWTDecodeError when Redis unavailable (fail-closed)
"""

import asyncio
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.auth.jwt_core import JWTDecodeError, JWTExpiredError, decode_jwt, encode_jwt
from services.run_jwt import (
    VALID_SCOPES,
    mint_run_jwt,
    revoke_run_jwt,
    revoke_run_jwt_async,
    validate_run_jwt,
)

_SECRET = "integration-test-secret-only-32chars!"
_RUN_ID = str(uuid.uuid4())
_TASK_ID = str(uuid.uuid4())
_AGENT_ID = str(uuid.uuid4())
_TENANT_ID = "tenant-integration"
_SCOPE = ["task:read", "task:write"]


@pytest.fixture(autouse=True)
def _inject_secret(monkeypatch):
    monkeypatch.setenv("RUN_JWT_SECRET", _SECRET)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("AUTOBOT_JWT_SECRET", raising=False)


@pytest.fixture()
def _no_audit():
    with patch("services.run_jwt.audit_record"):
        yield


@pytest.fixture()
def _no_redis():
    with patch("services.run_jwt.get_async_redis_client", new=AsyncMock(return_value=None)):
        yield


def _make_store():
    store: dict[str, str] = {}

    async def _client(**_kwargs):
        mock = AsyncMock()
        mock.set = AsyncMock(side_effect=lambda k, v, ex=None: store.update({k: v}))
        mock.exists = AsyncMock(side_effect=lambda k: int(k in store))
        return mock

    return store, _client


# ---------------------------------------------------------------------------
# mint_run_jwt — sync 5-arg API
# ---------------------------------------------------------------------------


class TestMintRunJwt:
    def test_returns_string(self, _no_audit):
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_claims_present(self, _no_audit):
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        claims = decode_jwt(token, _SECRET)
        assert claims["run_id"] == _RUN_ID
        assert claims["task_id"] == _TASK_ID
        assert claims["agent_id"] == _AGENT_ID
        assert claims["tenant_id"] == _TENANT_ID
        assert claims["scope"] == _SCOPE
        assert "jti" in claims
        assert "exp" in claims

    def test_no_aud_claim(self, _no_audit):
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        claims = decode_jwt(token, _SECRET)
        assert "aud" not in claims

    def test_raises_on_unknown_scope(self, _no_audit):
        with pytest.raises(ValueError, match="Unknown scopes"):
            mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, ["bad:scope"])

    def test_ttl_env_override(self, monkeypatch, _no_audit):
        import time

        monkeypatch.setenv("RUN_JWT_TTL_SECONDS", "60")
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        claims = decode_jwt(token, _SECRET)
        remaining = claims["exp"] - time.time()
        assert 55 <= remaining <= 65, f"expected ~60s TTL, got {remaining:.0f}s"


# ---------------------------------------------------------------------------
# validate_run_jwt — raises on failure (not returns None)
# ---------------------------------------------------------------------------


class TestValidateRunJwtValid:
    @pytest.mark.asyncio
    async def test_accepts_valid_token(self, _no_audit):
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
            claims = await validate_run_jwt(token)
        assert claims["run_id"] == _RUN_ID
        assert claims["agent_id"] == _AGENT_ID

    @pytest.mark.asyncio
    async def test_raises_when_jti_missing(self, _no_audit):
        bad_token = encode_jwt(
            {"run_id": _RUN_ID, "agent_id": _AGENT_ID},
            secret=_SECRET,
            expires_delta=timedelta(seconds=300),
        )
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            with pytest.raises(JWTDecodeError, match="missing jti"):
                await validate_run_jwt(bad_token)


# ---------------------------------------------------------------------------
# Blast radius: expired token raises JWTExpiredError
# ---------------------------------------------------------------------------


class TestBlastRadiusExpiry:
    @pytest.mark.asyncio
    async def test_expired_jwt_raises(self, _no_audit):
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
            expires_delta=timedelta(seconds=-1),
        )
        with pytest.raises(JWTExpiredError):
            await validate_run_jwt(expired_token)


# ---------------------------------------------------------------------------
# Fail-closed / fail-open Redis policy
# ---------------------------------------------------------------------------


class TestRedisFailPolicy:
    @pytest.mark.asyncio
    async def test_fail_closed_when_redis_unavailable(self, _no_audit, _no_redis):
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        with pytest.raises(JWTDecodeError, match="Redis unavailable"):
            await validate_run_jwt(token)

    @pytest.mark.asyncio
    async def test_fail_open_when_env_set(self, monkeypatch, _no_audit, _no_redis):
        monkeypatch.setenv("RUN_JWT_REDIS_FAIL_OPEN", "1")
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        claims = await validate_run_jwt(token)
        assert claims["run_id"] == _RUN_ID


# ---------------------------------------------------------------------------
# Denylist rejection: revoke → validate raises
# ---------------------------------------------------------------------------


class TestRevokeAndDenylist:
    @pytest.mark.asyncio
    async def test_revoked_jwt_rejected_sync(self, _no_audit):
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            revoke_run_jwt(token)
            await asyncio.sleep(0.05)
            with pytest.raises(JWTDecodeError, match="revoked"):
                await validate_run_jwt(token)

    @pytest.mark.asyncio
    async def test_revoke_async_no_race(self, _no_audit):
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            await revoke_run_jwt_async(token)
            with pytest.raises(JWTDecodeError, match="revoked"):
                await validate_run_jwt(token)

    def test_revoke_noop_on_expired_token(self, _no_audit, _no_redis):
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


# ---------------------------------------------------------------------------
# VALID_SCOPES completeness
# ---------------------------------------------------------------------------


class TestValidScopes:
    def test_minimum_required_scopes_present(self):
        required = {"mcp:knowledge", "mcp:filesystem", "task:read", "task:write", "agent:invoke"}
        assert required.issubset(VALID_SCOPES)
