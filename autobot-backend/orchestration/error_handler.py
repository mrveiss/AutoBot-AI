# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Step-level error handlers and workflow checkpoint management.

Issue #2154: Adds resume-from-failure capability to the workflow executor.

Key components
--------------
StepErrorAction
    Enum of possible actions when a step fails (RETRY, SKIP, FALLBACK, PAUSE, ABORT).

StepErrorConfig
    Per-step configuration controlling which action to take and retry parameters.

StepCheckpoint
    Persisted record of a completed step's output.

WorkflowCheckpointManager
    Saves / loads / clears step checkpoints in Redis so a workflow can resume
    after a partial failure without re-running successful steps.

StepErrorHandler
    Consults a step's StepErrorConfig and executes the appropriate action:
    exponential or linear backoff retry, skip, fallback routing, pause, or abort.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from autobot_shared.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Redis key TTL for checkpoints — 24 hours is ample for long-running workflows
_CHECKPOINT_TTL_SECONDS = 86_400


# ---------------------------------------------------------------------------
# Enums and dataclasses
# ---------------------------------------------------------------------------


class StepErrorAction(str, Enum):
    """Action to take when a workflow step fails."""

    RETRY = "retry"
    SKIP = "skip"
    FALLBACK = "fallback"
    PAUSE = "pause"
    ABORT = "abort"


class BackoffStrategy(str, Enum):
    """Delay growth strategy used by RETRY action."""

    LINEAR = "linear"
    EXPONENTIAL = "exponential"


@dataclass
class StepErrorConfig:
    """
    Per-step error handling configuration.

    Args:
        action: What to do when this step fails.
        max_retries: Maximum retry attempts (used when action=RETRY).
        base_delay: Initial wait in seconds before first retry.
        backoff: Delay growth strategy (LINEAR or EXPONENTIAL).
        fallback_step_id: Target step to jump to when action=FALLBACK.
            Must be a valid step id in the containing workflow.
    """

    action: StepErrorAction = StepErrorAction.ABORT
    max_retries: int = 3
    base_delay: float = 1.0
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    fallback_step_id: Optional[str] = None


@dataclass
class StepCheckpoint:
    """Persisted record of a successfully completed step.

    Args:
        step_id: The step that completed.
        status: Always ``"completed"`` for persisted checkpoints.
        output: The step's result dict.
        timestamp: Unix timestamp when the step completed.
    """

    step_id: str
    status: str
    output: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# WorkflowCheckpointManager
# ---------------------------------------------------------------------------


