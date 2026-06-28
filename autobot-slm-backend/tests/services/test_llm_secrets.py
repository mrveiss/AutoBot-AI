# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for LLM provider api_key vault integration (#10503).

Loads ``llm_secrets.py`` directly via importlib, stubs out the
``unified_vault_client`` module, and drives the public functions in isolation
so no live autobot-backend or DB is required.

Stub strategy: the lazy imports inside llm_secrets.py resolve from
``sys.modules[_UVC_KEY]`` at call time.  All tests operate on the *live*
stub object retrieved via ``sys.modules[_UVC_KEY]`` (the ``uvc`` fixture),
not on a stale module-level reference, so the tests work regardless of
whether test_sso_vault_client.py registered its own stub first.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND = Path(__file__).parent.parent.parent
_UVC_KEY = "user_management.services.unified_vault_client"

# ---------------------------------------------------------------------------
# One-time sys.modules stubs (idempotent — safe to run alongside other test
# files that install their own stubs for the same keys).
# ---------------------------------------------------------------------------

if "aiohttp" not in sys.modules:
    sys.modules["aiohttp"] = MagicMock()

if "autobot_shared.http_client" not in sys.modules:
    _hs = types.ModuleType("autobot_shared.http_client")
    _hs.sign_request = lambda *a, **kw: {}  # type: ignore[attr-defined]
    sys.modules["autobot_shared.http_client"] = _hs
    sys.modules.setdefault("autobot_shared", types.ModuleType("autobot_shared"))

if _UVC_KEY not in sys.modules:
    _stub = types.ModuleType(_UVC_KEY)
    sys.modules[_UVC_KEY] = _stub

# Ensure required attributes exist on whatever stub is live.
_live = sys.modules[_UVC_KEY]
for _attr, _default in [
    ("vault_create", AsyncMock()),
    ("vault_rotate", AsyncMock()),
    ("vault_read", AsyncMock()),
    ("vault_delete", AsyncMock()),
    ("vault_list", AsyncMock()),
    ("UnifiedVaultClientError", Exception),
    ("UnifiedVaultSecretNotFound", Exception),
    ("is_configured", lambda: False),
]:
    if not hasattr(_live, _attr):
        setattr(_live, _attr, _default)

sys.modules.setdefault("user_management.services", types.ModuleType("user_management.services"))
sys.modules.setdefault("user_management", types.ModuleType("user_management"))

# Always install the real-behaviour encryption stub so decrypt_data / encrypt_data
# return strings, not MagicMock instances, even if another test file already put
# a MagicMock at this key.
_enc = types.ModuleType("services.encryption")
_enc.encrypt_data = lambda v: f"ENC[{v}]"  # type: ignore[attr-defined]
_enc.decrypt_data = lambda v: v[4:-1] if v.startswith("ENC[") else v  # type: ignore[attr-defined]
sys.modules["services.encryption"] = _enc
sys.modules.setdefault("services", types.ModuleType("services"))

# ---------------------------------------------------------------------------
# Load the module under test
# ---------------------------------------------------------------------------


