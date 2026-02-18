# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Step Judge

Implements LLM-as-Judge for workflow step evaluation, approval, and quality assessment.
This judge evaluates workflow steps before execution to ensure quality, safety, and effectiveness.
"""

import json
import logging
from typing import Any, Dict, FrozenSet, List, Optional

from constants import WorkflowThresholds

from . import BaseLLMJudge, JudgmentDimension, JudgmentResult

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for approval recommendations
_APPROVAL_RECOMMENDATIONS: FrozenSet[str] = frozenset({"APPROVE", "CONDITIONAL"})


class WorkflowStepJudge(BaseLLMJudge):
    """Judge for evaluating workflow steps before execution"""

    def __init__(self, llm_interface=None):
        """Initialize workflow step judge with safety and quality thresholds."""
        super().__init__("workflow_step", llm_interface)
        # Issue #318: Use centralized constants instead of magic numbers
        self.safety_threshold = WorkflowThresholds.SAFETY_THRESHOLD
        self.quality_threshold = WorkflowThresholds.QUALITY_THRESHOLD

    async def evaluate_workflow_step(
        self,
        step_data: Dict[str, Any],
        workflow_context: Dict[str, Any],
        user_context: Dict[str, Any],
        alternatives: Optional[List[Dict[str, Any]]] = None,
        risk_tolerance: str = "medium",
    ) -> JudgmentResult:
        """
        Evaluate a workflow step for approval

        Args:
            step_data: The workflow step to evaluate
            workflow_context: Context about the current workflow
            user_context: Context about the user and their permissions
            alternatives: Alternative ways to accomplish the same goal
            risk_tolerance: User's risk tolerance (low/medium/high)

        Returns:
            JudgmentResult with detailed evaluation
        """
        # Define evaluation criteria
        criteria = [
            JudgmentDimension.SAFETY,
            JudgmentDimension.QUALITY,
            JudgmentDimension.RELEVANCE,
            JudgmentDimension.FEASIBILITY,
            JudgmentDimension.EFFICIENCY,
            JudgmentDimension.COMPLIANCE,
        ]

        # Prepare comprehensive context
        context = {
            "workflow_context": workflow_context,
            "user_context": user_context,
            "risk_tolerance": risk_tolerance,
            "safety_threshold": self.safety_threshold,
            "quality_threshold": self.quality_threshold,
        }

        return await self.make_judgment(
            subject=step_data,
            criteria=criteria,
            context=context,
            alternatives=alternatives,
        )

    def _build_judgment_context(
        self,
        step_data: Any,
        workflow_context: Dict[str, Any],
        user_context: Dict[str, Any],
        risk_tolerance: str,
    ) -> str:
        """Build context section for judgment prompt.

        Constructs the workflow step data and context information sections
        of the judgment prompt including workflow state and user permissions.

        Args:
            step_data: The workflow step data to evaluate.
            workflow_context: Context about the current workflow state.
            user_context: Context about the user and their permissions.
            risk_tolerance: User's risk tolerance level.

        Returns:
            Formatted string containing step and context sections.

        Related:
            Issue #665: Extract helper methods from _init_metrics functions.
        """
        return f"""Please evaluate the following workflow step for execution approval:

WORKFLOW STEP TO EVALUATE:
{json.dumps(step_data, indent=2)}

WORKFLOW CONTEXT:
- Current workflow: {workflow_context.get('workflow_name', 'Unknown')}
- Previous steps: {len(workflow_context.get('completed_steps', []))} completed
- Workflow goal: {workflow_context.get('goal', 'Not specified')}
- Current state: {workflow_context.get('current_state', 'Unknown')}

USER CONTEXT:
- User permissions: {user_context.get('permissions', [])}
- Risk tolerance: {risk_tolerance}
- User experience level: {user_context.get('experience_level', 'unknown')}
- Current environment: {user_context.get('environment', 'unknown')}"""

    def _build_judgment_criteria(self) -> str:
        """Build evaluation criteria section for judgment prompt.

        Constructs the standardized evaluation criteria section describing
        each dimension (safety, quality, relevance, feasibility, efficiency,
        compliance) and their specific assessment factors.

        Returns:
            Formatted string containing all evaluation criteria.

        Related:
            Issue #665: Extract helper methods from _init_metrics functions.
        """
        return """EVALUATION CRITERIA:
Please evaluate this step on the following dimensions (score 0.0 to 1.0):

1. SAFETY: Risk assessment and potential for harm
   - Consider command safety, system impact, data safety
   - Evaluate potential for unintended consequences
   - Check for destructive or irreversible operations

2. QUALITY: Likelihood of successful execution
   - Assess if the step will accomplish its intended goal
   - Check for proper parameters and configuration
   - Evaluate completeness and correctness

3. RELEVANCE: Alignment with workflow goals
   - Check if this step advances the workflow objective
   - Assess if it's necessary and not redundant
   - Evaluate timing and sequencing appropriateness

