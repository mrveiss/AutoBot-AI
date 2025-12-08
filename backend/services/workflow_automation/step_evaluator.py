# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Step Evaluator Module

LLM judge integration for evaluating workflow steps.
"""

import logging
from typing import Set

from backend.type_defs.common import Metadata

from .models import ActiveWorkflow, WorkflowStep, WorkflowStepStatus

logger = logging.getLogger(__name__)

# Performance optimization: O(1) lookup for approval recommendations (Issue #326)
APPROVAL_RECOMMENDATIONS: Set[str] = {"APPROVE", "CONDITIONAL"}


class WorkflowStepEvaluator:
    """Evaluates workflow steps using LLM judges"""

    def __init__(self):
        """Initialize step evaluator with LLM judges if available."""
        self.judges_enabled = False
        self.workflow_step_judge = None
        self.security_risk_judge = None
        self.multi_agent_arbitrator = None

        self._initialize_judges()

    def _initialize_judges(self) -> None:
        """Initialize LLM judges if available"""
        try:
            from src.judges.multi_agent_arbitrator import MultiAgentArbitrator
            from src.judges.security_risk_judge import SecurityRiskJudge
            from src.judges.workflow_step_judge import WorkflowStepJudge

            self.workflow_step_judge = WorkflowStepJudge()
            self.security_risk_judge = SecurityRiskJudge()
            self.multi_agent_arbitrator = MultiAgentArbitrator()
            self.judges_enabled = True
            logger.info("LLM judges initialized for workflow step evaluation")
        except ImportError as e:
            logger.warning(f"LLM judges not available: {e}")
            self.judges_enabled = False
        except Exception as e:
            logger.error(f"Failed to initialize LLM judges: {e}")
            self.judges_enabled = False

    async def evaluate_step(
        self, workflow: ActiveWorkflow, step: WorkflowStep
    ) -> Metadata:
        """Evaluate workflow step using LLM judges"""
        if not self.judges_enabled:
            return {"should_proceed": True, "reason": "Judges disabled"}

        try:
            # Prepare step data for evaluation
            step_data = {
                "step_id": step.step_id,
                "command": step.command,
                "description": step.description,
                "explanation": step.explanation,
                "risk_level": step.risk_level,
                "estimated_duration": step.estimated_duration,
                "dependencies": step.dependencies or [],
            }

            # Prepare workflow context
            workflow_context = {
                "workflow_name": workflow.name,
                "workflow_description": workflow.description,
                "current_step_index": workflow.current_step_index,
                "total_steps": len(workflow.steps),
                "completed_steps": [
                    s
                    for s in workflow.steps[: workflow.current_step_index]
                    if s.status == WorkflowStepStatus.COMPLETED
                ],
                "automation_mode": workflow.automation_mode.value,
                "session_id": workflow.session_id,
            }

            # Prepare user context (simplified for now)
            user_context = {
                "permissions": ["user"],
                "experience_level": "intermediate",
                "environment": "development",
            }

            # Evaluate with workflow step judge
            workflow_judgment = await self.workflow_step_judge.evaluate_workflow_step(
                step_data, workflow_context, user_context
            )

            # Evaluate with security risk judge for commands
            security_judgment = (
                await self.security_risk_judge.evaluate_command_security(
                    step.command,
                    {
                        "working_directory": "/home/user",
                        "user": "user",
                        "session_type": "automated_workflow",
                    },
                    user_permissions=["user"],
                    environment="development",
                )
            )

            # Combine judgments
            should_approve_workflow = (
                workflow_judgment.recommendation in APPROVAL_RECOMMENDATIONS
            )
            should_approve_security = (
                security_judgment.recommendation in APPROVAL_RECOMMENDATIONS
            )

            # Extract safety scores
            workflow_safety = next(
                (
                    s.score
                    for s in workflow_judgment.criterion_scores
                    if s.dimension.value == "safety"
                ),
                0.8,
            )
            security_safety = next(
                (
                    s.score
                    for s in security_judgment.criterion_scores
                    if s.dimension.value == "safety"
                ),
                0.8,
            )

            # Decision logic
            min_safety = min(workflow_safety, security_safety)
            should_proceed = (
                should_approve_workflow
                and should_approve_security
                and min_safety > 0.7
            )

            # Prepare response
            evaluation_result = {
                "should_proceed": should_proceed,
                "workflow_judgment": {
                    "recommendation": workflow_judgment.recommendation,
                    "overall_score": workflow_judgment.overall_score,
                    "reasoning": workflow_judgment.reasoning,
                },
                "security_judgment": {
                    "recommendation": security_judgment.recommendation,
                    "overall_score": security_judgment.overall_score,
                    "reasoning": security_judgment.reasoning,
                },
                "combined_safety_score": min_safety,
                "suggestions": (
                    workflow_judgment.improvement_suggestions
                    + security_judgment.improvement_suggestions
                ),
            }

            if not should_proceed:
                reasons = []
                if not should_approve_workflow:
                    reasons.append(
                        f"Workflow evaluation: {workflow_judgment.recommendation}"
                    )
                if not should_approve_security:
                    reasons.append(
                        f"Security evaluation: {security_judgment.recommendation}"
                    )
                if min_safety <= 0.7:
                    reasons.append(f"Safety score too low: {min_safety:.2f}")

                evaluation_result["reason"] = "; ".join(reasons)

            logger.info(
                f"Step evaluation for {step.step_id}: proceed={should_proceed}, "
                f"workflow_score={workflow_judgment.overall_score:.2f}, "
                f"security_score={security_judgment.overall_score:.2f}"
            )

            return evaluation_result

        except Exception as e:
            logger.error(f"Error in step evaluation: {e}")
            return {
                "should_proceed": True,  # Default to proceed on evaluation error
                "reason": f"Evaluation error: {str(e)}",
                "suggestions": ["Manual review recommended due to evaluation error"],
            }
