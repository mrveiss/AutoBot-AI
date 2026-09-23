# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Token and Cost Calculators Module

Contains classes for tracking token usage and calculating costs:
- TokenTracker: Tracks token usage across LLM calls
- CostCalculator: Calculates and estimates LLM usage costs

Extracted from llm_pattern_analyzer.py as part of Issue #381 refactoring.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from code_intelligence.llm_pattern_analysis.data_models import (
    CostEstimate,
    TokenUsage,
    UsagePattern,
)
from code_intelligence.llm_pattern_analysis.types import UsagePatternType
from constants.model_constants import OPENAI_GPT35_TURBO
from llm_shared.pricing.sync_cache import PricingCacheCold, get_cached_snapshot

logger = get_logger(__name__)

#: The two entries that are **not** models, and so cannot come from a catalogue
#: of models (#16230). `TokenTracker._calculate_cost` reads `"default"` when a
#: model name matches nothing; dropping it would make every unknown model free,
#: which is the silent-$0 failure #15860 was filed over. `"ollama"` is the
#: locally-served family, free by construction — the same rule
#: `autobot_shared.local_models.is_local_model` applies on the billing path.
#:
#: These are estimation constants for a projection surface, not prices charged
#: by anyone, and they are named here rather than hidden in a table so a reader
#: can see that the catalogue supplies every real price and these two supply
#: neither.
_NON_MODEL_RATES_PER_1K: Dict[str, Dict[str, float]] = {
    "ollama": {"prompt": 0.0, "completion": 0.0},
    "default": {"prompt": 0.001, "completion": 0.002},
}


def live_pricing_per_1k() -> Dict[str, Dict[str, float]]:
    """The live catalogue as per-1K ``{"prompt", "completion"}`` rates.

    Read per call, never bound at class-definition time (#16230). The old
    `MODEL_PRICING_PER_1K_TOKENS` was a module-level comprehension captured
    into `TokenTracker.DEFAULT_COSTS` and `CostCalculator.MODEL_PRICING` when
    this module was first imported, so a price that changed in Redis an hour
    later could never reach either of them — the process would have to restart
    to cost anything correctly.

    The catalogue is per 1M tokens; both consumers here divide by 1000 and read
    ``prompt``/``completion``. That conversion and that rename happen here, once
    and visibly, rather than at each of the four call sites.

    A cold or stale cache degrades to the non-model rates alone and says so.
    This is a projection surface, not a billing one, so it estimates rather than
    refusing — but an estimate computed off a catalogue that is not there is a
    different thing from one computed off a catalogue that is, and the log line
    is what tells them apart.
    """
    try:
        snapshot = get_cached_snapshot()
    except PricingCacheCold as exc:
        logger.warning(
            "llm_pattern_analysis: pricing cache unavailable (%s); cost projections fall back to "
            "the default estimate rate for every model (#16230)",
            exc,
        )
        return dict(_NON_MODEL_RATES_PER_1K)

    per_1k = {
        model_id: {
            "prompt": price.input_per_1m / 1000,
            "completion": price.output_per_1m / 1000,
        }
        for model_id, price in snapshot.items()
    }
    # Non-model entries last: a catalogue must never be able to shadow the
    # "default" fallback, or an unknown model would be priced as whatever
    # vendor happened to publish a model literally called "default".
    per_1k.update(_NON_MODEL_RATES_PER_1K)
    return per_1k


# =============================================================================
# Token Tracker
# =============================================================================


