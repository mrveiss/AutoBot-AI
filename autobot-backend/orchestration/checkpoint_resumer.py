# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
CheckpointResumer — owns resume-from-checkpoint logic for workflow execution.

Issue #6827: extracted from WorkflowExecutor god class (1,178 LOC).  The
save/load/apply/clear checkpoint operations are a self-contained concern that
belonged in a collaborator, not the main executor.  WorkflowExecutor now
delegates to this class for all checkpoint operations.

Responsibilities:
- Save a step checkpoint after successful completion.
- Load checkpoints from Redis and pre-populate execution_context for resume.
- Clear checkpoints when a workflow reaches a terminal state.
"""

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from constants.status_enums import TaskStatus

from .error_handler import StepCheckpoint, WorkflowCheckpointManager
from .variable_resolver import StepOutput

logger = get_logger(__name__)


class CheckpointResumer:
    """Encapsulates checkpoint persistence and resume logic.

    Used by WorkflowExecutor to save step progress and restore it on re-run.
    All Redis interactions are delegated to WorkflowCheckpointManager.
    """

    def __init__(self) -> None:
        self._manager = WorkflowCheckpointManager()

    def save(self, workflow_id: str, step_id: str, step_result: Dict[str, Any]) -> None:
        """Persist a checkpoint for *step_id* after successful execution.

        Silently skips when *workflow_id* is empty (e.g. DAG adapter calls).

        Issue #2154.
        """
        if not workflow_id:
            return
        checkpoint = StepCheckpoint(
            step_id=step_id,
            status=TaskStatus.COMPLETED.value,
            output=step_result,
        )
        self._manager.save(workflow_id, checkpoint)

    def apply(
        self,
        workflow_id: str,
        steps: List[Dict[str, Any]],
        execution_context: Dict[str, Any],
    ) -> None:
        """Load checkpoints from Redis and mark already-completed steps.

        Mutates *steps* in-place (sets ``status="completed"``) and populates
        ``execution_context["step_results"]`` and ``execution_context["step_outputs"]``
        so variable resolution works correctly for resumed steps.

        Issue #2154.  Issue #3231: refreshes TTL so long-paused workflows
        (e.g. awaiting human approval) get a fresh 30-day window.
        """
        checkpoints = self._manager.load_all(workflow_id)
        if not checkpoints:
            return

        # Issue #3231: refresh TTL at resume time.
        self._manager.refresh_ttl(workflow_id)

        logger.info(
            "Workflow %s: resuming with %d checkpointed steps: %s",
            workflow_id,
            len(checkpoints),
            list(checkpoints.keys()),
        )

        for step in steps:
            step_id = step["id"]
            cp = checkpoints.get(step_id)
            if cp is None:
                continue
            step["status"] = TaskStatus.COMPLETED.value
            execution_context["step_results"][step_id] = cp.output
            execution_context["step_outputs"][step_id] = StepOutput.from_step_result(cp.output)

    def clear(self, workflow_id: str) -> None:
        """Delete all checkpoints for a completed workflow.

        Called after successful terminal-state transition so Redis is not
        polluted with stale state.  Issue #2154.
        """
        self._manager.clear(workflow_id)
