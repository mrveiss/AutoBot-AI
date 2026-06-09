# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Counterfactual Reasoner for Decision Prediction

Predicts outcomes ("what if?") for decision interventions without executing them.
Uses execution history, causal knowledge, and fallback heuristics.

Supports:
- Empirical prediction: Based on similar historical decisions
- Causal prediction: Using known cause-effect relationships
- Heuristic fallback: Rules-based defaults when no data exists
"""

import json
import time
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

from .models import DecisionContext, InterventionOutcome

logger = get_logger(__name__)


class CounterfactualReasoner:
    """Predicts consequences of decision options before committing.

    Three-tier prediction strategy:
    1. Empirical: Query execution history for similar decisions
    2. Causal: Use known causal patterns (if available from Tier 2 RAG)
    3. Heuristic: Fall back to rule-based defaults
    """

    # Redis keys for execution history (single source of truth)
    EXECUTION_HISTORY_KEY = "decision:execution_history:{decision_type}"
    CAUSAL_PATTERNS_KEY = "causal:patterns:{action_type}"
    SIDE_EFFECTS_KEY = "decision:side_effects:{action_type}"

    def __init__(self):
        """Initialize counterfactual reasoner."""
        self.redis = None
        logger.info("CounterfactualReasoner initialized")

    async def _get_redis(self):
        """Lazy-load async Redis client."""
        if self.redis is None:
            self.redis = await get_async_redis_client()
        return self.redis

    async def what_if(
        self,
        decision_option: str,
        context: DecisionContext,
        action_details: Dict[str, Any],
    ) -> InterventionOutcome:
        """Predict outcome of a decision option (counterfactual simulation).

        Args:
            decision_option: Action name (e.g., "retry", "escalate", "automate")
            context: Decision context (for similarity matching)
            action_details: Full action dict from available_actions

        Returns:
            InterventionOutcome with predicted success rate, side effects, confidence
        """
        try:
            redis = await self._get_redis()

            # 1. Try empirical prediction first (fastest, most accurate)
            empirical_outcome = await self._predict_empirical(decision_option, context, redis)
            if empirical_outcome:
                return empirical_outcome

            # 2. Try causal prediction (if patterns exist)
            causal_outcome = await self._predict_causal(decision_option, context, redis)
            if causal_outcome:
                return causal_outcome

            # 3. Fall back to heuristics
            heuristic_outcome = self._predict_heuristic(decision_option, context, action_details)
            return heuristic_outcome

        except Exception as e:
            logger.error(f"Counterfactual prediction failed: {e}")
            # Return conservative prediction on error
            return self._predict_heuristic(decision_option, context, action_details)

    async def _predict_empirical(
        self,
        decision_option: str,
        context: DecisionContext,
        redis: Any,
    ) -> InterventionOutcome | None:
        """Predict based on execution history (what happened before?).

        Queries similar past decisions and aggregates their outcomes.
        Success rate = (successes / total_similar) with temporal decay.
        """
        try:
            # Look up execution history for this decision type + option
            history_key = self.EXECUTION_HISTORY_KEY.format(decision_type=context.decision_type.value)
            history_json = await redis.get(history_key)

            if not history_json:
                return None

            history = json.loads(history_json)
            similar_decisions = [h for h in history if h.get("option") == decision_option]

            if not similar_decisions or len(similar_decisions) < 2:
                return None

            # Aggregate outcomes with temporal decay
            success_count = 0
            total_count = len(similar_decisions)
            side_effects_aggregate: Dict[str, int] = {}
            latency_samples = []

            current_time = time.time()
            for decision in similar_decisions:
                age_days = (current_time - decision.get("timestamp", 0)) / 86400
                decay_weight = 0.95 ** min(age_days, 30)  # Cap at 30 days

                if decision.get("succeeded", False):
                    success_count += decay_weight

                # Aggregate side effects
                for effect in decision.get("side_effects", []):
                    effect_key = effect.get("type", "unknown")
                    side_effects_aggregate[effect_key] = side_effects_aggregate.get(effect_key, 0) + 1

                # Collect latency
                if decision.get("latency_ms"):
                    latency_samples.append(decision["latency_ms"])

            success_rate = success_count / max(total_count, 1)
            confidence = min(0.9, 0.5 + (total_count / 20.0))  # Higher for more data

            side_effects = [
                {
                    "type": effect_type,
                    "frequency": count / total_count,
                    "severity": self._assess_side_effect_severity(effect_type),
                }
                for effect_type, count in side_effects_aggregate.items()
            ]

            avg_latency = int(sum(latency_samples) / len(latency_samples)) if latency_samples else None

            return InterventionOutcome(
                option=decision_option,
                predicted_success_rate=min(success_rate, 1.0),
                side_effects=side_effects,
                confidence=confidence,
                reasoning=f"Empirical: {total_count} similar decisions, "
                f"{success_count:.1f} succeeded (decay-weighted)",
                prediction_source="empirical",
                supporting_evidence=[{"type": "history_count", "value": total_count}],
                estimated_latency_ms=avg_latency,
            )

        except Exception as e:
            logger.warning(f"Empirical prediction failed: {e}")
            return None

    async def _predict_causal(
        self,
        decision_option: str,
        context: DecisionContext,
        redis: Any,
    ) -> InterventionOutcome | None:
        """Predict based on causal knowledge (if/then relationships).

        Uses causal patterns stored in Redis (from Tier 2 RAG or manual rules).
        Example: "retry" CAUSES "latency_increase" if network is unstable.
        """
        try:
            causal_key = self.CAUSAL_PATTERNS_KEY.format(action_type=decision_option)
            patterns_json = await redis.get(causal_key)

            if not patterns_json:
                return None

            patterns = json.loads(patterns_json)

            # Match patterns against context
            applicable_patterns = []
            for pattern in patterns:
                if self._pattern_matches_context(pattern, context):
                    applicable_patterns.append(pattern)

            if not applicable_patterns:
                return None

            # Aggregate causal predictions
            success_rates = [p.get("predicted_success_rate", 0.5) for p in applicable_patterns]
            avg_success = sum(success_rates) / len(success_rates)

            side_effects = []
            for pattern in applicable_patterns:
                side_effects.extend(pattern.get("side_effects", []))

            return InterventionOutcome(
                option=decision_option,
                predicted_success_rate=avg_success,
                side_effects=side_effects,
                confidence=0.75,
                reasoning=f"Causal: {len(applicable_patterns)} patterns matched "
                f"({', '.join(p.get('name', 'unknown') for p in applicable_patterns)})",
                prediction_source="causal",
                supporting_evidence=[{"type": "pattern", "name": p.get("name")} for p in applicable_patterns],
            )

        except Exception as e:
            logger.warning(f"Causal prediction failed: {e}")
            return None

    def _predict_heuristic(
        self,
        decision_option: str,
        context: DecisionContext,
        action_details: Dict[str, Any],
    ) -> InterventionOutcome:
        """Fallback heuristic prediction when no empirical or causal data exists.

        Rule-based defaults for common decision types.
        """
        # Use action's declared confidence as base
        base_success_rate = action_details.get("confidence", 0.5)

        # Adjust based on context
        if context.get_high_risk_factors():
            base_success_rate *= 0.7  # Risk factors reduce success likelihood

        # Decision-type-specific heuristics
        side_effects = []
        fallback_risk = None
        latency_estimate = None

        if decision_option == "retry":
            side_effects = [
                {
                    "type": "latency_increase",
                    "frequency": 0.8,
                    "severity": "medium",
                    "description": "Retries add 2-5s per attempt",
                }
            ]
            fallback_risk = "backlog_growth"
            latency_estimate = 3000

        elif decision_option == "escalate":
            side_effects = [
                {
                    "type": "user_notification",
                    "frequency": 1.0,
                    "severity": "low",
                    "description": "User will be notified of escalation",
                },
                {
                    "type": "wait_time",
                    "frequency": 0.9,
                    "severity": "medium",
                    "description": "Wait for human response (5-60 minutes)",
                },
            ]
            fallback_risk = "timeout_waiting_for_human"
            latency_estimate = 300000  # 5 minutes avg

        elif decision_option == "automate":
            side_effects = [
                {
                    "type": "state_mutation",
                    "frequency": 1.0,
                    "severity": "high",
                    "description": "Automation modifies system state",
                }
            ]
            fallback_risk = "irreversible_change"
            latency_estimate = 500

        elif decision_option == "wait":
            side_effects = [
                {
                    "type": "deadline_risk",
                    "frequency": 0.6,
                    "severity": "medium",
                    "description": "Waiting might miss deadline",
                }
            ]
            fallback_risk = "missed_deadline"
            latency_estimate = 5000

        return InterventionOutcome(
            option=decision_option,
            predicted_success_rate=base_success_rate,
            side_effects=side_effects,
            confidence=0.5,  # Low confidence for heuristic
            reasoning=f"Heuristic default: {decision_option} typically succeeds "
            f"{base_success_rate:.1%} in {context.decision_type.value} decisions",
            prediction_source="heuristic",
            supporting_evidence=[{"type": "action_confidence", "value": action_details.get("confidence")}],
            fallback_risk=fallback_risk,
            estimated_latency_ms=latency_estimate,
        )

    def _pattern_matches_context(self, pattern: Dict[str, Any], context: DecisionContext) -> bool:
        """Check if a causal pattern applies to current context."""
        conditions = pattern.get("conditions", {})

        # If no conditions, pattern always matches
        if not conditions:
            return True

        # Match decision type
        if "decision_type" in conditions:
            if context.decision_type.value != conditions["decision_type"]:
                return False

        # Match risk level
        if "min_high_risk_factors" in conditions:
            high_risk_count = len(context.get_high_risk_factors())
            if high_risk_count < conditions["min_high_risk_factors"]:
                return False

        # Match context type presence by metadata type
        if "required_context_types" in conditions:
            # Look for elements with matching metadata type
            context_metadata_types = {ce.metadata.get("type") for ce in context.context_elements}
            required = set(conditions["required_context_types"])
            if not required.issubset(context_metadata_types):
                return False

        return True

    def _assess_side_effect_severity(self, effect_type: str) -> str:
        """Classify side effect severity."""
        high_severity = {
            "state_mutation",
            "irreversible_change",
            "data_loss",
            "system_failure",
        }
        medium_severity = {
            "latency_increase",
            "wait_time",
            "deadline_risk",
            "resource_usage",
        }

        if effect_type in high_severity:
            return "high"
        elif effect_type in medium_severity:
            return "medium"
        else:
            return "low"

    async def predict_retry_outcome(self, context: DecisionContext) -> InterventionOutcome:
        """Convenience method: Predict outcome of retry decision."""
        return await self.what_if("retry", context, {"confidence": 0.6})

    async def predict_escalation_outcome(self, context: DecisionContext) -> InterventionOutcome:
        """Convenience method: Predict outcome of escalation decision."""
        return await self.what_if("escalate", context, {"confidence": 0.9})

    async def predict_automation_outcome(self, context: DecisionContext) -> InterventionOutcome:
        """Convenience method: Predict outcome of automation decision."""
        return await self.what_if("automate", context, {"confidence": 0.7})
