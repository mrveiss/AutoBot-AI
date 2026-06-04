# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for run-scoped short-lived JWT service (#6473).

Integration test coverage:
- mint_run_jwt returns a verifiable token with correct claims
- validate_run_jwt accepts a valid token
- validate_run_jwt raises JWTExpiredError on an expired token (blast radius test)
- revoke_run_jwt + validate_run_jwt raises JWTDecodeError after revocation
- revoke_run_jwt_async confirms write before returning
- validate_run_jwt raises JWTDecodeError when Redis unavailable (fail-closed)
- RUN_JWT_REDIS_FAIL_OPEN=1 allows validation when Redis is down
- SECRET_KEY is NOT accepted as fallback signing secret
- mint_run_jwt raises ValueError on unknown scope
- _ttl() respects RUN_JWT_TTL_SECONDS env override
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.auth.jwt_core import JWTDecodeError, JWTExpiredError, encode_jwt
from services.run_jwt import (
    VALID_SCOPES,
    get_run_jwt_scopes,
    mint_run_jwt,
    refresh_run_jwt,
    revoke_run_jwt,
    revoke_run_jwt_async,
    validate_run_jwt,
)

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
    # Ensure SECRET_KEY fallback is absent for isolation
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("AUTOBOT_JWT_SECRET", raising=False)


@pytest.fixture()
def _no_redis():
    """Stub out Redis returning None — simulates unavailable Redis."""
    with patch("services.run_jwt.get_async_redis_client", new=AsyncMock(return_value=None)):
        yield


@pytest.fixture()
def _no_audit():
    """Suppress audit_record fire-and-forget so tests stay synchronous."""
    with patch("services.run_jwt.audit_record"):
        yield


def _make_store():
    """Return a (store dict, async redis mock) pair backed by that store."""
    store: dict[str, str] = {}

    def _set(k, v, ex=None, nx=False):
        if nx and k in store:
            return False
        store[k] = v
        return True

    async def _client(**_kwargs):
        mock = AsyncMock()
        mock.set = AsyncMock(side_effect=_set)
        mock.exists = AsyncMock(side_effect=lambda k: int(k in store))
        return mock

    return store, _client


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
        claims = decode_jwt(token, _SECRET, audience="autobot:run-validator")
        assert claims["run_id"] == _RUN_ID
        assert claims["task_id"] == _TASK_ID
        assert claims["agent_id"] == _AGENT_ID
        assert claims["tenant_id"] == _TENANT_ID
        assert claims["scope"] == _SCOPE
        assert claims["aud"] == "autobot:run-validator"
        assert "jti" in claims
        assert "exp" in claims

    def test_raises_on_unknown_scope(self, _no_audit):
        with pytest.raises(ValueError, match="Unknown scopes"):
            mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, ["mcp:knowledge", "bad:scope"])

    def test_ttl_env_override(self, monkeypatch, _no_audit):
        monkeypatch.setenv("RUN_JWT_TTL_SECONDS", "60")
        from autobot_shared.auth.jwt_core import decode_jwt

        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        claims = decode_jwt(token, _SECRET, audience="autobot:run-validator")
        remaining = claims["exp"] - time.time()
        assert 55 <= remaining <= 65, f"expected ~60s TTL, got {remaining:.0f}s"

    def test_secret_key_not_accepted_as_fallback(self, monkeypatch, _no_audit):
        """SECRET_KEY must not be accepted as a signing secret for run JWTs."""
        monkeypatch.delenv("RUN_JWT_SECRET")
        monkeypatch.setenv("SECRET_KEY", "some-general-app-secret")
        with pytest.raises(RuntimeError, match="RUN_JWT_SECRET"):
            mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)


# ---------------------------------------------------------------------------
# validate_run_jwt — valid token
# ---------------------------------------------------------------------------


class TestValidateRunJwtValid:
    @pytest.mark.asyncio
    async def test_accepts_valid_token(self, _no_audit, _no_redis):
        # _no_redis returns None → fail-closed raises unless token is valid
        # We need a real-Redis-like mock that says "not denied"
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
            claims = await validate_run_jwt(token)
        assert claims["run_id"] == _RUN_ID
        assert claims["agent_id"] == _AGENT_ID

    @pytest.mark.asyncio
    async def test_raises_when_jti_missing(self, _no_audit):
        """Token without jti claim must be rejected."""
        bad_token = encode_jwt(
            {"aud": "autobot:run-validator", "run_id": _RUN_ID, "agent_id": _AGENT_ID},
            secret=_SECRET,
            expires_delta=timedelta(seconds=300),
        )
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            with pytest.raises(JWTDecodeError, match="missing jti"):
                await validate_run_jwt(bad_token)


# ---------------------------------------------------------------------------
# aud claim enforcement (MVA-155)
# ---------------------------------------------------------------------------


