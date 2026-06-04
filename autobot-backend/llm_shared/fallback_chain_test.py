# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for model fallback chain manager (GH#8998).
"""

import os

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
        assert "claude-opus-4" in chains
        assert "claude-sonnet-4" in chains
        assert "gpt-4" in chains
        assert "gpt-4o" in chains

    def test_get_chain_by_model(self):
        """Get fallback chain by primary model name."""
        manager = FallbackChainManager()
        chain = manager.get_chain("claude-opus-4")

        assert chain is not None
        assert chain.primary_model == "claude-opus-4"
        assert "claude-sonnet-4" in chain.fallback_models

    def test_get_chain_case_insensitive(self):
        """Model names are case-insensitive."""
        manager = FallbackChainManager()
        chain1 = manager.get_chain("claude-opus-4")
        chain2 = manager.get_chain("CLAUDE-OPUS-4")

        assert chain1 is chain2

    def test_get_next_fallback_success(self):
        """Get next fallback model for a registered chain."""
        manager = FallbackChainManager()
        result = manager.get_next_fallback("claude-opus-4", "anthropic")

        assert result is not None
        next_model, next_provider = result
        assert next_model == "claude-sonnet-4"
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
        chain = manager.get_chain("claude-opus-4-cross")

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


class TestStreamFallback:
    """
    Tests for GH#8998 streaming fallback in LLMService.

    These tests verify that stream() applies the same fallback logic as chat():
    rate limit errors trigger fallback to the next model in the chain.
    """

    def _make_mock_provider(self, provider_name: str, model_name: str, raises: Exception | None = None):
        """Build a mock provider that either succeeds or raises on stream_completion."""
        from unittest.mock import MagicMock

        async def _stream_ok(*a, **kw):
            yield "chunk1"
            yield "chunk2"

        async def _stream_fail(*a, **kw):
            raise raises
            # unreachable, satisfies type checker
            yield  # noqa: unreachable

        provider = MagicMock()
        provider.provider_name = provider_name
        provider.stream_completion = _stream_ok if raises is None else _stream_fail
        return provider

    def _make_registry(self, providers: list):
        """Build a mock ProviderRegistry that returns providers in sequence."""
        from unittest.mock import MagicMock

        registry = MagicMock()
        provider_iter = iter(providers)

        async def _get_provider(*a, **kw):
            try:
                return next(provider_iter)
            except StopIteration:
                return None

        registry.get_provider_for_request = _get_provider
        return registry

    def test_stream_succeeds_without_fallback(self):
        """Successful stream returns all chunks."""
        import asyncio

        from services.llm_service import LLMService

        provider = self._make_mock_provider("anthropic", "claude-opus-4")
        registry = self._make_registry([provider])

        svc = LLMService(registry=registry)

        async def run():
            chunks = []
            async for chunk in svc.stream(messages=[{"role": "user", "content": "hi"}]):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.get_event_loop().run_until_complete(run())
        assert chunks == ["chunk1", "chunk2"]

    def test_stream_falls_back_on_rate_limit(self):
        """Rate limit error triggers fallback to the next model."""
        import asyncio

        from services.llm_service import LLMService

        primary = self._make_mock_provider("anthropic", "claude-opus-4", raises=Exception("429 Too Many Requests"))
        fallback = self._make_mock_provider("anthropic", "claude-sonnet-4")
        registry = self._make_registry([primary, fallback])

        svc = LLMService(registry=registry)

        async def run():
            chunks = []
            async for chunk in svc.stream(
                messages=[{"role": "user", "content": "hi"}],
                model_name="claude-opus-4",
                provider_name="anthropic",
            ):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.get_event_loop().run_until_complete(run())
        assert chunks == ["chunk1", "chunk2"]

    def test_stream_raises_on_non_rate_limit_error(self):
        """Non-rate-limit errors are re-raised immediately (no fallback)."""
        import asyncio

        from services.llm_service import LLMService

        primary = self._make_mock_provider("anthropic", "claude-opus-4", raises=Exception("Internal server error"))
        registry = self._make_registry([primary])
        svc = LLMService(registry=registry)

        async def run():
            chunks = []
            async for chunk in svc.stream(messages=[{"role": "user", "content": "hi"}]):
                chunks.append(chunk)

        try:
            asyncio.get_event_loop().run_until_complete(run())
            assert False, "Should have raised"
        except Exception as exc:
            assert "Internal server error" in str(exc)

    def test_stream_raises_when_all_fallbacks_exhausted(self):
        """RuntimeError raised when the full fallback chain is rate-limited."""
        import asyncio

        from services.llm_service import LLMService

        err = Exception("rate limit exceeded")
        p1 = self._make_mock_provider("anthropic", "claude-opus-4", raises=err)
        p2 = self._make_mock_provider("anthropic", "claude-sonnet-4", raises=err)
        p3 = self._make_mock_provider("anthropic", "claude-haiku-4", raises=err)
        registry = self._make_registry([p1, p2, p3])
        svc = LLMService(registry=registry)

        async def run():
            async for _ in svc.stream(
                messages=[{"role": "user", "content": "hi"}],
                model_name="claude-opus-4",
            ):
                pass

        try:
            asyncio.get_event_loop().run_until_complete(run())
            assert False, "Should have raised"
        except RuntimeError as exc:
            assert "exhausted" in str(exc).lower() or "rate limit" in str(exc).lower()
