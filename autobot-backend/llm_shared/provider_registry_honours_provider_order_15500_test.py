# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The registry's chain goes through the configured order (#15500).

This file exists because of #17394, where a fix shipped unbound: nine tests
covered the helper and none reached the call site, so reverting the fix left
the suite green.  The ordering rules are tested in
``autobot_shared/llm_provider_order_15500_test.py``; what is tested here is
that ``_populate_default_providers`` actually consults them.

Both tests force a second provider to register by handing
``resolve_provider_key`` an Anthropic key, rather than relying on whatever the
ambient environment happens to configure.  A one-provider registry cannot
demonstrate an ordering, and a test that quietly becomes a tautology when a
credential is absent would report a green it did not earn.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from autobot_shared import llm_provider_order
from autobot_shared.llm_provider_order import ORDER_ENV_VAR


@pytest.fixture
def two_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ollama (always) plus Anthropic, so there is an order to observe.

    Anthropic is the one to fake: its provider is constructed from the key
    alone, with no network call and no optional dependency beyond the SDK the
    backend already declares.
    """
    import services.provider_key_vault as vault

    monkeypatch.setattr(
        vault,
        "resolve_provider_key",
        lambda name, fallback=None: "test-key" if name == "ANTHROPIC_API_KEY" else None,
    )


def _chain_stored_by(registry: MagicMock) -> list[str]:
    assert registry.set_fallback_chain.called, "the registry never stored a chain"
    return list(registry.set_fallback_chain.call_args.args[0])


def test_the_registry_stores_exactly_what_the_order_returned(two_providers, monkeypatch: pytest.MonkeyPatch) -> None:
    """The seam itself: a spy that delegates to the real implementation.

    Asserting on the spy's own return value rather than on a sentinel means
    this stays true when the ordering rules change -- it pins the wiring, not
    the policy.
    """
    from llm_shared.provider_registry import _populate_default_providers

    real = llm_provider_order.apply_configured_order
    seen: dict[str, list[str]] = {}

    def spy(registered):
        seen["input"] = list(registered)
        seen["output"] = real(registered)
        return seen["output"]

    monkeypatch.delenv(ORDER_ENV_VAR, raising=False)
    monkeypatch.setattr(llm_provider_order, "apply_configured_order", spy)

    registry = MagicMock()
    _populate_default_providers(registry)

    assert seen, "the registry never consulted the configured order"
    assert _chain_stored_by(registry) == seen["output"]
    assert seen["input"][0] == "ollama", "registration order should still be Ollama-first"


def test_a_configured_order_reaches_the_chain_the_registry_stores(
    two_providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end, and the binding one: Ollama registers first either way, so
    Anthropic arriving first can only come from the configured order."""
    from llm_shared.provider_registry import _populate_default_providers

    monkeypatch.delenv(ORDER_ENV_VAR, raising=False)
    default = MagicMock()
    _populate_default_providers(default)
    baseline = _chain_stored_by(default)

    assert baseline[0] == "ollama"
    assert "anthropic" in baseline, f"fixture did not register Anthropic: {baseline}"

    monkeypatch.setenv(ORDER_ENV_VAR, "anthropic,*")
    configured = MagicMock()
    _populate_default_providers(configured)

    reordered = _chain_stored_by(configured)
    assert reordered[0] == "anthropic"
    assert set(reordered) == set(baseline), "reordering must not add or drop a provider"