def _load_llm_secrets():
    spec = importlib.util.spec_from_file_location(
        "_llm_secrets_under_test",
        _BACKEND / "user_management/services/llm_secrets.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_llm_sec = _load_llm_secrets()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def uvc():
    """Return the live unified_vault_client stub from sys.modules."""
    return sys.modules[_UVC_KEY]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _provider(name: str, api_key: str = "", **extra) -> dict:
    return {"name": name, "api_key": api_key, **extra}


# ---------------------------------------------------------------------------
# store_provider_api_key
# ---------------------------------------------------------------------------


class TestStoreProviderApiKey:
    @pytest.mark.asyncio
    async def test_no_api_key_returns_dict_unchanged(self, uvc, monkeypatch):
        monkeypatch.setattr(uvc, "is_configured", lambda: True)
        d = _provider("openai")
        result = await _llm_sec.store_provider_api_key("openai", d)
        assert result == d

    @pytest.mark.asyncio
    async def test_vault_create_called_for_new_key(self, uvc, monkeypatch):
        new_id = uuid.uuid4()
        monkeypatch.setattr(uvc, "is_configured", lambda: True)
        monkeypatch.setattr(uvc, "vault_create", AsyncMock(return_value={"id": str(new_id)}))

        result = await _llm_sec.store_provider_api_key("openai", _provider("openai", api_key="sk-abc"))

        uvc.vault_create.assert_called_once()
        assert "llm:provider:openai:api_key" in uvc.vault_create.call_args.args
        assert "api_key" not in result
        assert result["api_key_vault_id"] == str(new_id)
        assert result["api_key_ref"] == "llm:provider:openai:api_key"

    @pytest.mark.asyncio
    async def test_vault_rotate_called_for_existing_vault_id(self, uvc, monkeypatch):
        existing_id = uuid.uuid4()
        monkeypatch.setattr(uvc, "is_configured", lambda: True)
        monkeypatch.setattr(uvc, "vault_rotate", AsyncMock(return_value={"id": str(existing_id), "version": 2}))

        d = _provider("anthropic", api_key="new-key", api_key_vault_id=str(existing_id))
        result = await _llm_sec.store_provider_api_key("anthropic", d)

        uvc.vault_rotate.assert_called_once()
        assert result["api_key_vault_id"] == str(existing_id)
        assert "api_key" not in result

    @pytest.mark.asyncio
    async def test_fallback_inline_encrypt_when_not_configured(self, uvc, monkeypatch):
        monkeypatch.setattr(uvc, "is_configured", lambda: False)
        result = await _llm_sec.store_provider_api_key("openai", _provider("openai", api_key="sk-plain"))
        assert result["api_key"].startswith("ENC[")

    @pytest.mark.asyncio
    async def test_vault_error_propagates(self, uvc, monkeypatch):
        monkeypatch.setattr(uvc, "is_configured", lambda: True)
        monkeypatch.setattr(uvc, "vault_create", AsyncMock(side_effect=uvc.UnifiedVaultClientError("boom")))
        with pytest.raises(uvc.UnifiedVaultClientError):
            await _llm_sec.store_provider_api_key("openai", _provider("openai", api_key="sk-x"))


# ---------------------------------------------------------------------------
# retrieve_provider_api_key
# ---------------------------------------------------------------------------


class TestRetrieveProviderApiKey:
    @pytest.mark.asyncio
    async def test_reads_from_vault_by_id(self, uvc, monkeypatch):
        vid = uuid.uuid4()
        monkeypatch.setattr(uvc, "is_configured", lambda: True)
        monkeypatch.setattr(uvc, "vault_read", AsyncMock(return_value="secret-from-vault"))
        d = {"name": "openai", "api_key_vault_id": str(vid)}
        result = await _llm_sec.retrieve_provider_api_key("openai", d)
        assert result == "secret-from-vault"

    @pytest.mark.asyncio
    async def test_fallback_to_inline_when_not_configured(self, uvc, monkeypatch):
        monkeypatch.setattr(uvc, "is_configured", lambda: False)
        d = {"name": "openai", "api_key": "ENC[my-secret]"}
        result = await _llm_sec.retrieve_provider_api_key("openai", d)
        assert result == "my-secret"

    @pytest.mark.asyncio
    async def test_empty_string_when_no_key(self, uvc, monkeypatch):
        monkeypatch.setattr(uvc, "is_configured", lambda: False)
        d = {"name": "openai"}
        result = await _llm_sec.retrieve_provider_api_key("openai", d)
        assert result == ""

    @pytest.mark.asyncio
    async def test_vault_not_found_falls_back_to_legacy(self, uvc, monkeypatch):
        vid = uuid.uuid4()
        monkeypatch.setattr(uvc, "is_configured", lambda: True)
        monkeypatch.setattr(uvc, "vault_read", AsyncMock(side_effect=uvc.UnifiedVaultSecretNotFound("gone")))
        monkeypatch.setattr(uvc, "vault_list", AsyncMock(return_value=[]))
        d = {"name": "openai", "api_key_vault_id": str(vid), "api_key": "ENC[fallback]"}
        result = await _llm_sec.retrieve_provider_api_key("openai", d)
        assert result == "fallback"


# ---------------------------------------------------------------------------
# delete_provider_api_key
# ---------------------------------------------------------------------------


class TestDeleteProviderApiKey:
    @pytest.mark.asyncio
    async def test_delete_calls_vault_delete(self, uvc, monkeypatch):
        vid = uuid.uuid4()
        monkeypatch.setattr(uvc, "is_configured", lambda: True)
        monkeypatch.setattr(uvc, "vault_delete", AsyncMock())
        await _llm_sec.delete_provider_api_key("openai", {"api_key_vault_id": str(vid)})
        uvc.vault_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_op_when_not_configured(self, uvc, monkeypatch):
        monkeypatch.setattr(uvc, "is_configured", lambda: False)
        monkeypatch.setattr(uvc, "vault_delete", AsyncMock())
        await _llm_sec.delete_provider_api_key("openai", {"api_key_vault_id": str(uuid.uuid4())})
        uvc.vault_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_op_when_no_vault_id(self, uvc, monkeypatch):
        monkeypatch.setattr(uvc, "is_configured", lambda: True)
        monkeypatch.setattr(uvc, "vault_delete", AsyncMock())
        await _llm_sec.delete_provider_api_key("openai", {})
        uvc.vault_delete.assert_not_called()
