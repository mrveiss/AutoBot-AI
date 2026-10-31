# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Skip window, quota hold and the locality rule (#19753)."""

from __future__ import annotations

import importlib.util
from unittest.mock import MagicMock

import pytest

from llm_shared import failover_policy
from llm_shared.failover_policy import (
    hold_seconds,
    is_local_provider,
    locality_allows,
    marks_provider_wide,
    may_fail_over,
)
from llm_shared.provider_error_category import ProviderErrorCategory, ProviderFailure
from llm_shared.run_credentials import llm_principal_scope
from llm_shared.types import ProviderType


def _failure(category, retry_after=None):
    return ProviderFailure(category, "boom", retry_after)


def test_a_transient_failure_gets_the_plain_skip_window():
    assert hold_seconds(_failure(ProviderErrorCategory.PROVIDER_UNAVAILABLE)) is None
    assert hold_seconds(_failure(ProviderErrorCategory.RATE_LIMIT, 5)) is None


def test_a_quota_hold_lasts_until_the_stated_reset():
    assert hold_seconds(_failure(ProviderErrorCategory.BILLING, 7200)) == 7200


def test_a_quota_hold_without_a_stated_reset_uses_the_default():
    assert hold_seconds(_failure(ProviderErrorCategory.BILLING)) == failover_policy._QUOTA_HOLD_DEFAULT_SECONDS


def test_a_bogus_reset_is_bounded():
    assert hold_seconds(_failure(ProviderErrorCategory.BILLING, 10**9)) == failover_policy._QUOTA_HOLD_MAX_SECONDS


def _fresh_module():
    """A second copy of the module, executed now, so its import-time env reads see the patched environment."""
    spec = importlib.util.spec_from_file_location("llm_shared.failover_policy", failover_policy.__file__)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_windows_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("AUTOBOT_LLM_QUOTA_HOLD_DEFAULT_SECONDS", "111")
    monkeypatch.setenv("AUTOBOT_LLM_QUOTA_HOLD_MAX_SECONDS", "222")
    fresh = _fresh_module()
    assert fresh.hold_seconds(_failure(ProviderErrorCategory.BILLING)) == 111
    assert fresh.hold_seconds(_failure(ProviderErrorCategory.BILLING, 9999)) == 222


def test_the_windows_are_registered_with_the_defaults_the_code_uses():
    from autobot_shared.env_registry import REGISTRY

    for name, constant in (
        ("AUTOBOT_LLM_QUOTA_HOLD_DEFAULT_SECONDS", failover_policy._QUOTA_HOLD_DEFAULT_SECONDS),
        ("AUTOBOT_LLM_QUOTA_HOLD_MAX_SECONDS", failover_policy._QUOTA_HOLD_MAX_SECONDS),
    ):
        assert REGISTRY[name].default == constant


@pytest.mark.parametrize(
    ("name", "local"),
    [("ollama", True), ("vllm", True), ("openai", False), ("anthropic", False), ("mystery", False), (None, False)],
)
def test_locality_of_a_provider(name, local):
    assert is_local_provider(name) is local


def test_local_to_external_needs_an_operator_configured_chain():
    assert locality_allows("ollama", "openai", operator_configured=False) is False
    assert locality_allows("ollama", "openai", operator_configured=True) is True


def test_a_hop_naming_no_provider_is_external_for_a_local_origin():
    """The clone carries no provider, so the registry picks one by order -- possibly a hosted one."""
    assert locality_allows("ollama", None, operator_configured=False) is False
    assert locality_allows("ollama", None, operator_configured=True) is True


@pytest.mark.parametrize("origin", [None, "", "mystery-provider"])
def test_an_unknown_origin_is_local_so_it_cannot_hop_outward(origin):
    assert locality_allows(origin, "openai", operator_configured=False) is False
    assert locality_allows(origin, None, operator_configured=False) is False
    assert locality_allows(origin, "ollama", operator_configured=False) is True
    assert locality_allows(origin, "openai", operator_configured=True) is True


def test_a_hosted_origin_is_not_restricted():
    assert locality_allows("openai", "anthropic", operator_configured=False) is True
    assert locality_allows("openai", None, operator_configured=False) is True
    assert locality_allows("openai", "ollama", operator_configured=False) is True


def test_local_to_local_is_allowed():
    assert locality_allows("ollama", "vllm", operator_configured=False) is True


def test_local_providers_is_the_real_provider_type_set_not_a_mock():
    from llm_shared.optimization.router import OptimizationRouter

    assert isinstance(OptimizationRouter.LOCAL_PROVIDERS, set)
    assert {ProviderType.OLLAMA, ProviderType.VLLM} <= OptimizationRouter.LOCAL_PROVIDERS
    assert ProviderType.OPENAI not in OptimizationRouter.LOCAL_PROVIDERS
    assert isinstance(failover_policy.__file__, str) and not isinstance(failover_policy, MagicMock)


@pytest.mark.parametrize("reset", [1e999, float("inf"), float("nan"), -5.0, 0.0])
def test_a_non_finite_or_non_positive_reset_takes_the_default_without_raising(reset):
    assert hold_seconds(_failure(ProviderErrorCategory.BILLING, reset)) == failover_policy._QUOTA_HOLD_DEFAULT_SECONDS


def test_a_huge_finite_reset_is_clamped_before_int():
    assert hold_seconds(_failure(ProviderErrorCategory.BILLING, 1e300)) == failover_policy._QUOTA_HOLD_MAX_SECONDS


@pytest.fixture
def principal():
    with llm_principal_scope("user-1", "org-1"):
        yield


def test_without_a_principal_a_credential_failure_is_the_providers():
    auth = _failure(ProviderErrorCategory.AUTHENTICATION)
    assert may_fail_over(auth) is True
    assert marks_provider_wide(auth, "openai") is True


def test_with_a_principal_a_credential_failure_is_the_callers(principal):
    auth = _failure(ProviderErrorCategory.AUTHENTICATION)
    assert may_fail_over(auth) is False
    assert marks_provider_wide(auth, "openai") is False
    assert (
        may_fail_over(_failure(ProviderErrorCategory.PROVIDER_UNAVAILABLE)) is True
    )  # only credentials are the caller's


@pytest.mark.parametrize("category", [ProviderErrorCategory.PROVIDER_UNAVAILABLE, ProviderErrorCategory.TIMEOUT])
def test_a_5xx_or_timeout_marks_a_hosted_provider_but_not_a_local_one(category):
    assert marks_provider_wide(_failure(category), "openai") is True
    assert marks_provider_wide(_failure(category), "ollama") is False


@pytest.mark.parametrize("provider", ["ollama", "openai"])
def test_network_billing_and_rate_limit_mark_any_provider(provider):
    for category in (ProviderErrorCategory.NETWORK, ProviderErrorCategory.BILLING, ProviderErrorCategory.RATE_LIMIT):
        assert marks_provider_wide(_failure(category), provider) is True
