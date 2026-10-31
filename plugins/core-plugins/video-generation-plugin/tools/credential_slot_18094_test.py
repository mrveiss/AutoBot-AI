# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Video providers read keys through the host-injected slot; a refusal disables with its reason (#18094)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from autobot_shared.plugin_sdk.credential_binding import CredentialUnavailableError

_spec = importlib.util.spec_from_file_location("vg_providers_slot_test", Path(__file__).with_name("providers.py"))
providers = importlib.util.module_from_spec(_spec)
sys.modules["vg_providers_slot_test"] = providers
_spec.loader.exec_module(providers)

_ENV_VALUE = "env-video-key-0cc175b9"  # pragma: allowlist secret


def teardown_module() -> None:
    """Drop the registration above, so no later import inherits this module object."""
    sys.modules.pop("vg_providers_slot_test", None)


@pytest.fixture(autouse=True)
def _reset_slot():
    yield
    providers.set_credential_resolver(None)


def test_standalone_reads_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAY_API_KEY", _ENV_VALUE)
    assert providers.RunwayProvider().available is True


def test_the_injected_resolver_wins_over_the_environment(monkeypatch) -> None:
    monkeypatch.setenv("RUNWAY_API_KEY", _ENV_VALUE)
    providers.set_credential_resolver(lambda name: "")
    assert providers.RunwayProvider().available is False


def test_a_refusal_disables_the_provider_with_its_reason_not_the_env_key(monkeypatch) -> None:
    def _refuse(name: str) -> str:
        raise CredentialUnavailableError(f"vault unavailable: {name} could not be read")

    monkeypatch.setenv("RUNWAY_API_KEY", _ENV_VALUE)
    providers.set_credential_resolver(_refuse)
    provider = providers.RunwayProvider()

    assert provider.available is False
    assert "vault unavailable" in provider.unavailable_reason
    with pytest.raises(providers.ProviderError, match="vault unavailable"):
        provider._require_key()
    assert _ENV_VALUE not in provider.unavailable_reason
