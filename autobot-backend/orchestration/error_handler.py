# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Step-level Error Handlers and Workflow Checkpoint Management

Issue #2154: Implement workflow resume-from-failure and step-level error handlers.

Each workflow step may declare an ``error_config`` dict that controls how the
executor responds to failure.  Supported actions:

- RETRY:    Re-run the step up to ``max_retries`` times with configurable backoff.
- SKIP:     Mark the step skipped and continue to the next step.
- FALLBACK: Execute a different step (``fallback_step_id``) instead.
- PAUSE:    Halt execution and surface a ``paused`` status so an operator can
            decide how to proceed.
- ABORT:    Fail the entire workflow immediately (the default).

Checkpoints are saved to the ``workflows`` Redis database after each successful
step.  A paused or failed workflow can be resumed by calling
``execute_coordinated_workflow`` with ``resume_from_checkpoint=True``; completed
steps are skipped and execution continues from the first incomplete step.
"""

import asyncio
import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from autobot_shared.time_utils import now_utc
from constants.ttl_constants import TTL_30_DAYS
from retry_mechanism import BackoffStrategy, RetryConfig, RetryMechanism

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHECKPOINT_KEY_PREFIX = "autobot:workflow:checkpoint:"
# #3231 / #7010 cluster 2: paused workflows awaiting human approval must
# survive ≥30 days. Aligns with autobot_shared/ssot_config.py's
# `checkpoint_ttl_minutes` default of 43200 (30 days) for LangGraph
# checkpoint keys. Earlier TTL_7_DAYS was a stale carryover from when this
# value was used for short-term retry retention only.
CHECKPOINT_TTL = TTL_30_DAYS


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class StepErrorAction(str, Enum):
    """Actions available when a workflow step fails.

    Issue #2154.
    """

    RETRY = "retry"
    SKIP = "skip"
    FALLBACK = "fallback"
    PAUSE = "pause"
    ABORT = "abort"


# BackoffStrategy is imported from retry_mechanism (Issue #3830).
# The local enum is removed; callers use retry_mechanism.BackoffStrategy directly.

# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------


@dataclass
class StepErrorConfig:
    """
    Per-step error handling policy.

    Attach to a step dict as ``step["error_config"]``.  Unrecognised keys
    are ignored so callers can pass arbitrary dicts without breaking existing
    code.

    Attributes:
        action:           What to do on failure.  Defaults to ABORT.
        max_retries:      Maximum retry attempts when action is RETRY.
        base_delay:       Initial retry delay in seconds.
        backoff:          How the delay grows between retries.
        fallback_step_id: Step ID to execute instead when action is FALLBACK.

    Issue #2154.
    """

    action: StepErrorAction = StepErrorAction.ABORT
    max_retries: int = 3
    base_delay: float = 1.0
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    fallback_step_id: str | None = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepErrorConfig":
        """Build a StepErrorConfig from a raw dict, ignoring unknown keys.

        Accepts legacy backoff strings ("linear", "exponential") as well as the
        canonical retry_mechanism BackoffStrategy values (Issue #3830).
        """
        _BACKOFF_LEGACY_MAP = {
            "linear": BackoffStrategy.LINEAR,
            "exponential": BackoffStrategy.EXPONENTIAL,
        }
        raw_backoff = data.get("backoff", BackoffStrategy.EXPONENTIAL)
        if isinstance(raw_backoff, BackoffStrategy):
            backoff = raw_backoff
        elif isinstance(raw_backoff, str) and raw_backoff in _BACKOFF_LEGACY_MAP:
            backoff = _BACKOFF_LEGACY_MAP[raw_backoff]
        else:
            backoff = BackoffStrategy(raw_backoff)
        return cls(
            action=StepErrorAction(data.get("action", StepErrorAction.ABORT)),
            max_retries=int(data.get("max_retries", 3)),
            base_delay=float(data.get("base_delay", 1.0)),
            backoff=backoff,
            fallback_step_id=data.get("fallback_step_id"),
        )


# ---------------------------------------------------------------------------
# Checkpoint dataclass
# ---------------------------------------------------------------------------


@dataclass
class StepCheckpoint:
    """
    Snapshot of a single completed step that was persisted to Redis.

    Attributes:
        step_id:   Identifier of the step.
        status:    Terminal status: ``completed``, ``skipped``, ``fallback``.
        output:    Raw step result dict as returned by the executor.
        timestamp: ISO-8601 UTC timestamp when the checkpoint was saved.

    Issue #2154.
    """

    step_id: str
    status: str
    output: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: now_utc().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Serialise to a plain dict for JSON storage."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepCheckpoint":
        """Deserialise from a plain dict read from Redis."""
        return cls(
            step_id=data["step_id"],
            status=data["status"],
            output=data.get("output", {}),
            timestamp=data.get("timestamp", ""),
        )


# ---------------------------------------------------------------------------
# WorkflowCheckpointManager
# ---------------------------------------------------------------------------


class WorkflowCheckpointManager:
    """
    Saves and loads per-step checkpoints in the ``workflows`` Redis database.

    Key layout::

        autobot:workflow:checkpoint:<workflow_id>  →  Redis Hash
            field = step_id
            value = JSON-serialised StepCheckpoint

    Issue #2154.
    """

    def __init__(self) -> None:
        self._redis: Any = None

    def _get_redis(self) -> Any:
        """Lazy-initialise a synchronous Redis client for the workflows DB."""
        if self._redis is None:
            self._redis = get_redis_client(async_client=False, database="workflows")
        return self._redis

    def _checkpoint_key(self, workflow_id: str) -> str:
        return f"{CHECKPOINT_KEY_PREFIX}{workflow_id}"

    def save(self, workflow_id: str, checkpoint: StepCheckpoint) -> None:
        """
        Persist *checkpoint* for *workflow_id* / *step_id*.

        Refreshes the key TTL on every write so the hash expires as a unit.

        Issue #2154.
        """
        redis = self._get_redis()
        key = self._checkpoint_key(workflow_id)
        try:
            redis.hset(key, checkpoint.step_id, json.dumps(checkpoint.to_dict()))
            redis.expire(key, CHECKPOINT_TTL)
            logger.debug(
                "Checkpoint saved: workflow=%s step=%s status=%s",
                workflow_id,
                checkpoint.step_id,
                checkpoint.status,
            )
        except Exception as exc:
            logger.error(
                "Failed to save checkpoint for workflow=%s step=%s: %s",
                workflow_id,
                checkpoint.step_id,
                exc,
            )

    def refresh_ttl(self, workflow_id: str) -> None:
        """Refresh the TTL on a workflow's checkpoint hash key.

        Per #3231: an active session that resumes work on a paused workflow
        must reset the 30-day window so the checkpoint survives further idle
        time. Callers invoke this on every read/resume of a checkpoint.

        Redis errors are logged at warning level but never raised — a TTL
        refresh failure must not break the calling resume flow. Worst case
        the key expires earlier than intended; the next save() resets it.
        """
        redis = self._get_redis()
        key = self._checkpoint_key(workflow_id)
        try:
            redis.expire(key, CHECKPOINT_TTL)
        except Exception as exc:
            logger.warning(
                "Failed to refresh checkpoint TTL for workflow=%s: %s",
                workflow_id,
                exc,
            )

    def load_all(self, workflow_id: str) -> Dict[str, StepCheckpoint]:
        """
        Return all persisted checkpoints for *workflow_id*.

        Returns an empty dict when no checkpoint hash exists or Redis is
        unavailable.

        Issue #2154.
        """
        redis = self._get_redis()
        key = self._checkpoint_key(workflow_id)
        try:
            raw_map = redis.hgetall(key)
        except Exception as exc:
            logger.error("Failed to load checkpoints for workflow=%s: %s", workflow_id, exc)
            return {}

        result: Dict[str, StepCheckpoint] = {}
        for step_id_bytes, value_bytes in raw_map.items():
            step_id = step_id_bytes.decode() if isinstance(step_id_bytes, bytes) else step_id_bytes
            raw = value_bytes.decode() if isinstance(value_bytes, bytes) else value_bytes
            try:
                result[step_id] = StepCheckpoint.from_dict(json.loads(raw))
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning(
                    "Corrupt checkpoint for workflow=%s step=%s: %s",
                    workflow_id,
                    step_id,
                    exc,
                )
        return result

    def clear(self, workflow_id: str) -> None:
        """
        Delete all checkpoints for *workflow_id*.

        Called after a workflow completes successfully.

        Issue #2154.
        """
        redis = self._get_redis()
        key = self._checkpoint_key(workflow_id)
        try:
            redis.delete(key)
            logger.debug("Checkpoints cleared for workflow=%s", workflow_id)
        except Exception as exc:
            logger.error("Failed to clear checkpoints for workflow=%s: %s", workflow_id, exc)


# ---------------------------------------------------------------------------
# StepErrorHandler
# ---------------------------------------------------------------------------


class StepErrorHandler:
    """
    Consults a step's ``error_config`` after a failure and returns the
    resolution action and result.

    Usage (inside WorkflowExecutor)::

        handler = StepErrorHandler()
        outcome = await handler.handle_error(step, error, attempt, execution_context)
        if outcome["action"] == StepErrorAction.RETRY:
            # caller retries the step
        elif outcome["action"] == StepErrorAction.SKIP:
            # caller marks step skipped and continues
        ...

    Pass ``causal_recovery=True`` to enable causal-chain analysis on ABORT
    decisions (GH #6816).  When enabled, ``CausalErrorRecovery`` generates
    recovery recommendations logged at INFO level; the ABORT decision itself
    is not changed.

    Issue #2154.
    """

    def __init__(self, causal_recovery: bool = False) -> None:
        self._causal_recovery = causal_recovery

    def _parse_config(self, step: Dict[str, Any]) -> StepErrorConfig:
        """Extract StepErrorConfig from step dict, defaulting to ABORT."""
        raw = step.get("error_config")
        if isinstance(raw, dict):
            try:
                return StepErrorConfig.from_dict(raw)
            except (ValueError, KeyError) as exc:
                logger.warning(
                    "Step %s: invalid error_config %r — using ABORT default: %s",
                    step.get("id"),
                    raw,
                    exc,
                )
        return StepErrorConfig()

    def _compute_delay(self, config: StepErrorConfig, attempt: int) -> float:
        """
        Return the retry delay for *attempt* (1-based) under *config*.

        Delegates to RetryMechanism.calculate_delay so all backoff curves are
        computed by a single implementation (Issue #3830).
        """
        retry_config = RetryConfig(
            max_attempts=config.max_retries,
            base_delay=config.base_delay,
            max_delay=config.base_delay * (2**config.max_retries),  # no hard cap needed
            backoff_multiplier=2.0,
            jitter=False,
            strategy=config.backoff.to_retry_strategy(),
        )
        mechanism = RetryMechanism(retry_config)
        return mechanism.calculate_delay(attempt)

    async def handle_error(
        self,
        step: Dict[str, Any],
        error: Exception,
        attempt: int,
        execution_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Decide what to do after *step* raised *error* on *attempt* (1-based).

        Returns a dict with:
            action:       StepErrorAction chosen.
            delay:        Seconds to wait before RETRY (0.0 for other actions).
            fallback_id:  Fallback step ID when action is FALLBACK, else None.
            reason:       Human-readable explanation.

        Issue #2154.
        """
        config = self._parse_config(step)
        step_id = step.get("id", "<unknown>")

        logger.warning(
            "Step %s failed (attempt %d/%d) with error: %s",
            step_id,
            attempt,
            config.max_retries,
            error,
        )

        if config.action == StepErrorAction.RETRY and attempt < config.max_retries:
            delay = self._compute_delay(config, attempt)
            logger.info(
                "Step %s: RETRY in %.1fs (attempt %d of %d)",
                step_id,
                delay,
                attempt + 1,
                config.max_retries,
            )
            await asyncio.sleep(delay)
            return {
                "action": StepErrorAction.RETRY,
                "delay": delay,
                "fallback_id": None,
                "reason": f"retry {attempt + 1}/{config.max_retries} after {delay:.1f}s",
            }

        if config.action == StepErrorAction.RETRY and attempt >= config.max_retries:
            logger.error("Step %s: exhausted %d retries — ABORT", step_id, config.max_retries)
            return {
                "action": StepErrorAction.ABORT,
                "delay": 0.0,
                "fallback_id": None,
                "reason": f"max retries ({config.max_retries}) exhausted",
            }

        if config.action == StepErrorAction.SKIP:
            logger.info("Step %s: SKIP on error (error_config)", step_id)
            return {
                "action": StepErrorAction.SKIP,
                "delay": 0.0,
                "fallback_id": None,
                "reason": "step skipped due to error_config",
            }

        if config.action == StepErrorAction.FALLBACK:
            fallback_id = config.fallback_step_id
            if not fallback_id:
                logger.error(
                    "Step %s: FALLBACK configured but fallback_step_id is missing — ABORT",
                    step_id,
                )
                return {
                    "action": StepErrorAction.ABORT,
                    "delay": 0.0,
                    "fallback_id": None,
                    "reason": "FALLBACK configured but fallback_step_id not set",
                }
            logger.info("Step %s: FALLBACK → step %s", step_id, fallback_id)
            return {
                "action": StepErrorAction.FALLBACK,
                "delay": 0.0,
                "fallback_id": fallback_id,
                "reason": f"fallback to step {fallback_id}",
            }

        if config.action == StepErrorAction.PAUSE:
            logger.info(
                "Step %s: PAUSE requested — halting workflow %s",
                step_id,
                execution_context.get("workflow_id"),
            )
            return {
                "action": StepErrorAction.PAUSE,
                "delay": 0.0,
                "fallback_id": None,
                "reason": "workflow paused by step error_config",
            }

        # Default / ABORT — optionally run causal analysis (GH #6816)
        logger.error("Step %s: ABORT (error_config action=%s)", step_id, config.action)
        if self._causal_recovery:
            await self._run_causal_analysis(step_id, error, execution_context)
        return {
            "action": StepErrorAction.ABORT,
            "delay": 0.0,
            "fallback_id": None,
            "reason": f"step failed with action={config.action}",
        }

    async def _run_causal_analysis(
        self,
        step_id: str,
        error: Exception,
        execution_context: Dict[str, Any],
    ) -> None:
        """Run CausalErrorAnalyzer + CausalErrorRecovery and log recommendations (GH #6816).

        Never raises — analysis failure must not shadow the original error.
        """
        try:
            from orchestration.causal_error_analyzer import CausalErrorAnalyzer
            from orchestration.causal_error_recovery import get_recovery_recommender

            analyzer = CausalErrorAnalyzer()
            ctx = {"step_id": step_id, **execution_context}
            analysis = await analyzer.analyze_error_causally(error=error, context=ctx)
            plan = await get_recovery_recommender().recommend_recovery(
                error=error,
                causal_analysis=analysis,
                execution_context=ctx,
            )
            top = plan.recommended_actions[0] if plan.recommended_actions else None
            if top:
                logger.info(
                    "Causal recovery for step %s: action=%s confidence=%.2f",
                    step_id,
                    top.action.value,
                    plan.confidence,
                )
        except Exception as exc:
            logger.debug("Causal analysis skipped for step %s: %s", step_id, exc)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

#: Shared checkpoint manager — safe to reuse across workflow executions.
_checkpoint_manager = WorkflowCheckpointManager()

#: Shared error handler — stateless, safe to reuse across calls.
_error_handler = StepErrorHandler()
