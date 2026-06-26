# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for SSO unified-vault client and rotation service (#10153, #10154).

The conftest pre-stubs user_management.services.* so we load our modules the
same way test_sso_service.py does: directly via importlib.util.spec_from_file_location
so real module code executes without the MagicMock collision.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Directory of the autobot-slm-backend package root
_BACKEND = Path(__file__).parent.parent.parent


def _load_module(rel_path: str, mod_name: str):
    """Load a real .py file bypassing sys.modules stubs."""
    spec = importlib.util.spec_from_file_location(mod_name, _BACKEND / rel_path)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    # Inject lightweight stubs for any imports the module needs at load time.
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# Pre-stub aiohttp (not installed in test env) before loading vault client
if "aiohttp" not in sys.modules:
    sys.modules["aiohttp"] = MagicMock()
    sys.modules["aiohttp.ClientTimeout"] = MagicMock()
    sys.modules["aiohttp.ClientSession"] = MagicMock()

# Pre-stub autobot_shared.http_client with the real sign_request signature
_hs_mod = types.ModuleType("autobot_shared.http_client")


def _sign_stub(service_id, service_key, method, path, timestamp):
    return {
        "X-Service-ID": service_id,
        "X-Service-Signature": "fakesig",
        "X-Service-Timestamp": str(timestamp),
    }


_hs_mod.sign_request = _sign_stub  # type: ignore[attr-defined]
sys.modules["autobot_shared.http_client"] = _hs_mod
if "autobot_shared" not in sys.modules:
    sys.modules["autobot_shared"] = types.ModuleType("autobot_shared")

# Pre-stub user_management.models.sso so sso_rotation lazy imports succeed
_sso_model_stub = MagicMock()
sys.modules.setdefault("user_management.models.sso", _sso_model_stub)

# Pre-stub user_management.services.unified_vault_client (lazy-imported in rotation)
# We set real AsyncMock placeholders; individual tests replace them via patch.object.
_uvc_stub = types.ModuleType("user_management.services.unified_vault_client")
_uvc_stub.vault_rewrap_kek = AsyncMock()  # type: ignore[attr-defined]
_uvc_stub.vault_rotate = AsyncMock()  # type: ignore[attr-defined]
_uvc_stub.vault_read = AsyncMock()  # type: ignore[attr-defined]
_uvc_stub.vault_delete = AsyncMock()  # type: ignore[attr-defined]
_uvc_stub.vault_list = AsyncMock()  # type: ignore[attr-defined]
_uvc_stub.vault_create = AsyncMock()  # type: ignore[attr-defined]
_uvc_stub.UnifiedVaultClientError = Exception  # type: ignore[attr-defined]
_uvc_stub.UnifiedVaultSecretNotFound = Exception  # type: ignore[attr-defined]
sys.modules["user_management.services.unified_vault_client"] = _uvc_stub

# Load unified_vault_client directly (reads real module code)
_vault_client_mod = _load_module(
    "user_management/services/unified_vault_client.py",
    "_vault_client_under_test",
)

