# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provider preference order is configuration, not statement order (#15500).

The defect was that ``_populate_default_providers`` appended each provider as
its registration block ran, so Ollama -- the first block -- was always primary
and an operator's configured cloud provider was reached only once Ollama had
failed.  The tests that bind that fix are the ones whose input registration
order *disagrees* with the configured order: strip the ordering out and they
return the input unchanged and fail.

``test_no_configuration_reproduces_the_previous_chain`` is deliberately not one
of those.  Its whole point is that an operator who configures nothing sees no
change, so it passes with the ordering removed too -- it is a no-regression
assertion, not evidence that the ordering runs.  Saying so here because a suite
that cannot tell its binding tests from its agreeable ones is how #15826's
"passed, reproducing nothing" keeps happening.

The cross-provider model-hop half of #15500 lives in
``autobot-backend/llm_shared/fallback_chain_honours_provider_order_15500_test.py``
-- it needs the backend's conftest, which this directory does not get.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from autobot_shared import llm_provider_order
from autobot_shared.llm_provider_order import (
    DEFAULT_ORDER,
    ORDER_ENV_VAR,
    apply_configured_order,
    configured_order,
    order_providers,
    parse_order,
    provider_is_permitted,
)

#: The order ``_populate_default_providers`` produced before #15500, read off
#: the sequence of its registration blocks.  Ollama first is the bug.
REGISTRATION_ORDER = (
    "ollama",
    "openai",
    "anthropic",
    "groq",
    "mistral",
    "huggingface",
    "custom_openai",
    "openrouter",
    "nous",
    "vllm",
    "vertexai",
    "bedrock",
)


@pytest.fixture
def unset_order(monkeypatch: pytest.MonkeyPatch) -> None:
    """No configured order, so the default applies."""
    monkeypatch.delenv(ORDER_ENV_VAR, raising=False)


def _chain(registered, order: str) -> tuple[str, ...]:
    return order_providers(registered, parse_order(order)).chain


class TestTheThreeModes:
    """#15494's modes are values of this one setting (AC5, AC6, AC7)."""

    def test_no_configuration_reproduces_the_previous_chain(self, unset_order) -> None:
        """AC7's no-configuration default: local-first, unchanged.

        Agreeable by construction -- see the module docstring.
        """
        assert apply_configured_order(list(REGISTRATION_ORDER)) == list(REGISTRATION_ORDER)
        assert configured_order() == ("ollama", "*")

    def test_full_local_puts_ollama_first_whatever_keys_are_present(self) -> None:
        """AC6. Binding: Ollama registers LAST here, so first can only be ordering."""
        registered = ["anthropic", "openai", "ollama"]

        assert _chain(registered, "ollama,*") == ("ollama", "anthropic", "openai")

    def test_full_provider_puts_the_chosen_provider_first_and_drops_ollama(self) -> None:
        """AC5. An exhaustive order is how Ollama leaves the path, not just the front."""
        result = order_providers(REGISTRATION_ORDER, parse_order("anthropic"))

        assert result.chain == ("anthropic",)
        assert "ollama" not in result.chain
        assert "ollama" in result.excluded

    def test_full_provider_with_a_tail_still_demotes_rather_than_drops(self) -> None:
        """The contrast case for the one above: `*` is what decides drop vs demote."""
        result = order_providers(REGISTRATION_ORDER, parse_order("anthropic,*"))

        assert result.chain[0] == "anthropic"
        assert "ollama" in result.chain
        assert result.excluded == ()


class TestOrdering:
    def test_a_provider_outside_the_order_keeps_its_place_behind_the_named_ones(self) -> None:
        """AC3: no silent drop -- unnamed providers land at the `*` position."""
        registered = ["ollama", "openai", "anthropic", "groq"]

        assert _chain(registered, "anthropic,*") == ("anthropic", "ollama", "openai", "groq")

    def test_names_after_the_rest_token_come_last(self) -> None:
        """`*` is a position, not a terminator -- otherwise it swallows the tail."""
        registered = ["ollama", "openai", "anthropic"]

        assert _chain(registered, "anthropic,*,ollama") == ("anthropic", "openai", "ollama")

    def test_a_repeated_name_is_not_a_repeated_hop(self) -> None:
        assert _chain(["ollama", "openai"], "openai,openai,*") == ("openai", "ollama")

    def test_order_is_case_and_whitespace_insensitive(self) -> None:
        assert _chain(["ollama", "anthropic"], " Anthropic , * ") == ("anthropic", "ollama")

    def test_a_duplicate_registration_yields_one_chain_entry(self) -> None:
        assert _chain(["ollama", "ollama"], "ollama,*") == ("ollama",)

    def test_registration_order_decides_the_rest_block(self) -> None:
        """The `*` block is registration order, not sorted -- so it stays stable."""
        assert _chain(["vllm", "groq", "ollama"], "ollama,*") == ("ollama", "vllm", "groq")


