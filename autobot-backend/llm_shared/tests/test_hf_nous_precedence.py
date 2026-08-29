# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""HF_TOKEN / HUGGINGFACE_API_TOKEN now resolve through the vault seam (#15268).

Both were previously read as a bare ``config.hf_token or config.huggingface_api_token``
fallback in two places -- the HuggingFace provider's own registration, and the Nous
Portal provider's fallback chain. This proves both are now members of the
vault-resolved key set, both call sites route through ``resolve_provider_key``, and
the three-tier precedence for Nous Portal (``NOUS_API_KEY`` > ``HF_TOKEN`` >
``HUGGINGFACE_API_TOKEN``) is unchanged.
"""

from __future__ import annotations

import pytest

from llm_shared import provider_registry
from llm_shared.provider_registry import ProviderRegistry
from services.provider_key_vault import LLM_PROVIDER_KEY_NAMES


def test_hf_token_names_are_members_of_the_vault_resolved_key_set() -> None:
    assert {"HF_TOKEN", "HUGGINGFACE_API_TOKEN"} <= LLM_PROVIDER_KEY_NAMES


@pytest.fixture
def resolved(monkeypatch):
    """Spy on resolve_provider_key: records every name asked for, and answers each
    call from a per-test override map (env-unset default: falls through to the
    ``fallback`` argument the call site passed, exactly like the real function)."""
    import services.provider_key_vault as vault_mod

    answers: dict[str, str] = {}
    asked: list[str] = []

    def _spy(name: str, fallback: str = "") -> str:
        asked.append(name)
        return answers.get(name, fallback)

    monkeypatch.setattr(vault_mod, "resolve_provider_key", _spy)
    return answers, asked


def _populated_registry() -> ProviderRegistry:
    registry = ProviderRegistry()
    provider_registry._populate_default_providers(registry)
    return registry


def test_hf_token_and_huggingface_api_token_are_both_asked(resolved) -> None:
    _answers, asked = resolved
    _populated_registry()
    assert "HF_TOKEN" in asked
    assert "HUGGINGFACE_API_TOKEN" in asked


def test_nous_key_prefers_nous_api_key_over_both_hf_names(resolved) -> None:
    answers, _asked = resolved
    answers["NOUS_API_KEY"] = "nous-value"
    answers["HF_TOKEN"] = "hf-value"
    answers["HUGGINGFACE_API_TOKEN"] = "hf-legacy-value"
    nous = _populated_registry().get_provider_by_name("nous")
    assert nous is not None
    # Precedence is proven behaviourally: only the top tier winning could produce this.
    assert nous.settings["api_key"] == "nous-value"


def test_nous_key_falls_back_to_hf_token_when_nous_api_key_absent(resolved) -> None:
    answers, _asked = resolved
    answers["HF_TOKEN"] = "hf-value"
    answers["HUGGINGFACE_API_TOKEN"] = "hf-legacy-value"
    nous = _populated_registry().get_provider_by_name("nous")
    assert nous is not None
    assert nous.settings["api_key"] == "hf-value"


def test_nous_key_falls_back_to_huggingface_api_token_last(resolved) -> None:
    answers, _asked = resolved
    answers["HUGGINGFACE_API_TOKEN"] = "hf-legacy-value"
    nous = _populated_registry().get_provider_by_name("nous")
    assert nous is not None
    assert nous.settings["api_key"] == "hf-legacy-value"


def test_huggingface_provider_prefers_hf_token_over_huggingface_api_token(resolved) -> None:
    answers, _asked = resolved
    answers["HF_TOKEN"] = "hf-value"
    answers["HUGGINGFACE_API_TOKEN"] = "hf-legacy-value"
    hf = _populated_registry().get_provider_by_name("huggingface")
    assert hf is not None
    assert hf.settings["api_token"] == "hf-value"
