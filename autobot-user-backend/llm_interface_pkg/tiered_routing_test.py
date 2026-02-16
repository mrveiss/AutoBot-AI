# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for tiered model routing.

Issue #748: Tiered Model Distribution Implementation.
"""

import pytest

from backend.llm_interface_pkg.tiered_routing import (
    ComplexityResult,
    TaskComplexityScorer,
    TierConfig,
    TieredModelRouter,
    TierMetrics,
    TierModels,
)


class TestTierConfig:
    """Tests for TierConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = TierConfig()
        assert config.enabled is True
        assert config.complexity_threshold == 3.0
        assert config.models.simple == "gemma2:2b"
        assert config.models.complex == "mistral:7b-instruct"
        assert config.fallback_to_complex is True

    def test_custom_config(self):
        """Test custom configuration values."""
        config = TierConfig(
            enabled=False,
            complexity_threshold=5.0,
            models=TierModels(simple="phi:2.7b", complex="llama3:8b"),
        )
        assert config.enabled is False
        assert config.complexity_threshold == 5.0
        assert config.models.simple == "phi:2.7b"
        assert config.models.complex == "llama3:8b"


class TestComplexityResult:
    """Tests for ComplexityResult dataclass."""

    def test_simple_tier(self):
        """Test simple tier result."""
        result = ComplexityResult(
            score=1.5,
            factors={"length": 0.5, "code": 0.0},
            tier="simple",
            reasoning="Low complexity",
        )
        assert result.is_simple is True
        assert result.is_complex is False

    def test_complex_tier(self):
        """Test complex tier result."""
        result = ComplexityResult(
            score=7.5,
            factors={"length": 2.0, "code": 3.0},
            tier="complex",
            reasoning="High complexity",
        )
        assert result.is_simple is False
        assert result.is_complex is True


class TestTierMetrics:
    """Tests for TierMetrics tracking."""

    def test_record_simple_request(self):
        """Test recording simple tier request."""
        metrics = TierMetrics()
        result = ComplexityResult(score=1.5, factors={}, tier="simple", reasoning="")

        metrics.record(result)

        assert metrics.total_requests == 1
        assert metrics.simple_tier_requests == 1
        assert metrics.complex_tier_requests == 0
        assert metrics.avg_simple_score == 1.5

    def test_record_complex_request(self):
        """Test recording complex tier request."""
        metrics = TierMetrics()
        result = ComplexityResult(score=7.5, factors={}, tier="complex", reasoning="")

        metrics.record(result)

        assert metrics.total_requests == 1
        assert metrics.simple_tier_requests == 0
        assert metrics.complex_tier_requests == 1
        assert metrics.avg_complex_score == 7.5

    def test_to_dict(self):
        """Test metrics dictionary export."""
        metrics = TierMetrics()
        result = ComplexityResult(score=1.5, factors={}, tier="simple", reasoning="")
        metrics.record(result)

        data = metrics.to_dict()

        assert "simple_tier_requests" in data
        assert "complex_tier_requests" in data
        assert "simple_tier_percentage" in data
        assert data["simple_tier_percentage"] == 100.0


class TestTaskComplexityScorer:
    """Tests for TaskComplexityScorer."""

    @pytest.fixture
    def scorer(self):
        """Create scorer with default config."""
        config = TierConfig()
        return TaskComplexityScorer(config)

    def test_empty_messages(self, scorer):
        """Test scoring empty messages."""
        result = scorer.score([])
        assert result.score == 0.0
        assert result.tier == "simple"

    def test_simple_question(self, scorer):
        """Test scoring a simple question."""
        messages = [{"role": "user", "content": "What is Python?"}]
        result = scorer.score(messages)

        assert result.score < 3.0
        assert result.tier == "simple"

    def test_complex_code_request(self, scorer):
        """Test scoring a complex code request."""
        messages = [
            {
                "role": "user",
                "content": """
                Write a Python async function that:
                1. Connects to a Redis database
                2. Implements caching with TTL
                3. Uses connection pooling
                4. Handles authentication errors

                ```python
                async def get_cached_data(key):
                    # Implementation here
                    pass
                ```
                """,
            }
        ]
        result = scorer.score(messages)

        # Should be complex due to code patterns, technical terms, multi-step
        assert result.score >= 3.0
        assert result.tier == "complex"

    def test_technical_terms_detection(self, scorer):
        """Test detection of technical terminology."""
        messages = [
            {
                "role": "user",
                "content": "Explain how to implement OAuth authentication "
                "with JWT tokens and handle CORS issues in a REST API.",
            }
        ]
        result = scorer.score(messages)

        # Should detect: oauth, authentication, jwt, cors, rest, api
        assert result.factors["technical"] >= 2.0

    def test_code_detection(self, scorer):
        """Test detection of code patterns."""
        messages = [
            {
                "role": "user",
                "content": """
                ```python
                def hello_world():
                    print("Hello, World!")
                ```
                """,
            }
        ]
        result = scorer.score(messages)

        # Should detect code block and function definition
        assert result.factors["code"] >= 1.0

    def test_multi_step_detection(self, scorer):
        """Test detection of multi-step instructions."""
        messages = [
            {
                "role": "user",
                "content": "First, create a database. Then, add the tables. "
                "After that, seed the data. Finally, run migrations.",
            }
        ]
        result = scorer.score(messages)

        # Should detect multi-step indicators
        assert result.factors["multistep"] >= 2.0


class TestTieredModelRouter:
    """Tests for TieredModelRouter."""

    @pytest.fixture
    def router(self):
        """Create router with default config."""
        config = TierConfig()
        return TieredModelRouter(config)

    def test_route_simple_request(self, router):
        """Test routing a simple request."""
        messages = [{"role": "user", "content": "What time is it?"}]

        model, result = router.route(messages)

        assert model == "gemma2:2b"
        assert result.tier == "simple"

    def test_route_complex_request(self, router):
        """Test routing a complex request."""
        messages = [
            {
                "role": "user",
                "content": "Design a microservices architecture with "
                "Kubernetes deployment, Redis caching, and OAuth2 "
                "authentication using JWT tokens.",
            }
        ]

        model, result = router.route(messages)

        assert model == "mistral:7b-instruct"
        assert result.tier == "complex"

    def test_disabled_routing(self):
        """Test routing when disabled."""
        config = TierConfig(enabled=False)
        router = TieredModelRouter(config)
        messages = [{"role": "user", "content": "Simple question"}]

        model, result = router.route(messages)

        # Should return complex model when disabled
        assert model == "mistral:7b-instruct"
        assert "disabled" in result.reasoning.lower()

    def test_metrics_tracking(self, router):
        """Test metrics are tracked correctly."""
        messages = [{"role": "user", "content": "What is 2+2?"}]
        router.route(messages)

        metrics = router.get_metrics()

        assert metrics["total_requests"] == 1
        assert metrics["simple_tier_requests"] >= 0

    def test_get_model_for_tier(self, router):
        """Test getting model for specific tier."""
        assert router.get_model_for_tier("simple") == "gemma2:2b"
        assert router.get_model_for_tier("complex") == "mistral:7b-instruct"

        with pytest.raises(ValueError):
            router.get_model_for_tier("unknown")

    def test_should_fallback(self, router):
        """Test fallback logic."""
        assert router.should_fallback("simple") is True
        assert router.should_fallback("complex") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
