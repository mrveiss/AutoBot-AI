# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Comprehensive test suite for provider registry, switching, fallback chains,
and cost tracking - Issue #4341.

Tests verify:
- Provider registration and lookup
- Fallback chain ordering
- Per-conversation provider overrides
- Health check caching
- Provider switching at runtime
- Cost tracking per provider
- Model parameter enrichment
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock

import pytest

from llm_shared import BaseProvider, ProviderRegistry
from llm_shared.models import ChatMessage, LLMRequest, LLMResponse
from services.llm_cost_tracker import LLMCostTracker

# ============================================================================
# Mock Provider for Testing
# ============================================================================


class MockProvider(BaseProvider):
    """Mock provider for testing."""

    provider_name = "mock_test"

    def __init__(self, settings: Dict[str, Any] = None, fail_health: bool = False):
        super().__init__(settings)
        self.fail_health = fail_health
        self.chat_completion_called = False
        self.stream_completion_called = False

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        """Mock chat completion."""
        self.chat_completion_called = True
        self._total_requests += 1
        return LLMResponse(
            content="Mock response",
            model=request.model_name or "mock-model",
            provider=self.provider_name,
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )

    async def stream_completion(self, request: LLMRequest):
        """Mock stream completion."""
        self.stream_completion_called = True
        self._total_requests += 1
        yield "Mock "
        yield "stream "
        yield "response"

    async def is_available(self) -> bool:
        """Mock availability check."""
        if self.fail_health:
            return False
        return True

    async def list_models(self) -> List[str]:
        """Mock model list."""
        return ["mock-model-1", "mock-model-2"]


# ============================================================================
# Test Provider Registration
# ============================================================================


class TestProviderRegistration:
    """Test provider registration and lookup."""

    @pytest.mark.asyncio
    async def test_register_provider(self):
        """Test registering a provider."""
        registry = ProviderRegistry()
        provider = MockProvider()

        registry.register(provider)
        provider_list = registry.list_providers()
        assert any(p["name"] == "mock_test" for p in provider_list)

    @pytest.mark.asyncio
    async def test_register_duplicate_warns(self, caplog):
        """Test registering a duplicate provider logs warning."""
        registry = ProviderRegistry()
        provider1 = MockProvider()
        provider2 = MockProvider()

        registry.register(provider1)
        registry.register(provider2)

        # Check that warning was logged
        assert "Replacing existing provider" in caplog.text

    @pytest.mark.asyncio
    async def test_unregister_provider(self):
        """Test unregistering a provider."""
        registry = ProviderRegistry()
        provider = MockProvider()

        registry.register(provider)
        assert len(registry.list_providers()) > 0

        registry.unregister("mock_test")
        assert "mock_test" not in [p["name"] for p in registry.list_providers()]

    @pytest.mark.asyncio
    async def test_get_provider_by_name(self):
        """Test retrieving a provider by name."""
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)

        retrieved = await registry.get_provider("mock_test")
        assert retrieved is provider

    @pytest.mark.asyncio
    async def test_get_nonexistent_provider_returns_none(self):
        """Test retrieving nonexistent provider returns None."""
        registry = ProviderRegistry()

        retrieved = await registry.get_provider("nonexistent")
        assert retrieved is None


# ============================================================================
# Test Fallback Chains
# ============================================================================


class TestFallbackChains:
    """Test provider fallback chain logic."""

    @pytest.mark.asyncio
    async def test_fallback_chain_ordering(self):
        """Test that fallback chain respects priority order."""
        registry = ProviderRegistry()
        providers = [MockProvider() for _ in range(3)]
        providers[0].provider_name = "primary"
        providers[1].provider_name = "secondary"
        providers[2].provider_name = "tertiary"

        for p in providers:
            registry.register(p)

        chain = ["primary", "secondary", "tertiary"]
        registry.set_fallback_chain(chain)

        assert registry._fallback_chain == chain

    @pytest.mark.asyncio
    async def test_fallback_uses_primary_when_available(self):
        """Test fallback uses primary provider when available."""
        registry = ProviderRegistry()
        primary = MockProvider()
        secondary = MockProvider()
        primary.provider_name = "primary"
        secondary.provider_name = "secondary"

        registry.register(primary)
        registry.register(secondary)
        registry.set_fallback_chain(["primary", "secondary"])

        request = LLMRequest(
            messages=[ChatMessage(role="user", content="test")],
            model_name="test-model",
        )
        selected = await registry.get_provider_for_request(request=request)

        assert selected is primary

    @pytest.mark.asyncio
    async def test_fallback_skips_unavailable_provider(self):
        """Test fallback skips unavailable primary and uses secondary."""
        registry = ProviderRegistry()
        primary = MockProvider(fail_health=True)
        secondary = MockProvider()
        primary.provider_name = "primary"
        secondary.provider_name = "secondary"

        registry.register(primary)
        registry.register(secondary)
        registry.set_fallback_chain(["primary", "secondary"])

        request = LLMRequest(
            messages=[ChatMessage(role="user", content="test")],
            model_name="test-model",
        )
        selected = await registry.get_provider_for_request(request=request)

        assert selected is secondary

    @pytest.mark.asyncio
    async def test_fallback_returns_none_when_all_unavailable(self):
        """Test fallback returns None when all providers unavailable."""
        registry = ProviderRegistry()
        primary = MockProvider(fail_health=True)
        secondary = MockProvider(fail_health=True)
        primary.provider_name = "primary"
        secondary.provider_name = "secondary"

        registry.register(primary)
        registry.register(secondary)
        registry.set_fallback_chain(["primary", "secondary"])

        request = LLMRequest(
            messages=[ChatMessage(role="user", content="test")],
            model_name="test-model",
        )
        selected = await registry.get_provider_for_request(request=request)

        assert selected is None


