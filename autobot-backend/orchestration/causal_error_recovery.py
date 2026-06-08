# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Causal Error Recovery System

Extends causal error analysis with smart recovery strategies based on error types,
causal chains, and patterns. Provides recovery recommendations with confidence
scoring and alternative actions.

Issue #2154: Enhanced error handling with root-cause analysis and recovery planning.
"""

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.time_utils import now_utc
from constants.ttl_constants import TTL_30_DAYS
from orchestration.causal_error_analyzer import CausalErrorAnalysis

logger = get_logger(__name__)

# Redis key patterns for failure patterns
FAILURE_PATTERN_PREFIX = "failure:pattern:"
FAILURE_PATTERN_RESOLUTION_PREFIX = "failure:resolution:"
FAILURE_PATTERN_COUNT_SUFFIX = ":count"
FAILURE_PATTERN_CHAIN_SUFFIX = ":chain"
FAILURE_PATTERN_RESOLUTIONS_SUFFIX = ":resolutions"


class RecoveryAction(str, Enum):
    """Possible recovery actions for errors."""

    RETRY_IMMEDIATELY = "retry_immediately"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    RETRY_WITH_EXPONENTIAL = "retry_with_exponential"
    WAIT_FOR_DEPENDENCY = "wait_for_dependency"
    RESTRUCTURE_WORKFLOW = "restructure_workflow"
    ESCALATE = "escalate"
    SKIP_STEP = "skip_step"
    FALLBACK_TO_ALTERNATIVE = "fallback_to_alternative"
    SCALE_RESOURCES = "scale_resources"
    CIRCUIT_BREAK = "circuit_break"


@dataclass
class RecoveryAction_:
    """A single recovery action candidate."""

    action: RecoveryAction
    description: str
    likelihood_to_succeed: float  # 0.0-1.0
    cost: float  # 0.0-1.0 (resource/performance cost)
    risk: float  # 0.0-1.0 (risk of making things worse)
    expected_outcome: str
    estimated_delay_seconds: float = 0.0

    @property
    def score(self) -> float:
        """Compute overall score: higher is better.

        Score = likelihood - cost - risk (weighted to favor success).
        """
        return self.likelihood_to_succeed * 2.0 - self.cost - self.risk


@dataclass
class RecoveryPlan:
    """Complete recovery plan for an error."""

    error_id: str
    error_type: str
    root_cause: str
    causal_chain: str
    is_leaf_error: bool  # True if immediate cause, False if downstream
    is_known_pattern: bool
    pattern_frequency: int  # How many times have we seen this pattern?

    # Recommended actions ranked by score
    recommended_actions: List[RecoveryAction_] = field(default_factory=list)

    # Metadata
    confidence: float = 0.0  # Overall confidence in this plan
    timestamp: str = field(default_factory=lambda: now_utc().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "error_id": self.error_id,
            "error_type": self.error_type,
            "root_cause": self.root_cause,
            "causal_chain": self.causal_chain,
            "is_leaf_error": self.is_leaf_error,
            "is_known_pattern": self.is_known_pattern,
            "pattern_frequency": self.pattern_frequency,
            "recommended_actions": [asdict(a) for a in self.recommended_actions],
            "confidence": self.confidence,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryPlan":
        """Deserialize from dict."""
        actions = [
            RecoveryAction_(
                action=RecoveryAction(a["action"]),
                description=a["description"],
                likelihood_to_succeed=a["likelihood_to_succeed"],
                cost=a["cost"],
                risk=a["risk"],
                expected_outcome=a["expected_outcome"],
                estimated_delay_seconds=a.get("estimated_delay_seconds", 0.0),
            )
            for a in data.get("recommended_actions", [])
        ]
        return cls(
            error_id=data["error_id"],
            error_type=data["error_type"],
            root_cause=data["root_cause"],
            causal_chain=data["causal_chain"],
            is_leaf_error=data["is_leaf_error"],
            is_known_pattern=data["is_known_pattern"],
            pattern_frequency=data["pattern_frequency"],
            recommended_actions=actions,
            confidence=data.get("confidence", 0.0),
            timestamp=data.get("timestamp", ""),
        )


class CausalErrorRecovery:
    """
    Recommends recovery actions based on causal error analysis.

    Integrates with CausalErrorAnalyzer to understand error causation,
    then applies heuristics and learned patterns to suggest recovery strategies.
    """

    def __init__(self):
        self._redis: Any | None = None

    def _get_redis(self) -> Any:
        """Lazy-init sync Redis client."""
        if self._redis is None:
            self._redis = get_redis_client(async_client=False, database="main")
        return self._redis

    async def recommend_recovery(
        self,
        error: Exception,
        causal_analysis: CausalErrorAnalysis,
        execution_context: Dict[str, Any] | None = None,
    ) -> RecoveryPlan:
        """
        Recommend recovery actions for an error.

        Args:
            error: The exception that occurred
            causal_analysis: Results from CausalErrorAnalyzer
            execution_context: Step/workflow context

        Returns:
            RecoveryPlan with ranked recovery actions
        """
        execution_context = execution_context or {}
        error_type = type(error).__name__
        error_id = f"{error_type}:{hash(str(error)) % 100000}"

        # Classify error as leaf or downstream
        is_leaf_error = self._is_leaf_error(error_type, causal_analysis)

        # Check if this is a known failure pattern
        pattern_hash = self._hash_causal_chain(causal_analysis.causal_chain)
        pattern_frequency, is_known = self._check_pattern(pattern_hash)

        # Generate recovery actions based on error type and context
        recovery_actions = self._generate_recovery_actions(error, error_type, causal_analysis, execution_context)

        # Score and rank actions
        recovery_actions.sort(key=lambda a: a.score, reverse=True)

        # Compute confidence in recovery plan
        base_confidence = causal_analysis.confidence
        pattern_boost = 0.15 if is_known else 0.0
        confidence = min(1.0, base_confidence + pattern_boost)

        plan = RecoveryPlan(
            error_id=error_id,
            error_type=error_type,
            root_cause=causal_analysis.root_cause,
            causal_chain=causal_analysis.causal_chain,
            is_leaf_error=is_leaf_error,
            is_known_pattern=is_known,
            pattern_frequency=pattern_frequency,
            recommended_actions=recovery_actions[:3],  # Top 3 actions
            confidence=confidence,
        )

        logger.info(
            "Recovery plan generated: error_id=%s, actions=%d, confidence=%.2f",
            error_id,
            len(plan.recommended_actions),
            confidence,
        )

        return plan

    def _is_leaf_error(self, error_type: str, causal_analysis: CausalErrorAnalysis) -> bool:
        """Determine if error is immediate (leaf) or downstream (cascading)."""
        # If causal chain has arrows indicating multiple steps, it's downstream
        if "→" in causal_analysis.causal_chain or "->" in causal_analysis.causal_chain:
            # Count arrow count; if > 1, likely cascading
            arrow_count = causal_analysis.causal_chain.count("→") + causal_analysis.causal_chain.count("->")
            return arrow_count <= 1

        # Confounders suggest downstream effect
        return len(causal_analysis.confounders_identified) == 0

    def _hash_causal_chain(self, causal_chain: str) -> str:
        """Hash a causal chain for pattern matching."""
        import hashlib

        return hashlib.md5(causal_chain.encode(), usedforsecurity=False).hexdigest()[:16]

    def _check_pattern(self, pattern_hash: str) -> tuple[int, bool]:
        """Check if a pattern is known and return frequency."""
        try:
            redis = self._get_redis()
            count_key = f"{FAILURE_PATTERN_PREFIX}{pattern_hash}{FAILURE_PATTERN_COUNT_SUFFIX}"
            count = redis.get(count_key)
            if count:
                frequency = int(count)
                return frequency, True
            return 0, False
        except Exception as exc:
            logger.warning("Failed to check pattern frequency: %s", exc)
            return 0, False

    def _generate_recovery_actions(
        self,
        error: Exception,
        error_type: str,
        causal_analysis: CausalErrorAnalysis,
        execution_context: Dict[str, Any],
    ) -> List[RecoveryAction_]:
        """Generate recovery actions based on error characteristics."""
        actions: List[RecoveryAction_] = []

        # Classify error root cause
        root_lower = causal_analysis.root_cause.lower()

        # Network/timeout errors → retry with backoff
        if any(x in error_type.lower() for x in ["timeout", "connection", "networkio", "timeout_error"]):
            actions.append(
                RecoveryAction_(
                    action=RecoveryAction.RETRY_WITH_BACKOFF,
                    description="Retry with exponential backoff (transient network failure)",
                    likelihood_to_succeed=0.75,
                    cost=0.1,
                    risk=0.05,
                    expected_outcome="Connection re-established, request succeeds",
                    estimated_delay_seconds=2.0,
                )
            )
            actions.append(
                RecoveryAction_(
                    action=RecoveryAction.WAIT_FOR_DEPENDENCY,
                    description="Wait for upstream service/resource to become available",
                    likelihood_to_succeed=0.65,
                    cost=0.2,
                    risk=0.1,
                    expected_outcome="Service comes online, retry succeeds",
                    estimated_delay_seconds=5.0,
                )
            )

        # Resource exhaustion → scale or wait
        if any(x in root_lower for x in ["pool", "resource", "capacity", "memory", "connection"]):
            actions.append(
                RecoveryAction_(
                    action=RecoveryAction.WAIT_FOR_DEPENDENCY,
                    description="Wait for resource to become available (pool recovery)",
                    likelihood_to_succeed=0.7,
                    cost=0.15,
                    risk=0.08,
                    expected_outcome="Other operations release resources, retry succeeds",
                    estimated_delay_seconds=3.0,
                )
            )
            actions.append(
                RecoveryAction_(
                    action=RecoveryAction.SCALE_RESOURCES,
                    description="Scale up resources (connection pool, memory, etc.)",
                    likelihood_to_succeed=0.6,
                    cost=0.5,
                    risk=0.2,
                    expected_outcome="More resources available, step succeeds",
                    estimated_delay_seconds=10.0,
                )
            )

        # Workflow design issue → restructure
        if any(
            x in root_lower
            for x in [
                "ordering",
                "dependency",
                "circular",
                "sequence",
                "step",
                "workflow",
            ]
        ):
            actions.append(
                RecoveryAction_(
                    action=RecoveryAction.RESTRUCTURE_WORKFLOW,
                    description="Restructure workflow steps (fix ordering/dependencies)",
                    likelihood_to_succeed=0.8,
                    cost=0.3,
                    risk=0.15,
                    expected_outcome="Step runs with correct dependencies met",
                    estimated_delay_seconds=0.0,
                )
            )
            actions.append(
                RecoveryAction_(
                    action=RecoveryAction.SKIP_STEP,
                    description="Skip problematic step if optional",
                    likelihood_to_succeed=0.5,
                    cost=0.1,
                    risk=0.3,
                    expected_outcome="Workflow continues without this step",
                    estimated_delay_seconds=0.0,
                )
            )

        # Permission/access errors → escalate
        if any(x in error_type.lower() for x in ["permission", "forbidden", "auth", "unauthorized", "access"]):
            actions.append(
                RecoveryAction_(
                    action=RecoveryAction.ESCALATE,
                    description="Escalate to operator (permission denied)",
                    likelihood_to_succeed=0.4,
                    cost=0.0,
                    risk=0.0,
                    expected_outcome="Operator grants permission, workflow resumed",
                    estimated_delay_seconds=0.0,
                )
            )

        # Generic transient errors → immediate retry first, then backoff
        if not actions:
            actions.append(
                RecoveryAction_(
                    action=RecoveryAction.RETRY_IMMEDIATELY,
                    description="Retry immediately (transient error)",
                    likelihood_to_succeed=0.4,
                    cost=0.05,
                    risk=0.1,
                    expected_outcome="Error condition resolved, retry succeeds",
                    estimated_delay_seconds=0.0,
                )
            )
            actions.append(
                RecoveryAction_(
                    action=RecoveryAction.RETRY_WITH_EXPONENTIAL,
                    description="Retry with exponential backoff (unknown transient)",
                    likelihood_to_succeed=0.55,
                    cost=0.1,
                    risk=0.12,
                    expected_outcome="Backoff allows error condition to clear",
                    estimated_delay_seconds=2.0,
                )
            )

        # Always offer escalation as fallback
        if len(actions) < 3:
            actions.append(
                RecoveryAction_(
                    action=RecoveryAction.ESCALATE,
                    description="Escalate to human operator for manual intervention",
                    likelihood_to_succeed=0.5,
                    cost=0.0,
                    risk=0.0,
                    expected_outcome="Operator investigates and resolves error",
                    estimated_delay_seconds=0.0,
                )
            )

        return actions

    async def record_recovery_attempt(
        self,
        recovery_plan: RecoveryPlan,
        action_taken: RecoveryAction,
        success: bool,
        outcome: str | None = None,
    ) -> None:
        """
        Record that we attempted a recovery action.

        This feeds back into pattern learning.

        Args:
            recovery_plan: The plan we followed
            action_taken: The action we executed
            success: Whether the action succeeded
            outcome: Optional outcome description
        """
        pattern_hash = self._hash_causal_chain(recovery_plan.causal_chain)

        try:
            redis = self._get_redis()

            # Increment pattern count
            count_key = f"{FAILURE_PATTERN_PREFIX}{pattern_hash}{FAILURE_PATTERN_COUNT_SUFFIX}"
            redis.incr(count_key)
            redis.expire(count_key, TTL_30_DAYS)

            # Store causal chain
            chain_key = f"{FAILURE_PATTERN_PREFIX}{pattern_hash}{FAILURE_PATTERN_CHAIN_SUFFIX}"
            redis.set(chain_key, recovery_plan.causal_chain, ex=TTL_30_DAYS)

            # Record resolution (which action actually worked)
            if success:
                resolution_data = {
                    "action": action_taken.value,
                    "outcome": outcome or "success",
                    "timestamp": now_utc().isoformat(),
                }
                redis.hset(
                    f"{FAILURE_PATTERN_PREFIX}{pattern_hash}{FAILURE_PATTERN_RESOLUTIONS_SUFFIX}",
                    action_taken.value,
                    json.dumps(resolution_data),
                )
                redis.expire(
                    f"{FAILURE_PATTERN_PREFIX}{pattern_hash}{FAILURE_PATTERN_RESOLUTIONS_SUFFIX}",
                    TTL_30_DAYS,
                )

            logger.debug(
                "Recorded recovery attempt: pattern=%s, action=%s, success=%s",
                pattern_hash,
                action_taken.value,
                success,
            )
        except Exception as exc:
            logger.warning("Failed to record recovery attempt: %s", exc)


# Module-level singleton
_recovery_recommender = CausalErrorRecovery()


def get_recovery_recommender() -> CausalErrorRecovery:
    """Get the shared recovery recommender singleton."""
    return _recovery_recommender