class TestValidateAudClaim:
    @pytest.mark.asyncio
    async def test_rejects_wrong_aud(self, _no_audit):
        """Token with a different aud value must be rejected — cross-validator reuse prevention."""
        bad_token = encode_jwt(
            {
                "jti": str(uuid.uuid4()),
                "aud": "some-other-validator",
                "run_id": _RUN_ID,
                "task_id": _TASK_ID,
                "agent_id": _AGENT_ID,
                "tenant_id": _TENANT_ID,
                "scope": _SCOPE,
            },
            secret=_SECRET,
            expires_delta=timedelta(seconds=300),
        )
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            with pytest.raises(JWTDecodeError):
                await validate_run_jwt(bad_token)

    @pytest.mark.asyncio
    async def test_rejects_missing_aud(self, _no_audit):
        """Token without an aud claim must be rejected."""
        bad_token = encode_jwt(
            {
                "jti": str(uuid.uuid4()),
                "run_id": _RUN_ID,
                "task_id": _TASK_ID,
                "agent_id": _AGENT_ID,
                "tenant_id": _TENANT_ID,
                "scope": _SCOPE,
            },
            secret=_SECRET,
            expires_delta=timedelta(seconds=300),
        )
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            with pytest.raises(JWTDecodeError):
                await validate_run_jwt(bad_token)

    @pytest.mark.asyncio
    async def test_aud_env_override(self, monkeypatch, _no_audit):
        """RUN_JWT_AUDIENCE env var changes the expected audience for both mint and validate."""
        monkeypatch.setenv("RUN_JWT_AUDIENCE", "custom:validator")
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
            claims = await validate_run_jwt(token)
        assert claims["aud"] == "custom:validator"


# ---------------------------------------------------------------------------
# Blast radius test: expired JWT → access denied
# ---------------------------------------------------------------------------


