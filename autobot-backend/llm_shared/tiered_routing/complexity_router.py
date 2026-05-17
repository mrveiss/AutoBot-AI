# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
ComplexityRouter — routes by task-complexity score (original TieredModelRouter logic).

Issue #6595: Extracted from tier_router.py so it can be one pluggable strategy
alongside CostRouter and LatencyRouter.  tier_router.py retains backward-compat
aliases pointing here.
"""

from typing import Dict, List, Tuple

from autobot_shared.logging_manager import get_logger

from ..optimization.model_inspector import inspect_model
from .complexity_scorer import TaskComplexityScorer
from .tier_config import ComplexityResult, TierConfig, TierMetrics

logger = get_logger(__name__)


class ComplexityRouter:
    """Routes requests to model tiers based on complexity score (0-10 scale)."""

    def __init__(
        self,
        config: TierConfig | None = None,
        scorer: TaskComplexityScorer | None = None,
    ) -> None:
        self.config = config or TierConfig.from_config()
        self.scorer = scorer or TaskComplexityScorer(self.config)
        self._metrics = TierMetrics()

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def route(
        self,
        messages: List[Dict],
        requested_model: str | None = None,
    ) -> Tuple[str, ComplexityResult]:
        if not self.config.enabled:
            return self.config.models.complex, ComplexityResult(
                score=0.0,
                factors={},
                tier="complex",
                reasoning="Tiered routing disabled",
            )

        result = self.scorer.score(messages)
        selected_model = self.config.models.simple if result.is_simple else self.config.models.complex
        self._metrics.record(result)

        if self.config.logging.log_routing_decisions:
            self._log_decision(requested_model, selected_model, result)

        return selected_model, result

    def _log_decision(
        self,
        requested_model: str | None,
        selected_model: str,
        result: ComplexityResult,
    ) -> None:
        if requested_model and requested_model != selected_model:
            logger.info(
                "ComplexityRouter: %s -> %s (score=%.1f, tier=%s, reason=%s)",
                requested_model,
                selected_model,
                result.score,
                result.tier,
                result.reasoning,
            )
        else:
            logger.debug(
                "ComplexityRouter: selected %s (score=%.1f, tier=%s)",
                selected_model,
                result.score,
                result.tier,
            )

    def record_fallback(self) -> None:
        self._metrics.record_fallback()
        logger.warning("ComplexityRouter fallback triggered: simple -> complex tier")

    def get_metrics(self) -> Dict:
        return self._metrics.to_dict()

    def reset_metrics(self) -> None:
        self._metrics = TierMetrics()

    def get_model_for_tier(self, tier: str) -> str:
        if tier == "simple":
            return self.config.models.simple
        if tier == "complex":
            return self.config.models.complex
        raise ValueError(f"Unknown tier: {tier}")

    def should_fallback(self, tier: str) -> bool:
        return tier == "simple" and self.config.fallback_to_complex

    def model_fits_in_vram(self, model_name: str, available_vram_gb: float) -> bool:
        info = inspect_model(model_name)
        if info is None:
            return True
        fits = info.estimated_size_gb <= available_vram_gb
        if not fits:
            logger.warning(
                "VRAM check: %s needs ~%.1f GB, %.1f GB available",
                model_name,
                info.estimated_size_gb,
                available_vram_gb,
            )
        return fits


__all__ = ["ComplexityRouter"]
