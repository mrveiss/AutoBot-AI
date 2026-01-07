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
            logger.warning("LLM judges not available: %s", e)
            self.judges_enabled = False
        except Exception as e:
            logger.error("Failed to initialize LLM judges: %s", e)
            self.judges_enabled = False

    def _prepare_step_data(self, step: WorkflowStep) -> Metadata:
        """
        Prepare step data dictionary for evaluation.

        Issue #281: Extracted helper for step data preparation.

        Args:
            step: WorkflowStep to prepare

        Returns:
            Dictionary with step data
        """
        return {
            "step_id": step.step_id,
            "command": step.command,
            "description": step.description,
            "explanation": step.explanation,
            "risk_level": step.risk_level,
            "estimated_duration": step.estimated_duration,
            "dependencies": step.dependencies or [],
        }

    def _prepare_workflow_context(self, workflow: ActiveWorkflow) -> Metadata:
        """
        Prepare workflow context dictionary for evaluation.

        Issue #281: Extracted helper for workflow context preparation.

        Args:
            workflow: ActiveWorkflow to prepare context from

        Returns:
            Dictionary with workflow context
        """
        return {
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

    def _extract_safety_score(self, judgment, default: float = 0.8) -> float:
        """
        Extract safety score from judgment criterion scores.

        Issue #281: Extracted helper for safety score extraction.

        Args:
            judgment: Judgment object with criterion_scores
            default: Default score if safety not found

        Returns:
            Safety score as float
        """
        return next(
            (
                s.score
                for s in judgment.criterion_scores
                if s.dimension.value == "safety"
            ),
            default,
        )

    def _build_evaluation_result(
        self,
        should_proceed: bool,
        workflow_judgment,
        security_judgment,
        min_safety: float,
        should_approve_workflow: bool,
        should_approve_security: bool,
    ) -> Metadata:
        """
        Build the evaluation result dictionary.

        Issue #281: Extracted helper for result building.

        Args:
            should_proceed: Whether step should proceed
            workflow_judgment: Workflow judge result
            security_judgment: Security judge result
            min_safety: Minimum safety score
            should_approve_workflow: Workflow approval status
            should_approve_security: Security approval status

        Returns:
            Evaluation result dictionary
        """
        result: Metadata = {
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
            result["reason"] = "; ".join(reasons)

        return result

    async def _run_judge_evaluations(
        self, step_data: Metadata, workflow_context: Metadata, user_context: Metadata, command: str
    ) -> tuple:
        """
        Run workflow and security judge evaluations.

        Issue #665: Extracted from evaluate_step to reduce function length.

        Args:
            step_data: Prepared step data
            workflow_context: Prepared workflow context
            user_context: User context dictionary
            command: Step command to evaluate

        Returns:
            Tuple of (workflow_judgment, security_judgment)
        """
        workflow_judgment = await self.workflow_step_judge.evaluate_workflow_step(
            step_data, workflow_context, user_context
        )
        security_judgment = await self.security_risk_judge.evaluate_command_security(
            command,
            {
                "working_directory": "/home/user",
                "user": "user",
                "session_type": "automated_workflow",
            },
            user_permissions=["user"],
            environment="development",
        )
        return workflow_judgment, security_judgment

    def _build_evaluation_error_response(self, error: Exception) -> Metadata:
        """
        Build error response for evaluation failure.

        Issue #665: Extracted from evaluate_step to reduce function length.

        Args:
            error: Exception that occurred

        Returns:
            Error response dictionary
        """
        return {
            "should_proceed": True,  # Default to proceed on evaluation error
            "reason": f"Evaluation error: {str(error)}",
            "suggestions": ["Manual review recommended due to evaluation error"],
        }

    async def evaluate_step(
        self, workflow: ActiveWorkflow, step: WorkflowStep
    ) -> Metadata:
        """
        Evaluate workflow step using LLM judges.

        Issue #281: Refactored from 144 lines to use extracted helper methods.
        Issue #665: Further refactored with _run_judge_evaluations and error handler.

        Args:
            workflow: Active workflow containing the step
            step: WorkflowStep to evaluate

        Returns:
            Evaluation result with should_proceed and judgment details
        """
        if not self.judges_enabled:
            return {"should_proceed": True, "reason": "Judges disabled"}

        try:
            # Prepare data (Issue #281: uses helpers)
            step_data = self._prepare_step_data(step)
            workflow_context = self._prepare_workflow_context(workflow)
            user_context = {
                "permissions": ["user"],
                "experience_level": "intermediate",
                "environment": "development",
            }

            # Evaluate with judges (Issue #665: uses helper)
            workflow_judgment, security_judgment = await self._run_judge_evaluations(
                step_data, workflow_context, user_context, step.command
            )

            # Combine judgments
            should_approve_workflow = workflow_judgment.recommendation in APPROVAL_RECOMMENDATIONS
            should_approve_security = security_judgment.recommendation in APPROVAL_RECOMMENDATIONS

            # Extract safety scores (Issue #281: uses helper)
            workflow_safety = self._extract_safety_score(workflow_judgment)
            security_safety = self._extract_safety_score(security_judgment)
            min_safety = min(workflow_safety, security_safety)

            # Decision logic
            should_proceed = should_approve_workflow and should_approve_security and min_safety > 0.7

            # Build result (Issue #281: uses helper)
            evaluation_result = self._build_evaluation_result(
                should_proceed, workflow_judgment, security_judgment,
                min_safety, should_approve_workflow, should_approve_security,
            )

            logger.info(
                "Step evaluation for %s: proceed=%s, workflow_score=%.2f, security_score=%.2f",
                step.step_id, should_proceed, workflow_judgment.overall_score, security_judgment.overall_score
            )

            return evaluation_result

        except Exception as e:
            logger.error("Error in step evaluation: %s", e)
            return self._build_evaluation_error_response(e)