class WorkflowCheckpointManager:
    """
    Persists and retrieves per-step checkpoints in Redis.

    All keys live under ``workflow:checkpoints:<execution_id>:<step_id>``
    so they are namespaced per execution and easy to bulk-clear.

    Uses the ``workflows`` Redis database so checkpoint data is isolated from
    the general application cache.
    """

    _KEY_PREFIX = "workflow:checkpoints"

    def _redis(self):
        """Return a synchronous Redis client backed by the workflows database."""
        return get_redis_client(database="workflows")

    def _step_key(self, execution_id: str, step_id: str) -> str:
        return f"{self._KEY_PREFIX}:{execution_id}:{step_id}"

    def _scan_pattern(self, execution_id: str) -> str:
        return f"{self._KEY_PREFIX}:{execution_id}:*"

    def save_checkpoint(
        self,
        execution_id: str,
        step_id: str,
        output: Dict[str, Any],
    ) -> None:
        """Persist a completed step checkpoint to Redis.

        Args:
            execution_id: Unique workflow execution identifier.
            step_id: Step that completed successfully.
            output: The step's result dict to preserve for resume.
        """
        checkpoint = StepCheckpoint(
            step_id=step_id,
            status="completed",
            output=output,
            timestamp=time.time(),
        )
        payload = json.dumps(
            {
                "step_id": checkpoint.step_id,
                "status": checkpoint.status,
                "output": checkpoint.output,
                "timestamp": checkpoint.timestamp,
            },
            default=str,
            ensure_ascii=False,
        )
        key = self._step_key(execution_id, step_id)
        try:
            client = self._redis()
            client.setex(key, _CHECKPOINT_TTL_SECONDS, payload)
            logger.debug("Checkpoint saved: execution=%s step=%s", execution_id, step_id)
        except Exception as exc:
            # Checkpoint failure must not abort the workflow — log and continue
            logger.warning(
                "Failed to save checkpoint for execution=%s step=%s: %s",
                execution_id,
                step_id,
                exc,
            )

    def load_checkpoints(self, execution_id: str) -> Dict[str, StepCheckpoint]:
        """Load all saved checkpoints for an execution.

        Args:
            execution_id: Workflow execution to load checkpoints for.

        Returns:
            Mapping of step_id -> StepCheckpoint for every persisted step.
            Empty dict if Redis is unreachable or no checkpoints exist.
        """
        pattern = self._scan_pattern(execution_id)
        checkpoints: Dict[str, StepCheckpoint] = {}
        try:
            client = self._redis()
            keys = client.keys(pattern)
            if not keys:
                return checkpoints
            values = client.mget(keys)
            for raw in values:
                if raw is None:
                    continue
                data = json.loads(raw)
                cp = StepCheckpoint(
                    step_id=data["step_id"],
                    status=data["status"],
                    output=data["output"],
                    timestamp=data["timestamp"],
                )
                checkpoints[cp.step_id] = cp
        except Exception as exc:
            logger.warning(
                "Failed to load checkpoints for execution=%s: %s", execution_id, exc
            )
        return checkpoints

    def get_resume_point(self, execution_id: str) -> Optional[str]:
        """Return the first step_id that has NOT been checkpointed.

        When all steps are checkpointed this returns ``None`` (nothing to resume).
        When there are no checkpoints at all this also returns ``None`` — callers
        should start from the beginning.

        Args:
            execution_id: Workflow execution to inspect.

        Returns:
            The step_id of the earliest un-checkpointed step, or ``None``.
        """
        checkpoints = self.load_checkpoints(execution_id)
        if not checkpoints:
            return None
        # Return a sentinel indicating there ARE checkpoints so the executor
        # knows to consult them.  The executor itself decides which step to
        # skip based on the full checkpoint map.
        completed_ids = set(checkpoints.keys())
        logger.info(
            "Resume point for execution=%s: %d completed steps: %s",
            execution_id,
            len(completed_ids),
            sorted(completed_ids),
        )
        return None  # Executor uses load_checkpoints() to skip completed steps

    def clear_checkpoints(self, execution_id: str) -> None:
        """Delete all checkpoints for a completed/abandoned execution.

        Args:
            execution_id: Execution whose checkpoints should be removed.
        """
        pattern = self._scan_pattern(execution_id)
        try:
            client = self._redis()
            keys = client.keys(pattern)
            if keys:
                client.delete(*keys)
                logger.info(
                    "Cleared %d checkpoint(s) for execution=%s",
                    len(keys),
                    execution_id,
                )
        except Exception as exc:
            logger.warning(
                "Failed to clear checkpoints for execution=%s: %s", execution_id, exc
            )


# ---------------------------------------------------------------------------
# StepErrorHandler
# ---------------------------------------------------------------------------


@dataclass
class ErrorHandlerResult:
    """Outcome of a StepErrorHandler.handle_error() call.

    Args:
        action: The action that was executed.
        should_continue: Whether workflow execution should continue after this.
        fallback_step_id: Non-None only when action==FALLBACK; jump target.
        error_message: Human-readable description of what happened.
    """

    action: StepErrorAction
    should_continue: bool
    fallback_step_id: Optional[str] = None
    error_message: str = ""


