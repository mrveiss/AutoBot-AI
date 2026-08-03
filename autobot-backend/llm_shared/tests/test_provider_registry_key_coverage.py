# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every vault-declared provider key must be resolved at registry build time.

``LLM_PROVIDER_KEY_NAMES`` is the set of API-key names the provider-key vault
captures and hydrates (#10088 Task 7).  A name in that set that no provider
ever asks for is dead configuration: the operator stores a key and nothing
consumes it.

The check used to sit in ``tests/migrations/test_provider_key_vault.py`` as
``assert name in inspect.getsource(_populate_default_providers)`` -- a grep
that a docstring mention satisfied, and that the module's ``requires_postgres``
gate skipped entirely on any machine without a disposable Postgres (#13311).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.provider_key_vault import LLM_PROVIDER_KEY_NAMES


# Names whose resolution is gated behind a *separate* setting, so a bare
# registry build never reaches them.  The gate is enabled below rather than
# excused: a vault name that no reachable configuration consults would be dead,
# and the grep this file replaced could not tell the two apart.
GATED_BY = {"CUSTOM_OPENAI_API_KEY": ("custom_openai_base_url", "https://custom-openai.invalid/v1")}


@pytest.fixture
def resolved_key_names(monkeypatch) -> list[str]:
    """Run the registry build, recording every key name it resolves.

    The spy returns ``""`` so no cloud provider is constructed: the assertion
    is about which names are *asked for*, and building real providers would
    need credentials and network.
    """
    import services.provider_key_vault as vault_mod
    from autobot_shared.ssot_config import config
    from llm_shared import provider_registry

    for _name, (setting, value) in GATED_BY.items():
        monkeypatch.setattr(config, setting, value, raising=False)

    asked: list[str] = []

    def _spy(name: str, fallback: str = "") -> str:
        asked.append(name)
        return ""

    monkeypatch.setattr(vault_mod, "resolve_provider_key", _spy)
    provider_registry._populate_default_providers(MagicMock())
    return asked


def test_the_gated_names_really_are_gated(monkeypatch) -> None:
    """Document the gap the coverage fixture papers over.

    Storing ``CUSTOM_OPENAI_API_KEY`` in the vault does nothing at all unless
    ``CUSTOM_OPENAI_BASE_URL`` is also set, and the only signal is a DEBUG log.
    Pin that so the coupling cannot change silently.
    """
    import services.provider_key_vault as vault_mod
    from autobot_shared.ssot_config import config
    from llm_shared import provider_registry

    asked: list[str] = []
    monkeypatch.setattr(vault_mod, "resolve_provider_key", lambda name, fallback="": (asked.append(name), "")[1])
    for _name, (setting, _value) in GATED_BY.items():
        monkeypatch.setattr(config, setting, "", raising=False)
    provider_registry._populate_default_providers(MagicMock())

    assert set(GATED_BY) & set(asked) == set(), "gate removed -- update GATED_BY, it is now unconditional"


def test_the_spy_saw_the_registry_run(resolved_key_names: list[str]) -> None:
    """Guard the guard: an empty recording would satisfy every assertion below."""
    assert resolved_key_names, "_populate_default_providers resolved no keys at all"


def test_every_declared_name_is_resolved_at_runtime(resolved_key_names: list[str]) -> None:
    """A declared name nobody asks for is a key the operator stores in vain."""
    missing = [name for name in LLM_PROVIDER_KEY_NAMES if name not in resolved_key_names]

    assert not missing, f"declared in LLM_PROVIDER_KEY_NAMES but never resolved at runtime: {missing}"


def test_no_key_is_resolved_under_a_name_the_vault_never_captures(resolved_key_names: list[str]) -> None:
    """The mirror: a name the registry asks for but the vault never stores can
    only ever be served from the environment, never from the vault."""
    unknown = sorted(set(resolved_key_names) - set(LLM_PROVIDER_KEY_NAMES))

    assert not unknown, f"resolved through the vault but never captured into it: {unknown}"
