# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Token and Cost Calculators Module

Contains classes for tracking token usage and calculating costs:
- TokenTracker: Tracks token usage across LLM calls
- CostCalculator: Calculates and estimates LLM usage costs

Extracted from llm_pattern_analyzer.py as part of Issue #381 refactoring.
"""

from datetime import datetime
from typing import Any, Dict, List

from backend.code_intelligence.llm_pattern_analysis.data_models import (
    CostEstimate,
    TokenUsage,
    UsagePattern,
)
from backend.code_intelligence.llm_pattern_analysis.types import UsagePatternType

# =============================================================================
# Token Tracker
# =============================================================================


class TokenTracker:
    """
    Tracks token usage across LLM calls for cost analysis.

    Provides real-time tracking and historical analysis of token consumption
    to identify optimization opportunities.
    """

    # Token cost estimates per 1K tokens (based on common pricing)
    DEFAULT_COSTS = {
        "gpt-4": {"prompt": 0.03, "completion": 0.06},
        "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
        "gpt-3.5-turbo": {"prompt": 0.0015, "completion": 0.002},
        "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
        "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
        "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
        "ollama": {"prompt": 0.0, "completion": 0.0},  # Local, no API cost
        "default": {"prompt": 0.001, "completion": 0.002},
    }

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
        hour_key = datetime.now().strftime("%Y-%m-%d-%H")
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
        costs = self.DEFAULT_COSTS.get("default")

        for model_key, model_costs in self.DEFAULT_COSTS.items():
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

    # Model pricing per 1K tokens (USD)
    MODEL_PRICING = {
        "gpt-4": {"prompt": 0.03, "completion": 0.06},
        "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
        "gpt-4o": {"prompt": 0.005, "completion": 0.015},
        "gpt-3.5-turbo": {"prompt": 0.0015, "completion": 0.002},
        "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
        "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
        "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
        "claude-sonnet-4": {"prompt": 0.003, "completion": 0.015},
        "ollama": {"prompt": 0.0, "completion": 0.0},
    }

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
        daily_completion_cost = (daily_calls * avg_completion / 1000) * pricing[
            "completion"
        ]
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
            pricing = cls.MODEL_PRICING.get(
                model, cls.MODEL_PRICING.get("gpt-3.5-turbo")
            )
            daily_calls = len(model_pats) * daily_call_multiplier
            avg_prompt, avg_completion = cls._estimate_avg_tokens(model_pats)

            estimate = cls._create_cost_estimate(
                model, daily_calls, avg_prompt, avg_completion, pricing
            )
            estimates.append(estimate)

        return estimates
