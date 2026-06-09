# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Safety Limits — per-step timeouts, resource quotas, and cost budgets.

Issue #2159: Add per-step timeout enforcement, WorkflowLimits config, and
CostTracker service for token/cost budgeting per workflow execution.
"""

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_STEP_TIMEOUT_S: int = 300  # 5 minutes
_DEFAULT_MAX_STEPS: int = 100
_DEFAULT_MAX_TOKENS: int = 50_000
_DEFAULT_MAX_OUTPUT_BYTES: int = 10 * 1024 * 1024  # 10 MB
_DEFAULT_MAX_CONCURRENT: int = 3


# ---------------------------------------------------------------------------
# WorkflowLimits — system/workflow-level resource quotas
# ---------------------------------------------------------------------------


@dataclass
class WorkflowLimits:
    """
    Resource quotas for a single workflow execution.

    Issue #2159: Enforced by WorkflowExecutor and ConcurrentWorkflowLimiter.
    All fields have safe defaults; callers may override per workflow.
    """

    max_concurrent: int = _DEFAULT_MAX_CONCURRENT
    max_steps: int = _DEFAULT_MAX_STEPS
    max_tokens: int = _DEFAULT_MAX_TOKENS
    max_output_bytes: int = _DEFAULT_MAX_OUTPUT_BYTES
    default_step_timeout_s: int = _DEFAULT_STEP_TIMEOUT_S

    def validate(self) -> None:
        """Raise ValueError when any limit is out of acceptable range."""
        if self.max_concurrent < 1:
            raise ValueError("max_concurrent must be >= 1")
        if self.max_steps < 1:
            raise ValueError("max_steps must be >= 1")
        if self.max_tokens < 1:
            raise ValueError("max_tokens must be >= 1")
        if self.max_output_bytes < 1:
            raise ValueError("max_output_bytes must be >= 1")
        if self.default_step_timeout_s < 1:
            raise ValueError("default_step_timeout_s must be >= 1")


# ---------------------------------------------------------------------------
# CostTracker — per-execution token/cost accumulation
# ---------------------------------------------------------------------------


@dataclass
class _ExecutionCost:
    """Running totals for one workflow execution."""

    workflow_id: str
    total_tokens: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_output_bytes: int = 0
    llm_call_count: int = 0
    started_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict:
        """Serialise to plain dict for analytics/logging."""
        return {
            "workflow_id": self.workflow_id,
            "total_tokens": self.total_tokens,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_output_bytes": self.total_output_bytes,
            "llm_call_count": self.llm_call_count,
            "elapsed_seconds": round(time.time() - self.started_at, 2),
        }


class CostTracker:
    """
    Tracks LLM token usage and output size per workflow execution.

    Issue #2159: Accumulates usage per execution, enforces budget limits, and
    exposes per-workflow analytics.  Thread-safe for concurrent coroutines via
    asyncio — no threading.Lock required (single-threaded event loop).

    Usage::

        tracker = CostTracker()
        tracker.start(workflow_id)
        tracker.record_tokens(workflow_id, input_tokens=100, output_tokens=200)
        tracker.record_output_bytes(workflow_id, len(result_bytes))
        summary = tracker.get_summary(workflow_id)
    """

    def __init__(self) -> None:
        self._executions: Dict[str, _ExecutionCost] = {}

    def start(self, workflow_id: str) -> None:
        """Begin cost tracking for *workflow_id*."""
        self._executions[workflow_id] = _ExecutionCost(workflow_id=workflow_id)
        logger.debug("CostTracker: started tracking workflow %s", workflow_id)

    def record_tokens(
        self,
        workflow_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """Accumulate token counts for one LLM call inside *workflow_id*."""
        cost = self._executions.get(workflow_id)
        if cost is None:
            logger.warning("CostTracker: unknown workflow_id %s — ignoring", workflow_id)
            return
        cost.total_input_tokens += input_tokens
        cost.total_output_tokens += output_tokens
        cost.total_tokens += input_tokens + output_tokens
        cost.llm_call_count += 1

    def record_output_bytes(self, workflow_id: str, byte_count: int) -> None:
        """Accumulate step output size for *workflow_id*."""
        cost = self._executions.get(workflow_id)
        if cost is None:
            return
        cost.total_output_bytes += byte_count

    def check_token_budget(self, workflow_id: str, limits: WorkflowLimits) -> bool:
        """
        Return True when token budget has NOT been exceeded.

        Returns False and logs a warning when the workflow has exhausted its
        token budget so the caller can abort.
        """
        cost = self._executions.get(workflow_id)
        if cost is None:
            return True
        if cost.total_tokens >= limits.max_tokens:
            logger.warning(
                "CostTracker: workflow %s exceeded token budget (%d >= %d)",
                workflow_id,
                cost.total_tokens,
                limits.max_tokens,
            )
            return False
        return True

    def check_output_budget(self, workflow_id: str, limits: WorkflowLimits) -> bool:
        """Return True when output-byte budget has NOT been exceeded."""
        cost = self._executions.get(workflow_id)
        if cost is None:
            return True
        if cost.total_output_bytes >= limits.max_output_bytes:
            logger.warning(
                "CostTracker: workflow %s exceeded output budget (%d bytes >= %d bytes)",
                workflow_id,
                cost.total_output_bytes,
                limits.max_output_bytes,
            )
            return False
        return True

    def get_summary(self, workflow_id: str) -> Dict | None:
        """Return cost summary dict, or None if *workflow_id* is unknown."""
        cost = self._executions.get(workflow_id)
        return cost.to_dict() if cost else None

    def finish(self, workflow_id: str) -> Dict | None:
        """
        Remove tracking entry for *workflow_id* and return its final summary.

        The summary is logged at INFO level for cost analytics queries.
        """
        cost = self._executions.pop(workflow_id, None)
        if cost is None:
            return None
        summary = cost.to_dict()
        logger.info(
            "CostTracker: workflow %s finished — tokens=%d (in=%d out=%d) "
            "output_bytes=%d llm_calls=%d elapsed=%.1fs",
            workflow_id,
            summary["total_tokens"],
            summary["total_input_tokens"],
            summary["total_output_tokens"],
            summary["total_output_bytes"],
            summary["llm_call_count"],
            summary["elapsed_seconds"],
        )
        return summary

    def top_expensive(self, limit: int = 10) -> list:
        """
        Return the top *limit* in-progress executions sorted by token usage (desc).

        Issue #2159: Cost analytics — which workflows consume the most tokens.
        """
        sorted_costs = sorted(
            self._executions.values(),
            key=lambda c: c.total_tokens,
            reverse=True,
        )
        return [c.to_dict() for c in sorted_costs[:limit]]


# ---------------------------------------------------------------------------
# StepTimeoutManager — per-step asyncio timeout enforcement
# ---------------------------------------------------------------------------


class StepTimeoutEnforcer:
    """
    Wraps step execution coroutines with per-step timeouts.

    Issue #2159: Each WorkflowStep may define timeout_seconds; falls back to
    WorkflowLimits.default_step_timeout_s when not set.

    Usage::

        enforcer = StepTimeoutEnforcer()
        result = await enforcer.run_with_timeout(
            coro=execute_step(),
            step_id=step.step_id,
            timeout_seconds=step.timeout_seconds,
            limits=limits,
        )
        # raises StepTimeoutError on timeout
    """

    async def run_with_timeout(
        self,
        coro,
        step_id: str,
        timeout_seconds: int | None,
        limits: WorkflowLimits,
    ):
        """
        Await *coro* with a deadline.

        Args:
            coro: Awaitable step coroutine.
            step_id: Step identifier for log messages.
            timeout_seconds: Override timeout; None means use limits default.
            limits: WorkflowLimits providing the default_step_timeout_s fallback.

        Returns:
            Whatever *coro* returns.

        Raises:
            StepTimeoutError: When the step exceeds its deadline.
        """
        effective_timeout = timeout_seconds if timeout_seconds is not None else limits.default_step_timeout_s
        try:
            return await asyncio.wait_for(coro, timeout=effective_timeout)
        except asyncio.TimeoutError:
            logger.error(
                "StepTimeoutEnforcer: step %s timed out after %ds",
                step_id,
                effective_timeout,
            )
            raise StepTimeoutError(step_id, effective_timeout)


class StepTimeoutError(Exception):
    """Raised when a workflow step exceeds its configured timeout."""

    def __init__(self, step_id: str, timeout_seconds: int) -> None:
        self.step_id = step_id
        self.timeout_seconds = timeout_seconds
        super().__init__(f"Step '{step_id}' exceeded timeout of {timeout_seconds}s")
