# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for model fallback chain manager (GH#8998).
"""

import os
from unittest.mock import MagicMock

from autobot_shared.ssot_claude_models import CLAUDE_HAIKU, CLAUDE_OPUS, CLAUDE_SONNET

from . import fallback_chain as fallback_chain_module
from .fallback_chain import FallbackChain, FallbackChainManager, get_fallback_chain_manager


class TestFallbackChain:
    """Tests for FallbackChain dataclass."""

    def test_get_next_fallback_from_primary(self):
        """Primary model failure returns first fallback."""
        chain = FallbackChain(
            primary_model="claude-opus-4",
            fallback_models=["claude-sonnet-4", "claude-haiku-4"],
            primary_provider="anthropic",
            fallback_providers=["anthropic", "anthropic"],
        )

        result = chain.get_next_fallback("claude-opus-4")
        assert result == ("claude-sonnet-4", "anthropic")

    def test_get_next_fallback_from_middle(self):
        """Fallback from middle of chain returns next model."""
        chain = FallbackChain(
            primary_model="claude-opus-4",
            fallback_models=["claude-sonnet-4", "claude-haiku-4"],
            primary_provider="anthropic",
            fallback_providers=["anthropic", "anthropic"],
        )

        result = chain.get_next_fallback("claude-sonnet-4")
        assert result == ("claude-haiku-4", "anthropic")

    def test_get_next_fallback_chain_exhausted(self):
        """Last model in chain returns None."""
        chain = FallbackChain(
            primary_model="claude-opus-4",
            fallback_models=["claude-sonnet-4", "claude-haiku-4"],
            primary_provider="anthropic",
            fallback_providers=["anthropic", "anthropic"],
        )

        result = chain.get_next_fallback("claude-haiku-4")
        assert result is None

    def test_get_next_fallback_unknown_model(self):
        """Model not in chain returns None."""
        chain = FallbackChain(
            primary_model="claude-opus-4",
            fallback_models=["claude-sonnet-4"],
        )

        result = chain.get_next_fallback("gpt-4")
        assert result is None

    def test_get_next_fallback_no_providers(self):
        """Chain without providers returns None for provider."""
        chain = FallbackChain(
            primary_model="claude-opus-4",
            fallback_models=["claude-sonnet-4"],
        )

        result = chain.get_next_fallback("claude-opus-4")
        assert result == ("claude-sonnet-4", None)


class TestFallbackChainManager:
    """Tests for FallbackChainManager."""

    def test_default_chains_loaded(self):
        """Default fallback chains are loaded on init."""
        manager = FallbackChainManager()
        chains = manager.list_chains()

        # Check that common models have default chains
        assert CLAUDE_OPUS in chains
        assert CLAUDE_SONNET in chains
        assert "gpt-4" in chains
        assert "gpt-4o" in chains

    def test_get_chain_by_model(self):
        """Get fallback chain by primary model name."""
        manager = FallbackChainManager()
        chain = manager.get_chain(CLAUDE_OPUS)

        assert chain is not None
        assert chain.primary_model == CLAUDE_OPUS
        assert CLAUDE_SONNET in chain.fallback_models

    def test_get_chain_case_insensitive(self):
        """Model names are case-insensitive."""
        manager = FallbackChainManager()
        chain1 = manager.get_chain(CLAUDE_OPUS)
        chain2 = manager.get_chain(CLAUDE_OPUS.upper())

        assert chain1 is chain2

    def test_get_next_fallback_success(self):
        """Get next fallback model for a registered chain."""
        manager = FallbackChainManager()
        result = manager.get_next_fallback(CLAUDE_OPUS, "anthropic")

        assert result is not None
        next_model, next_provider = result
        assert next_model == CLAUDE_SONNET
        assert next_provider == "anthropic"

    def test_get_next_fallback_no_chain(self):
        """No fallback for unregistered model."""
        manager = FallbackChainManager()
        result = manager.get_next_fallback("unknown-model", "unknown-provider")

        assert result is None

    def test_register_custom_chain(self):
        """Can register a custom fallback chain."""
        manager = FallbackChainManager()
        custom_chain = FallbackChain(
            primary_model="my-custom-model",
            fallback_models=["fallback-1", "fallback-2"],
        )

        manager.register_chain(custom_chain)
        chain = manager.get_chain("my-custom-model")

        assert chain is not None
        assert chain.primary_model == "my-custom-model"
        assert chain.fallback_models == ["fallback-1", "fallback-2"]

    def test_env_chain_loading(self):
        """Fallback chains can be loaded from environment variables."""
        os.environ["AUTOBOT_FALLBACK_CHAIN_TEST_MODEL"] = "anthropic:fallback-1,openai:fallback-2"

        manager = FallbackChainManager()
        chain = manager.get_chain("test-model")

        assert chain is not None
        assert chain.fallback_models == ["fallback-1", "fallback-2"]
        assert chain.fallback_providers == ["anthropic", "openai"]

        # Cleanup
        del os.environ["AUTOBOT_FALLBACK_CHAIN_TEST_MODEL"]

    def test_env_chain_without_providers(self):
        """Env chains can specify models without providers."""
        os.environ["AUTOBOT_FALLBACK_CHAIN_ENV_MODEL"] = "fallback-1,fallback-2,fallback-3"

        manager = FallbackChainManager()
        chain = manager.get_chain("env-model")

        assert chain is not None
        assert chain.fallback_models == ["fallback-1", "fallback-2", "fallback-3"]
        assert chain.fallback_providers is None

        # Cleanup
        del os.environ["AUTOBOT_FALLBACK_CHAIN_ENV_MODEL"]

    def test_cross_provider_fallback(self):
        """Fallback chains can span multiple providers."""
        manager = FallbackChainManager()
        chain = manager.get_chain(f"{CLAUDE_OPUS}-cross")

        assert chain is not None
        assert chain.primary_provider == "anthropic"
        assert "gpt-4o" in chain.fallback_models
        assert "openai" in (chain.fallback_providers or [])


class TestSingleton:
    """Tests for the global singleton."""

    def test_get_fallback_chain_manager_singleton(self):
        """get_fallback_chain_manager returns the same instance."""
        manager1 = get_fallback_chain_manager()
        manager2 = get_fallback_chain_manager()

        assert manager1 is manager2


class TestLegacyEnvKeys:
    """An update must not drop a chain configured under the pre-#20884 short names."""

    def test_old_style_variable_still_yields_its_chain_on_the_new_ids(self, monkeypatch):
        # The module logger is replaced, so the log flood filter's remaining allowance cannot hide the warning.
        logger = MagicMock()
        monkeypatch.setattr(fallback_chain_module, "logger", logger)
        monkeypatch.setenv("AUTOBOT_FALLBACK_CHAIN_CLAUDE_OPUS_4", "anthropic:claude-sonnet-4,openai:gpt-4o-mini")
        chain = FallbackChainManager().get_chain(CLAUDE_OPUS)

        assert chain is not None
        assert chain.operator_configured
        assert chain.fallback_models == [CLAUDE_SONNET, "gpt-4o-mini"]
        assert any("deprecated" in call.args[0] for call in logger.warning.call_args_list)

    def test_a_tier_alias_variable_resolves_without_a_warning(self, monkeypatch):
        logger = MagicMock()
        monkeypatch.setattr(fallback_chain_module, "logger", logger)
        monkeypatch.setenv("AUTOBOT_FALLBACK_CHAIN_OPUS", "anthropic:sonnet")
        chain = FallbackChainManager().get_chain(CLAUDE_OPUS)

        assert chain is not None and chain.fallback_models == [CLAUDE_SONNET]
        assert not any("deprecated" in call.args[0] for call in logger.warning.call_args_list)

    def test_a_non_anthropic_hop_keeps_its_own_model_name(self, monkeypatch):
        monkeypatch.setenv("AUTOBOT_FALLBACK_CHAIN_OPUS", "ollama:opus,anthropic:haiku")
        chain = FallbackChainManager().get_chain(CLAUDE_OPUS)

        assert chain is not None and chain.fallback_models == ["opus", CLAUDE_HAIKU]
