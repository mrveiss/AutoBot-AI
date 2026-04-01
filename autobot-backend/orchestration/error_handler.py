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
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHECKPOINT_KEY_PREFIX = "autobot:workflow:checkpoint:"
CHECKPOINT_TTL = 7 * 24 * 3600  # 7 days in seconds


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


class BackoffStrategy(str, Enum):
    """Retry delay growth strategy.

    Issue #2154.
    """

    LINEAR = "linear"
    EXPONENTIAL = "exponential"


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
    fallback_step_id: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepErrorConfig":
        """Build a StepErrorConfig from a raw dict, ignoring unknown keys."""
        return cls(
            action=StepErrorAction(data.get("action", StepErrorAction.ABORT)),
            max_retries=int(data.get("max_retries", 3)),
            base_delay=float(data.get("base_delay", 1.0)),
            backoff=BackoffStrategy(data.get("backoff", BackoffStrategy.EXPONENTIAL)),
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
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

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
            logger.error(
                "Failed to load checkpoints for workflow=%s: %s", workflow_id, exc
            )
            return {}

        result: Dict[str, StepCheckpoint] = {}
        for step_id_bytes, value_bytes in raw_map.items():
            step_id = (
                step_id_bytes.decode()
                if isinstance(step_id_bytes, bytes)
                else step_id_bytes
            )
            raw = (
                value_bytes.decode() if isinstance(value_bytes, bytes) else value_bytes
            )
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
            logger.error(
                "Failed to clear checkpoints for workflow=%s: %s", workflow_id, exc
            )


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

    Issue #2154.
    """

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

        LINEAR:      base_delay * attempt
        EXPONENTIAL: base_delay * 2^(attempt-1)

        Issue #2154.
        """
        if config.backoff == BackoffStrategy.LINEAR:
            return config.base_delay * attempt
        return config.base_delay * (2 ** (attempt - 1))

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
            logger.error(
                "Step %s: exhausted %d retries — ABORT", step_id, config.max_retries
            )
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

        # Default / ABORT
        logger.error("Step %s: ABORT (error_config action=%s)", step_id, config.action)
        return {
            "action": StepErrorAction.ABORT,
            "delay": 0.0,
            "fallback_id": None,
            "reason": f"step failed with action={config.action}",
        }


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

#: Shared checkpoint manager — safe to reuse across workflow executions.
_checkpoint_manager = WorkflowCheckpointManager()

#: Shared error handler — stateless, safe to reuse across calls.
_error_handler = StepErrorHandler()
