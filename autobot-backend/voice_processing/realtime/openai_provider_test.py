# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``OpenAIRealtimeProvider._api_key`` resolves through the vault seam.

Found during #15269's guard sweep: this call site read ``cfg.llm.openai_api_key``
directly, so a key captured through the setup wizard resolved for every other OpenAI
consumer but silently failed realtime voice negotiation.
"""

from __future__ import annotations

from voice_processing.realtime.openai_provider import OpenAIRealtimeProvider


def test_api_key_resolves_through_the_vault_seam_when_env_and_config_are_unset(monkeypatch) -> None:
    """A key captured only via the wizard (config empty, env unset) still resolves."""
    import services.provider_key_vault as vault_mod
    from autobot_shared.ssot_config import get_config

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(get_config().llm, "openai_api_key", "", raising=False)
    monkeypatch.setattr(vault_mod, "_hydrated_keys", {"OPENAI_API_KEY": "vault-only-value"})

    assert OpenAIRealtimeProvider._api_key() == "vault-only-value"


def test_api_key_prefers_config_over_the_vault(monkeypatch) -> None:
    """Dual-read, config(env)-first -- unchanged by this fix."""
    import services.provider_key_vault as vault_mod
    from autobot_shared.ssot_config import get_config

    monkeypatch.setattr(get_config().llm, "openai_api_key", "config-value", raising=False)
    monkeypatch.setattr(vault_mod, "_hydrated_keys", {"OPENAI_API_KEY": "vault-value"})

    assert OpenAIRealtimeProvider._api_key() == "config-value"


def test_api_key_falls_back_to_literal_env_read_as_last_resort(monkeypatch) -> None:
    """The pre-existing os.environ fallback is preserved, not removed."""
    import services.provider_key_vault as vault_mod
    from autobot_shared.ssot_config import get_config

    monkeypatch.setattr(get_config().llm, "openai_api_key", "", raising=False)
    monkeypatch.setattr(vault_mod, "_hydrated_keys", {})
    monkeypatch.setenv("OPENAI_API_KEY", "literal-env-value")

    assert OpenAIRealtimeProvider._api_key() == "literal-env-value"
