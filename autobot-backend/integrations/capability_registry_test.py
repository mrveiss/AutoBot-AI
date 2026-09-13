# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Slack/Discord bot tokens resolve through the vault seam (#15276).

``integrations.capability_registry`` is the third ``CredentialGatedRegistry``
sibling named in ``autobot_shared/credential_gated_registry.py``'s own docstring
(``agent_loop.search.registry`` and ``llm_shared.provider_registry`` were the
other two, fixed by #15267/#15268) -- the only one of the three never migrated
to ``resolve_provider_key`` until now. Mirrors
``agent_loop/search/registry_test.py``'s spy technique.
"""

from __future__ import annotations

import pytest

import integrations.capability_registry as capability_registry_mod
from integrations.capability_registry import CapabilityRegistry, _populate_default_providers

_MESSAGING_KEY_NAMES = {"SLACK_BOT_TOKEN", "DISCORD_BOT_TOKEN"}


@pytest.fixture
def asked_names(monkeypatch) -> list[str]:
    """Run the registry build, recording every credential name it resolves."""
    import services.provider_key_vault as vault_mod

    asked: list[str] = []

    def _spy(name: str, fallback: str = "") -> str:
        asked.append(name)
        return ""  # no real integration classes get constructed for an empty token

    monkeypatch.setattr(vault_mod, "resolve_provider_key", _spy)
    _populate_default_providers(CapabilityRegistry())
    return asked


def test_the_spy_saw_the_registry_run(asked_names: list[str]) -> None:
    """Guard the guard: an empty recording would satisfy every assertion below."""
    assert asked_names, "_populate_default_providers resolved no keys at all"


def test_both_messaging_tokens_resolve_through_the_vault_seam(asked_names: list[str]) -> None:
    missing = _MESSAGING_KEY_NAMES - set(asked_names)
    assert not missing, f"declared messaging credentials never resolved at runtime: {missing}"


def test_env_var_wins_over_the_vault(monkeypatch) -> None:
    """Dual-read, env-first: an Ansible-provisioned deployment is unaffected.

    Asserted via the token actually handed to ``_register_messaging_if_token``
    rather than by inspecting the constructed integration's internals, which
    are a different module's concern.
    """
    import services.provider_key_vault as vault_mod

    monkeypatch.setattr(vault_mod, "_hydrated_keys", {"SLACK_BOT_TOKEN": "vault-value"})

    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config, "slack_bot_token", "env-value", raising=False)
    monkeypatch.setattr(config, "discord_bot_token", "", raising=False)

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        capability_registry_mod,
        "_register_messaging_if_token",
        lambda registry, provider, token, integration_cls, adapter_cls: calls.append((provider, token)),
    )

    _populate_default_providers(CapabilityRegistry())

    assert ("slack", "env-value") in calls


def test_vault_only_token_still_reaches_registration(monkeypatch) -> None:
    """A token captured only via the wizard (no env var) still resolves."""
    import services.provider_key_vault as vault_mod

    monkeypatch.setattr(vault_mod, "_hydrated_keys", {"DISCORD_BOT_TOKEN": "vault-only-value"})

    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config, "slack_bot_token", "", raising=False)
    monkeypatch.setattr(config, "discord_bot_token", "", raising=False)

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        capability_registry_mod,
        "_register_messaging_if_token",
        lambda registry, provider, token, integration_cls, adapter_cls: calls.append((provider, token)),
    )

    _populate_default_providers(CapabilityRegistry())

    assert ("discord", "vault-only-value") in calls


def test_a_resolve_failure_degrades_to_no_registration_never_an_exception(monkeypatch) -> None:
    """The registry's never-raise contract: nothing here may propagate an exception."""
    import services.provider_key_vault as vault_mod

    def _boom(name: str, fallback: str = "") -> str:
        raise RuntimeError("simulated vault outage")

    monkeypatch.setattr(vault_mod, "resolve_provider_key", _boom)

    from autobot_shared.credential_gated_registry import gated_registry_singleton

    accessor = gated_registry_singleton(CapabilityRegistry, _populate_default_providers)
    registry = accessor()  # must not raise -- population failures are caught and logged
    assert registry is not None
