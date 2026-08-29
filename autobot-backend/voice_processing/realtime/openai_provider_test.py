# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``OpenAIRealtimeProvider._api_key`` resolves through the vault seam.

Found during #15269's guard sweep: this call site read ``cfg.llm.openai_api_key``
directly, so a key captured through the setup wizard resolved for every other OpenAI
consumer but silently failed realtime voice negotiation.

Exactly two tiers -- env (via ``cfg.llm.openai_api_key``), then the System vault. An
earlier revision carried a third ``os.environ.get(...)`` tail; review established it
was unreachable (``cfg.llm.openai_api_key`` is itself populated from ``os.environ`` at
load, and nothing in this codebase mutates ``os.environ`` for ``OPENAI_API_KEY`` at
runtime, so the two reads could never diverge) and it was removed rather than kept as
a decoration. ``test_only_two_tiers_are_consulted`` pins that directly: with both
tiers empty, the result is empty -- there is no third source to fall through to.
"""

from __future__ import annotations

from voice_processing.realtime.openai_provider import OpenAIRealtimeProvider


def test_api_key_resolves_through_the_vault_seam_when_config_is_empty(monkeypatch) -> None:
    """A key captured only via the wizard (config empty) still resolves."""
    import services.provider_key_vault as vault_mod
    from autobot_shared.ssot_config import get_config

    monkeypatch.setattr(get_config().llm, "openai_api_key", "", raising=False)
    monkeypatch.setattr(vault_mod, "_hydrated_keys", {"OPENAI_API_KEY": "vault-only-value"})

    assert OpenAIRealtimeProvider._api_key() == "vault-only-value"


def test_api_key_prefers_config_over_the_vault(monkeypatch) -> None:
    """Dual-read, config(env)-first -- the first and only preferred tier."""
    import services.provider_key_vault as vault_mod
    from autobot_shared.ssot_config import get_config

    monkeypatch.setattr(get_config().llm, "openai_api_key", "config-value", raising=False)
    monkeypatch.setattr(vault_mod, "_hydrated_keys", {"OPENAI_API_KEY": "vault-value"})

    assert OpenAIRealtimeProvider._api_key() == "config-value"


def test_only_two_tiers_are_consulted(monkeypatch) -> None:
    """Both tiers empty -> empty result -- there is no third fallback to reach.

    A regression that resurrects the removed ``os.environ`` tail would make this
    fail: it sets the literal env var while leaving both real tiers empty, so a
    reintroduced third read would return it instead of the correct ``""``.
    """
    import services.provider_key_vault as vault_mod
    from autobot_shared.ssot_config import get_config

    monkeypatch.setattr(get_config().llm, "openai_api_key", "", raising=False)
    monkeypatch.setattr(vault_mod, "_hydrated_keys", {})
    monkeypatch.setenv("OPENAI_API_KEY", "should-never-be-read-by-a-third-tier")

    assert OpenAIRealtimeProvider._api_key() == ""
