# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

# sso_service.py imports SSOSecretsManager from sso_secrets; stub it so the
# module loads without the real SQLAlchemy/encryption stack.
_SSO_SECRETS = "user_management.services.sso_secrets"
if _SSO_SECRETS not in sys.modules:
    sys.modules[_SSO_SECRETS] = MagicMock()

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
_pkce_challenge_s256 = _sso_mod._pkce_challenge_s256
# ─────────────────────────────────────────────────────────────────────────────


# ---------------------------------------------------------------------------
# PKCE helper — RFC 7636 S256 challenge derivation (Task 1)
# ---------------------------------------------------------------------------


def test_pkce_challenge_s256_matches_rfc7636():
    """S256 challenge must match the RFC 7636 reference computation."""
    import base64
    import hashlib

    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    assert _pkce_challenge_s256(verifier) == expected


def test_pkce_challenge_is_url_safe_and_unpadded():
    """Challenge must be URL-safe base64 with no padding characters."""
    challenge = _pkce_challenge_s256("a" * 64)
    assert "=" not in challenge and "+" not in challenge and "/" not in challenge


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
        import json

        redis, store = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            state, verifier = await service._generate_oauth_state(_PROVIDER_ID)

        assert state
        assert len(store) == 1
        key = f"sso:state:{state}"
        assert key in store
        stored = json.loads(store[key])
        assert stored == {"provider_id": str(_PROVIDER_ID), "code_verifier": verifier}

    @pytest.mark.asyncio
    async def test_set_called_with_correct_ttl(self):
        import json

        redis, _ = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            state, verifier = await service._generate_oauth_state(_PROVIDER_ID)

        expected_payload = json.dumps({"provider_id": str(_PROVIDER_ID), "code_verifier": verifier})
        redis.set.assert_awaited_once_with(f"sso:state:{state}", expected_payload, ex=600)

    @pytest.mark.asyncio
    async def test_returns_token_even_when_redis_unavailable(self):
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=None):
            state, verifier = await service._generate_oauth_state(_PROVIDER_ID)
        assert state  # token still generated; Redis write silently skipped
        assert verifier  # verifier is still returned


# ---------------------------------------------------------------------------
# _validate_oauth_state
# ---------------------------------------------------------------------------


class TestValidateOauthState:
    @pytest.mark.asyncio
    async def test_round_trip_returns_provider_id(self):
        redis, store = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            state, _ = await service._generate_oauth_state(_PROVIDER_ID)
            recovered_id, recovered_verifier = await service._validate_oauth_state(state)

        assert recovered_id == _PROVIDER_ID
        assert recovered_verifier is not None  # verifier round-trips through JSON

    @pytest.mark.asyncio
    async def test_second_use_raises(self):
        """GETDEL must make state single-use to prevent replay attacks."""
        redis, store = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            state, _ = await service._generate_oauth_state(_PROVIDER_ID)
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
            state, _ = await service._generate_oauth_state(_PROVIDER_ID)
            await service._validate_oauth_state(state)

        assert f"sso:state:{state}" not in store


# ---------------------------------------------------------------------------
# PKCE verifier persisted in OAuth state (Task 2)
# ---------------------------------------------------------------------------


class TestPkceStateStorage:
    @pytest.mark.asyncio
    async def test_generate_state_persists_verifier(self):
        """_generate_oauth_state stores JSON with provider_id + code_verifier."""
        import json

        redis, _ = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            state, verifier = await service._generate_oauth_state(_PROVIDER_ID)

        assert isinstance(state, str) and len(verifier) >= 43
        key, value = redis.set.call_args.args[0], redis.set.call_args.args[1]
        assert key == f"sso:state:{state}"
        stored = json.loads(value)
        assert stored == {"provider_id": str(_PROVIDER_ID), "code_verifier": verifier}

    @pytest.mark.asyncio
    async def test_validate_state_returns_provider_and_verifier(self):
        """_validate_oauth_state returns (provider_id, code_verifier) from JSON."""
        import json

        redis, store = _mock_redis()
        verifier = "v" * 64
        store[f"sso:state:abc"] = json.dumps({"provider_id": str(_PROVIDER_ID), "code_verifier": verifier})
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            got_pid, got_verifier = await service._validate_oauth_state("abc")

        assert got_pid == _PROVIDER_ID and got_verifier == verifier

    @pytest.mark.asyncio
    async def test_validate_state_legacy_plain_uuid(self):
        """Legacy plain-UUID values (pre-PKCE deploys) decode to code_verifier=None."""
        redis, store = _mock_redis()
        store[f"sso:state:abc"] = str(_PROVIDER_ID)
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            got_pid, got_verifier = await service._validate_oauth_state("abc")

        assert got_pid == _PROVIDER_ID and got_verifier is None

    @pytest.mark.asyncio
    async def test_validate_state_rejects_missing(self):
        """Missing state token raises SSOAuthenticationError."""
        redis, _ = _mock_redis()
        service = _make_service()
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            with pytest.raises(SSOAuthenticationError):
                await service._validate_oauth_state("nonexistent")


