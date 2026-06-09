# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for provider-agnostic model tier resolution (GH#8487)."""

from __future__ import annotations

import pytest

from llc.services.model_tiers import ModelTierService


@pytest.fixture()
def svc() -> ModelTierService:
    return ModelTierService()


# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------


class TestDetectProvider:
    def test_anthropic(self, svc):
        assert svc.detect_provider("claude-sonnet-4-6") == "anthropic"
        assert svc.detect_provider("claude-haiku-4-5-20251001") == "anthropic"

    def test_openai(self, svc):
        assert svc.detect_provider("gpt-4o") == "openai"
        assert svc.detect_provider("gpt-4o-mini") == "openai"

    def test_google(self, svc):
        assert svc.detect_provider("gemini-1.5-pro") == "google"
        assert svc.detect_provider("gemini-1.5-flash") == "google"

    def test_mistral(self, svc):
        assert svc.detect_provider("mistral-large-latest") == "mistral"
        assert svc.detect_provider("mixtral-8x7b") == "mistral"

    def test_groq_llama(self, svc):
        assert svc.detect_provider("llama-3.3-70b-versatile") == "groq"

    def test_together_meta(self, svc):
        assert svc.detect_provider("meta-llama/Llama-3-70b-chat-hf") == "together"

    def test_unknown(self, svc):
        assert svc.detect_provider("unknown-model-xyz") is None

    def test_empty(self, svc):
        assert svc.detect_provider("") is None
        assert svc.detect_provider(None) is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Assistant model resolution
# ---------------------------------------------------------------------------


class TestResolveAssistantModel:
    def test_anthropic_resolves_haiku(self, svc):
        result = svc.resolve_assistant_model(senior_agent_adapter_config={"model": "claude-sonnet-4-6"})
        assert result == "claude-haiku-4-5-20251001"

    def test_openai_resolves_mini(self, svc):
        result = svc.resolve_assistant_model(senior_agent_adapter_config={"model": "gpt-4o"})
        assert result == "gpt-4o-mini"

    def test_google_resolves_flash(self, svc):
        result = svc.resolve_assistant_model(senior_agent_adapter_config={"model": "gemini-1.5-pro"})
        assert result == "gemini-1.5-flash"

    def test_per_agent_override_wins(self, svc):
        """adapterConfig.model_tier.assistant takes highest precedence."""
        result = svc.resolve_assistant_model(
            senior_agent_adapter_config={
                "model": "claude-sonnet-4-6",
                "model_tier": {"assistant": "my-custom-cheap-model"},
            }
        )
        assert result == "my-custom-cheap-model"

    def test_company_override_wins_over_platform(self, svc):
        result = svc.resolve_assistant_model(
            senior_agent_adapter_config={"model": "gpt-4o"},
            company_overrides={"openai": {"assistant": "gpt-3.5-turbo"}},
        )
        assert result == "gpt-3.5-turbo"

    def test_agent_override_wins_over_company(self, svc):
        result = svc.resolve_assistant_model(
            senior_agent_adapter_config={
                "model": "gpt-4o",
                "model_tier": {"assistant": "agent-override"},
            },
            company_overrides={"openai": {"assistant": "company-override"}},
        )
        assert result == "agent-override"

    def test_unknown_provider_returns_none(self, svc):
        result = svc.resolve_assistant_model(senior_agent_adapter_config={"model": "totally-unknown-model"})
        assert result is None

    def test_empty_adapter_config_returns_none(self, svc):
        result = svc.resolve_assistant_model(senior_agent_adapter_config={})
        assert result is None


# ---------------------------------------------------------------------------
# Tier map
# ---------------------------------------------------------------------------


class TestGetTierMap:
    def test_returns_platform_defaults(self, svc):
        tier_map = svc.get_tier_map()
        assert "anthropic" in tier_map
        assert tier_map["anthropic"]["assistant"] == "claude-haiku-4-5-20251001"
        assert "openai" in tier_map
        assert "google" in tier_map

    def test_company_override_merged(self, svc):
        tier_map = svc.get_tier_map(
            company_overrides={"openai": {"senior": "gpt-4-turbo", "assistant": "gpt-3.5-turbo"}}
        )
        assert tier_map["openai"]["assistant"] == "gpt-3.5-turbo"
        assert tier_map["openai"]["senior"] == "gpt-4-turbo"
        # Other providers should remain unchanged
        assert tier_map["anthropic"]["assistant"] == "claude-haiku-4-5-20251001"