def test_an_exhaustive_order_keeps_ollama_out_of_the_stored_chain(
    two_providers, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC5 at the call site: registered, and absent from the fallback chain."""
    from llm_shared.provider_registry import _populate_default_providers

    monkeypatch.setenv(ORDER_ENV_VAR, "anthropic")
    registry = MagicMock()
    _populate_default_providers(registry)

    assert _chain_stored_by(registry) == ["anthropic"]

    registered = [call.args[0].provider_name for call in registry.register.call_args_list]
    assert "ollama" in registered, "Ollama must still register; it is out of the CHAIN only"


# ---------------------------------------------------------------------------
# Request selection, not just the stored chain.
#
# The chain tests above pin what ``_populate_default_providers`` hands to
# ``set_fallback_chain``. They cannot see ``get_provider_for_request``, which
# appended *every* registered provider after the chain -- so an exhaustive order
# ordered the chain and excluded nobody, and the first time the named provider
# was unreachable the caller was served the provider they had excluded. That is
# #15500's own defect surviving inside its own fix.
# ---------------------------------------------------------------------------


class _FakeProvider:
    def __init__(self, name: str) -> None:
        self.provider_name = name


class _NeverDegraded:
    async def is_degraded(self, name, model_name=None):  # noqa: ANN001, ANN201
        return False


def _registry(monkeypatch: pytest.MonkeyPatch, registered, chain, unreachable=()):
    """A registry whose providers are all healthy except those named unreachable.

    ``unreachable`` is how the scenario is set up rather than asserted: a chain
    whose first provider answers is served by the first candidate and proves
    nothing about the ones behind it.
    """
    from llm_shared import provider_registry as registry_module

    registry = registry_module.ProviderRegistry()
    registry._providers = {name: _FakeProvider(name) for name in registered}
    registry._fallback_chain = list(chain)

    async def _no_org_preference(org_id):  # noqa: ANN001, ANN202
        return None

    async def _get_provider(name):  # noqa: ANN001, ANN202
        return None if name in unreachable else registry._providers.get(name)

    monkeypatch.setattr(registry, "_resolve_org_provider", _no_org_preference)
    monkeypatch.setattr(registry, "get_provider", _get_provider)
    monkeypatch.setattr(registry_module, "get_degradation_store", lambda: _NeverDegraded())
    return registry


@pytest.mark.asyncio
async def test_an_exhaustive_order_keeps_an_unnamed_provider_out_of_request_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scenario #15494's ``full_provider`` mode is for: the chosen provider only."""
    monkeypatch.setenv(ORDER_ENV_VAR, "anthropic")
    registry = _registry(
        monkeypatch,
        registered=["ollama", "anthropic"],
        chain=["anthropic"],
        unreachable=["anthropic"],
    )

    assert await registry.get_provider_for_request() is None


@pytest.mark.asyncio
async def test_a_provider_the_order_excludes_is_still_reachable_by_explicit_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An exclusion governs "everything else", never a caller who names a provider."""
    monkeypatch.setenv(ORDER_ENV_VAR, "anthropic")
    registry = _registry(
        monkeypatch,
        registered=["ollama", "anthropic"],
        chain=["anthropic"],
        unreachable=["anthropic"],
    )

    provider = await registry.get_provider_for_request(provider_name="ollama")

    assert provider is not None
    assert provider.provider_name == "ollama"


@pytest.mark.asyncio
async def test_the_rest_token_still_admits_every_registered_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The default order must keep behaving as it did before #15500."""
    monkeypatch.setenv(ORDER_ENV_VAR, "anthropic,*")
    registry = _registry(
        monkeypatch,
        registered=["ollama", "anthropic"],
        chain=["anthropic", "ollama"],
        unreachable=["anthropic"],
    )

    provider = await registry.get_provider_for_request()

    assert provider is not None
    assert provider.provider_name == "ollama"


@pytest.mark.asyncio
async def test_an_outage_caused_by_the_order_does_not_report_unreachability(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nothing here is unreachable -- the configuration permitted nothing.

    Reporting "All providers unavailable or not configured" would send an
    operator to look at network and credentials for a setting they chose.
    """
    monkeypatch.setenv(ORDER_ENV_VAR, "anthropic")
    registry = _registry(
        monkeypatch,
        registered=["ollama", "anthropic"],
        chain=["anthropic"],
        unreachable=["anthropic"],
    )

    with caplog.at_level("ERROR"):
        assert await registry.get_provider_for_request() is None

    errors = " ".join(record.getMessage() for record in caplog.records if record.levelname == "ERROR")
    assert ORDER_ENV_VAR in errors
    assert "ollama" in errors
    assert "All providers unavailable" not in errors