# ---------------------------------------------------------------------------
# SAML relay state Redis round-trip (GH#9075)
# ---------------------------------------------------------------------------


def _make_saml_provider() -> MagicMock:
    """Return a minimal SSOProvider mock for SAML tests."""
    provider = MagicMock()
    provider.id = _PROVIDER_ID
    provider.config = {
        "entity_id": "https://sp.example.com",
        "idp_metadata_url": "https://idp.example.com/metadata",
    }
    return provider


class TestSamlRelayStateRedisRoundTrip:
    """SAML relay state uses the same Redis key-space as OAuth state.

    _generate_saml_authn_request stores relay_state → provider.id in Redis
    under sso:state:{relay_state} with a 10-minute TTL.  _validate_oauth_state
    consumes it atomically via GETDEL (single-use, replay-safe).
    """

    @pytest.mark.asyncio
    async def test_saml_relay_state_stored_in_redis(self):
        redis, store = _mock_redis()
        service = _make_service()
        provider = _make_saml_provider()

        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.return_value = (
            "req-id",
            {"headers": [("Location", "https://idp.example.com/sso")]},
        )
        with (
            patch.object(_sso_mod, "get_redis_client", return_value=redis),
            patch.object(service, "_build_saml_client", return_value=mock_client),
        ):
            redirect_url, relay_state = await service._generate_saml_authn_request(provider)

        assert relay_state
        assert f"sso:state:{relay_state}" in store
        assert store[f"sso:state:{relay_state}"] == str(_PROVIDER_ID)

    @pytest.mark.asyncio
    async def test_saml_relay_state_stored_with_600s_ttl(self):
        redis, _ = _mock_redis()
        service = _make_service()
        provider = _make_saml_provider()

        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.return_value = (
            "req-id",
            {"headers": [("Location", "https://idp.example.com/sso")]},
        )
        with (
            patch.object(_sso_mod, "get_redis_client", return_value=redis),
            patch.object(service, "_build_saml_client", return_value=mock_client),
        ):
            _, relay_state = await service._generate_saml_authn_request(provider)

        redis.set.assert_awaited_once_with(f"sso:state:{relay_state}", str(_PROVIDER_ID), ex=600)

    @pytest.mark.asyncio
    async def test_saml_relay_state_round_trip_via_validate(self):
        """Relay state stored by initiation is consumable by _validate_oauth_state."""
        redis, store = _mock_redis()
        service = _make_service()
        provider = _make_saml_provider()

        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.return_value = (
            "req-id",
            {"headers": [("Location", "https://idp.example.com/sso")]},
        )
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            with patch.object(service, "_build_saml_client", return_value=mock_client):
                _, relay_state = await service._generate_saml_authn_request(provider)
            recovered_id, recovered_verifier = await service._validate_oauth_state(relay_state)

        # SAML stores plain UUID string (legacy path); verifier is None
        assert recovered_id == _PROVIDER_ID
        assert recovered_verifier is None
        assert f"sso:state:{relay_state}" not in store

    @pytest.mark.asyncio
    async def test_saml_relay_state_single_use(self):
        """Relay state is single-use — second validation attempt must raise."""
        redis, _ = _mock_redis()
        service = _make_service()
        provider = _make_saml_provider()

        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.return_value = (
            "req-id",
            {"headers": [("Location", "https://idp.example.com/sso")]},
        )
        with patch.object(_sso_mod, "get_redis_client", return_value=redis):
            with patch.object(service, "_build_saml_client", return_value=mock_client):
                _, relay_state = await service._generate_saml_authn_request(provider)
            await service._validate_oauth_state(relay_state)
            with pytest.raises(SSOAuthenticationError, match="Invalid or expired"):
                await service._validate_oauth_state(relay_state)

    @pytest.mark.asyncio
    async def test_saml_relay_state_redis_unavailable_silently_skips_store(self):
        """If Redis is down, initiation still returns a relay_state token."""
        service = _make_service()
        provider = _make_saml_provider()

        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.return_value = (
            "req-id",
            {"headers": [("Location", "https://idp.example.com/sso")]},
        )
        with (
            patch.object(_sso_mod, "get_redis_client", return_value=None),
            patch.object(service, "_build_saml_client", return_value=mock_client),
        ):
            redirect_url, relay_state = await service._generate_saml_authn_request(provider)

        assert relay_state
        assert redirect_url == "https://idp.example.com/sso"

    @pytest.mark.asyncio
    async def test_saml_returns_idp_redirect_url(self):
        """_generate_saml_authn_request must return the IdP Location URL."""
        redis, _ = _mock_redis()
        service = _make_service()
        provider = _make_saml_provider()

        expected_url = "https://idp.example.com/sso?SAMLRequest=abc123"
        mock_client = MagicMock()
        mock_client.prepare_for_authenticate.return_value = (
            "req-id",
            {"headers": [("Location", expected_url)]},
        )
        with (
            patch.object(_sso_mod, "get_redis_client", return_value=redis),
            patch.object(service, "_build_saml_client", return_value=mock_client),
        ):
            redirect_url, _ = await service._generate_saml_authn_request(provider)

        assert redirect_url == expected_url