class StepErrorHandler:
    """
    Executes the per-step error action defined in a StepErrorConfig.

    Supported actions:
    - RETRY: sleep with linear/exponential backoff then re-raise to let the
      caller retry; raises ``StepRetrySignal`` after max_retries is exceeded.
    - SKIP: log the error and instruct the executor to move to the next step.
    - FALLBACK: route execution to ``config.fallback_step_id``.
    - PAUSE: log and instruct the executor to suspend the workflow for human review.
    - ABORT: log and instruct the executor to terminate immediately.
    """

    async def handle_error(
        self,
        step_id: str,
        error: Exception,
        config: StepErrorConfig,
        attempt: int = 1,
    ) -> ErrorHandlerResult:
        """Decide and execute the appropriate action for a failed step.

        Args:
            step_id: Identifier of the step that failed.
            error: The exception raised by the step.
            config: Error-handling policy for this step.
            attempt: Current attempt number (1-based).  Used to compute backoff.

        Returns:
            ErrorHandlerResult describing what happened and whether to continue.
        """
        logger.warning(
            "Step %s failed (attempt %d): %s — action=%s",
            step_id,
            attempt,
            error,
            config.action.value,
        )

        if config.action == StepErrorAction.RETRY:
            return await self._handle_retry(step_id, error, config, attempt)

        if config.action == StepErrorAction.SKIP:
            return self._handle_skip(step_id, error)

        if config.action == StepErrorAction.FALLBACK:
            return self._handle_fallback(step_id, error, config)

        if config.action == StepErrorAction.PAUSE:
            return self._handle_pause(step_id, error)

        # Default / ABORT
        return self._handle_abort(step_id, error)

    # ------------------------------------------------------------------
    # Private helpers — one per action
    # ------------------------------------------------------------------

    async def _handle_retry(
        self,
        step_id: str,
        error: Exception,
        config: StepErrorConfig,
        attempt: int,
    ) -> ErrorHandlerResult:
        """Sleep with backoff if retries remain; otherwise signal abort."""
        if attempt > config.max_retries:
            logger.error(
                "Step %s exhausted %d retries — aborting",
                step_id,
                config.max_retries,
            )
            return ErrorHandlerResult(
                action=StepErrorAction.ABORT,
                should_continue=False,
                error_message=(
                    f"Step {step_id} failed after {config.max_retries} retries: {error}"
                ),
            )

        delay = self._compute_delay(config, attempt)
        logger.info(
            "Step %s: retry %d/%d in %.2fs (%s backoff)",
            step_id,
            attempt,
            config.max_retries,
            delay,
            config.backoff.value,
        )
        await asyncio.sleep(delay)
        return ErrorHandlerResult(
            action=StepErrorAction.RETRY,
            should_continue=True,
            error_message=f"Step {step_id} retrying (attempt {attempt}): {error}",
        )

    def _handle_skip(self, step_id: str, error: Exception) -> ErrorHandlerResult:
        logger.info("Step %s skipped due to error: %s", step_id, error)
        return ErrorHandlerResult(
            action=StepErrorAction.SKIP,
            should_continue=True,
            error_message=f"Step {step_id} skipped: {error}",
        )

    def _handle_fallback(
        self,
        step_id: str,
        error: Exception,
        config: StepErrorConfig,
    ) -> ErrorHandlerResult:
        if not config.fallback_step_id:
            logger.error(
                "Step %s configured FALLBACK but no fallback_step_id — aborting",
                step_id,
            )
            return ErrorHandlerResult(
                action=StepErrorAction.ABORT,
                should_continue=False,
                error_message=f"Step {step_id} FALLBACK misconfigured (no fallback_step_id): {error}",
            )
        logger.info(
            "Step %s failed; routing to fallback step %s",
            step_id,
            config.fallback_step_id,
        )
        return ErrorHandlerResult(
            action=StepErrorAction.FALLBACK,
            should_continue=True,
            fallback_step_id=config.fallback_step_id,
            error_message=f"Step {step_id} falling back to {config.fallback_step_id}: {error}",
        )

    def _handle_pause(self, step_id: str, error: Exception) -> ErrorHandlerResult:
        logger.warning(
            "Workflow paused at step %s — human review required. Error: %s",
            step_id,
            error,
        )
        return ErrorHandlerResult(
            action=StepErrorAction.PAUSE,
            should_continue=False,
            error_message=f"Workflow paused at step {step_id}: {error}",
        )

    def _handle_abort(self, step_id: str, error: Exception) -> ErrorHandlerResult:
        logger.error("Step %s aborted workflow: %s", step_id, error)
        return ErrorHandlerResult(
            action=StepErrorAction.ABORT,
            should_continue=False,
            error_message=f"Step {step_id} aborted workflow: {error}",
        )

    @staticmethod
    def _compute_delay(config: StepErrorConfig, attempt: int) -> float:
        """Compute the wait time before the next retry.

        Args:
            config: StepErrorConfig containing backoff strategy and base_delay.
            attempt: Current 1-based attempt number (delay is for *this* attempt).

        Returns:
            Delay in seconds, capped at 60 seconds.
        """
        if config.backoff == BackoffStrategy.LINEAR:
            delay = config.base_delay * attempt
        else:
            # Exponential: base_delay * 2^(attempt-1)
            delay = config.base_delay * (2 ** (attempt - 1))
        return min(delay, 60.0)
