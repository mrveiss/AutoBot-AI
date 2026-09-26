# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A model fallback hop may not reach a provider the order excludes (#15500).

``fallback_chain`` is a different axis from provider preference order -- model
to cheaper model -- and it stays one.  The overlap the issue's Notes ask about
is the cross-provider hop, and that hop is part of the generation path: a
provider held out of the fallback chain that a model hop can still reach is not
absent, merely inconvenient, and #15494's ``full_provider`` mode needs it
absent.

The ordering rules themselves are tested in
``autobot_shared/llm_provider_order_15500_test.py``; this file tests only the
seam between the two.
"""

from __future__ import annotations

import pytest

from autobot_shared.llm_provider_order import ORDER_ENV_VAR
from llm_shared.fallback_chain import FallbackChain, FallbackChainManager


@pytest.fixture
def unset_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ORDER_ENV_VAR, raising=False)


def _manager_with_a_local_tail() -> FallbackChainManager:
    """A chain whose first hop is local and whose second is cloud.

    Two hops, not one: a filter that merely *stopped* at an excluded hop would
    pass a single-hop test, and stopping is not skipping.
    """
    manager = FallbackChainManager()
    manager.register_chain(
        FallbackChain(
            primary_model="order-test-primary",
            fallback_models=["order-test-local", "order-test-cloud"],
            primary_provider="anthropic",
            fallback_providers=["ollama", "openai"],
        )
    )
    return manager


def test_a_hop_via_an_excluded_provider_is_skipped_for_the_next_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Binding: it must ADVANCE past the excluded hop, not stop at it."""
    monkeypatch.setenv(ORDER_ENV_VAR, "anthropic,openai")

    hop = _manager_with_a_local_tail().get_next_fallback("order-test-primary")

    assert hop == ("order-test-cloud", "openai")


def test_the_first_hop_is_taken_when_the_order_admits_everything(unset_order) -> None:
    """The contrast case: under the default order nothing is skipped."""
    hop = _manager_with_a_local_tail().get_next_fallback("order-test-primary")

    assert hop == ("order-test-local", "ollama")


def test_a_chain_whose_every_remaining_hop_is_excluded_reports_exhausted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ORDER_ENV_VAR, "anthropic")

    assert _manager_with_a_local_tail().get_next_fallback("order-test-primary") is None


def test_a_hop_naming_no_provider_is_left_alone(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hop with no provider inherits the request's own, so there is nothing
    for the order to judge -- filtering it would break same-provider chains,
    which are the majority of the shipped ones."""
    monkeypatch.setenv(ORDER_ENV_VAR, "anthropic")
    manager = FallbackChainManager()
    manager.register_chain(
        FallbackChain(
            primary_model="order-test-bare",
            fallback_models=["order-test-cheaper"],
        )
    )

    assert manager.get_next_fallback("order-test-bare") == ("order-test-cheaper", None)


def test_the_shipped_cross_provider_chain_still_reaches_ollama_by_default(
    unset_order,
) -> None:
    """No behaviour change to the chains the manager ships with."""
    manager = FallbackChainManager()

    assert manager.get_next_fallback("claude-opus-4-cross") == ("gpt-4o", "openai")

    chain = manager.get_chain("claude-opus-4-cross")
    assert chain is not None
    assert chain.get_next_fallback("gpt-4o") == ("ollama/llama3", "ollama")


def test_the_shipped_cross_provider_chain_loses_its_local_tail_under_full_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5 on a real shipped chain rather than a fixture.

    ``get_chain`` is used rather than ``get_next_fallback("gpt-4o")`` because a
    chain keyed on ``gpt-4o`` is also registered and wins the exact-match
    lookup -- the assertion has to reach the cross-provider chain to say
    anything about it.
    """
    monkeypatch.setenv(ORDER_ENV_VAR, "anthropic,openai")
    manager = FallbackChainManager()

    chain = manager.get_chain("claude-opus-4-cross")
    assert chain is not None
    assert chain.get_next_fallback("gpt-4o") == ("ollama/llama3", "ollama")
    assert manager._first_permitted(chain, "gpt-4o") is None
