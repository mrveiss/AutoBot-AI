# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Controller Module

Handles workflow control actions (pause, resume, cancel, approve, skip).
"""

from datetime import datetime, timezone
from typing import Awaitable, Callable, Dict

from autobot_shared.logging_manager import get_logger
from monitoring.prometheus_metrics import get_metrics_manager

from .executor import WorkflowExecutor
from .messaging import WorkflowMessenger
from .models import ActiveWorkflow, StepNotAwaitingApproval, WorkflowControlRequest, WorkflowStepStatus

logger = get_logger(__name__)


StepDecision = Callable[[ActiveWorkflow, str, Dict[str, ActiveWorkflow]], Awaitable[None]]


class WorkflowController:
    """Handles workflow control actions from user"""

    def __init__(self, messenger: WorkflowMessenger, executor: WorkflowExecutor) -> None:
        """Initialize controller with messenger and executor components."""
        self.messenger = messenger
        self.executor = executor
        self.prometheus_metrics = get_metrics_manager()

    async def handle_control(
        self,
        control_request: WorkflowControlRequest,
        workflows: Dict[str, ActiveWorkflow],
    ) -> bool:
        """Handle workflow control actions from user"""
        workflow_id = control_request.workflow_id

        if workflow_id not in workflows:
            logger.error("Workflow %s not found for control action", workflow_id)
            return False

        workflow = workflows[workflow_id]
        action = control_request.action.lower()

        # Log user intervention
        intervention = {
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "action": action,
            "step_id": control_request.step_id,
            "user_input": control_request.user_input,
        }
        workflow.user_interventions.append(intervention)

        if action == "pause":
            return await self._pause_workflow(workflow)

        elif action == "resume":
            return await self._resume_workflow(workflow, workflows)

        elif action == "cancel":
            return await self._cancel_workflow(workflow, workflows)

        elif action == "approve_step":
            return await self._approve_step(workflow, control_request.step_id, workflows)

        elif action == "skip_step":
            return await self._skip_step(workflow, control_request.step_id, workflows)

        else:
            logger.warning("Unknown workflow control action: %s", action)
            return False

    async def _pause_workflow(self, workflow: ActiveWorkflow) -> bool:
        """Pause workflow execution"""
        workflow.is_paused = True
        await self.messenger.send_message(
            workflow.session_id,
            {"type": "workflow_paused", "workflow_id": workflow.workflow_id},
        )
        return True

    async def _resume_workflow(self, workflow: ActiveWorkflow, workflows: Dict[str, ActiveWorkflow]) -> bool:
        """Resume workflow execution"""
        workflow.is_paused = False
        await self.messenger.send_message(
            workflow.session_id,
            {"type": "workflow_resumed", "workflow_id": workflow.workflow_id},
        )
        await self.executor.process_next_step(workflow, workflows)
        return True

    async def _cancel_workflow(self, workflow: ActiveWorkflow, workflows: Dict[str, ActiveWorkflow]) -> bool:
        """Cancel workflow execution"""
        workflow.is_cancelled = True
        await self.executor.cancel_workflow(workflow, workflows)
        return True

    @staticmethod
    def _still_awaiting(workflow: ActiveWorkflow, step_id: str) -> bool:
        """True while *step_id* exists and is parked in WAITING_APPROVAL (the decision was not accepted)."""
        return any(s.step_id == step_id and s.status == WorkflowStepStatus.WAITING_APPROVAL for s in workflow.steps)

    async def _decide_step(
        self,
        workflow: ActiveWorkflow,
        step_id: str,
        workflows: Dict[str, ActiveWorkflow],
        decision: str,
        apply: StepDecision,
    ) -> bool:
        """Apply a step decision, then withdraw its pending approval record (#21101).

        The executor refuses a decision for an unknown, non-current or not-awaiting step by
        raising StepNotAwaitingApproval (route: 409); nothing was accepted, so the record stays
        listed and the approver can still act. Once the decision is accepted (apply returned, or
        the step left WAITING_APPROVAL before apply failed), the record is withdrawn in a finally,
        so a failure in the continuation *apply* runs (the following steps) cannot leave an
        orphan approval behind. The metric is recorded once per accepted decision, with that
        decision as its outcome.
        """
        was_awaiting = self._still_awaiting(workflow, step_id)
        try:
            await apply(workflow, step_id, workflows)
        except StepNotAwaitingApproval:
            raise  # refused: this call accepted nothing, so it withdraws and records nothing
        except BaseException:
            if was_awaiting and not self._still_awaiting(workflow, step_id):
                await self._finish_decision(workflow, step_id, decision, failing=True)
            raise
        await self._finish_decision(workflow, step_id, decision, failing=False)
        return True

    async def _finish_decision(self, workflow: ActiveWorkflow, step_id: str, decision: str, failing: bool) -> None:
        """Withdraw the accepted decision's record and record its metric once.

        While the apply failure is in flight (*failing*) a withdraw error is logged so it cannot
        replace that failure; on success it surfaces. The metric is recorded either way.
        """
        try:
            await self.executor.step_approvals.withdraw(workflow.workflow_id, step_id)
        except Exception:
            if not failing:
                raise
            logger.exception("Failed to withdraw approval for step %s of %s", step_id, workflow.workflow_id)
        finally:
            self.prometheus_metrics.record_workflow_approval(workflow_type="automated_workflow", decision=decision)

    async def _approve_step(
        self,
        workflow: ActiveWorkflow,
        step_id: str,
        workflows: Dict[str, ActiveWorkflow],
    ) -> bool:
        """Approve and execute a workflow step"""
        return await self._decide_step(workflow, step_id, workflows, "approved", self.executor.approve_and_execute_step)

    async def _skip_step(
        self,
        workflow: ActiveWorkflow,
        step_id: str,
        workflows: Dict[str, ActiveWorkflow],
    ) -> bool:
        """Skip a workflow step"""
        return await self._decide_step(workflow, step_id, workflows, "skipped", self.executor.skip_step)
