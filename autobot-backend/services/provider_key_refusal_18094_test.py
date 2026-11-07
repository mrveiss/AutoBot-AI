# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A key the vault holds but cannot read is refused, never resolved from env (#18094, owner decision 2026-10-12).

Pins the three states -- vaulted, unreadable, absent -- and that every caller class contains the
refusal visibly (the LLM bootstrap is pinned in
llm_shared/tests/test_provider_key_refusal_18094.py, where llm_shared loads for real): registration sites skip the one provider with the reason logged, call-time sites
fail with the reason, and nothing raises out of a startup or listing path.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import provider_key_vault as pkv

_ENV_VALUE = "env-rotated-out-5f4dcc3b"  # pragma: allowlist secret
_VAULT_VALUE = "vault-current-1a79a4d6"  # pragma: allowlist secret
_NAME = "FLUX_API_KEY"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(pkv, "_hydrated_keys", {})
    monkeypatch.setattr(pkv, "_unreadable_keys", set())
    monkeypatch.setattr(pkv, "_env_fallback_logged", set())
    monkeypatch.setattr(pkv, "_vault_state", pkv.VAULT_REACHABLE)  # empty vault; lazy-path tests set their own


async def _hydrate(read: AsyncMock, monkeypatch) -> list[str]:
    from services.envelope_secrets_service import EnvelopeSecretsService

    service = MagicMock(spec=EnvelopeSecretsService, instance=True)
    service.read = read

    async def _only(_session, name):
        return "secret-id" if name == _NAME else None

    with (
        patch("services.envelope_secrets_service.EnvelopeSecretsService", autospec=True, return_value=service),
        patch.object(pkv, "_find_system_secret_id", side_effect=_only),
        patch.object(pkv, "_register_credential_dependency", AsyncMock()),
    ):
        return await pkv.hydrate_provider_keys_from_vault(MagicMock(commit=AsyncMock()), root_key=b"k" * 32)


@pytest.mark.asyncio
async def test_an_unreadable_vault_row_is_refused_even_with_env_present(monkeypatch, caplog) -> None:
    monkeypatch.setenv(_NAME, _ENV_VALUE)
    with caplog.at_level(logging.WARNING):
        assert await _hydrate(AsyncMock(side_effect=RuntimeError("decrypt failed")), monkeypatch) == []
        with pytest.raises(pkv.VaultKeyUnavailableError) as exc:
            pkv.resolve_provider_key(_NAME, _ENV_VALUE)
        with pytest.raises(pkv.VaultKeyUnavailableError):
            pkv.resolve_image_provider_key(_NAME)
    assert "vault unavailable" in str(exc.value) and _NAME in str(exc.value)
    assert "vault unreadable: refusing" in caplog.text
    assert "vault has no key" not in caplog.text
    assert _ENV_VALUE not in caplog.text and _ENV_VALUE not in str(exc.value)


