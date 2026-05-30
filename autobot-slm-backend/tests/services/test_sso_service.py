# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for Redis-backed OAuth2 state in SSOService (MVA-1733)."""

import importlib.util
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Load sso_service.py directly, bypassing conftest stubs ───────────────────
# autobot-slm-backend/conftest.py pre-stubs all user_management.* modules as
# MagicMocks to prevent the api/__init__.py import chain (Issue #3499).
# Because user_management.services is a MagicMock (not a real package), the
# standard `from user_management.services.sso_service import ...` path always
# fails with "not a package".  The fix: load the real .py file directly via
# spec_from_file_location, mirroring the pattern in drift_checker_test.py.
#
# Before exec'ing the module we pre-populate sys.modules for every import that
# sso_service.py contains so that its top-level imports resolve without hitting
# the real SQLAlchemy/DB stack:
#   - user_management.models.sso   (not in conftest list — add it)
#   - user_management.services.base_service  (replace MagicMock with real cls)
#   - autobot_shared.redis_client  (real module, available via pythonpath)

_MODELS_SSO = "user_management.models.sso"
if _MODELS_SSO not in sys.modules:
    sys.modules[_MODELS_SSO] = MagicMock()

# Provide a minimal real BaseService so `class SSOService(BaseService)` compiles
# and SSOService(session=...) is constructable.
_base_mod = types.ModuleType("user_management.services.base_service")


class _BaseService:
    def __init__(self, session):
        self.session = session


_base_mod.BaseService = _BaseService  # type: ignore[attr-defined]
sys.modules["user_management.services.base_service"] = _base_mod

_SSO_PY = Path(__file__).parent.parent.parent / "user_management" / "services" / "sso_service.py"
_spec = importlib.util.spec_from_file_location("_sso_service_under_test", _SSO_PY)
_sso_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_sso_mod)  # type: ignore[union-attr]

SSOService = _sso_mod.SSOService
SSOAuthenticationError = _sso_mod.SSOAuthenticationError
# ─────────────────────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROVIDER_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _make_service() -> SSOService:  # type: ignore[valid-type]
    """Return an SSOService with a mock DB session (state tests need no real DB)."""
    return SSOService(session=MagicMock())


def _mock_redis(stored: dict | None = None) -> tuple[MagicMock, dict]:
    """Return a (redis_mock, store) tuple backed by an optional in-memory dict."""
    store: dict = stored if stored is not None else {}

    async def _set(key, value, ex=None):
        store[key] = value

    async def _getdel(key):
        return store.pop(key, None)

    redis = MagicMock()
    redis.set = AsyncMock(side_effect=_set)
    redis.getdel = AsyncMock(side_effect=_getdel)
    return redis, store


# ---------------------------------------------------------------------------
# _generate_oauth_state
# ---------------------------------------------------------------------------


class TestGenerateOauthState:
    @pytest.mark.asyncio
    async def test_stores_provider_id_in_redis(self):
        redis, store = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            state = await service._generate_oauth_state(_PROVIDER_ID)

        assert state
        assert len(store) == 1
        key = f"sso:state:{state}"
        assert key in store
        assert store[key] == str(_PROVIDER_ID)

    @pytest.mark.asyncio
    async def test_set_called_with_correct_ttl(self):
        redis, _ = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            state = await service._generate_oauth_state(_PROVIDER_ID)

        redis.set.assert_awaited_once_with(f"sso:state:{state}", str(_PROVIDER_ID), ex=600)

    @pytest.mark.asyncio
    async def test_returns_token_even_when_redis_unavailable(self):
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=None):
            state = await service._generate_oauth_state(_PROVIDER_ID)
        assert state  # token still generated; Redis write silently skipped


# ---------------------------------------------------------------------------
# _validate_oauth_state
# ---------------------------------------------------------------------------


class TestValidateOauthState:
    @pytest.mark.asyncio
    async def test_round_trip_returns_provider_id(self):
        redis, store = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            state = await service._generate_oauth_state(_PROVIDER_ID)
            recovered = await service._validate_oauth_state(state)

        assert recovered == _PROVIDER_ID

    @pytest.mark.asyncio
    async def test_second_use_raises(self):
        """GETDEL must make state single-use to prevent replay attacks."""
        redis, store = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            state = await service._generate_oauth_state(_PROVIDER_ID)
            await service._validate_oauth_state(state)  # first use succeeds
            with pytest.raises(SSOAuthenticationError, match="Invalid or expired"):
                await service._validate_oauth_state(state)  # second use raises

    @pytest.mark.asyncio
    async def test_invalid_state_raises(self):
        redis, _ = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            with pytest.raises(SSOAuthenticationError, match="Invalid or expired"):
                await service._validate_oauth_state("nonexistent-state-token")

    @pytest.mark.asyncio
    async def test_redis_unavailable_raises(self):
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=None):
            with pytest.raises(SSOAuthenticationError, match="Redis unavailable"):
                await service._validate_oauth_state("any-state")

    @pytest.mark.asyncio
    async def test_state_removed_after_validation(self):
        """Key must be consumed — no residual entry in Redis after successful validation."""
        redis, store = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            state = await service._generate_oauth_state(_PROVIDER_ID)
            await service._validate_oauth_state(state)

        assert f"sso:state:{state}" not in store