# ============================================================================
# Test Per-Conversation Provider Overrides
# ============================================================================


class TestConversationOverrides:
    """Test per-conversation provider pinning."""

    @pytest.mark.asyncio
    async def test_set_conversation_provider(self):
        """Test setting provider for a conversation."""
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)

        registry.set_conversation_provider("conv-123", "mock_test")
        assert registry.get_conversation_provider_name("conv-123") == "mock_test"

    @pytest.mark.asyncio
    async def test_clear_conversation_provider(self):
        """Test clearing conversation override."""
        registry = ProviderRegistry()
        registry.set_conversation_provider("conv-123", "mock_test")
        registry.clear_conversation_provider("conv-123")

        assert registry.get_conversation_provider_name("conv-123") is None

    @pytest.mark.asyncio
    async def test_conversation_override_takes_priority(self):
        """Test conversation override takes priority over fallback chain."""
        registry = ProviderRegistry()
        primary = MockProvider()
        override = MockProvider()
        primary.provider_name = "primary"
        override.provider_name = "override"

        registry.register(primary)
        registry.register(override)
        registry.set_fallback_chain(["primary"])
        registry.set_conversation_provider("conv-123", "override")

        request = LLMRequest(
            messages=[ChatMessage(role="user", content="test")],
            model_name="test-model",
        )
        selected = await registry.get_provider_for_request(conversation_id="conv-123", request=request)

        assert selected is override


# ============================================================================
# Test Health Checks
# ============================================================================


class TestHealthChecks:
    """Test provider health monitoring."""

    @pytest.mark.asyncio
    async def test_health_check_caches_results(self):
        """Test health check results are cached."""
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)

        # First check
        result1 = await registry._check_health_cached("mock_test")
        # Mock the underlying provider to fail on next call
        provider.fail_health = True
        # Second check should return cached result (not failed)
        result2 = await registry._check_health_cached("mock_test")

        assert result1 == result2 == True

    @pytest.mark.asyncio
    async def test_health_check_all_parallel(self):
        """Test health_check_all runs in parallel."""
        registry = ProviderRegistry()
        providers = [MockProvider() for _ in range(3)]
        for i, p in enumerate(providers):
            p.provider_name = f"provider_{i}"
            registry.register(p)

        results = await registry.health_check_all()

        assert len(results) == 3
        assert all(results.values())  # All should be available

    @pytest.mark.asyncio
    async def test_health_check_handles_exceptions(self):
        """Test health check gracefully handles exceptions."""
        registry = ProviderRegistry()
        provider = MockProvider()
        provider.provider_name = "broken"
        registry.register(provider)

        # Mock is_available to raise exception
        provider.is_available = AsyncMock(side_effect=Exception("Connection error"))

        result = await registry._check_health_cached("broken")
        assert result is False


# ============================================================================
# Test Provider Selection
# ============================================================================


class TestProviderSelection:
    """Test provider selection logic."""

    @pytest.mark.asyncio
    async def test_explicit_provider_name_has_priority(self):
        """Test explicit provider name takes highest priority."""
        registry = ProviderRegistry()
        provider1 = MockProvider()
        provider2 = MockProvider()
        provider1.provider_name = "provider1"
        provider2.provider_name = "provider2"

        registry.register(provider1)
        registry.register(provider2)

        selected = await registry.get_provider_for_request(provider_name="provider2")
        assert selected is provider2

    @pytest.mark.asyncio
    async def test_request_enrichment_applies_model_params(self):
        """Test request enrichment applies model parameters."""
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)

        request = LLMRequest(
            messages=[ChatMessage(role="user", content="test")],
            model_name="gpt-4",
        )

        # Enrich should not raise even with minimal defaults
        enriched = registry.enrich_request(request, "mock_test")
        assert enriched is request


# ============================================================================
# Test Cost Tracking Integration
# ============================================================================