# Load sso_rotation directly (needs minimal stubs)
_sso_rotation_mod = _load_module(
    "user_management/services/sso_rotation.py",
    "_sso_rotation_under_test",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_session():
    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    session.execute.return_value = result_mock
    return session


def _mock_provider(provider_id: uuid.UUID, config: dict) -> MagicMock:
    p = MagicMock()
    p.id = provider_id
    p.config = config
    return p


# ---------------------------------------------------------------------------
# unified_vault_client tests
# ---------------------------------------------------------------------------


class TestUnifiedVaultClientConfig:
    def test_check_configured_raises_when_key_missing(self, monkeypatch):
        monkeypatch.setattr(_vault_client_mod, "_SERVICE_KEY", "")
        with pytest.raises(_vault_client_mod.UnifiedVaultClientError, match="SLM_SERVICE_KEY"):
            _vault_client_mod._check_configured()

    def test_check_configured_passes_with_key(self, monkeypatch):
        monkeypatch.setattr(_vault_client_mod, "_SERVICE_KEY", "aabbcc" * 10)
        # Should not raise
        _vault_client_mod._check_configured()

    def test_is_configured_false_without_key(self, monkeypatch):
        monkeypatch.setattr(_vault_client_mod, "_SERVICE_KEY", "")
        assert _vault_client_mod.is_configured() is False

    def test_is_configured_true_with_key(self, monkeypatch):
        monkeypatch.setattr(_vault_client_mod, "_SERVICE_KEY", "aabbcc" * 10)
        assert _vault_client_mod.is_configured() is True

    def test_auth_headers_returns_three_keys(self, monkeypatch):
        monkeypatch.setattr(_vault_client_mod, "_SERVICE_KEY", "aabbcc" * 10)
        monkeypatch.setattr(_vault_client_mod, "_SERVICE_ID", "test-slm")
        headers = _vault_client_mod._auth_headers("POST", "/api/v2/secrets/system")
        assert set(headers.keys()) == {"X-Service-ID", "X-Service-Signature", "X-Service-Timestamp"}
        assert headers["X-Service-ID"] == "test-slm"

    @pytest.mark.asyncio
    async def test_request_raises_secret_not_found_on_404(self, monkeypatch):
        monkeypatch.setattr(_vault_client_mod, "_SERVICE_KEY", "aabbcc" * 10)

        # Simulate a 404 response from aiohttp
        resp_mock = AsyncMock()
        resp_mock.status = 404
        resp_mock.ok = False
        resp_mock.__aenter__ = AsyncMock(return_value=resp_mock)
        resp_mock.__aexit__ = AsyncMock(return_value=False)

        session_mock = AsyncMock()
        session_mock.request = MagicMock(return_value=resp_mock)
        session_mock.__aenter__ = AsyncMock(return_value=session_mock)
        session_mock.__aexit__ = AsyncMock(return_value=False)

        with patch.object(
            sys.modules["aiohttp"],
            "ClientSession",
            return_value=session_mock,
        ):
            with pytest.raises(_vault_client_mod.UnifiedVaultSecretNotFound):
                await _vault_client_mod._request("GET", "/api/v2/secrets/system/some-id")

    @pytest.mark.asyncio
    async def test_request_raises_client_error_on_500(self, monkeypatch):
        monkeypatch.setattr(_vault_client_mod, "_SERVICE_KEY", "aabbcc" * 10)

        resp_mock = AsyncMock()
        resp_mock.status = 500
        resp_mock.ok = False
        resp_mock.text = AsyncMock(return_value="internal error")
        resp_mock.__aenter__ = AsyncMock(return_value=resp_mock)
        resp_mock.__aexit__ = AsyncMock(return_value=False)

        session_mock = AsyncMock()
        session_mock.request = MagicMock(return_value=resp_mock)
        session_mock.__aenter__ = AsyncMock(return_value=session_mock)
        session_mock.__aexit__ = AsyncMock(return_value=False)

        with patch.object(sys.modules["aiohttp"], "ClientSession", return_value=session_mock):
            with pytest.raises(_vault_client_mod.UnifiedVaultClientError):
                await _vault_client_mod._request("GET", "/api/v2/secrets/system/some-id")

    @pytest.mark.asyncio
    async def test_rewrap_targets_service_system_path(self, monkeypatch):
        """vault_rewrap_kek must hit the service-auth /system/{id}/rewrap route,
        not the user-auth /{id}/rewrap route (which would 401 under service HMAC)."""
        captured = {}

        async def _fake_request(method, path, **kwargs):
            captured["method"] = method
            captured["path"] = path
            return {"id": "x", "version": 1}

        monkeypatch.setattr(_vault_client_mod, "_request", _fake_request)
        sid = uuid.uuid4()
        await _vault_client_mod.vault_rewrap_kek(sid, "Zm9vYmFy")
        assert captured["method"] == "POST"
        assert captured["path"] == f"/api/v2/secrets/system/{sid}/rewrap"


# ---------------------------------------------------------------------------
# sso_rotation tests — staleness
# ---------------------------------------------------------------------------


class TestSSORotationStaleness:
    def test_none_timestamp_is_stale(self):
        assert _sso_rotation_mod._is_stale(None) is True

    def test_recent_timestamp_not_stale(self):
        max_age = _sso_rotation_mod.SSO_SECRET_MAX_AGE_DAYS
        fresh = (datetime.now(timezone.utc) - timedelta(days=max_age - 1)).isoformat()
        assert _sso_rotation_mod._is_stale(fresh) is False

    def test_old_timestamp_is_stale(self):
        max_age = _sso_rotation_mod.SSO_SECRET_MAX_AGE_DAYS
        old = (datetime.now(timezone.utc) - timedelta(days=max_age + 1)).isoformat()
        assert _sso_rotation_mod._is_stale(old) is True

    def test_invalid_timestamp_is_stale(self):
        assert _sso_rotation_mod._is_stale("not-a-date") is True

    def test_check_staleness_returns_per_field_report(self):
        pid = uuid.uuid4()
        max_age = _sso_rotation_mod.SSO_SECRET_MAX_AGE_DAYS
        old = (datetime.now(timezone.utc) - timedelta(days=max_age + 5)).isoformat()
        config = {"client_secret_rotated_at": old}
        report = _sso_rotation_mod.check_staleness(pid, config, fields=["client_secret"])
        assert report["client_secret"]["stale"] is True
        assert report["client_secret"]["max_age_days"] == max_age

    def test_check_staleness_fresh_not_stale(self):
        pid = uuid.uuid4()
        fresh = datetime.now(timezone.utc).isoformat()
        config = {"client_secret_rotated_at": fresh}
        report = _sso_rotation_mod.check_staleness(pid, config, fields=["client_secret"])
        assert report["client_secret"]["stale"] is False

    def test_check_staleness_unknown_timestamp_is_stale(self):
        pid = uuid.uuid4()
        report = _sso_rotation_mod.check_staleness(pid, {}, fields=["client_secret"])
        assert report["client_secret"]["stale"] is True


# ---------------------------------------------------------------------------
# sso_rotation — rotate_kek
# ---------------------------------------------------------------------------


def _make_session_with_provider(provider):
    """Return an AsyncMock session whose execute().scalar_one_or_none() yields *provider*."""
    session = _mock_session()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = provider
    session.execute.return_value = result_mock
    return session


class TestRotateKEK:
    @pytest.mark.asyncio
    async def test_rotate_kek_calls_vault_rewrap_and_returns_result(self):
        pid = uuid.uuid4()
        vault_id = uuid.uuid4()

        provider = _mock_provider(pid, {"client_secret_vault_id": str(vault_id)})
        # Stub SSOProvider query result via the model stub
        _sso_model_stub.SSOProvider = MagicMock()
        session = _make_session_with_provider(provider)

        rewrap_ret = {"id": str(vault_id), "version": 2, "name": "test"}
        _uvc_stub.vault_rewrap_kek = AsyncMock(return_value=rewrap_ret)

        with (
            patch.object(_sso_rotation_mod, "_update_provider_config", new=AsyncMock()),
            patch.object(_sso_rotation_mod, "_write_audit", new=AsyncMock()),
        ):
            result = await _sso_rotation_mod.rotate_kek(
                session,
                provider_id=pid,
                field="client_secret",
                new_root_key_b64="dGVzdGtleXRlc3RrZXl0ZXN0a2V5dGVzdGtleQ==",
                actor_id="admin",
            )

        assert result["action"] == "rotate_kek"
        assert result["vault_id"] == str(vault_id)
        assert "rotated_at" in result

    @pytest.mark.asyncio
    async def test_rotate_kek_raises_when_no_vault_id_in_config(self):
        pid = uuid.uuid4()
        provider = _mock_provider(pid, {})  # no vault_id
        _sso_model_stub.SSOProvider = MagicMock()
        session = _make_session_with_provider(provider)

        with pytest.raises(_sso_rotation_mod.SSORotationError, match="vault_id"):
            await _sso_rotation_mod.rotate_kek(
                session, provider_id=pid, field="client_secret", new_root_key_b64="dGVzdA=="
            )

    @pytest.mark.asyncio
    async def test_rotate_kek_raises_when_provider_not_found(self):
        _sso_model_stub.SSOProvider = MagicMock()
        session = _make_session_with_provider(None)

        with pytest.raises(_sso_rotation_mod.SSORotationError, match="not found"):
            await _sso_rotation_mod.rotate_kek(
                session, provider_id=uuid.uuid4(), field="client_secret", new_root_key_b64="dGVzdA=="
            )


# ---------------------------------------------------------------------------
# sso_rotation — rotate_value
# ---------------------------------------------------------------------------


class TestRotateValue:
    @pytest.mark.asyncio
    async def test_rotate_value_calls_vault_rotate_and_returns_result(self):
        pid = uuid.uuid4()
        vault_id = uuid.uuid4()

        provider = _mock_provider(pid, {"client_secret_vault_id": str(vault_id)})
        _sso_model_stub.SSOProvider = MagicMock()
        session = _make_session_with_provider(provider)

        rotate_ret = {"id": str(vault_id), "version": 3, "name": "test"}
        _uvc_stub.vault_rotate = AsyncMock(return_value=rotate_ret)

        with (
            patch.object(_sso_rotation_mod, "_update_provider_config", new=AsyncMock()),
            patch.object(_sso_rotation_mod, "_write_audit", new=AsyncMock()),
        ):
            result = await _sso_rotation_mod.rotate_value(
                session,
                provider_id=pid,
                field="client_secret",
                new_value="new-super-secret",
                actor_id="admin",
            )

        assert result["action"] == "rotate_value"
        assert result["vault_id"] == str(vault_id)
        assert "rotated_at" in result

    @pytest.mark.asyncio
    async def test_rotate_value_raises_when_no_vault_id_in_config(self):
        pid = uuid.uuid4()
        provider = _mock_provider(pid, {})
        _sso_model_stub.SSOProvider = MagicMock()
        session = _make_session_with_provider(provider)

        with pytest.raises(_sso_rotation_mod.SSORotationError, match="vault_id"):
            await _sso_rotation_mod.rotate_value(session, provider_id=pid, field="client_secret", new_value="something")

    @pytest.mark.asyncio
    async def test_rotate_value_raises_when_provider_not_found(self):
        _sso_model_stub.SSOProvider = MagicMock()
        session = _make_session_with_provider(None)

        with pytest.raises(_sso_rotation_mod.SSORotationError, match="not found"):
            await _sso_rotation_mod.rotate_value(
                session, provider_id=uuid.uuid4(), field="client_secret", new_value="x"
            )


# ---------------------------------------------------------------------------
# Module-level constant env override (SSO_SECRET_MAX_AGE_DAYS)
# ---------------------------------------------------------------------------


class TestMaxAgeDaysConstant:
    def test_default_is_90(self):
        # Default when env var not set is 90
        assert _sso_rotation_mod._DEFAULT_MAX_AGE_DAYS == 90

    def test_resolver_returns_default_for_invalid_value(self, monkeypatch):
        monkeypatch.setenv("SSO_SECRET_MAX_AGE_DAYS", "bad-value")
        result = _sso_rotation_mod._resolve_max_age_days()
        assert result == 90

    def test_resolver_returns_default_for_zero(self, monkeypatch):
        monkeypatch.setenv("SSO_SECRET_MAX_AGE_DAYS", "0")
        result = _sso_rotation_mod._resolve_max_age_days()
        assert result == 90

    def test_resolver_returns_custom_valid_value(self, monkeypatch):
        monkeypatch.setenv("SSO_SECRET_MAX_AGE_DAYS", "30")
        result = _sso_rotation_mod._resolve_max_age_days()
        assert result == 30