class TokenTracker:
    """
    Tracks token usage across LLM calls for cost analysis.

    Provides real-time tracking and historical analysis of token consumption
    to identify optimization opportunities.
    """

    # #16230: `DEFAULT_COSTS = MODEL_PRICING_PER_1K_TOKENS` used to live here,
    # bound once at import. Nothing outside this module ever read it, so it is
    # gone rather than re-exposed as a property — the rates are read per call
    # from `live_pricing_per_1k()` at the one place that uses them.

    def __init__(self):
        """Initialize the token tracker."""
        self.usage_history: List[TokenUsage] = []
        self.model_usage: Dict[str, TokenUsage] = {}
        self.hourly_usage: Dict[str, int] = {}
        self.total_cost: float = 0.0

    def track_usage(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> TokenUsage:
        """
        Track token usage for an LLM call.

        Args:
            model: The model used for the call
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Number of tokens in the completion

        Returns:
            TokenUsage record with cost estimation
        """
        total_tokens = prompt_tokens + completion_tokens
        cost = self._calculate_cost(model, prompt_tokens, completion_tokens)

        usage = TokenUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=cost,
        )

        self.usage_history.append(usage)
        self.total_cost += cost

        # Update model-specific tracking
        if model not in self.model_usage:
            self.model_usage[model] = TokenUsage()
        self.model_usage[model].prompt_tokens += prompt_tokens
        self.model_usage[model].completion_tokens += completion_tokens
        self.model_usage[model].total_tokens += total_tokens
        self.model_usage[model].estimated_cost_usd += cost

        # Update hourly tracking
        hour_key = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d-%H")
        self.hourly_usage[hour_key] = self.hourly_usage.get(hour_key, 0) + total_tokens

        return usage

    def _calculate_cost(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> float:
        """Calculate cost for token usage."""
        model_lower = model.lower()
        # One read: the live view is rebuilt per call, so scanning a second
        # copy could match against a catalogue that had changed underneath.
        rates = live_pricing_per_1k()
        costs = rates["default"]

        for model_key, model_costs in rates.items():
            if model_key in model_lower:
                costs = model_costs
                break

        prompt_cost = (prompt_tokens / 1000) * costs["prompt"]
        completion_cost = (completion_tokens / 1000) * costs["completion"]

        return prompt_cost + completion_cost

    def get_usage_summary(self) -> Dict[str, Any]:
        """Get a summary of token usage."""
        if not self.usage_history:
            return {
                "total_calls": 0,
                "total_tokens": 0,
                "total_cost_usd": 0.0,
                "avg_tokens_per_call": 0,
            }

        total_tokens = sum(u.total_tokens for u in self.usage_history)
        return {
            "total_calls": len(self.usage_history),
            "total_tokens": total_tokens,
            "total_cost_usd": self.total_cost,
            "avg_tokens_per_call": total_tokens // len(self.usage_history),
            "model_breakdown": {
                model: {
                    "tokens": usage.total_tokens,
                    "cost_usd": usage.estimated_cost_usd,
                }
                for model, usage in self.model_usage.items()
            },
        }


# =============================================================================
# Cost Calculator
# =============================================================================


class CostCalculator:
    """
    Calculates and estimates LLM usage costs.

    Provides cost projections and optimization potential analysis.
    """

    # #16230: `MODEL_PRICING = MODEL_PRICING_PER_1K_TOKENS` used to live here,
    # bound at class-definition time. Read per call from `live_pricing_per_1k()`
    # at its one call site instead; nothing outside this module read the
    # attribute, so nothing needs it to still exist.

    @classmethod
    def _estimate_avg_tokens(cls, model_pats: List[UsagePattern]) -> tuple:
        """
        Estimate average token counts based on pattern types.

        Args:
            model_pats: List of patterns for a specific model

        Returns:
            Tuple of (avg_prompt_tokens, avg_completion_tokens)

        Issue #620.
        """
        avg_prompt = 500
        avg_completion = 300

        for pat in model_pats:
            if pat.pattern_type == UsagePatternType.EMBEDDING:
                avg_prompt = 200
                avg_completion = 0
            elif pat.pattern_type == UsagePatternType.CODE_GENERATION:
                avg_prompt = 800
                avg_completion = 600

        return avg_prompt, avg_completion

    @classmethod
    def _create_cost_estimate(
        cls,
        model: str,
        daily_calls: int,
        avg_prompt: int,
        avg_completion: int,
        pricing: Dict[str, float],
    ) -> CostEstimate:
        """
        Create a CostEstimate for a model.

        Args:
            model: Model name
            daily_calls: Estimated daily API calls
            avg_prompt: Average prompt tokens
            avg_completion: Average completion tokens
            pricing: Pricing dict with prompt/completion costs

        Returns:
            CostEstimate instance

        Issue #620.
        """
        daily_prompt_cost = (daily_calls * avg_prompt / 1000) * pricing["prompt"]
        daily_completion_cost = (daily_calls * avg_completion / 1000) * pricing["completion"]
        daily_cost = daily_prompt_cost + daily_completion_cost

        return CostEstimate(
            model=model,
            daily_calls=daily_calls,
            avg_prompt_tokens=avg_prompt,
            avg_completion_tokens=avg_completion,
            cost_per_1k_prompt=pricing["prompt"],
            cost_per_1k_completion=pricing["completion"],
            daily_cost_usd=daily_cost,
            monthly_cost_usd=daily_cost * 30,
            optimization_potential_percent=25.0,
            optimized_monthly_cost_usd=daily_cost * 30 * 0.75,
        )

    @classmethod
    def estimate_costs(
        cls,
        patterns: List[UsagePattern],
        daily_call_multiplier: int = 100,
    ) -> List[CostEstimate]:
        """
        Estimate costs based on detected patterns.

        Args:
            patterns: List of usage patterns
            daily_call_multiplier: Estimated daily calls per pattern

        Returns:
            List of cost estimates by model
        """
        estimates = []

        model_patterns: Dict[str, List[UsagePattern]] = {}
        for pattern in patterns:
            model = pattern.model_used or "unknown"
            if model not in model_patterns:
                model_patterns[model] = []
            model_patterns[model].append(pattern)

        for model, model_pats in model_patterns.items():
            # One read per model, not two: `cls.MODEL_PRICING.get(...)` twice
            # used to hit the same frozen dict, but each call now rebuilds the
            # snapshot view, and the fallback must come from the same catalogue
            # the lookup missed in. The final `["default"]` is what keeps a cold
            # cache from returning None here and crashing the projection — the
            # old code could not reach that state because its table was a literal.
            catalogue = live_pricing_per_1k()
            pricing = catalogue.get(model) or catalogue.get(OPENAI_GPT35_TURBO) or catalogue["default"]
            daily_calls = len(model_pats) * daily_call_multiplier
            avg_prompt, avg_completion = cls._estimate_avg_tokens(model_pats)

            estimate = cls._create_cost_estimate(model, daily_calls, avg_prompt, avg_completion, pricing)
            estimates.append(estimate)

        return estimates
