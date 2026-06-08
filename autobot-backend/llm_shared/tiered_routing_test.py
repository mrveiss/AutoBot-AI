# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for tiered model routing.

Issue #748: Tiered Model Distribution Implementation.
"""

import pytest

from autobot_shared.ssot_config import DEFAULT_LLM_MODEL
from llm_shared.tiered_routing import (
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
        assert config.models.complex == DEFAULT_LLM_MODEL
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
                    print("Hello, World!")  # noqa: print
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

        assert model == DEFAULT_LLM_MODEL
        assert result.tier == "complex"

    def test_disabled_routing(self):
        """Test routing when disabled."""
        config = TierConfig(enabled=False)
        router = TieredModelRouter(config)
        messages = [{"role": "user", "content": "Simple question"}]

        model, result = router.route(messages)

        # Should return complex model when disabled
        assert model == DEFAULT_LLM_MODEL
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
        assert router.get_model_for_tier("complex") == DEFAULT_LLM_MODEL
        assert router.get_model_for_tier("long_context") == DEFAULT_LLM_MODEL

        with pytest.raises(ValueError):
            router.get_model_for_tier("unknown")

    def test_should_fallback(self, router):
        """Test fallback logic."""
        assert router.should_fallback("simple") is True
        assert router.should_fallback("complex") is False


class TestLongContextTier:
    """Tests for the long_context tier routing (GH#7349)."""

    @pytest.fixture
    def config(self):
        # Use complexity_threshold=2.5 so clearly technical messages score as complex.
        return TierConfig(
            models=TierModels(
                simple="gemma2:2b",
                complex=DEFAULT_LLM_MODEL,
                long_context=DEFAULT_LLM_MODEL,
            ),
            complexity_threshold=2.5,
            long_context_threshold=100,
        )

    @pytest.fixture
    def router(self, config):
        return TieredModelRouter(config)

    def _make_long_messages(self, token_count: int) -> list:
        """Build a message list whose total char count implies ~token_count tokens."""
        content = "word " * (token_count * 4)
        return [{"role": "user", "content": content}]

    def test_short_low_complexity_routes_to_simple(self, router):
        """Short input with low complexity → simple tier."""
        messages = [{"role": "user", "content": "What time is it?"}]
        model, result = router.route(messages)
        assert result.tier == "simple"
        assert model == "gemma2:2b"

    def test_short_high_complexity_routes_to_complex(self, router):
        """Short input with high complexity → complex tier."""
        messages = [
            {
                "role": "user",
                "content": (
                    "Design a microservices architecture using Kubernetes, "
                    "Redis caching, OAuth2 authentication, and JWT tokens."
                ),
            }
        ]
        model, result = router.route(messages)
        assert result.tier == "complex"
        assert model == DEFAULT_LLM_MODEL

    def test_long_low_complexity_routes_to_long_context(self, config, router):
        """Long input with low complexity → long_context tier (GH#7349)."""
        messages = self._make_long_messages(config.long_context_threshold + 10)
        model, result = router.route(messages)
        assert result.tier == "long_context"
        assert model == config.models.long_context
        assert result.is_long_context is True

    def test_long_high_complexity_routes_to_long_context(self, config, router):
        """Long input with high complexity → long_context tier takes precedence (GH#7349)."""
        long_prefix = "word " * ((config.long_context_threshold + 10) * 4)
        complex_suffix = (
            " Design a microservices architecture using Kubernetes, Redis, OAuth2, JWT, "
            "async functions, database migrations, and encryption algorithms."
        )
        messages = [{"role": "user", "content": long_prefix + complex_suffix}]
        model, result = router.route(messages)
        assert result.tier == "long_context"
        assert model == config.models.long_context

    def test_long_context_tier_not_triggered_below_threshold(self, config, router):
        """Input just below threshold does NOT route to long_context."""
        messages = self._make_long_messages(config.long_context_threshold - 10)
        model, result = router.route(messages)
        assert result.tier != "long_context"

    def test_long_context_custom_model(self):
        """long_context tier uses its configured model."""
        config = TierConfig(
            models=TierModels(
                simple="gemma2:2b",
                complex=DEFAULT_LLM_MODEL,
                long_context="jamba:large",
            ),
            long_context_threshold=50,
        )
        router = TieredModelRouter(config)
        messages = [{"role": "user", "content": "x " * (50 * 4 + 4)}]
        model, result = router.route(messages)
        assert result.tier == "long_context"
        assert model == "jamba:large"

    def test_metrics_track_long_context_requests(self, router, config):
        """Metrics correctly count long_context tier requests."""
        messages = self._make_long_messages(config.long_context_threshold + 10)
        router.route(messages)
        metrics = router.get_metrics()
        assert metrics["long_context_tier_requests"] == 1
        assert metrics["total_requests"] == 1

    def test_tier_models_default_long_context(self):
        """TierModels carries long_context field with a default."""
        models = TierModels()
        assert hasattr(models, "long_context")
        assert models.long_context == DEFAULT_LLM_MODEL

    def test_tier_config_default_long_context_threshold(self):
        """TierConfig has long_context_threshold defaulting to 16000."""
        config = TierConfig()
        assert config.long_context_threshold == 16000

    def test_complexity_result_is_long_context_property(self):
        """ComplexityResult.is_long_context returns True for long_context tier."""
        result = ComplexityResult(score=1.0, factors={}, tier="long_context", reasoning="long", input_tokens=20000)
        assert result.is_long_context is True
        assert result.is_simple is False
        assert result.is_complex is False


class TestSSMRouting:
    """Tests for SSM/linear-attention tier routing (GH#7353)."""

    SSM_MODEL = "mamba:3b"
    MESSAGES = [{"role": "user", "content": "Summarize this document."}]

    def _config_with_ssm(self, threshold: int = 2000) -> TierConfig:
        return TierConfig(
            models=TierModels(
                simple="gemma2:2b",
                complex=DEFAULT_LLM_MODEL,
                long_context=DEFAULT_LLM_MODEL,
                ssm=self.SSM_MODEL,
            ),
            ssm_output_token_threshold=threshold,
        )

    def test_high_expected_output_tokens_routes_to_ssm(self):
        """expected_output_tokens >= threshold routes to SSM model when registered."""
        config = self._config_with_ssm(threshold=2000)
        router = TieredModelRouter(config)
        model, result = router.route(self.MESSAGES, expected_output_tokens=2000)
        assert result.tier == "ssm"
        assert model == self.SSM_MODEL

    def test_above_threshold_routes_to_ssm(self):
        """expected_output_tokens well above threshold also routes to SSM."""
        config = self._config_with_ssm(threshold=2000)
        router = TieredModelRouter(config)
        model, result = router.route(self.MESSAGES, expected_output_tokens=5000)
        assert result.tier == "ssm"
        assert model == self.SSM_MODEL

    def test_below_threshold_does_not_route_to_ssm(self):
        """expected_output_tokens below threshold uses normal complexity routing."""
        config = self._config_with_ssm(threshold=2000)
        router = TieredModelRouter(config)
        model, result = router.route(self.MESSAGES, expected_output_tokens=1999)
        assert result.tier != "ssm"
        assert model != self.SSM_MODEL

    def test_no_ssm_model_registered_falls_back_to_transformer(self):
        """When no SSM model is registered, high output tokens fall through to transformer tier."""
        config = TierConfig(
            models=TierModels(simple="gemma2:2b", complex=DEFAULT_LLM_MODEL, ssm=""),
            ssm_output_token_threshold=2000,
        )
        router = TieredModelRouter(config)
        model, result = router.route(self.MESSAGES, expected_output_tokens=2000)
        assert result.tier != "ssm"
        assert model != ""

    def test_no_hint_no_ssm_routing(self):
        """No expected_output_tokens hint: no regression, normal routing applies."""
        config = self._config_with_ssm(threshold=2000)
        router = TieredModelRouter(config)
        model, result = router.route(self.MESSAGES)
        assert result.tier != "ssm"

    def test_metrics_track_ssm_requests(self):
        """TierMetrics records SSM tier requests."""
        config = self._config_with_ssm(threshold=2000)
        router = TieredModelRouter(config)
        router.route(self.MESSAGES, expected_output_tokens=2000)
        metrics = router.get_metrics()
        assert metrics["ssm_tier_requests"] == 1
        assert metrics["total_requests"] == 1

    def test_is_ssm_property(self):
        """ComplexityResult.is_ssm returns True for ssm tier."""
        result = ComplexityResult(score=1.0, factors={}, tier="ssm", reasoning="decode-heavy")
        assert result.is_ssm is True
        assert result.is_simple is False
        assert result.is_complex is False

    def test_ssm_tier_default_empty(self):
        """TierModels.ssm defaults to empty string (no SSM model registered)."""
        models = TierModels()
        assert models.ssm == ""

    def test_ssm_output_token_threshold_default(self):
        """TierConfig.ssm_output_token_threshold defaults to 2000."""
        config = TierConfig()
        assert config.ssm_output_token_threshold == 2000


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
