# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Web-search provider credentials resolve through the vault seam (#15267).

Mirrors ``llm_shared/tests/test_provider_registry_key_coverage.py``'s spy technique:
monkeypatch ``resolve_provider_key`` to record every name it is asked for (never
touching a real vault or network), then run the registry's real population function.
"""

from __future__ import annotations

import pytest

from agent_loop.search.registry import SearchProviderRegistry, _populate_default_providers

_SEARCH_KEY_NAMES = {
    "SEARXNG_INSTANCE_URL",
    "SEARXNG_BASIC_AUTH_USER",
    "SEARXNG_BASIC_AUTH_PASS",
    "SEARXNG_TOKEN",
    "BRAVE_SEARCH_API_KEY",
}


@pytest.fixture
def asked_names(monkeypatch) -> list[str]:
    """Run the registry build, recording every credential name it resolves.

    The spy returns ``""`` for every name so no provider actually registers --
    the assertion is about which names are *asked for*, not what a real vault
    or env would return.
    """
    import services.provider_key_vault as vault_mod

    asked: list[str] = []

    def _spy(name: str, fallback: str = "") -> str:
        asked.append(name)
        return ""

    monkeypatch.setattr(vault_mod, "resolve_provider_key", _spy)
    _populate_default_providers(SearchProviderRegistry())
    return asked


def test_the_spy_saw_the_registry_run(asked_names: list[str]) -> None:
    """Guard the guard: an empty recording would satisfy every assertion below."""
    assert asked_names, "_populate_default_providers resolved no keys at all"


def test_every_search_credential_resolves_through_the_vault_seam(asked_names: list[str]) -> None:
    """Every name #15267 lists as evidence must be asked for via resolve_provider_key."""
    missing = _SEARCH_KEY_NAMES - set(asked_names)
    assert not missing, f"declared search credentials never resolved at runtime: {missing}"


def test_env_var_wins_over_the_vault(monkeypatch) -> None:
    """Dual-read, env-first: an Ansible-provisioned deployment is unaffected."""
    import services.provider_key_vault as vault_mod
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(vault_mod, "_hydrated_keys", {"BRAVE_SEARCH_API_KEY": "vault-value"})
    monkeypatch.setattr(config, "brave_search_api_key", "env-value", raising=False)

    registry = SearchProviderRegistry()
    _populate_default_providers(registry)

    provider = registry.get_provider("brave")
    assert provider is not None
    assert provider.api_key == "env-value"


def test_vault_only_credential_still_registers_the_provider(monkeypatch) -> None:
    """A key captured only via the wizard (no env var) still resolves and registers."""
    import services.provider_key_vault as vault_mod
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(vault_mod, "_hydrated_keys", {"BRAVE_SEARCH_API_KEY": "vault-only-value"})
    monkeypatch.setattr(config, "brave_search_api_key", "", raising=False)

    registry = SearchProviderRegistry()
    _populate_default_providers(registry)

    provider = registry.get_provider("brave")
    assert provider is not None
    assert provider.api_key == "vault-only-value"


def test_a_resolve_failure_degrades_to_no_provider_never_an_exception(monkeypatch) -> None:
    """The registry's never-raise contract: nothing here may propagate an exception."""
    import services.provider_key_vault as vault_mod

    def _boom(name: str, fallback: str = "") -> str:
        raise RuntimeError("simulated vault outage")

    monkeypatch.setattr(vault_mod, "resolve_provider_key", _boom)

    from autobot_shared.credential_gated_registry import gated_registry_singleton

    accessor = gated_registry_singleton(SearchProviderRegistry, _populate_default_providers)
    registry = accessor()  # must not raise -- population failures are caught and logged
    assert registry is not None
