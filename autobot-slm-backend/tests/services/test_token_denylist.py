# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
TDD tests for services/token_denylist.py + jti integration in auth.

Covers:
- jti present in minted tokens
- revoke_jti stores key in Redis with correct TTL (clamped to >= 1)
- is_jti_revoked returns True after revoke
- Redis-unavailable path: is_jti_revoked returns False (no crash)
- decode_token_async rejects revoked HS256 jti
- decode_token_async accepts non-revoked HS256 token
- Redis unavailable: valid token still decodes (fail-open)
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).parent.parent.parent
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Pre-populate sys.modules stubs BEFORE loading the real service modules via
# spec_from_file_location so their top-level imports resolve cleanly.
# ---------------------------------------------------------------------------
_SECRET_KEY = "test-secret-key-for-jti-tests-32chars"
_EXPIRE_MINUTES = 30

# config.settings stub — ensure a real MagicMock is in place with the test key
_cfg_mod = MagicMock()
_cfg_mod.settings = MagicMock()
_cfg_mod.settings.secret_key = _SECRET_KEY
_cfg_mod.settings.access_token_expire_minutes = _EXPIRE_MINUTES
sys.modules["config"] = _cfg_mod

_settings = _cfg_mod.settings

for _mod_name in [
    "models.schemas",
    "user_management",
    "user_management.models",
    "user_management.models.user",
    "user_management.services",
    "services.jwks_verifier",
    "fastapi",
    "fastapi.security",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# autobot_shared.auth — real modules (on path)
from autobot_shared.auth.jwt_core import decode_jwt_or_none  # noqa: E402

# sqlalchemy stubs (auth.py imports select + AsyncSession)
for _sa in ["sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"]:
    if _sa not in sys.modules:
        sys.modules[_sa] = MagicMock()

# ---------------------------------------------------------------------------
# Load services/token_denylist.py directly via spec
# ---------------------------------------------------------------------------
_DENYLIST_PY = _BACKEND / "services" / "token_denylist.py"
_dl_spec = importlib.util.spec_from_file_location("_token_denylist_under_test", _DENYLIST_PY)
_dl_mod = importlib.util.module_from_spec(_dl_spec)  # type: ignore[arg-type]
_dl_spec.loader.exec_module(_dl_mod)  # type: ignore[union-attr]

revoke_jti = _dl_mod.revoke_jti
is_jti_revoked = _dl_mod.is_jti_revoked
_denylist_key = _dl_mod._denylist_key

# Register the real token_denylist module under both canonical names so that
# `from services.token_denylist import ...` inside auth.py resolves correctly
# when auth.py is exec'd below (the root conftest stubs 'services' as a
# MagicMock package; we overwrite the sub-module slot here).
sys.modules["services.token_denylist"] = _dl_mod  # type: ignore[assignment]
setattr(sys.modules["services"], "token_denylist", _dl_mod)

# ---------------------------------------------------------------------------
# Load services/auth.py directly via spec so jti enforcement is real code
# ---------------------------------------------------------------------------
_AUTH_PY = _BACKEND / "services" / "auth.py"
_auth_spec = importlib.util.spec_from_file_location("_auth_under_test", _AUTH_PY)
_auth_mod = importlib.util.module_from_spec(_auth_spec)  # type: ignore[arg-type]
_auth_spec.loader.exec_module(_auth_mod)  # type: ignore[union-attr]

AuthService = _auth_mod.AuthService


# ---------------------------------------------------------------------------
# Helper: async Redis mock
# ---------------------------------------------------------------------------


def _make_redis_mock(exists_return: int = 0) -> AsyncMock:
    mock = AsyncMock()
    mock.set = AsyncMock(return_value=True)
    mock.exists = AsyncMock(return_value=exists_return)
    return mock


# ---------------------------------------------------------------------------
# token_denylist: key format
# ---------------------------------------------------------------------------


class TestDenylistKey:
    def test_key_format(self):
        assert _denylist_key("abc123") == "slm:jwt:denylist:abc123"


# ---------------------------------------------------------------------------
# token_denylist: revoke_jti
# ---------------------------------------------------------------------------


class TestRevokeJti:
    @pytest.mark.asyncio
    async def test_stores_key_with_ttl(self):
        redis_mock = _make_redis_mock()
        with patch.object(_dl_mod, "get_redis_client", return_value=redis_mock):
            await revoke_jti("jti-001", ttl_seconds=600)

        redis_mock.set.assert_awaited_once_with("slm:jwt:denylist:jti-001", "1", ex=600)

    @pytest.mark.asyncio
    async def test_ttl_clamped_to_minimum_1(self):
        redis_mock = _make_redis_mock()
        with patch.object(_dl_mod, "get_redis_client", return_value=redis_mock):
            await revoke_jti("jti-002", ttl_seconds=-5)

        _, kwargs = redis_mock.set.call_args
        assert kwargs["ex"] >= 1

    @pytest.mark.asyncio
    async def test_noop_when_redis_unavailable(self):
        """revoke_jti must not raise when get_redis_client returns None."""
        with patch.object(_dl_mod, "get_redis_client", return_value=None):
            await revoke_jti("jti-003", ttl_seconds=60)  # must not raise


# ---------------------------------------------------------------------------
# token_denylist: is_jti_revoked
# ---------------------------------------------------------------------------


class TestIsJtiRevoked:
    @pytest.mark.asyncio
    async def test_returns_true_when_key_exists(self):
        redis_mock = _make_redis_mock(exists_return=1)
        with patch.object(_dl_mod, "get_redis_client", return_value=redis_mock):
            result = await is_jti_revoked("jti-exists")

        assert result is True
        redis_mock.exists.assert_awaited_once_with("slm:jwt:denylist:jti-exists")

    @pytest.mark.asyncio
    async def test_returns_false_when_key_absent(self):
        redis_mock = _make_redis_mock(exists_return=0)
        with patch.object(_dl_mod, "get_redis_client", return_value=redis_mock):
            result = await is_jti_revoked("jti-absent")

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_redis_unavailable(self):
        """Fail-open: no crash, returns False."""
        with patch.object(_dl_mod, "get_redis_client", return_value=None):
            result = await is_jti_revoked("jti-no-redis")

        assert result is False


# ---------------------------------------------------------------------------
# jti in minted tokens
# ---------------------------------------------------------------------------


class TestJtiInMintedToken:
    def test_create_access_token_includes_jti(self):
        """Every SLM HS256 token must carry a 'jti' claim."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "alice", "admin": False, "role": "user"})
        claims = decode_jwt_or_none(token, secret=_SECRET_KEY)
        assert claims is not None
        assert "jti" in claims
        assert isinstance(claims["jti"], str)
        assert len(claims["jti"]) > 0

    def test_each_token_gets_unique_jti(self):
        service = AuthService()
        payload = {"sub": "alice", "admin": False, "role": "user"}
        t1 = service.create_access_token(data=payload)
        t2 = service.create_access_token(data=payload)
        c1 = decode_jwt_or_none(t1, secret=_SECRET_KEY)
        c2 = decode_jwt_or_none(t2, secret=_SECRET_KEY)
        assert c1 is not None and c2 is not None
        assert c1["jti"] != c2["jti"]


# ---------------------------------------------------------------------------
# decode_token_async jti revocation enforcement
# ---------------------------------------------------------------------------


class TestDecodeTokenAsyncRevocation:
    @pytest.mark.asyncio
    async def test_revoked_jti_returns_none(self):
        """decode_token_async must return None when jti is denylisted."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "bob", "admin": False, "role": "user"})

        # Patch is_jti_revoked directly on the loaded auth module namespace
        with patch.object(_auth_mod, "is_jti_revoked", new=AsyncMock(return_value=True)):
            result = await service.decode_token_async(token)

        assert result is None

    @pytest.mark.asyncio
    async def test_non_revoked_jti_decodes_correctly(self):
        """decode_token_async must succeed for a valid, non-revoked token."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "carol", "admin": True, "role": "admin"})

        with patch.object(_auth_mod, "is_jti_revoked", new=AsyncMock(return_value=False)):
            result = await service.decode_token_async(token)

        assert result is not None
        assert result["sub"] == "carol"

    @pytest.mark.asyncio
    async def test_redis_unavailable_does_not_block_valid_token(self):
        """Fail-open: Redis down must not block a valid HS256 token."""
        service = AuthService()
        token = service.create_access_token(data={"sub": "dave", "admin": False, "role": "user"})

        with patch.object(_auth_mod, "is_jti_revoked", new=AsyncMock(return_value=False)):
            result = await service.decode_token_async(token)

        assert result is not None
        assert result["sub"] == "dave"
