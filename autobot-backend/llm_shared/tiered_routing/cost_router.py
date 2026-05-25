# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
CostRouter — picks the cheapest available provider for the requested model class.

Issue #6595: Cost-aware routing strategy.

Uses MODEL_PRICING_PER_1M_TOKENS to score candidates and picks the one with the
lowest blended cost (0.3 * input + 0.7 * output, matching typical chat ratios).
When all candidates have zero cost (local models) it falls back to complexity
scoring so routing is still meaningful.
"""

from typing import Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import MODEL_PRICING_PER_1M_TOKENS

from .complexity_scorer import TaskComplexityScorer
from .tier_config import ComplexityResult, TierConfig, TierMetrics

logger = get_logger(__name__)

_BLENDED_INPUT_WEIGHT = 0.3
_BLENDED_OUTPUT_WEIGHT = 0.7


def _blended_cost(model: str) -> float:
    """Return blended cost per 1M tokens; 0.0 for local / unknown models."""
    pricing = MODEL_PRICING_PER_1M_TOKENS.get(model)
    if pricing is None:
        return 0.0
    return pricing["input"] * _BLENDED_INPUT_WEIGHT + pricing["output"] * _BLENDED_OUTPUT_WEIGHT


class CostRouter:
    """
    Selects the cheapest available model that meets the minimum quality tier.

    Candidates are the two models declared in TierConfig.  If both have zero
    cost (local Ollama models) the router falls back to complexity-based
    selection so the result is still sensible.
    """

    def __init__(self, config: TierConfig | None = None) -> None:
        self.config = config or TierConfig.from_config()
        self._scorer = TaskComplexityScorer(self.config)
        self._metrics = TierMetrics()
        self._total_requests = 0
        self._cost_savings_usd: float = 0.0

    def route(
        self,
        messages: List[Dict],
        requested_model: str | None = None,
    ) -> Tuple[str, ComplexityResult]:
        self._total_requests += 1

        # Score complexity to know minimum quality bar
        complexity = self._scorer.score(messages)

        candidates = self._candidates(complexity)
        selected = self._cheapest(candidates)

        # Track savings vs always using complex model
        complex_cost = _blended_cost(self.config.models.complex)
        selected_cost = _blended_cost(selected)
        if complex_cost > selected_cost:
            self._cost_savings_usd += (complex_cost - selected_cost) / 1_000_000

        result = ComplexityResult(
            score=complexity.score,
            factors=complexity.factors,
            tier="simple" if selected == self.config.models.simple else "complex",
            reasoning=f"CostRouter selected cheapest: {selected} "
            f"(blended ${_blended_cost(selected):.4f}/1M tokens)",
        )

        self._metrics.record(result)
        logger.debug("CostRouter: %s (blended cost $%.4f/1M)", selected, _blended_cost(selected))
        return selected, result

    def _candidates(self, complexity: ComplexityResult) -> List[str]:
        """Return eligible candidates given complexity floor."""
        if complexity.is_simple:
            return [self.config.models.simple, self.config.models.complex]
        return [self.config.models.complex]

    def _cheapest(self, candidates: List[str]) -> str:
        costs = {m: _blended_cost(m) for m in candidates}
        # If all costs are zero (local) pick the first candidate (simpler = cheaper in runtime)
        if all(c == 0.0 for c in costs.values()):
            return candidates[0]
        return min(costs, key=lambda m: costs[m])

    def get_metrics(self) -> Dict:
        base = self._metrics.to_dict()
        base["total_requests"] = self._total_requests
        base["estimated_cost_savings_usd"] = round(self._cost_savings_usd, 6)
        return base


__all__ = ["CostRouter"]
