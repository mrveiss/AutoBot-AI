# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Controller Module

Handles workflow control actions (pause, resume, cancel, approve, skip).
"""

from datetime import datetime, timezone
from typing import Dict

from autobot_shared.logging_manager import get_logger
from monitoring.prometheus_metrics import get_metrics_manager

from .executor import WorkflowExecutor
from .messaging import WorkflowMessenger
from .models import ActiveWorkflow, WorkflowControlRequest

logger = get_logger(__name__)


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

    async def _decide_step(
        self, workflow: ActiveWorkflow, step_id: str, workflows: Dict[str, ActiveWorkflow], decision: str, apply
    ) -> bool:
        """Apply a step decision, then withdraw its pending approval record (#21101).

        The executor refuses a decision for an unknown, non-current or not-awaiting step by
        raising StepNotAwaitingApproval (route: 409), so a refusal leaves the record listed and
        the approver can still act. The record is withdrawn only once *apply* has returned. If
        *apply* raises after accepting, the exception propagates before the withdraw and the
        record stays pending rather than being lost.
        """
        await apply(workflow, step_id, workflows)
        await self.executor.step_approvals.withdraw(workflow.workflow_id, step_id)
        self.prometheus_metrics.record_workflow_approval(workflow_type="automated_workflow", decision=decision)
        return True

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
