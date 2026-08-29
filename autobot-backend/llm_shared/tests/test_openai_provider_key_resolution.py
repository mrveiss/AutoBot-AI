# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``OpenAIProvider._resolve_api_key`` now has exactly two tiers (#15276).

Before this fix, a falsy ``config.openai_api_key`` fell through to a second,
freshly re-imported ``_ssot_config.llm.openai_api_key`` read -- the dead-tier
trap #15267's review also found in ``voice_processing/realtime/openai_provider.py``
(fixed by #15269/#15277). ``config`` (the flat proxy) and ``config.llm`` resolve
to the same singleton via ``AutoBotConfig.__getattr__`` delegation, so the second
tier could never fire: once the first read was falsy, the second could only ever
repeat it. This module pins the resolution order that replaced it -- settings
override, then exactly one vault-seam call, no bare-config retry after -- so a
future edit cannot reintroduce a third tier without a test going red.
"""

from __future__ import annotations

import pytest

from llm_shared.providers.openai import OpenAIProvider


@pytest.fixture
def resolved(monkeypatch):
    """Spy on ``resolve_provider_key`` as bound in ``llm_shared.providers.openai``
    (a module-level import there, unlike ``provider_registry``'s lazy one) --
    patching ``services.provider_key_vault`` itself would not reach it."""
    answers: dict[str, str] = {}
    asked: list[str] = []

    def _spy(name: str, fallback: str = "") -> str:
        asked.append(name)
        return answers.get(name, fallback)

    monkeypatch.setattr("llm_shared.providers.openai.resolve_provider_key", _spy)
    return answers, asked


def test_settings_override_wins_and_the_seam_is_never_consulted(resolved) -> None:
    _answers, asked = resolved
    provider = OpenAIProvider(settings={"api_key": "settings-value"})
    assert provider._resolve_api_key() == "settings-value"
    assert asked == []


def test_falls_through_to_the_vault_seam_when_no_settings_override(resolved) -> None:
    answers, asked = resolved
    answers["OPENAI_API_KEY"] = "vault-value"
    provider = OpenAIProvider(settings={})
    assert provider._resolve_api_key() == "vault-value"
    assert asked == ["OPENAI_API_KEY"]


def test_exactly_one_seam_call_with_no_bare_config_retry_after(resolved) -> None:
    """The dead-tier trap #15276 removed: one seam call, nothing tried after it.

    Deliberately does not assert on the returned value -- the real
    ``config.openai_api_key`` fallback the spy is called with is
    environment-dependent, and this test's only claim is about call count.
    """
    _answers, asked = resolved
    provider = OpenAIProvider(settings={})
    provider._resolve_api_key()
    assert asked == ["OPENAI_API_KEY"], "a second lookup means a reintroduced dead tier"
