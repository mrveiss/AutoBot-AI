# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tiered Model Router - Routes requests to appropriate model tiers.

Issue #748: Tiered Model Distribution Implementation.

Selects the appropriate model tier based on task complexity scoring.
"""

import logging
from typing import Dict, List, Optional, Tuple

from .complexity_scorer import TaskComplexityScorer
from .tier_config import ComplexityResult, TierConfig, TierMetrics

logger = logging.getLogger(__name__)


class TieredModelRouter:
    """
    Routes LLM requests to appropriate model tiers based on complexity.

    Uses TaskComplexityScorer to evaluate request complexity and routes:
    - Simple requests (score < threshold) to lightweight model
    - Complex requests (score >= threshold) to capable model

    Provides fallback support and metrics tracking.
    """

    def __init__(
        self,
        config: Optional[TierConfig] = None,
        scorer: Optional[TaskComplexityScorer] = None,
    ):
        """
        Initialize tiered model router.

        Args:
            config: Tier configuration (loads from SSOT if None)
            scorer: Complexity scorer (creates new if None)
        """
        self.config = config or TierConfig.from_config()
        self.scorer = scorer or TaskComplexityScorer(self.config)
        self._metrics = TierMetrics()

    @property
    def enabled(self) -> bool:
        """Check if tiered routing is enabled."""
        return self.config.enabled

    def route(
        self,
        messages: List[Dict],
        requested_model: Optional[str] = None,
    ) -> Tuple[str, ComplexityResult]:
        """
        Route a request to the appropriate model tier.

        Args:
            messages: List of message dicts to analyze
            requested_model: Originally requested model (for logging)

        Returns:
            Tuple of (selected_model, complexity_result)
        """
        if not self.config.enabled:
            # Return default complex model if routing disabled
            return self.config.models.complex, ComplexityResult(
                score=0.0,
                factors={},
                tier="complex",
                reasoning="Tiered routing disabled",
            )

        # Score the request
        result = self.scorer.score(messages)

        # Select model based on tier
        if result.is_simple:
            selected_model = self.config.models.simple
        else:
            selected_model = self.config.models.complex

        # Record metrics
        self._metrics.record(result)

        # Log routing decision
        if self.config.logging.log_routing_decisions:
            self._log_routing_decision(requested_model, selected_model, result)

        return selected_model, result

    def _log_routing_decision(
        self,
        requested_model: Optional[str],
        selected_model: str,
        result: ComplexityResult,
    ) -> None:
        """Log the routing decision for observability."""
        if requested_model and requested_model != selected_model:
            logger.info(
                "Tiered routing: %s -> %s (score=%.1f, tier=%s, reason=%s)",
                requested_model,
                selected_model,
                result.score,
                result.tier,
                result.reasoning,
            )
        else:
            logger.debug(
                "Tiered routing: selected %s (score=%.1f, tier=%s)",
                selected_model,
                result.score,
                result.tier,
            )

    def record_fallback(self) -> None:
        """
        Record when a fallback from simple to complex tier occurred.

        Call this when the simple tier model fails and falls back to complex.
        """
        self._metrics.record_fallback()
        logger.warning("Tiered routing fallback triggered: simple -> complex tier")

    def get_metrics(self) -> Dict:
        """
        Get routing metrics for monitoring.

        Returns:
            Dictionary with routing statistics
        """
        return self._metrics.to_dict()

    def reset_metrics(self) -> None:
        """Reset all routing metrics."""
        self._metrics = TierMetrics()

    def get_model_for_tier(self, tier: str) -> str:
        """
        Get the model name for a specific tier.

        Args:
            tier: "simple" or "complex"

        Returns:
            Model name for the tier

        Raises:
            ValueError: If tier is not recognized
        """
        if tier == "simple":
            return self.config.models.simple
        elif tier == "complex":
            return self.config.models.complex
        else:
            raise ValueError(f"Unknown tier: {tier}")

    def should_fallback(self, tier: str) -> bool:
        """
        Check if fallback should be attempted for a tier.

        Args:
            tier: Current tier that failed

        Returns:
            True if fallback to complex tier should be attempted
        """
        return tier == "simple" and self.config.fallback_to_complex


# Module-level singleton for easy access
_router_instance: Optional[TieredModelRouter] = None


def get_tiered_router(
    config: Optional[TierConfig] = None,
    force_new: bool = False,
) -> TieredModelRouter:
    """
    Get or create the tiered model router singleton.

    Args:
        config: Optional configuration (only used on first call or force_new)
        force_new: Force creation of new instance

    Returns:
        TieredModelRouter instance
    """
    global _router_instance

    if _router_instance is None or force_new:
        _router_instance = TieredModelRouter(config)

    return _router_instance


__all__ = [
    "TieredModelRouter",
    "get_tiered_router",
]
