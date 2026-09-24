# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Workflow Step Evaluator Module

LLM judge integration for evaluating workflow steps.
"""

from typing import Set

from autobot_shared.logging_manager import get_logger
from judges import (
    DEGRADATION_EVALUATION_ERROR,
    DEGRADATION_JUDGE_UNAVAILABLE,
    ERROR_MODEL_SENTINEL,
)
from monitoring.prometheus_metrics import get_metrics_manager
from type_defs.common import Metadata

from .models import ActiveWorkflow, WorkflowStep, WorkflowStepStatus

logger = get_logger(__name__)

# Performance optimization: O(1) lookup for approval recommendations (Issue #326)
APPROVAL_RECOMMENDATIONS: Set[str] = {"APPROVE", "CONDITIONAL"}


class WorkflowStepEvaluator:
    """Evaluates workflow steps using LLM judges"""

    def __init__(self) -> None:
        """Initialize step evaluator with LLM judges if available."""
        self.judges_enabled = False
        self.workflow_step_judge = None
        self.security_risk_judge = None
        self.multi_agent_arbitrator = None

        self._initialize_judges()

    def _initialize_judges(self) -> None:
        """Initialize LLM judges if available"""
        try:
            from judges.multi_agent_arbitrator import MultiAgentArbitrator
            from judges.security_risk_judge import SecurityRiskJudge
            from judges.workflow_step_judge import WorkflowStepJudge

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
                s for s in workflow.steps[: workflow.current_step_index] if s.status == WorkflowStepStatus.COMPLETED
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
            (s.score for s in judgment.criterion_scores if s.dimension.value == "safety"),
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
            "suggestions": (workflow_judgment.improvement_suggestions + security_judgment.improvement_suggestions),
        }

        if not should_proceed:
            reasons = []
            if not should_approve_workflow:
                reasons.append(f"Workflow evaluation: {workflow_judgment.recommendation}")
            if not should_approve_security:
                reasons.append(f"Security evaluation: {security_judgment.recommendation}")
            if min_safety <= 0.7:
                reasons.append(f"Safety score too low: {min_safety:.2f}")
            result["reason"] = "; ".join(reasons)

        return result

    async def _run_judge_evaluations(
        self,
        step_data: Metadata,
        workflow_context: Metadata,
        user_context: Metadata,
        command: str,
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

    def _check_judge_errors(self, judgments: tuple, step_id: str) -> Metadata | None:
        """Resolve a step whose judges could not be read, else None (#1464, #17307).

        The old form hard-coded ``should_proceed: True`` and said so in a
        ``logger.warning``, so a step approved because nobody could read the
        judge looked exactly like a step a judge approved. Now the outcome
        comes from :data:`JUDGE_FAIL_CLOSED`, the response carries
        ``judge_available: False`` and a degradation code, and both the
        outcome and its cause are counted.
        """
        error_judges = [j for j in judgments if j.llm_model_used == ERROR_MODEL_SENTINEL]
        if not error_judges:
            return None
        reasons = [j.reasoning for j in error_judges]
        return self._degraded_response(DEGRADATION_JUDGE_UNAVAILABLE, "; ".join(reasons), step_id)

    def _degraded_response(self, degradation: str, detail: str, step_id: str) -> Metadata:
        """Build the evaluation result for a step no judge could decide (#17307).

        ``should_proceed`` follows the policy; everything else in the payload
        exists so a consumer -- or an operator reading the metric -- can tell
        this apart from a judgment. ``judge_available: False`` is the field to
        branch on; ``degradation`` says which failure it was.
        """
        import judges  # noqa: PLC0415 -- read at call time so the policy can be patched

        proceed = not judges.JUDGE_FAIL_CLOSED
        verb = "Approved" if proceed else "Held"
        logger.warning(
            "step %s: %s — %s by the %s policy (AUTOBOT_JUDGE_FAIL_CLOSED=%s): %s",
            step_id,
            degradation,
            verb.lower(),
            "fail-closed" if judges.JUDGE_FAIL_CLOSED else "fail-open",
            "1" if judges.JUDGE_FAIL_CLOSED else "0",
            detail,
        )
        self._record_degradation(degradation, proceed)
        return {
            "should_proceed": proceed,
            "reason": f"{verb} ({degradation}): {detail}",
            "judge_available": False,
            "degradation": degradation,
            "fail_closed": judges.JUDGE_FAIL_CLOSED,
            "suggestions": ["Manual review recommended — no judgment was read for this step"],
        }

    @staticmethod
    def _record_degradation(degradation: str, proceeded: bool) -> None:
        """Count the degraded outcome and its cause (#17307).

        Two existing counters rather than a new one: the approval counter is
        where "approved" and "approved without a judgment" have to be
        distinguishable, and the error counter is where the cause belongs.
        A metrics backend that is not up must not break a workflow step, so a
        failure here is logged and swallowed deliberately -- the decision it
        annotates has already been made and logged above.
        """
        decision = "approved_judge_unavailable" if proceeded else "blocked_judge_unavailable"
        try:
            metrics = get_metrics_manager()
            metrics.record_workflow_approval("step_evaluation", decision)
            metrics.record_error(degradation, "workflow_step_evaluator", decision)
        except Exception as exc:  # pragma: no cover - metrics backend optional
            logger.debug("step_evaluator: could not record degradation metric: %s", exc)

    def _build_evaluation_error_response(self, error: Exception, step_id: str = "unknown") -> Metadata:
        """Build the response for an evaluator failure (#665, #17307).

        Same class of defect as the judge-unavailable path: this returned a
        bare ``should_proceed: True`` for *any* exception, so an evaluator that
        crashed approved the step. It now goes through the same policy and
        carries the same distinguishing fields.
        """
        return self._degraded_response(DEGRADATION_EVALUATION_ERROR, str(error), step_id)

    async def evaluate_step(self, workflow: ActiveWorkflow, step: WorkflowStep) -> Metadata:
        """Evaluate workflow step using LLM judges. Ref: #1088.

        Issue #281: Refactored from 144 lines to use extracted helper methods.
        Issue #665: Further refactored with _run_judge_evaluations and error handler.
        """
        if not self.judges_enabled:
            return {"should_proceed": True, "reason": "Judges disabled"}

        try:
            step_data = self._prepare_step_data(step)
            workflow_context = self._prepare_workflow_context(workflow)
            user_context = {
                "permissions": ["user"],
                "experience_level": "intermediate",
                "environment": "development",
            }
            workflow_judgment, security_judgment = await self._run_judge_evaluations(
                step_data, workflow_context, user_context, step.command
            )

            # Fail-open: if either judge errored (LLM unavailable),
            # approve with warning instead of silently rejecting (#1464)
            judge_error = self._check_judge_errors((workflow_judgment, security_judgment), step.step_id)
            if judge_error:
                return judge_error

            should_approve_workflow = workflow_judgment.recommendation in APPROVAL_RECOMMENDATIONS
            should_approve_security = security_judgment.recommendation in APPROVAL_RECOMMENDATIONS
            workflow_safety = self._extract_safety_score(workflow_judgment)
            security_safety = self._extract_safety_score(security_judgment)
            min_safety = min(workflow_safety, security_safety)
            should_proceed = should_approve_workflow and should_approve_security and min_safety > 0.7
            evaluation_result = self._build_evaluation_result(
                should_proceed,
                workflow_judgment,
                security_judgment,
                min_safety,
                should_approve_workflow,
                should_approve_security,
            )
            logger.info(
                "Step evaluation for %s: proceed=%s, workflow_score=%.2f, security_score=%.2f",
                step.step_id,
                should_proceed,
                workflow_judgment.overall_score,
                security_judgment.overall_score,
            )
            return evaluation_result

        except Exception as e:
            logger.error("Error in step evaluation: %s", e)
            return self._build_evaluation_error_response(e, getattr(step, "step_id", "unknown"))
