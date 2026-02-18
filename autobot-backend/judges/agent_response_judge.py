# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Response Quality Judge

Implements LLM-as-Judge for evaluating agent response quality, relevance, and effectiveness.
This judge assesses agent outputs to improve system reliability and user experience.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from constants import AgentThresholds

from . import BaseLLMJudge, JudgmentDimension, JudgmentResult

logger = logging.getLogger(__name__)


class AgentResponseJudge(BaseLLMJudge):
    """Judge for evaluating agent response quality and effectiveness"""

    def __init__(self, llm_interface=None):
        """Initialize agent response judge with quality evaluation thresholds."""
        super().__init__("agent_response", llm_interface)
        # Issue #318: Use centralized constants instead of magic numbers
        self.quality_threshold = AgentThresholds.QUALITY_THRESHOLD
        self.relevance_threshold = AgentThresholds.RELEVANCE_THRESHOLD

    async def evaluate_agent_response(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
        agent_type: str,
        context: Dict[str, Any],
        expected_capabilities: Optional[List[str]] = None,
        user_satisfaction: Optional[float] = None,
    ) -> JudgmentResult:
        """
        Evaluate an agent's response quality

        Args:
            request: The original user request/task
            response: The agent's response
            agent_type: Type of agent (chat, research, security, etc.)
            context: Relevant context for evaluation
            expected_capabilities: What the agent should be able to do
            user_satisfaction: User feedback score if available

        Returns:
            JudgmentResult with detailed evaluation
        """
        # Define evaluation criteria
        criteria = [
            JudgmentDimension.RELEVANCE,
            JudgmentDimension.ACCURACY,
            JudgmentDimension.COMPLETENESS,
            JudgmentDimension.QUALITY,
            JudgmentDimension.CONSISTENCY,
            JudgmentDimension.EFFICIENCY,
        ]

        # Prepare comprehensive context
        eval_context = {
            "request": request,
            "agent_type": agent_type,
            "context": context,
            "expected_capabilities": expected_capabilities or [],
            "user_satisfaction": user_satisfaction,
            "quality_threshold": self.quality_threshold,
            "relevance_threshold": self.relevance_threshold,
        }

        return await self.make_judgment(
            subject=response, criteria=criteria, context=eval_context
        )

    def _build_request_context_section(
        self,
        agent_type: str,
        request: Dict[str, Any],
        response: Any,
        agent_context: Dict[str, Any],
        expected_capabilities: List[str],
        user_satisfaction: Optional[float],
    ) -> str:
        """Issue #665: Extracted from _prepare_judgment_prompt to reduce function length."""
        satisfaction_str = user_satisfaction if user_satisfaction else "Not provided"
        return f"""
Please evaluate the following agent response for quality and effectiveness:

AGENT TYPE: {agent_type}

ORIGINAL REQUEST:
{json.dumps(request, indent=2)}

AGENT RESPONSE TO EVALUATE:
{json.dumps(response, indent=2)}

CONTEXT:
{json.dumps(agent_context, indent=2)}

EXPECTED AGENT CAPABILITIES:
{json.dumps(expected_capabilities, indent=2)}

USER SATISFACTION SCORE: {satisfaction_str}
"""

    def _build_evaluation_criteria_section(self) -> str:
        """Issue #665: Extracted from _prepare_judgment_prompt to reduce function length."""
        return """
EVALUATION CRITERIA:
Please evaluate this response on the following dimensions (score 0.0 to 1.0):

1. RELEVANCE: How well does the response address the original request?
   - Does it answer the specific question asked?
   - Is it focused on the right topic/domain?
   - Does it stay within the agent's intended scope?

2. ACCURACY: How correct and reliable is the information provided?
   - Are facts, data, and statements accurate?
   - Are any claims properly supported?
   - Are there factual errors or misinformation?

3. COMPLETENESS: How thoroughly does the response address the request?
   - Are all parts of the request addressed?
   - Is sufficient detail provided?
   - Are important aspects missing?

4. QUALITY: Overall excellence of the response
   - Is the response well-structured and clear?
   - Is the language appropriate and professional?
   - Does it demonstrate understanding of the task?

5. CONSISTENCY: Internal coherence and alignment with agent behavior
   - Is the response internally consistent?
   - Does it align with the agent's typical behavior?
   - Are there contradictions or confusing elements?

6. EFFICIENCY: Resource utilization and response appropriateness
   - Is the response appropriately concise or detailed?
   - Does it avoid unnecessary complexity?
   - Is the effort proportional to the request?
"""

    def _build_agent_specific_section(
        self, agent_type: str, context: Dict[str, Any]
    ) -> str:
        """Issue #665: Extracted from _prepare_judgment_prompt to reduce function length."""
        relevance_threshold = context.get("relevance_threshold", 0.8)
        quality_threshold = context.get("quality_threshold", 0.7)
        return f"""
AGENT-SPECIFIC EVALUATION FACTORS:

For {agent_type} agents, also consider:
- Domain expertise demonstration
- Appropriate use of tools and capabilities
- Error handling and edge case management
- Communication style matching user needs
- Security and safety considerations

BENCHMARKS:
- Relevance score must be >= {relevance_threshold} for good response
- Quality score must be >= {quality_threshold} for good response

Please provide your evaluation in the required JSON format with:
- Detailed reasoning for each criterion score
- Specific evidence from the response
- Clear overall assessment
- Improvement suggestions for the agent
- Identification of any critical issues

Focus on practical assessment that helps improve agent performance and user experience.
"""

    async def _prepare_judgment_prompt(
        self,
        subject: Any,
        criteria: List[JudgmentDimension],
        context: Dict[str, Any],
        alternatives: Optional[List[Any]] = None,
        **kwargs,
    ) -> str:
        """Prepare the prompt for agent response evaluation."""
        response = subject
        request = context.get("request", {})
        agent_type = context.get("agent_type", "unknown")
        agent_context = context.get("context", {})
        expected_capabilities = context.get("expected_capabilities", [])
        user_satisfaction = context.get("user_satisfaction")

        # Issue #665: Build prompt from extracted helper methods
        prompt_parts = [
            self._build_request_context_section(
                agent_type,
                request,
                response,
                agent_context,
                expected_capabilities,
                user_satisfaction,
            ),
            self._build_evaluation_criteria_section(),
            self._build_agent_specific_section(agent_type, context),
        ]

        return "".join(prompt_parts).strip()

    async def assess_response_quality(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
        agent_type: str,
        context: Dict[str, Any],
    ) -> tuple[bool, float, str]:
        """
        Quick quality assessment for agent responses

        Returns:
            tuple: (is_good_quality: bool, overall_score: float, summary: str)
        """
        try:
            judgment = await self.evaluate_agent_response(
                request, response, agent_type, context
            )

            # Check quality and relevance thresholds
            relevance_score = next(
                (
                    s.score
                    for s in judgment.criterion_scores
                    if s.dimension == JudgmentDimension.RELEVANCE
                ),
                0.0,
            )
            quality_score = next(
                (
                    s.score
                    for s in judgment.criterion_scores
                    if s.dimension == JudgmentDimension.QUALITY
                ),
                0.0,
            )

            is_good = (
                relevance_score >= self.relevance_threshold
                and quality_score >= self.quality_threshold
                and judgment.overall_score >= self.quality_threshold
            )

            summary = (
                f"Quality: {quality_score:.2f}, Relevance: {relevance_score:.2f},"
                f"Overall: {judgment.overall_score:.2f}"
            )

            return is_good, judgment.overall_score, summary

        except Exception as e:
            logger.error("Error in response quality assessment: %s", e)
            return False, 0.0, f"Assessment error: {str(e)}"

    def _build_feedback_by_dimension(self, criterion_scores: List) -> Dict[str, Any]:
        """
        Build detailed feedback dictionary organized by evaluation dimension.

        Args:
            criterion_scores: List of criterion score objects from judgment.

        Returns:
            Dict mapping dimension names to their feedback details.

        Issue #620.
        """
        feedback = {}
        for score in criterion_scores:
            feedback[score.dimension.value] = {
                "score": score.score,
                "confidence": score.confidence.value,
                "reasoning": score.reasoning,
                "evidence": score.evidence,
            }
        return feedback

    def _categorize_scores_by_threshold(
        self, criterion_scores: List, threshold: float, above: bool = True
    ) -> List[str]:
        """
        Categorize dimension scores based on a threshold.

        Args:
            criterion_scores: List of criterion score objects from judgment.
            threshold: Score threshold for categorization.
            above: If True, return dimensions >= threshold; otherwise < threshold.

        Returns:
            List of dimension names matching the criteria.

        Issue #620.
        """
        if above:
            return [
                score.dimension.value
                for score in criterion_scores
                if score.score >= threshold
            ]
        return [
            score.dimension.value
            for score in criterion_scores
            if score.score < threshold
        ]

    async def get_improvement_feedback(
        self,
        request: Dict[str, Any],
        response: Dict[str, Any],
        agent_type: str,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Get detailed improvement feedback for agent responses

        Returns:
            Dict with improvement suggestions and performance metrics
        """
        try:
            judgment = await self.evaluate_agent_response(
                request, response, agent_type, context
            )

            return {
                "overall_assessment": {
                    "score": judgment.overall_score,
                    "recommendation": judgment.recommendation,
                    "confidence": judgment.confidence.value,
                },
                "detailed_feedback": self._build_feedback_by_dimension(
                    judgment.criterion_scores
                ),
                "priority_improvements": self._categorize_scores_by_threshold(
                    judgment.criterion_scores, 0.7, above=False
                ),
                "improvement_suggestions": judgment.improvement_suggestions,
                "strengths": self._categorize_scores_by_threshold(
                    judgment.criterion_scores, 0.8, above=True
                ),
                "areas_for_improvement": self._categorize_scores_by_threshold(
                    judgment.criterion_scores, 0.7, above=False
                ),
                "reasoning": judgment.reasoning,
            }

        except Exception as e:
            logger.error("Error generating improvement feedback: %s", e)
            return {
                "error": str(e),
                "overall_assessment": {"score": 0.0, "recommendation": "ERROR"},
                "improvement_suggestions": ["Resolve evaluation error and retry"],
            }

    async def compare_agent_responses(
        self,
        request: Dict[str, Any],
        responses: List[Dict[str, Any]],
        agent_types: List[str],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Compare multiple agent responses to the same request (Issue #665: refactored).

        Returns:
            Dict with ranked responses and comparative analysis
        """
        try:
            # Evaluate and rank each response
            evaluations = await self._evaluate_all_responses(
                request, responses, agent_types, context
            )
            evaluations.sort(key=lambda x: x["evaluation"].overall_score, reverse=True)

            # Generate comparative insights
            best_eval = evaluations[0]["evaluation"]
            worst_eval = evaluations[-1]["evaluation"]
            dimension_leaders = self._find_dimension_leaders(evaluations)

            return {
                "best_response": evaluations[0],
                "all_evaluations": evaluations,
                "comparative_analysis": {
                    "score_range": {
                        "highest": best_eval.overall_score,
                        "lowest": worst_eval.overall_score,
                        "spread": best_eval.overall_score - worst_eval.overall_score,
                    },
                    "dimension_leaders": dimension_leaders,
                    "consensus_strengths": self._find_consensus_strengths(evaluations),
                    "common_weaknesses": self._find_common_weaknesses(evaluations),
                },
                "recommendation": (
                    f"Best response from {evaluations[0]['agent_type']} agent"
                ),
            }

        except Exception as e:
            logger.error("Error comparing agent responses: %s", e)
            return {
                "error": str(e),
                "best_response": None,
                "recommendation": "Unable to compare responses due to error",
            }

    async def _evaluate_all_responses(
        self,
        request: Dict[str, Any],
        responses: List[Dict[str, Any]],
        agent_types: List[str],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Evaluate all agent responses (Issue #665: extracted helper)."""
        evaluations = []
        for i, (response, agent_type) in enumerate(zip(responses, agent_types)):
            evaluation = await self.evaluate_agent_response(
                request, response, agent_type, context
            )
            evaluations.append(
                {
                    "response_index": i,
                    "agent_type": agent_type,
                    "response": response,
                    "evaluation": evaluation,
                }
            )
        return evaluations

    def _find_dimension_leaders(
        self, evaluations: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Find best performing agent for each dimension (Issue #665: extracted helper)."""
        dimension_leaders = {}
        for dimension in JudgmentDimension:
            best_score = 0.0
            best_agent = None
            for eval_data in evaluations:
                scores = eval_data["evaluation"].criterion_scores
                dim_score = next(
                    (s.score for s in scores if s.dimension == dimension), 0.0
                )
                if dim_score > best_score:
                    best_score = dim_score
                    best_agent = eval_data["agent_type"]

            if best_agent:
                dimension_leaders[dimension.value] = {
                    "agent": best_agent,
                    "score": best_score,
                }
        return dimension_leaders

    def _find_consensus_strengths(self, evaluations: List[Dict]) -> List[str]:
        """Find dimensions where all agents performed well"""
        if not evaluations:
            return []

        strengths = []
        for dimension in JudgmentDimension:
            all_good = True
            for eval_data in evaluations:
                scores = eval_data["evaluation"].criterion_scores
                dim_score = next(
                    (s.score for s in scores if s.dimension == dimension), 0.0
                )
                if dim_score < 0.7:  # Threshold for "good"
                    all_good = False
                    break

            if all_good:
                strengths.append(dimension.value)

        return strengths

    def _find_common_weaknesses(self, evaluations: List[Dict]) -> List[str]:
        """Find dimensions where all agents performed poorly"""
        if not evaluations:
            return []

        weaknesses = []
        for dimension in JudgmentDimension:
            all_weak = True
            for eval_data in evaluations:
                scores = eval_data["evaluation"].criterion_scores
                dim_score = next(
                    (s.score for s in scores if s.dimension == dimension), 0.0
                )
                if dim_score >= 0.7:  # Threshold for "good"
                    all_weak = False
                    break

            if all_weak:
                weaknesses.append(dimension.value)

        return weaknesses

    def _get_system_prompt(self) -> str:
        """Get specialized system prompt for agent response evaluation"""
        return """You are an expert AI judge specializing in evaluating agent response quality and effectiveness. Your role is to assess how well AI agents fulfill user requests and provide valuable assistance.

Your expertise includes:
- Natural language understanding and generation assessment
- Task completion evaluation
- Information accuracy verification
- User experience optimization
- Agent behavior analysis
- Communication effectiveness

Evaluation Guidelines:
1. USER-CENTRIC: Focus on user value and satisfaction
2. CONTEXT-AWARE: Consider the specific agent type and capabilities
3. OBJECTIVE: Base assessments on observable evidence
4. CONSTRUCTIVE: Provide actionable improvement suggestions
5. COMPREHENSIVE: Evaluate all aspects of response quality
6. FAIR: Apply consistent standards across different agents

Key Assessment Areas:
- Does the response directly address what was asked?
- Is the information provided accurate and reliable?
- Is the response complete enough to be useful?
- Is the communication clear and appropriate?
- Does it demonstrate proper understanding of the task?
- Are there any safety, ethical, or quality concerns?

Agent-Specific Considerations:
- Chat agents: Focus on helpfulness, clarity, engagement
- Research agents: Emphasize accuracy, comprehensiveness, source quality
- Security agents: Prioritize safety, compliance, risk assessment
- Code agents: Evaluate correctness, efficiency, best practices
- Task agents: Assess goal achievement, step-by-step clarity

Quality Benchmarks:
- Excellent (0.9-1.0): Exceptional response, exceeds expectations
- Good (0.7-0.8): Solid response, meets user needs well
- Acceptable (0.5-0.6): Basic response, minimally adequate
- Poor (0.3-0.4): Significant issues, limited value
- Unacceptable (0.0-0.2): Major problems, potential harm

Response Format Requirements:
Always respond with valid JSON containing all required fields:
- overall_score: float between 0.0 and 1.0
- recommendation: exactly one of "APPROVE", "REJECT", "CONDITIONAL", "REVISE"
- confidence: exactly one of "very_low", "low", "medium", "high", "very_high"
- reasoning: detailed explanation focusing on user value
- criterion_scores: array with all requested criteria evaluated
- improvement_suggestions: specific, actionable feedback for the agent
- alternatives_analysis: if alternative responses are provided

Be thorough but practical - your evaluation helps improve agent performance and user experience."""