class TestNamesThatMatchNothing:
    def test_a_named_provider_without_credentials_is_reported_not_raised(self) -> None:
        """AC4: named but unregistered is a log line and an `unmatched` entry."""
        result = order_providers(["ollama"], parse_order("anthropic,ollama"))

        assert result.chain == ("ollama",)
        assert result.unmatched == ("anthropic",)

    def test_an_unmatched_name_is_logged_with_the_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ORDER_ENV_VAR, "anthropic,*")

        with patch.object(llm_provider_order.logger, "info") as info:
            assert apply_configured_order(["ollama"]) == ["ollama"]

        logged = " ".join(str(call) for call in info.call_args_list)
        assert "anthropic" in logged
        assert ORDER_ENV_VAR in logged

    def test_an_excluded_provider_is_named_in_a_log_line_too(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The other half of "no silent drop": a provider an exhaustive order
        leaves out says so, and says it is still reachable."""
        monkeypatch.setenv(ORDER_ENV_VAR, "anthropic")

        with patch.object(llm_provider_order.logger, "info") as info:
            assert apply_configured_order(["ollama", "anthropic"]) == ["anthropic"]

        logged = " ".join(str(call) for call in info.call_args_list)
        assert "ollama" in logged
        assert "explicit request" in logged


class TestConfiguredOrder:
    def test_an_order_naming_no_provider_falls_back_to_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`,` is neither unset nor blank, so env_str hands it straight through.

        Taken literally it is an empty chain and no provider reachable by
        fallback -- a configuration mistake, not a request for silence.
        """
        monkeypatch.setenv(ORDER_ENV_VAR, ",")

        with patch.object(llm_provider_order.logger, "warning") as warning:
            assert configured_order() == parse_order(DEFAULT_ORDER)

        assert warning.called

    def test_a_blank_value_takes_the_default_without_a_warning(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The contrast case: env_str already treats blank as absent (#12782)."""
        monkeypatch.setenv(ORDER_ENV_VAR, "")

        with patch.object(llm_provider_order.logger, "warning") as warning:
            assert configured_order() == parse_order(DEFAULT_ORDER)

        assert not warning.called

    def test_the_var_is_registered_with_the_local_first_default(self) -> None:
        """``env()`` raises KeyError for an unregistered var, so registration is
        part of the feature, not paperwork.

        The literal is spelled out rather than compared to ``DEFAULT_ORDER``:
        the registry entry already imports that constant, so comparing the two
        would assert a tautology. The default is a behaviour contract -- #15500
        promises an operator who configures nothing sees no change -- so
        changing it should have to come past this line.
        """
        from autobot_shared.env_registry import REGISTRY

        assert REGISTRY[ORDER_ENV_VAR].default == "ollama,*"
        assert DEFAULT_ORDER == "ollama,*"


class TestProviderIsPermitted:
    def test_a_rest_token_admits_a_provider_the_order_never_names(self) -> None:
        assert provider_is_permitted("ollama", parse_order("anthropic,*"))

    def test_an_exhaustive_order_refuses_a_provider_it_does_not_name(self) -> None:
        assert not provider_is_permitted("ollama", parse_order("anthropic,openai"))

    def test_an_exhaustive_order_admits_the_providers_it_names(self) -> None:
        assert provider_is_permitted("Anthropic", parse_order("anthropic,openai"))

    def test_it_reads_the_environment_when_given_no_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(ORDER_ENV_VAR, "anthropic")

        assert not provider_is_permitted("ollama")
        assert provider_is_permitted("anthropic")