def test_a_key_absent_from_the_vault_falls_back_to_env_and_says_so(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        assert pkv.resolve_provider_key(_NAME, _ENV_VALUE) == _ENV_VALUE
    assert "vault has no key: using the environment" in caplog.text
    assert _ENV_VALUE not in caplog.text


@pytest.mark.asyncio
async def test_a_later_successful_hydration_clears_the_refusal(monkeypatch) -> None:
    await _hydrate(AsyncMock(side_effect=RuntimeError("decrypt failed")), monkeypatch)
    with pytest.raises(pkv.VaultKeyUnavailableError):
        pkv.resolve_provider_key(_NAME, _ENV_VALUE)

    assert await _hydrate(AsyncMock(return_value=_VAULT_VALUE.encode("utf-8")), monkeypatch) == [_NAME]
    assert pkv.resolve_provider_key(_NAME, _ENV_VALUE) == _VAULT_VALUE


@pytest.mark.asyncio
async def test_a_failed_re_read_drops_the_old_cached_value(monkeypatch) -> None:
    pkv._hydrated_keys[_NAME] = _VAULT_VALUE
    await _hydrate(AsyncMock(side_effect=RuntimeError("decrypt failed")), monkeypatch)
    with pytest.raises(pkv.VaultKeyUnavailableError):
        pkv.resolve_provider_key(_NAME, _ENV_VALUE)


@pytest.mark.asyncio
async def test_a_row_removed_from_the_vault_returns_to_the_env_fallback(monkeypatch) -> None:
    pkv._unreadable_keys.add(_NAME)
    with patch.object(pkv, "_find_system_secret_id", AsyncMock(return_value=None)):
        with patch("services.envelope_secrets_service.EnvelopeSecretsService", autospec=True):
            await pkv.hydrate_provider_keys_from_vault(MagicMock(commit=AsyncMock()), root_key=b"k" * 32)
    assert pkv.resolve_provider_key(_NAME, _ENV_VALUE) == _ENV_VALUE


def test_a_capture_clears_the_refusal() -> None:
    pkv._unreadable_keys.add(_NAME)
    pkv._refresh_hydrated_key(_NAME, _VAULT_VALUE)
    assert pkv.resolve_provider_key(_NAME, _ENV_VALUE) == _VAULT_VALUE


def test_registration_refusal_contains_only_the_refusal(caplog) -> None:
    pkv._unreadable_keys.add(_NAME)
    with caplog.at_level(logging.ERROR):
        with pkv.registration_refusal("Flux provider"):
            pkv.resolve_provider_key(_NAME, _ENV_VALUE)
    assert "Flux provider not registered -- vault unavailable" in caplog.text
    with pytest.raises(ValueError):
        with pkv.registration_refusal("other"):
            raise ValueError("not a refusal")


# --- callers: each contains the refusal visibly -------------------------------------------------


@pytest.mark.asyncio
async def test_image_listing_reports_the_refusal_per_provider() -> None:
    from api import image_generation as api

    pkv._unreadable_keys.add(_NAME)
    response = await api.list_providers.__wrapped__(current_user=None)
    flux = {p.name: p for p in response.providers}["flux"]
    assert flux.available is False and "vault unavailable" in flux.reason


def test_slack_hook_is_off_with_the_reason_and_not_cached(monkeypatch, caplog) -> None:
    from agent_loop import slack_hook

    monkeypatch.setattr(slack_hook, "_hook", None)
    pkv._unreadable_keys.add("SLACK_BOT_TOKEN")
    with caplog.at_level(logging.ERROR):
        hook = slack_hook.get_slack_hook()
    assert isinstance(hook, slack_hook._NullSlackHook) and slack_hook._hook is None
    assert "Slack notifications disabled: vault unavailable" in caplog.text


@pytest.mark.asyncio
async def test_a_health_checker_reports_the_refusal_instead_of_crashing() -> None:
    from services.provider_health.providers import OpenAIHealth

    pkv._unreadable_keys.add("OPENAI_API_KEY")
    result = await OpenAIHealth().check_health()
    assert result.available is False and "vault unavailable" in result.message


def test_search_registry_skips_brave_with_the_reason(monkeypatch, caplog) -> None:
    from agent_loop.search.registry import SearchProviderRegistry, _populate_default_providers
    from autobot_shared.ssot_config import config

    pkv._unreadable_keys.add("BRAVE_SEARCH_API_KEY")
    monkeypatch.setattr(config, "brave_search_api_key", _ENV_VALUE, raising=False)
    registry = SearchProviderRegistry()
    with caplog.at_level(logging.ERROR):
        _populate_default_providers(registry)
    assert registry.get_provider("brave") is None
    assert "Brave search provider not registered" in caplog.text


def test_realtime_voice_reports_unconfigured_not_an_exception() -> None:
    from voice_processing.realtime.openai_provider import OpenAIRealtimeProvider

    pkv._unreadable_keys.add("OPENAI_API_KEY")
    assert OpenAIRealtimeProvider().is_configured is False
    with pytest.raises(pkv.VaultKeyUnavailableError):
        OpenAIRealtimeProvider._api_key()
