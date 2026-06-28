# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for services/rs256_denylist.py — cross-service RS256 jti denylist (#10278).

Covers:
- revoke_rs256_jti writes to correct Redis key with TTL
- TTL is clamped to minimum 1
- Redis unavailable → no crash (fail-open)
- is_rs256_jti_revoked returns True after revoke
- is_rs256_jti_revoked returns False when key absent
- is_rs256_jti_revoked returns False when Redis unavailable (fail-open)
- Key prefix is the shared cross-service namespace
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

for _m in ["sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm"]:
    if _m not in sys.modules:
        sys.modules[_m] = MagicMock()

# ---------------------------------------------------------------------------
# Load module under test
# ---------------------------------------------------------------------------
_DL_PY = _BACKEND / "services" / "rs256_denylist.py"
_spec = importlib.util.spec_from_file_location("_rs256_denylist", _DL_PY)
_dl_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_dl_mod)  # type: ignore[union-attr]

revoke_rs256_jti = _dl_mod.revoke_rs256_jti
is_rs256_jti_revoked = _dl_mod.is_rs256_jti_revoked
RS256_DENYLIST_PREFIX = _dl_mod.RS256_DENYLIST_PREFIX


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock(exists_return: int = 0) -> AsyncMock:
    mock = AsyncMock()
    mock.set = AsyncMock(return_value=True)
    mock.exists = AsyncMock(return_value=exists_return)
    return mock


# ---------------------------------------------------------------------------
# Key namespace
# ---------------------------------------------------------------------------


class TestKeyNamespace:
    def test_prefix_is_shared_cross_service(self):
        """The prefix must be the shared cross-service namespace, not slm-only."""
        assert RS256_DENYLIST_PREFIX == "auth:rs256:jti:denylist:"

    def test_key_uses_prefix(self):
        key = _dl_mod._rs256_denylist_key("test-jti")
        assert key == "auth:rs256:jti:denylist:test-jti"


# ---------------------------------------------------------------------------
# revoke_rs256_jti
# ---------------------------------------------------------------------------


class TestRevokeRS256Jti:
    @pytest.mark.asyncio
    async def test_writes_key_with_ttl(self):
        redis_mock = _make_redis_mock()
        get_client = AsyncMock(return_value=redis_mock)
        with patch.object(_dl_mod, "get_async_redis_client", get_client):
            await revoke_rs256_jti("jti-abc", ttl_seconds=3600)

        redis_mock.set.assert_awaited_once_with("auth:rs256:jti:denylist:jti-abc", "1", ex=3600)

    @pytest.mark.asyncio
    async def test_ttl_clamped_to_minimum_1(self):
        redis_mock = _make_redis_mock()
        get_client = AsyncMock(return_value=redis_mock)
        with patch.object(_dl_mod, "get_async_redis_client", get_client):
            await revoke_rs256_jti("jti-negative", ttl_seconds=-100)

        _, kwargs = redis_mock.set.call_args
        assert kwargs["ex"] >= 1

    @pytest.mark.asyncio
    async def test_noop_when_redis_unavailable(self):
        get_client = AsyncMock(return_value=None)
        with patch.object(_dl_mod, "get_async_redis_client", get_client):
            await revoke_rs256_jti("jti-no-redis", ttl_seconds=60)  # must not raise


# ---------------------------------------------------------------------------
# is_rs256_jti_revoked
# ---------------------------------------------------------------------------


class TestIsRS256JtiRevoked:
    @pytest.mark.asyncio
    async def test_returns_true_when_key_exists(self):
        redis_mock = _make_redis_mock(exists_return=1)
        get_client = AsyncMock(return_value=redis_mock)
        with patch.object(_dl_mod, "get_async_redis_client", get_client):
            result = await is_rs256_jti_revoked("jti-revoked")
        assert result is True
        redis_mock.exists.assert_awaited_once_with("auth:rs256:jti:denylist:jti-revoked")

    @pytest.mark.asyncio
    async def test_returns_false_when_key_absent(self):
        redis_mock = _make_redis_mock(exists_return=0)
        get_client = AsyncMock(return_value=redis_mock)
        with patch.object(_dl_mod, "get_async_redis_client", get_client):
            result = await is_rs256_jti_revoked("jti-not-revoked")
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_redis_unavailable(self):
        """Fail-open: Redis down must not block valid tokens."""
        get_client = AsyncMock(return_value=None)
        with patch.object(_dl_mod, "get_async_redis_client", get_client):
            result = await is_rs256_jti_revoked("jti-redis-down")
        assert result is False


# ---------------------------------------------------------------------------
# Integration: revoke then check
# ---------------------------------------------------------------------------


class TestRevokeAndCheck:
    @pytest.mark.asyncio
    async def test_revoke_then_is_revoked_true(self):
        """Simulate the write→read cycle using a shared mock."""
        store: dict = {}

        async def _set(key, val, ex=None):
            store[key] = val

        async def _exists(key):
            return 1 if key in store else 0

        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock(side_effect=_set)
        redis_mock.exists = AsyncMock(side_effect=_exists)

        get_client = AsyncMock(return_value=redis_mock)
        with patch.object(_dl_mod, "get_async_redis_client", get_client):
            await revoke_rs256_jti("jti-flow", ttl_seconds=600)
            result = await is_rs256_jti_revoked("jti-flow")

        assert result is True