4. FEASIBILITY: Technical possibility of execution
   - Check if required resources are available
   - Assess if dependencies are met
   - Evaluate system capabilities and constraints

5. EFFICIENCY: Resource utilization and performance
   - Assess computational/time costs
   - Check for more efficient alternatives
   - Evaluate resource impact

6. COMPLIANCE: Adherence to policies and best practices
   - Check security policy compliance
   - Assess regulatory requirements
   - Evaluate coding/operational standards"""

    def _format_judgment_instructions(
        self,
        context: Dict[str, Any],
        risk_tolerance: str,
        alternatives: Optional[List[Any]] = None,
    ) -> str:
        """Format decision criteria and final instructions for judgment.

        Constructs the alternatives section, decision thresholds, and
        output format instructions for the judgment prompt.

        Args:
            context: Context dictionary containing threshold values.
            risk_tolerance: User's risk tolerance level.
            alternatives: Optional list of alternative approaches to consider.

        Returns:
            Formatted string with alternatives, criteria, and instructions.

        Related:
            Issue #665: Extract helper methods from _init_metrics functions.
        """
        alternatives_text = (
            json.dumps(alternatives, indent=2)
            if alternatives
            else "No alternatives provided"
        )
        return f"""ALTERNATIVES TO CONSIDER:
{alternatives_text}

DECISION CRITERIA:
- Safety score must be ≥ {context.get('safety_threshold', 0.7)} for approval
- Quality score must be ≥ {context.get('quality_threshold', 0.6)} for approval
- Consider user's risk tolerance: {risk_tolerance}

Please provide your evaluation in the required JSON format with:
- Detailed reasoning for each criterion
- Specific evidence for your scores
- Clear recommendation (APPROVE/REJECT/CONDITIONAL/REVISE)
- Actionable improvement suggestions if applicable
- Analysis of alternatives if provided

