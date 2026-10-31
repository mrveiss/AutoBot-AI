# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Skip window, quota hold and the locality rule (#19753)."""

from __future__ import annotations

import importlib.util

import pytest

from llm_shared import failover_policy
from llm_shared.failover_policy import hold_seconds, is_local_provider, locality_allows
from llm_shared.provider_error_category import ProviderErrorCategory, ProviderFailure


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


def test_other_directions_are_not_restricted():
    assert locality_allows("ollama", "vllm", operator_configured=False) is True
    assert locality_allows("openai", "anthropic", operator_configured=False) is True
    assert locality_allows("openai", "ollama", operator_configured=False) is True
    assert locality_allows("ollama", None, operator_configured=False) is True  # inherits the failed provider
