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

from backend.type_defs.common import Metadata
from src.monitoring.prometheus_metrics import get_metrics_manager

from .models import ActiveWorkflow, WorkflowStep, WorkflowStepStatus
from .step_evaluator import WorkflowStepEvaluator

if TYPE_CHECKING:
    from .messaging import WorkflowMessenger

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """Handles workflow step execution and processing"""

    def __init__(self, messenger: "WorkflowMessenger"):
        self.messenger = messenger
        self.step_evaluator = WorkflowStepEvaluator()
        self.prometheus_metrics = get_metrics_manager()

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

    async def process_next_step(
        self, workflow: ActiveWorkflow, workflows: Dict[str, ActiveWorkflow]
    ) -> None:
        """Process the next step in workflow"""
        if workflow.is_paused or workflow.is_cancelled:
            return

        if workflow.current_step_index >= len(workflow.steps):
            # Workflow completed
            await self._complete_workflow(workflow, workflows)
            return

        current_step = workflow.steps[workflow.current_step_index]

        # Check dependencies
        if not self._check_step_dependencies(workflow, current_step):
            logger.warning(f"Step {current_step.step_id} dependencies not met")
            current_step.status = WorkflowStepStatus.SKIPPED
            workflow.current_step_index += 1
            await self.process_next_step(workflow, workflows)
            return

        # Evaluate step with LLM judges if enabled
        if self.step_evaluator.judges_enabled:
            try:
                step_evaluation = await self.step_evaluator.evaluate_step(
                    workflow, current_step
                )
                if not step_evaluation.get("should_proceed", True):
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
                    return
            except Exception as e:
                logger.error(f"Error evaluating workflow step with LLM judge: {e}")
                # Continue without judge evaluation

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
            # Execute command via terminal
            result = await self._execute_command(
                workflow.session_id, current_step.command
            )

            current_step.status = WorkflowStepStatus.COMPLETED
            current_step.execution_result = result
            current_step.completed_at = datetime.now()

            # Record Prometheus workflow step metric (success)
            workflow_type = "automated_workflow"
            step_type = "command_execution"
            self.prometheus_metrics.record_workflow_step(
                workflow_type=workflow_type, step_type=step_type, status="completed"
            )

            # Move to next step
            workflow.current_step_index += 1

            # Small delay before next step
            await asyncio.sleep(2)
            await self.process_next_step(workflow, workflows)

        except Exception as e:
            logger.error(f"Step execution failed: {e}")
            current_step.status = WorkflowStepStatus.FAILED
            current_step.execution_result = {"error": str(e)}

            # Record Prometheus workflow step metric (failed)
            workflow_type = "automated_workflow"
            step_type = "command_execution"
            self.prometheus_metrics.record_workflow_step(
                workflow_type=workflow_type, step_type=step_type, status="failed"
            )

            # Pause workflow on error
            workflow.is_paused = True
            await self.messenger.send_message(
                workflow.session_id,
                {
                    "type": "step_failed",
                    "workflow_id": workflow.workflow_id,
                    "step_id": step_id,
                    "error": str(e),
                },
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
            await asyncio.sleep(1)
            await self.process_next_step(workflow, workflows)

    async def _execute_command(self, session_id: str, command: str) -> Metadata:
        """Execute command via terminal session"""
        # This would integrate with the existing terminal WebSocket system
        # For now, simulate command execution
        logger.info(f"Executing workflow command: {command}")

        # Simulate command execution delay
        await asyncio.sleep(1)

        return {
            "command": command,
            "exit_code": 0,
            "stdout": f"Simulated output for: {command}",
            "stderr": "",
            "execution_time": 1.0,
        }

    async def _complete_workflow(
        self, workflow: ActiveWorkflow, workflows: Dict[str, ActiveWorkflow]
    ) -> None:
        """Complete workflow execution"""
        workflow.completed_at = datetime.now()

        # Record Prometheus workflow execution metric (success)
        if workflow.prometheus_start_time:
            duration = time.time() - workflow.prometheus_start_time
            workflow_type = "automated_workflow"
            failed_steps = len(
                [s for s in workflow.steps if s.status == WorkflowStepStatus.FAILED]
            )
            status = "failed" if failed_steps > 0 else "success"
            self.prometheus_metrics.record_workflow_execution(
                workflow_type=workflow_type, status=status, duration=duration
            )

            # Update active workflows count (decrement)
            active_count = (
                len(
                    [
                        w
                        for w in workflows.values()
                        if w.started_at and not w.completed_at
                    ]
                )
                - 1
            )
            self.prometheus_metrics.update_active_workflows(
                workflow_type=workflow_type, count=max(0, active_count)
            )

        # Send completion message
        await self.messenger.send_message(
            workflow.session_id,
            {
                "type": "workflow_completed",
                "workflow_id": workflow.workflow_id,
                "name": workflow.name,
                "total_steps": len(workflow.steps),
                "completed_steps": len(
                    [
                        s
                        for s in workflow.steps
                        if s.status == WorkflowStepStatus.COMPLETED
                    ]
                ),
                "skipped_steps": len(
                    [
                        s
                        for s in workflow.steps
                        if s.status == WorkflowStepStatus.SKIPPED
                    ]
                ),
                "failed_steps": len(
                    [s for s in workflow.steps if s.status == WorkflowStepStatus.FAILED]
                ),
            },
        )

    async def cancel_workflow(
        self, workflow: ActiveWorkflow, workflows: Dict[str, ActiveWorkflow]
    ) -> None:
        """Cancel workflow execution"""
        workflow.is_cancelled = True
        workflow.completed_at = datetime.now()

        # Record Prometheus workflow execution metric (cancelled)
        if workflow.prometheus_start_time:
            duration = time.time() - workflow.prometheus_start_time
            workflow_type = "automated_workflow"
            self.prometheus_metrics.record_workflow_execution(
                workflow_type=workflow_type, status="cancelled", duration=duration
            )

            # Update active workflows count (decrement)
            active_count = (
                len(
                    [
                        w
                        for w in workflows.values()
                        if w.started_at and not w.completed_at
                    ]
                )
                - 1
            )
            self.prometheus_metrics.update_active_workflows(
                workflow_type=workflow_type, count=max(0, active_count)
            )

        await self.messenger.send_message(
            workflow.session_id,
            {"type": "workflow_cancelled", "workflow_id": workflow.workflow_id},
        )