Focus on being thorough but practical - the goal is to ensure safe, effective workflow execution."""

    async def _prepare_judgment_prompt(
        self,
        subject: Any,
        criteria: List[JudgmentDimension],
        context: Dict[str, Any],
        alternatives: Optional[List[Any]] = None,
        **kwargs,
    ) -> str:
        """Prepare the prompt for workflow step evaluation.

        Assembles the complete judgment prompt by combining context,
        criteria, and instruction sections from helper methods.

        Args:
            subject: The workflow step data to evaluate.
            criteria: List of judgment dimensions to evaluate.
            context: Context dictionary with workflow, user, and threshold info.
            alternatives: Optional list of alternative approaches.
            **kwargs: Additional keyword arguments (unused).

        Returns:
            Complete formatted prompt string for LLM evaluation.

        Related:
            Issue #665: Extract helper methods from _init_metrics functions.
        """
        workflow_context = context.get("workflow_context", {})
        user_context = context.get("user_context", {})
        risk_tolerance = context.get("risk_tolerance", "medium")

        context_section = self._build_judgment_context(
            subject, workflow_context, user_context, risk_tolerance
        )
        criteria_section = self._build_judgment_criteria()
        instructions_section = self._format_judgment_instructions(
            context, risk_tolerance, alternatives
        )

        return f"{context_section}\n\n{criteria_section}\n\n{instructions_section}"

    def _extract_dimension_score(
        self, judgment: JudgmentResult, dimension: JudgmentDimension
    ) -> float:
        """
        Extract score for a specific dimension from judgment result.

        Args:
            judgment: The JudgmentResult containing criterion scores.
            dimension: The JudgmentDimension to extract score for.

        Returns:
            The score for the dimension, or 0.0 if not found.

        Issue #620.
        """
        return next(
            (s.score for s in judgment.criterion_scores if s.dimension == dimension),
            0.0,
        )

    def _check_threshold_violation(
        self, score: float, threshold: float, score_name: str
    ) -> Optional[tuple[bool, str]]:
        """
        Check if a score violates its threshold.

        Args:
            score: The actual score value.
            threshold: The minimum required threshold.
            score_name: Name of the score for error message.

        Returns:
            Tuple of (False, reason) if threshold violated, None otherwise.

        Issue #620.
        """
        if score < threshold:
            return (
                False,
                f"{score_name} score ({score:.2f}) below threshold ({threshold})",
            )
        return None

    async def should_approve_step(
        self,
        step_data: Dict[str, Any],
        workflow_context: Dict[str, Any],
        user_context: Dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Quick approval check for workflow steps (Issue #620: uses extracted helpers).

        Returns:
            tuple: (should_approve: bool, reason: str)
        """
        try:
            judgment = await self.evaluate_workflow_step(
                step_data, workflow_context, user_context
            )

            safety_score = self._extract_dimension_score(
                judgment, JudgmentDimension.SAFETY
            )
            quality_score = self._extract_dimension_score(
                judgment, JudgmentDimension.QUALITY
            )

            safety_violation = self._check_threshold_violation(
                safety_score, self.safety_threshold, "Safety"
            )
            if safety_violation:
                return safety_violation

            quality_violation = self._check_threshold_violation(
                quality_score, self.quality_threshold, "Quality"
            )
            if quality_violation:
                return quality_violation

            if judgment.recommendation in _APPROVAL_RECOMMENDATIONS:
                return True, f"Approved: {judgment.reasoning[:100]}..."
            return False, judgment.reasoning

        except Exception as e:
            logger.error("Error in workflow step approval: %s", e)
            return False, f"Evaluation error: {str(e)}"

    async def suggest_improvements(
        self,
        step_data: Dict[str, Any],
        workflow_context: Dict[str, Any],
        user_context: Dict[str, Any],
    ) -> List[str]:
        """
        Get improvement suggestions for a workflow step

        Returns:
            List of specific improvement suggestions
        """
        try:
            judgment = await self.evaluate_workflow_step(
                step_data, workflow_context, user_context
            )
            return judgment.improvement_suggestions

        except Exception as e:
            logger.error("Error getting improvement suggestions: %s", e)
            return [f"Error generating suggestions: {str(e)}"]

    async def _evaluate_alternative_steps(
        self,
        alternatives: List[Dict[str, Any]],
        primary_step: Dict[str, Any],
        workflow_context: Dict[str, Any],
        user_context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Evaluate each alternative step against the primary. Issue #620."""
        evaluations = []
        for i, alt_step in enumerate(alternatives):
            alt_eval = await self.evaluate_workflow_step(
                alt_step, workflow_context, user_context, [primary_step]
            )
            evaluations.append(
                {"step": alt_step, "evaluation": alt_eval, "type": f"alternative_{i+1}"}
            )
        return evaluations

    def _build_comparison_result(
        self, evaluations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Build ranked comparison result from evaluations. Issue #620."""
        evaluations.sort(key=lambda x: x["evaluation"].overall_score, reverse=True)
        return {
            "best_option": evaluations[0],
            "all_evaluations": evaluations,
            "ranking_rationale": (
                "Ranked by overall score considering safety, quality, and efficiency"
            ),
            "recommendation": evaluations[0]["evaluation"].recommendation,
        }

    async def compare_alternatives(
        self,
        primary_step: Dict[str, Any],
        alternatives: List[Dict[str, Any]],
        workflow_context: Dict[str, Any],
        user_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compare multiple workflow step alternatives

        Returns:
            Dict with ranked alternatives and recommendations
        """
        try:
            # Evaluate primary step
            primary_eval = await self.evaluate_workflow_step(
                primary_step, workflow_context, user_context, alternatives
            )
            evaluations = [
                {"step": primary_step, "evaluation": primary_eval, "type": "primary"}
            ]

            # Evaluate alternatives and build result
            alt_evals = await self._evaluate_alternative_steps(
                alternatives, primary_step, workflow_context, user_context
            )
            evaluations.extend(alt_evals)

            return self._build_comparison_result(evaluations)

        except Exception as e:
            logger.error("Error comparing alternatives: %s", e)
            return {
                "error": str(e),
                "best_option": None,
                "all_evaluations": [],
                "recommendation": "REJECT",
            }

    def _get_system_prompt(self) -> str:
        """Get specialized system prompt for workflow step evaluation"""
        return """You are an expert AI judge specializing in workflow step evaluation and approval. Your role is to assess workflow steps for safety, quality, and effectiveness before execution.

Your expertise includes:
- Risk assessment and safety evaluation
- Technical feasibility analysis
- Workflow optimization and efficiency
- Security and compliance checking
- Alternative solution analysis

Evaluation Guidelines:
1. SAFETY FIRST: Always prioritize user and system safety
2. BE PRACTICAL: Consider real-world constraints and user context
3. BE SPECIFIC: Provide concrete, actionable feedback
4. CONSIDER ALTERNATIVES: Suggest better approaches when possible
5. BE CONSISTENT: Apply evaluation criteria uniformly
6. EXPLAIN REASONING: Provide clear justification for scores

Critical Safety Considerations:
- Destructive operations (rm, format, delete)
- Network security risks
- Data exposure or privacy concerns
- System instability risks
- Privilege escalation attempts
- Resource exhaustion potential

Quality Factors:
- Correctness of approach
- Completeness of parameters
- Error handling and robustness
- Maintainability and clarity
- Performance and efficiency

Response Format Requirements:
Always respond with valid JSON containing all required fields:
- overall_score: float between 0.0 and 1.0
- recommendation: exactly one of "APPROVE", "REJECT", "CONDITIONAL", "REVISE"
- confidence: exactly one of "very_low", "low", "medium", "high", "very_high"
- reasoning: detailed explanation (2-3 sentences minimum)
- criterion_scores: array with all requested criteria
- improvement_suggestions: array of specific, actionable suggestions
- alternatives_analysis: array analyzing provided alternatives

Be thorough, objective, and focused on enabling safe, effective workflow execution."""