class TestBlastRadiusExpiry:
    @pytest.mark.asyncio
    async def test_expired_jwt_raises(self, _no_audit):
        """Core blast-radius scenario: a leaked token auto-expires.

        We craft a token with a past expiry timestamp to prove that even
        without explicit revocation a leaked credential becomes useless once
        exp passes — regardless of Redis availability.
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
        # Expiry check happens before Redis lookup — no mock needed
        with pytest.raises(JWTExpiredError):
            await validate_run_jwt(expired_token)


# ---------------------------------------------------------------------------
# Redis fail-closed / fail-open policy
# ---------------------------------------------------------------------------


class TestRedisFailPolicy:
    @pytest.mark.asyncio
    async def test_fail_closed_when_redis_unavailable(self, _no_audit, _no_redis):
        """validate_run_jwt must raise JWTDecodeError when Redis is down (default)."""
        store, client = _make_store()  # unused — _no_redis patches to None
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        with pytest.raises(JWTDecodeError, match="Redis unavailable"):
            await validate_run_jwt(token)

    @pytest.mark.asyncio
    async def test_fail_open_when_env_set(self, monkeypatch, _no_audit, _no_redis):
        """RUN_JWT_REDIS_FAIL_OPEN=1 allows validation when Redis is unavailable."""
        monkeypatch.setenv("RUN_JWT_REDIS_FAIL_OPEN", "1")
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        claims = await validate_run_jwt(token)  # must not raise
        assert claims["run_id"] == _RUN_ID


# ---------------------------------------------------------------------------
# revoke_run_jwt → validate_run_jwt raises after revocation
# ---------------------------------------------------------------------------


class TestRevokeRunJwt:
    @pytest.mark.asyncio
    async def test_revoked_jwt_rejected_sync(self, _no_audit):
        """Revoked JTI must be rejected even if the token has not expired yet."""
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        store, client = _make_store()

        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            revoke_run_jwt(token)
            # Allow the fire-and-forget coroutine to complete
            await asyncio.sleep(0.05)
            with pytest.raises(JWTDecodeError, match="revoked"):
                await validate_run_jwt(token)

    @pytest.mark.asyncio
    async def test_revoke_async_no_race(self, _no_audit):
        """revoke_run_jwt_async must write to Redis before returning."""
        token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
        store, client = _make_store()

        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            await revoke_run_jwt_async(token)
            # No sleep needed — async variant awaits the Redis write
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
# refresh_run_jwt
# ---------------------------------------------------------------------------


class TestRefreshRunJwt:
    @pytest.mark.asyncio
    async def test_refresh_returns_new_token(self, _no_audit):
        """Refreshed token must be a different string with the same claims."""
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            original = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
            refreshed = await refresh_run_jwt(original, _RUN_ID)
        assert isinstance(refreshed, str)
        assert refreshed != original
        assert refreshed.count(".") == 2

    @pytest.mark.asyncio
    async def test_refresh_preserves_scope(self, _no_audit):
        """Refreshed token must carry the same scope as the original."""
        from autobot_shared.auth.jwt_core import decode_jwt

        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            original = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
            refreshed = await refresh_run_jwt(original, _RUN_ID)
        claims = decode_jwt(refreshed, _SECRET, audience="autobot:run-validator")
        assert claims["scope"] == _SCOPE
        assert claims["run_id"] == _RUN_ID
        assert claims["agent_id"] == _AGENT_ID

    @pytest.mark.asyncio
    async def test_refresh_revokes_old_token(self, _no_audit):
        """After refresh, the original token must be rejected."""
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            original = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
            await refresh_run_jwt(original, _RUN_ID)
            with pytest.raises(JWTDecodeError, match="revoked"):
                await validate_run_jwt(original)

    @pytest.mark.asyncio
    async def test_refresh_denied_on_expired_token(self, _no_audit):
        """Expired tokens must not be refreshable."""
        expired = encode_jwt(
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
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            with pytest.raises(JWTExpiredError):
                await refresh_run_jwt(expired, _RUN_ID)

    @pytest.mark.asyncio
    async def test_refresh_denied_on_run_id_mismatch(self, _no_audit):
        """Refresh must reject tokens whose run_id does not match the path param."""
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
            with pytest.raises(JWTDecodeError, match="run_id mismatch"):
                await refresh_run_jwt(token, "completely-different-run-id")

    @pytest.mark.asyncio
    async def test_refresh_denied_on_revoked_token(self, _no_audit):
        """Already-revoked tokens must not be refreshable."""
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)
            await revoke_run_jwt_async(token)
            with pytest.raises(JWTDecodeError, match="revoked"):
                await refresh_run_jwt(token, _RUN_ID)

    @pytest.mark.asyncio
    async def test_old_token_survives_mint_failure(self, _no_audit):
        """Regression: MVA-170 — old token must remain valid when minting fails.

        If mint_run_jwt raises (e.g. bad scope or secret misconfiguration),
        refresh_run_jwt must not have revoked the original token yet.  The
        agent must be able to continue using the old token.
        """
        store, client = _make_store()
        with patch("services.run_jwt.get_async_redis_client", side_effect=client):
            token = mint_run_jwt(_RUN_ID, _TASK_ID, _AGENT_ID, _TENANT_ID, _SCOPE)

            with patch("services.run_jwt.mint_run_jwt", side_effect=RuntimeError("mint failure")):
                with pytest.raises(RuntimeError, match="mint failure"):
                    await refresh_run_jwt(token, _RUN_ID)

            # Old token must still be valid — revoke must not have run
            claims = await validate_run_jwt(token)
            assert claims["run_id"] == _RUN_ID


# ---------------------------------------------------------------------------
# VALID_SCOPES completeness check
# ---------------------------------------------------------------------------


class TestValidScopes:
    def test_minimum_required_scopes_present(self):
        required = {"mcp:knowledge", "task:read"}
        assert required.issubset(VALID_SCOPES)


# ---------------------------------------------------------------------------
# get_run_jwt_scopes — scope resolution (MVA-204)
# ---------------------------------------------------------------------------


class TestGetRunJwtScopes:
    def test_coordinator_has_invoke(self):
        scopes = get_run_jwt_scopes("coordinator")
        assert "task:read" in scopes
        assert "task:write" in scopes
        assert "agent:invoke" in scopes

    def test_specialist_has_write_not_invoke(self):
        scopes = get_run_jwt_scopes("specialist")
        assert "task:read" in scopes
        assert "task:write" in scopes
        assert "agent:invoke" not in scopes

    def test_worker_has_write_not_invoke(self):
        scopes = get_run_jwt_scopes("worker")
        assert "task:read" in scopes
        assert "task:write" in scopes
        assert "agent:invoke" not in scopes

    def test_unknown_agent_type_gets_minimum(self):
        scopes = get_run_jwt_scopes("totally_unknown_type")
        assert scopes == ["task:read"]

    def test_all_returned_scopes_are_valid(self):
        for agent_type in ("coordinator", "specialist", "worker", "unknown"):
            for scope in get_run_jwt_scopes(agent_type):
                assert scope in VALID_SCOPES, f"invalid scope {scope!r} for agent_type={agent_type!r}"

    def test_read_only_task_type_strips_write_and_invoke(self):
        scopes = get_run_jwt_scopes("coordinator", task_type="read_only")
        assert "task:write" not in scopes
        assert "agent:invoke" not in scopes
        assert "task:read" in scopes

    def test_read_only_task_type_on_worker_is_idempotent(self):
        with_hint = get_run_jwt_scopes("worker", task_type="read_only")
        assert "task:write" not in with_hint
        assert "task:read" in with_hint
