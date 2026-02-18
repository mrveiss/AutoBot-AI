# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Execution Module

Handles workflow step execution, dependency checking, and command execution.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import TYPE_CHECKING, Dict

from backend.constants.threshold_constants import TimingConstants
from backend.monitoring.prometheus_metrics import get_metrics_manager
from backend.type_defs.common import Metadata

from .models import (
    ActiveWorkflow,
    PlanApprovalMode,
    PlanApprovalRequest,
    PlanApprovalStatus,
    WorkflowStep,
    WorkflowStepStatus,
)
from .step_evaluator import WorkflowStepEvaluator

if TYPE_CHECKING:
    from .messaging import WorkflowMessenger

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """Handles workflow step execution and processing"""

    def __init__(self, messenger: "WorkflowMessenger"):
        """Initialize executor with messenger and step evaluator."""
        self.messenger = messenger
        self.step_evaluator = WorkflowStepEvaluator()
        self.prometheus_metrics = get_metrics_manager()
        # Issue #390: Track pending plan approvals
        self._pending_plan_approvals: Dict[str, PlanApprovalRequest] = {}
        self._plan_approval_events: Dict[str, asyncio.Event] = {}

    async def start_execution(
        self, workflow: ActiveWorkflow, workflows: Dict[str, ActiveWorkflow]
    ) -> bool:
        """Start executing automated workflow"""
        workflow.started_at = datetime.now()
        workflow.prometheus_start_time = time.time()

        # Update active workflows count in Prometheus
        workflow_type = "automated_workflow"
        active_count = len(
            [w for w in workflows.values() if w.started_at and not w.completed_at]
        )
        self.prometheus_metrics.update_active_workflows(
            workflow_type=workflow_type, count=active_count
        )

        # Send workflow start message to frontend
        await self.messenger.send_message(
            workflow.session_id,
            {
                "type": "start_workflow",
                "workflow": {
                    "id": workflow.workflow_id,
                    "name": workflow.name,
                    "description": workflow.description,
                    "steps": [
                        {
                            "stepNumber": i + 1,
                            "totalSteps": len(workflow.steps),
                            "command": step.command,
                            "description": step.description,
                            "explanation": step.explanation,
                            "requiresConfirmation": step.requires_confirmation,
                        }
                        for i, step in enumerate(workflow.steps)
                    ],
                },
            },
        )

        # Start processing first step
        await self.process_next_step(workflow, workflows)
        return True

    async def _evaluate_step_with_judges(
        self, workflow: ActiveWorkflow, current_step: WorkflowStep
    ) -> bool:
        """
        Evaluate step with LLM judges if enabled.

        Args:
            workflow: The active workflow
            current_step: The step to evaluate

        Returns:
            True if step should proceed, False if rejected. Issue #620.
        """
        if not self.step_evaluator.judges_enabled:
            return True

        try:
            step_evaluation = await self.step_evaluator.evaluate_step(
                workflow, current_step
            )
            if step_evaluation.get("should_proceed", True):
                return True

            logger.warning(
                f"Step {current_step.step_id} rejected by LLM judge: "
                f"{step_evaluation.get('reason', 'Unknown')}"
            )
            current_step.status = WorkflowStepStatus.FAILED
            workflow.is_paused = True
            await self.messenger.send_message(
                workflow.session_id,
                {
                    "type": "step_rejected_by_judge",
                    "workflow_id": workflow.workflow_id,
                    "step_id": current_step.step_id,
                    "reason": step_evaluation.get(
                        "reason", "Step rejected by safety evaluation"
                    ),
                    "suggestions": step_evaluation.get("suggestions", []),
                },
            )
            return False
        except Exception as e:
            logger.error("Error evaluating workflow step with LLM judge: %s", e)
            # Continue without judge evaluation
            return True

    async def process_next_step(
        self, workflow: ActiveWorkflow, workflows: Dict[str, ActiveWorkflow]
    ) -> None:
        """Process the next step in workflow"""
        if workflow.is_paused or workflow.is_cancelled:
            return

        if workflow.current_step_index >= len(workflow.steps):
            await self._complete_workflow(workflow, workflows)
            return

        current_step = workflow.steps[workflow.current_step_index]

        # Check dependencies
        if not self._check_step_dependencies(workflow, current_step):
            logger.warning("Step %s dependencies not met", current_step.step_id)
            current_step.status = WorkflowStepStatus.SKIPPED
            workflow.current_step_index += 1
            await self.process_next_step(workflow, workflows)
            return

        # Evaluate step with LLM judges if enabled (Issue #620: extracted)
        if not await self._evaluate_step_with_judges(workflow, current_step):
            return

        # Update step status
        current_step.status = WorkflowStepStatus.WAITING_APPROVAL
        current_step.started_at = datetime.now()

        # Send step confirmation request to frontend
        await self._send_step_confirmation_request(workflow, current_step)

    async def _send_step_confirmation_request(
        self, workflow: ActiveWorkflow, step: WorkflowStep
    ) -> None:
        """Send step confirmation request to frontend"""
        step_data = {
            "stepNumber": workflow.current_step_index + 1,
            "totalSteps": len(workflow.steps),
            "command": step.command,
            "description": step.description,
            "explanation": step.explanation,
            "requiresConfirmation": step.requires_confirmation,
            "riskLevel": step.risk_level,
            "estimatedDuration": step.estimated_duration,
        }

        await self.messenger.send_message(
            workflow.session_id,
            {
                "type": "step_confirmation_required",
                "workflow_id": workflow.workflow_id,
                "step_id": step.step_id,
                "step_data": step_data,
            },
        )

    def _check_step_dependencies(
        self, workflow: ActiveWorkflow, step: WorkflowStep
    ) -> bool:
        """Check if step dependencies are satisfied"""
        if not step.dependencies:
            return True

        for dep_step_id in step.dependencies:
            dep_step = None
            for s in workflow.steps:
                if s.step_id == dep_step_id:
                    dep_step = s
                    break

            if not dep_step or dep_step.status != WorkflowStepStatus.COMPLETED:
                return False

        return True

    def _record_step_metric(self, status: str) -> None:
        """
        Record Prometheus workflow step metric.

        Args:
            status: The step status ('completed' or 'failed'). Issue #620.
        """
        workflow_type = "automated_workflow"
        step_type = "command_execution"
        self.prometheus_metrics.record_workflow_step(
            workflow_type=workflow_type, step_type=step_type, status=status
        )

    async def _handle_step_execution_failure(
        self,
        workflow: ActiveWorkflow,
        current_step: WorkflowStep,
        step_id: str,
        error: Exception,
    ) -> None:
        """
        Handle step execution failure.

        Args:
            workflow: The active workflow
            current_step: The step that failed
            step_id: The step ID
            error: The exception that occurred. Issue #620.
        """
        logger.error("Step execution failed: %s", error)
        current_step.status = WorkflowStepStatus.FAILED
        current_step.execution_result = {"error": str(error)}

        self._record_step_metric("failed")

        workflow.is_paused = True
        await self.messenger.send_message(
            workflow.session_id,
            {
                "type": "step_failed",
                "workflow_id": workflow.workflow_id,
                "step_id": step_id,
                "error": str(error),
            },
        )

    async def approve_and_execute_step(
        self,
        workflow: ActiveWorkflow,
        step_id: str,
        workflows: Dict[str, ActiveWorkflow],
    ) -> None:
        """Approve and execute workflow step"""
        current_step = workflow.steps[workflow.current_step_index]

        if current_step.step_id != step_id:
            logger.error(
                f"Step ID mismatch: expected {current_step.step_id}, got {step_id}"
            )
            return

        current_step.status = WorkflowStepStatus.EXECUTING

        try:
            result = await self._execute_command(
                workflow.session_id, current_step.command
            )

            current_step.status = WorkflowStepStatus.COMPLETED
            current_step.execution_result = result
            current_step.completed_at = datetime.now()

            self._record_step_metric("completed")

            workflow.current_step_index += 1
            await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)
            await self.process_next_step(workflow, workflows)

        except Exception as e:
            await self._handle_step_execution_failure(
                workflow, current_step, step_id, e
            )

    async def skip_step(
        self,
        workflow: ActiveWorkflow,
        step_id: str,
        workflows: Dict[str, ActiveWorkflow],
    ) -> None:
        """Skip current workflow step"""
        current_step = workflow.steps[workflow.current_step_index]

        if current_step.step_id == step_id:
            current_step.status = WorkflowStepStatus.SKIPPED
            current_step.completed_at = datetime.now()
            workflow.current_step_index += 1

            # Continue with next step
            await asyncio.sleep(TimingConstants.STANDARD_DELAY)
            await self.process_next_step(workflow, workflows)

    async def _execute_command(self, session_id: str, command: str) -> Metadata:
        """Execute command via terminal session"""
        # This would integrate with the existing terminal WebSocket system
        # For now, simulate command execution
        logger.info("Executing workflow command: %s", command)

        # Simulate command execution delay
        await asyncio.sleep(1)

        return {
            "command": command,
            "exit_code": 0,
            "stdout": f"Simulated output for: {command}",
            "stderr": "",
            "execution_time": 1.0,
        }

    def _record_workflow_completion_metrics(
        self, workflow: ActiveWorkflow, workflows: Dict[str, ActiveWorkflow]
    ) -> None:
        """
        Record Prometheus metrics for workflow completion.

        Args:
            workflow: The completed workflow
            workflows: All active workflows for counting. Issue #620.
        """
        if not workflow.prometheus_start_time:
            return

        duration = time.time() - workflow.prometheus_start_time
        workflow_type = "automated_workflow"
        failed_steps = len(
            [s for s in workflow.steps if s.status == WorkflowStepStatus.FAILED]
        )
        status = "failed" if failed_steps > 0 else "success"
        self.prometheus_metrics.record_workflow_execution(
            workflow_type=workflow_type, status=status, duration=duration
        )

        active_count = (
            len([w for w in workflows.values() if w.started_at and not w.completed_at])
            - 1
        )
        self.prometheus_metrics.update_active_workflows(
            workflow_type=workflow_type, count=max(0, active_count)
        )

    def _build_completion_message(self, workflow: ActiveWorkflow) -> dict:
        """
        Build workflow completion message payload.

        Args:
            workflow: The completed workflow

        Returns:
            Completion message dict. Issue #620.
        """
        return {
            "type": "workflow_completed",
            "workflow_id": workflow.workflow_id,
            "name": workflow.name,
            "total_steps": len(workflow.steps),
            "completed_steps": len(
                [s for s in workflow.steps if s.status == WorkflowStepStatus.COMPLETED]
            ),
            "skipped_steps": len(
                [s for s in workflow.steps if s.status == WorkflowStepStatus.SKIPPED]
            ),
            "failed_steps": len(
                [s for s in workflow.steps if s.status == WorkflowStepStatus.FAILED]
            ),
        }

    async def _complete_workflow(
        self, workflow: ActiveWorkflow, workflows: Dict[str, ActiveWorkflow]
    ) -> None:
        """Complete workflow execution"""
        workflow.completed_at = datetime.now()

        self._record_workflow_completion_metrics(workflow, workflows)

        await self.messenger.send_message(
            workflow.session_id, self._build_completion_message(workflow)
        )

    def _record_cancellation_metrics(
        self, workflow: ActiveWorkflow, workflows: Dict[str, ActiveWorkflow]
    ) -> None:
        """
        Record Prometheus metrics for workflow cancellation.

        Args:
            workflow: The cancelled workflow
            workflows: All active workflows for counting. Issue #620.
        """
        if not workflow.prometheus_start_time:
            return

        duration = time.time() - workflow.prometheus_start_time
        workflow_type = "automated_workflow"
        self.prometheus_metrics.record_workflow_execution(
            workflow_type=workflow_type, status="cancelled", duration=duration
        )

        active_count = (
            len([w for w in workflows.values() if w.started_at and not w.completed_at])
            - 1
        )
        self.prometheus_metrics.update_active_workflows(
            workflow_type=workflow_type, count=max(0, active_count)
        )

    async def cancel_workflow(
        self, workflow: ActiveWorkflow, workflows: Dict[str, ActiveWorkflow]
    ) -> None:
        """Cancel workflow execution"""
        workflow.is_cancelled = True
        workflow.completed_at = datetime.now()

        # Issue #390: Clear any pending approval when workflow is cancelled
        self.clear_pending_approval(workflow.workflow_id)

        self._record_cancellation_metrics(workflow, workflows)

        await self.messenger.send_message(
            workflow.session_id,
            {"type": "workflow_cancelled", "workflow_id": workflow.workflow_id},
        )

    # =========================================================================
    # Issue #390: Plan Approval System - Present Plan Before Execution
    # =========================================================================

    # Issue #390: Currently only FULL_PLAN_APPROVAL is implemented
    _SUPPORTED_APPROVAL_MODES = frozenset({PlanApprovalMode.FULL_PLAN_APPROVAL})

    def _validate_approval_params(
        self, approval_mode: PlanApprovalMode, timeout_seconds: int
    ) -> int:
        """
        Validate approval mode and timeout parameters (Issue #665: extracted helper).

        Args:
            approval_mode: The requested approval mode
            timeout_seconds: Requested timeout in seconds

        Returns:
            Validated (possibly capped) timeout value

        Raises:
            ValueError: If approval mode unsupported or timeout invalid
        """
        if approval_mode not in self._SUPPORTED_APPROVAL_MODES:
            supported = [m.value for m in self._SUPPORTED_APPROVAL_MODES]
            raise ValueError(
                f"Approval mode '{approval_mode.value}' is not yet implemented. "
                f"Supported modes: {supported}"
            )

        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        if timeout_seconds > 3600:
            logger.warning(
                f"Timeout {timeout_seconds}s exceeds max 3600s, capping at 3600s"
            )
            return 3600

        return timeout_seconds

    def _check_existing_approval(self, workflow_id: str) -> PlanApprovalRequest | None:
        """
        Check for existing pending approval (Issue #665: extracted helper).

        Args:
            workflow_id: The workflow ID to check

        Returns:
            Existing PlanApprovalRequest if still pending, None otherwise
        """
        if workflow_id not in self._pending_plan_approvals:
            return None

        existing = self._pending_plan_approvals[workflow_id]
        if existing.status in [
            PlanApprovalStatus.AWAITING_APPROVAL,
            PlanApprovalStatus.PRESENTED,
        ]:
            logger.warning(
                f"Approval already pending for {workflow_id}, returning existing"
            )
            return existing

        # If resolved, cleanup first
        self.clear_pending_approval(workflow_id)
        return None

    def _create_approval_request(
        self,
        workflow: ActiveWorkflow,
        approval_mode: PlanApprovalMode,
        timeout_seconds: int,
    ) -> PlanApprovalRequest:
        """
        Create a new plan approval request (Issue #665: extracted helper).

        Args:
            workflow: The workflow to create approval for
            approval_mode: The approval mode
            timeout_seconds: Timeout for approval

        Returns:
            New PlanApprovalRequest instance
        """
        risk_assessment = self._assess_plan_risk(workflow)
        total_duration = sum(step.estimated_duration for step in workflow.steps)

        return PlanApprovalRequest(
            workflow_id=workflow.workflow_id,
            plan_summary=f"Execute {len(workflow.steps)} steps: {workflow.description}",
            total_steps=len(workflow.steps),
            steps_preview=workflow.steps,
            approval_mode=approval_mode,
            status=PlanApprovalStatus.PENDING,
            risk_assessment=risk_assessment,
            estimated_total_duration=total_duration,
            timeout_seconds=timeout_seconds,
        )

    async def present_plan_for_approval(
        self,
        workflow: ActiveWorkflow,
        approval_mode: PlanApprovalMode = PlanApprovalMode.FULL_PLAN_APPROVAL,
        timeout_seconds: int = 300,
    ) -> PlanApprovalRequest:
        """
        Present workflow plan to user and wait for approval before execution.

        Issue #390: Multi-step tasks should present plan before execution.
        Issue #665: Refactored to use extracted helper methods.

        Args:
            workflow: The workflow to present for approval
            approval_mode: How approval should be requested (currently only full_plan supported)
            timeout_seconds: How long to wait for user approval

        Returns:
            PlanApprovalRequest with approval status

        Raises:
            ValueError: If unsupported approval_mode is requested
        """
        # Validate parameters (Issue #665: uses helper)
        timeout_seconds = self._validate_approval_params(approval_mode, timeout_seconds)

        # Check for existing pending approval (Issue #665: uses helper)
        existing = self._check_existing_approval(workflow.workflow_id)
        if existing:
            return existing

        # Create approval request (Issue #665: uses helper)
        approval_request = self._create_approval_request(
            workflow, approval_mode, timeout_seconds
        )

        # Store pending approval
        self._pending_plan_approvals[workflow.workflow_id] = approval_request
        self._plan_approval_events[workflow.workflow_id] = asyncio.Event()

        # Present plan to user via WebSocket
        await self._send_plan_presentation(workflow, approval_request)

        # Update status
        approval_request.status = PlanApprovalStatus.AWAITING_APPROVAL
        approval_request.presented_at = datetime.now()

        logger.info(
            f"Plan presented for workflow {workflow.workflow_id}, "
            f"awaiting approval (mode: {approval_mode.value})"
        )

        return approval_request

    async def wait_for_plan_approval(
        self,
        workflow_id: str,
        timeout_seconds: int = 300,
    ) -> PlanApprovalRequest:
        """
        Wait for user to approve or reject the presented plan.

        Issue #390: Block execution until user approves plan.

        Args:
            workflow_id: ID of the workflow awaiting approval
            timeout_seconds: Maximum time to wait for approval

        Returns:
            PlanApprovalRequest with final status (approved/rejected/timeout)
        """
        if workflow_id not in self._pending_plan_approvals:
            raise ValueError(f"No pending approval for workflow {workflow_id}")

        approval_request = self._pending_plan_approvals[workflow_id]
        approval_event = self._plan_approval_events[workflow_id]

        try:
            # Wait for approval event with timeout
            await asyncio.wait_for(approval_event.wait(), timeout=timeout_seconds)

            logger.info(
                f"Plan approval received for workflow {workflow_id}: "
                f"{approval_request.status.value}"
            )

        except asyncio.TimeoutError:
            approval_request.status = PlanApprovalStatus.TIMEOUT
            approval_request.resolved_at = datetime.now()
            logger.warning(
                f"Plan approval timeout for workflow {workflow_id} "
                f"after {timeout_seconds}s"
            )

        finally:
            # Cleanup
            self._plan_approval_events.pop(workflow_id, None)

        return approval_request

    def handle_plan_approval_response(
        self,
        workflow_id: str,
        approved: bool,
        modifications: list[str] | None = None,
        reason: str | None = None,
    ) -> bool:
        """
        Handle user's response to plan approval request.

        Issue #390: Process user's decision on presented plan.

        Args:
            workflow_id: ID of the workflow
            approved: Whether user approved the plan
            modifications: List of step IDs to modify/skip (optional)
            reason: User's reason for rejection/modification (optional)

        Returns:
            True if response was processed, False if no pending approval
        """
        if workflow_id not in self._pending_plan_approvals:
            logger.warning("No pending approval for workflow %s", workflow_id)
            return False

        approval_request = self._pending_plan_approvals[workflow_id]

        if approved:
            approval_request.status = PlanApprovalStatus.APPROVED
        elif modifications:
            approval_request.status = PlanApprovalStatus.MODIFIED
        else:
            approval_request.status = PlanApprovalStatus.REJECTED

        approval_request.resolved_at = datetime.now()
        approval_request.user_response = reason

        # Signal waiting coroutine
        if workflow_id in self._plan_approval_events:
            self._plan_approval_events[workflow_id].set()

        logger.info(
            f"Plan approval response for workflow {workflow_id}: "
            f"approved={approved}, status={approval_request.status.value}"
        )

        return True

    async def _send_plan_presentation(
        self,
        workflow: ActiveWorkflow,
        approval_request: PlanApprovalRequest,
    ) -> None:
        """
        Send plan presentation message to frontend.

        Issue #390: WebSocket message to present full plan to user.
        """
        await self.messenger.send_message(
            workflow.session_id,
            {
                "type": "workflow_plan_presented",
                "workflow_id": workflow.workflow_id,
                "plan": approval_request.to_presentation_dict(),
                "approval_options": {
                    "approve_all": "Approve entire plan and execute",
                    "approve_step_by_step": "Review and approve each step",
                    "modify": "Modify plan before execution",
                    "reject": "Reject plan and cancel",
                },
            },
        )

    def _assess_plan_risk(self, workflow: ActiveWorkflow) -> str:
        """
        Assess overall risk level of workflow plan.

        Issue #390: Provide risk assessment in plan presentation.
        """
        risk_counts = {"low": 0, "medium": 0, "high": 0, "critical": 0}

        for step in workflow.steps:
            risk_level = step.risk_level.lower()
            if risk_level in risk_counts:
                risk_counts[risk_level] += 1

        # Determine overall risk
        if risk_counts["critical"] > 0:
            return f"CRITICAL - {risk_counts['critical']} critical risk step(s)"
        elif risk_counts["high"] > 0:
            return f"HIGH - {risk_counts['high']} high risk step(s)"
        elif risk_counts["medium"] > 0:
            return f"MEDIUM - {risk_counts['medium']} medium risk step(s)"
        else:
            return f"LOW - All {risk_counts['low']} steps are low risk"

    def get_pending_approval(self, workflow_id: str) -> PlanApprovalRequest | None:
        """Get pending plan approval request for a workflow."""
        return self._pending_plan_approvals.get(workflow_id)

    def clear_pending_approval(self, workflow_id: str) -> None:
        """Clear pending approval request (e.g., after workflow completes)."""
        self._pending_plan_approvals.pop(workflow_id, None)
        self._plan_approval_events.pop(workflow_id, None)