class TestCostTracking:
    """Test cost tracking per provider."""

    @pytest.mark.asyncio
    async def test_cost_tracker_initialization(self):
        """Test cost tracker initializes correctly."""
        tracker = LLMCostTracker()
        assert tracker is not None

    @pytest.mark.asyncio
    async def test_provider_stats_tracking(self):
        """Test provider statistics tracking."""
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)

        # Make a request
        request = LLMRequest(
            messages=[ChatMessage(role="user", content="test")],
            model_name="test-model",
        )
        await provider.chat_completion(request)

        stats = provider.get_stats()
        assert stats["total_requests"] == 1
        assert stats["provider"] == "mock_test"


# ============================================================================
# Test Provider API
# ============================================================================


class TestProviderIntrospection:
    """Test provider introspection and stats."""

    @pytest.mark.asyncio
    async def test_list_providers(self):
        """Test listing all registered providers."""
        registry = ProviderRegistry()
        providers = [MockProvider() for _ in range(2)]
        providers[0].provider_name = "provider1"
        providers[1].provider_name = "provider2"

        for p in providers:
            registry.register(p)

        provider_list = registry.list_providers()
        names = [p["name"] for p in provider_list]

        assert "provider1" in names
        assert "provider2" in names

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test retrieving registry statistics."""
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)
        registry.set_fallback_chain(["mock_test"])

        stats = registry.get_stats()
        assert "providers" in stats
        assert "fallback_chain" in stats
        assert "mock_test" in stats["providers"]


# ============================================================================
# Integration Tests
# ============================================================================


class TestProviderIntegration:
    """End-to-end integration tests for provider system."""

    @pytest.mark.asyncio
    async def test_chat_completion_through_registry(self):
        """Test complete chat completion flow through registry."""
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)
        registry.set_fallback_chain(["mock_test"])

        request = LLMRequest(
            messages=[ChatMessage(role="user", content="Hello")],
            model_name="mock-model",
        )

        selected = await registry.get_provider_for_request(request=request)
        assert selected is not None

        response = await selected.chat_completion(request)
        assert response.content == "Mock response"
        assert provider.chat_completion_called

    @pytest.mark.asyncio
    async def test_stream_completion_through_registry(self):
        """Test streaming completion through registry."""
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)

        request = LLMRequest(
            messages=[ChatMessage(role="user", content="Hello")],
            model_name="mock-model",
        )

        selected = await registry.get_provider_for_request(request=request)
        result = []
        async for chunk in selected.stream_completion(request):
            result.append(chunk)

        assert "".join(result) == "Mock stream response"
        assert provider.stream_completion_called

    @pytest.mark.asyncio
    async def test_runtime_provider_switching(self):
        """Test switching providers at runtime for same conversation."""
        registry = ProviderRegistry()
        provider1 = MockProvider()
        provider2 = MockProvider()
        provider1.provider_name = "primary"
        provider2.provider_name = "secondary"

        registry.register(provider1)
        registry.register(provider2)
        registry.set_fallback_chain(["primary", "secondary"])

        conv_id = "conv-xyz"

        # Initially use primary
        request = LLMRequest(
            messages=[ChatMessage(role="user", content="test")],
            model_name="test",
        )
        selected = await registry.get_provider_for_request(conversation_id=conv_id, request=request)
        assert selected is provider1

        # Switch to secondary
        registry.set_conversation_provider(conv_id, "secondary")
        selected = await registry.get_provider_for_request(conversation_id=conv_id, request=request)
        assert selected is provider2

        # Clear override, back to primary
        registry.clear_conversation_provider(conv_id)
        selected = await registry.get_provider_for_request(conversation_id=conv_id, request=request)
        assert selected is provider1


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_fallback_chain(self):
        """Test behavior with empty fallback chain."""
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)
        registry.set_fallback_chain([])

        request = LLMRequest(
            messages=[ChatMessage(role="user", content="test")],
            model_name="test",
        )
        # Should still find provider even without fallback chain
        selected = await registry.get_provider_for_request(request=request)
        assert selected is provider

    @pytest.mark.asyncio
    async def test_explicit_provider_takes_priority_over_conversation(self):
        """Test explicit provider request overrides conversation setting."""
        registry = ProviderRegistry()
        provider1 = MockProvider()
        provider2 = MockProvider()
        provider1.provider_name = "primary"
        provider2.provider_name = "secondary"

        registry.register(provider1)
        registry.register(provider2)
        registry.set_conversation_provider("conv-id", "secondary")

        # Explicit request should take priority
        selected = await registry.get_provider_for_request(provider_name="primary", conversation_id="conv-id")
        assert selected is provider1

    @pytest.mark.asyncio
    async def test_nonexistent_conversation_provider_fallback(self):
        """Test fallback when conversation references nonexistent provider."""
        registry = ProviderRegistry()
        provider = MockProvider()
        registry.register(provider)
        registry.set_conversation_provider("conv-id", "nonexistent")

        request = LLMRequest(
            messages=[ChatMessage(role="user", content="test")],
            model_name="test",
        )
        # Should gracefully fall back to available providers
        selected = await registry.get_provider_for_request(conversation_id="conv-id", request=request)
        assert selected is provider


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
