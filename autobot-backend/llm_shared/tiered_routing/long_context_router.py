# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
LongContextRouter — routes large-prompt requests to SSM/hybrid models.

MVA-1386 / GH#7349: long_context tier for tiered_routing/.

Eligible models:
  architecture_family ∈ {ssm, hybrid} AND context_window_tokens > 32K.

Eligible requests:
  estimated input_tokens > LONG_CONTEXT_PROMPT_THRESHOLD (8 192).

When no eligible model is registered the router falls back to complexity-based
tier selection (simple / complex) so the request still completes.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from autobot_shared.logging_manager import get_logger

from ..model_param_registry import list_long_context_candidates
from .complexity_scorer import TaskComplexityScorer
from .tier_config import ComplexityResult, TierConfig, TierMetrics

logger = get_logger(__name__)

# Token threshold above which a request is a candidate for long_context routing.
LONG_CONTEXT_PROMPT_THRESHOLD: int = 8_192

# Minimum declared native context window for a model to qualify as eligible.
LONG_CONTEXT_MIN_WINDOW: int = 32_768


class LongContextRouter:
    """Routes prompts >8K tokens to SSM/hybrid long-context models.

    Routing priority chain inside route():
    1. Tiered routing disabled → complex tier (unchanged behaviour).
    2. Prompt > 8K tokens AND eligible SSM/hybrid model registered
       → long_context tier, no compression triggered.
    3. Fallback → complexity-based tier (simple / complex).
    """

    def __init__(
        self,
        config: TierConfig | None = None,
        scorer: TaskComplexityScorer | None = None,
    ) -> None:
        self.config = config or TierConfig.from_config()
        self.scorer = scorer or TaskComplexityScorer(self.config)
        self._metrics = TierMetrics()
        self._eligible_cache: Optional[List[str]] = None

    # ------------------------------------------------------------------
    # RoutingStrategy protocol
    # ------------------------------------------------------------------

    def route(
        self,
        messages: List[Dict],
        requested_model: str | None = None,
    ) -> Tuple[str, ComplexityResult]:
        """Select a model for *messages*.

        Args:
            messages:        Conversation messages to analyse.
            requested_model: Model originally requested by the caller.

        Returns:
            (selected_model, result) tuple.
        """
        if not self.config.enabled:
            return self.config.models.complex, ComplexityResult(
                score=0.0,
                factors={},
                tier="complex",
                reasoning="Tiered routing disabled",
            )

        result = self.scorer.score(messages)

        if result.input_tokens > LONG_CONTEXT_PROMPT_THRESHOLD:
            model = self._pick_long_context_model()
            if model is not None:
                lc_result = ComplexityResult(
                    score=result.score,
                    factors=result.factors,
                    tier="long_context",
                    reasoning=(
                        f"Prompt tokens ({result.input_tokens}) exceed "
                        f"long_context threshold ({LONG_CONTEXT_PROMPT_THRESHOLD}); "
                        f"routed to SSM/hybrid model {model!r}"
                    ),
                    input_tokens=result.input_tokens,
                )
                self._metrics.record(lc_result)
                self._log_decision(requested_model, model, lc_result)
                return model, lc_result

            logger.warning(
                "LongContextRouter: prompt has %d tokens but no eligible "
                "SSM/hybrid model (context_window > %d) is registered; "
                "falling back to complexity routing.",
                result.input_tokens,
                LONG_CONTEXT_MIN_WINDOW,
            )

        # Complexity-based fallback
        selected = self.config.models.simple if result.is_simple else self.config.models.complex
        self._metrics.record(result)
        self._log_decision(requested_model, selected, result)
        return selected, result

    def get_metrics(self) -> Dict:
        """Return routing metrics dict."""
        return self._metrics.to_dict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _pick_long_context_model(self) -> Optional[str]:
        """Return the eligible model with the largest declared context window."""
        eligible = self._get_eligible_models()
        return eligible[0] if eligible else None

    def _get_eligible_models(self) -> List[str]:
        """Return (cached) list of eligible SSM/hybrid models, sorted by window size."""
        if self._eligible_cache is None:
            self._eligible_cache = list_long_context_candidates(
                min_context_window=LONG_CONTEXT_MIN_WINDOW,
            )
            logger.info(
                "LongContextRouter: eligible long-context model(s): %s",
                self._eligible_cache or "none",
            )
        return self._eligible_cache

    def invalidate_cache(self) -> None:
        """Force re-discovery of eligible models on the next route() call."""
        self._eligible_cache = None

    def _log_decision(
        self,
        requested_model: str | None,
        selected_model: str,
        result: ComplexityResult,
    ) -> None:
        if requested_model and requested_model != selected_model:
            logger.info(
                "LongContextRouter: %s → %s (tokens=%d, tier=%s)",
                requested_model,
                selected_model,
                result.input_tokens,
                result.tier,
            )
        else:
            logger.debug(
                "LongContextRouter: selected %s (tokens=%d, tier=%s)",
                selected_model,
                result.input_tokens,
                result.tier,
            )


__all__ = [
    "LongContextRouter",
    "LONG_CONTEXT_PROMPT_THRESHOLD",
    "LONG_CONTEXT_MIN_WINDOW",
]
