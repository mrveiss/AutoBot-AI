# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Multi-Agent Arbitrator Judge

Implements LLM-as-Judge for coordinating decisions between multiple agents,
resolving conflicts, and selecting optimal agent responses in multi-agent scenarios.
"""

import json
import logging
from typing import Any, Dict, FrozenSet, List, Optional

from src.constants import AgentThresholds

from . import BaseLLMJudge, JudgmentDimension, JudgmentResult

logger = logging.getLogger(__name__)

# Issue #380: Module-level frozenset for approval recommendations
_APPROVAL_RECOMMENDATIONS: FrozenSet[str] = frozenset({"APPROVE", "CONDITIONAL"})

# Issue #398: Module-level constant for arbitration criteria documentation
_ARBITRATION_CRITERIA_TEMPLATE = """
ARBITRATION CRITERIA:
Please evaluate and compare these responses on the following dimensions (score 0.0 to 1.0):

1. QUALITY: Overall excellence and usefulness of each response
   - Is the response well-structured and clear?
   - Does it demonstrate proper understanding?
   - Is the quality consistent with user expectations?

2. RELEVANCE: How well each response addresses the user request
   - Does it directly answer what was asked?
   - Is it focused on the right topic/domain?
   - Does it stay within appropriate scope?

3. ACCURACY: Correctness and reliability of information
   - Are facts, data, and statements accurate?
   - Are claims properly supported?
   - Are there factual errors or misinformation?

4. COMPLETENESS: Thoroughness in addressing the request
   - Are all parts of the request addressed?
   - Is sufficient detail provided?
   - Are important aspects missing?

5. CONSISTENCY: Internal coherence and logical flow
   - Is each response internally consistent?
   - Do responses align with expected agent behavior?
   - Are there contradictions between responses?

6. EFFICIENCY: Appropriateness and resource utilization
   - Is the response appropriately concise or detailed?
   - Does it avoid unnecessary complexity?
   - Is the effort proportional to the request?

ARBITRATION GOALS:
- Select the BEST OVERALL response for the user
- Identify any significant conflicts or contradictions
- Recommend the most appropriate agent for this type of request
- Suggest improvements for future multi-agent coordination
"""

# Issue #620: Module-level constant for conflict analysis template
_CONFLICT_ANALYSIS_TEMPLATE = """
CONFLICT ANALYSIS REQUIREMENTS:

1. CONSISTENCY CHECK: Identify contradictions between responses
   - Do agents provide conflicting information?
   - Are there incompatible recommendations?
   - Do responses contradict each other's assumptions?

2. ACCURACY VERIFICATION: Check for factual disagreements
   - Which agents provide more accurate information?
   - Are there verifiable factual conflicts?
   - Which claims are better supported?

3. COMPLETENESS COMPARISON: Assess coverage differences
   - Do some agents miss important aspects others cover?
   - Are there significant gaps in some responses?
   - Which response is most comprehensive?

CONFLICT SEVERITY LEVELS:
- HIGH: Direct contradictions, incompatible actions, factual conflicts
- MEDIUM: Different approaches, varying priorities, partial disagreements
- LOW: Minor differences in emphasis, style, or detail level

Please provide detailed conflict analysis in the required JSON format with:
- Overall consistency score (0.0 to 1.0)
- Specific conflicts identified with evidence
- Severity assessment for each conflict
- Recommendations for conflict resolution
- Suggested improvements for agent coordination

Focus on identifying real conflicts that would confuse or mislead users, not minor stylistic differences.
"""


class MultiAgentArbitrator(BaseLLMJudge):
    """Judge for arbitrating between multiple agent responses and coordinating agent interactions"""

    def __init__(self, llm_interface=None):
        """Initialize arbitrator with consensus thresholds and dimension weights."""
        super().__init__("multi_agent_arbitrator", llm_interface)
        # Issue #318: Use centralized constants instead of magic numbers
        self.consensus_threshold = AgentThresholds.CONSENSUS_THRESHOLD
        self.quality_weight = AgentThresholds.QUALITY_WEIGHT
        self.relevance_weight = AgentThresholds.RELEVANCE_WEIGHT
        self.consistency_weight = AgentThresholds.CONSISTENCY_WEIGHT

    async def arbitrate_agent_responses(
        self,
        user_request: Dict[str, Any],
        agent_responses: List[Dict[str, Any]],
        agent_types: List[str],
        context: Dict[str, Any],
        conflict_resolution_strategy: str = "quality_first",
    ) -> JudgmentResult:
        """
        Arbitrate between multiple agent responses to select the best one

        Args:
            user_request: The original user request
            agent_responses: List of responses from different agents
            agent_types: List of agent types corresponding to responses
            context: Relevant context for arbitration
            conflict_resolution_strategy: Strategy for resolving conflicts

        Returns:
            JudgmentResult with selected best response and reasoning
        """
        # Define evaluation criteria for multi-agent arbitration
        criteria = [
            JudgmentDimension.QUALITY,
            JudgmentDimension.RELEVANCE,
            JudgmentDimension.ACCURACY,
            JudgmentDimension.COMPLETENESS,
            JudgmentDimension.CONSISTENCY,
            JudgmentDimension.EFFICIENCY,
        ]

        # Prepare comprehensive arbitration context
        arbitration_context = {
            "user_request": user_request,
            "agent_types": agent_types,
            "conflict_resolution_strategy": conflict_resolution_strategy,
            "context": context,
            "consensus_threshold": self.consensus_threshold,
            "response_count": len(agent_responses),
            "weights": {
                "quality": self.quality_weight,
                "relevance": self.relevance_weight,
                "consistency": self.consistency_weight,
            },
        }

        # Create combined subject for evaluation
        combined_subject = {"responses": agent_responses, "agent_types": agent_types}

        return await self.make_judgment(
            subject=combined_subject,
            criteria=criteria,
            context=arbitration_context,
            alternatives=agent_responses,
        )

    def _get_consistency_score(self, judgment: JudgmentResult) -> float:
        """Extract consistency score from judgment criterion scores. Issue #620."""
        return next(
            (
                s.score
                for s in judgment.criterion_scores
                if s.dimension == JudgmentDimension.CONSISTENCY
            ),
            0.0,
        )

    def _determine_conflict_severity(self, consistency_score: float) -> str:
        """Determine conflict severity based on consistency score. Issue #620."""
        if consistency_score < 0.5:
            return "high"
        elif consistency_score < 0.7:
            return "medium"
        return "low"

    def _build_conflict_result(
        self, judgment: JudgmentResult, consistency_score: float
    ) -> Dict[str, Any]:
        """Build conflict detection result dictionary. Issue #620."""
        return {
            "has_conflicts": consistency_score < self.consensus_threshold,
            "consistency_score": consistency_score,
            "conflict_severity": self._determine_conflict_severity(consistency_score),
            "conflicting_areas": self._identify_conflicting_areas(judgment),
            "resolution_suggestions": judgment.improvement_suggestions,
            "detailed_analysis": judgment.reasoning,
        }

    async def detect_agent_conflicts(
        self,
        agent_responses: List[Dict[str, Any]],
        agent_types: List[str],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Detect conflicts and contradictions between agent responses. Issue #620.

        Returns:
            Dict with conflict analysis and resolution suggestions
        """
        try:
            criteria = [
                JudgmentDimension.CONSISTENCY,
                JudgmentDimension.ACCURACY,
                JudgmentDimension.COMPLETENESS,
            ]
            conflict_context = {
                "agent_types": agent_types,
                "context": context,
                "analysis_type": "conflict_detection",
                "response_count": len(agent_responses),
            }

            judgment = await self.make_judgment(
                subject={"responses": agent_responses, "agent_types": agent_types},
                criteria=criteria,
                context=conflict_context,
            )

            consistency_score = self._get_consistency_score(judgment)
            return self._build_conflict_result(judgment, consistency_score)

        except Exception as e:
            logger.error("Error detecting agent conflicts: %s", e)
            return {
                "has_conflicts": False,
                "error": str(e),
                "conflict_severity": "unknown",
            }

    async def _evaluate_responses_for_consensus(
        self,
        user_request: Dict[str, Any],
        agent_responses: List[Dict[str, Any]],
        agent_types: List[str],
        context: Dict[str, Any],
        consensus_method: str,
    ) -> List[Dict[str, Any]]:
        """Evaluate all agent responses for consensus building.

        Issue #665: Extracted from coordinate_agent_consensus to reduce function length.

        Returns:
            List of evaluation dictionaries with response, agent_type, evaluation, and index.
        """
        evaluations = []
        for i, (response, agent_type) in enumerate(zip(agent_responses, agent_types)):
            eval_context = {
                "user_request": user_request,
                "agent_type": agent_type,
                "context": context,
                "consensus_method": consensus_method,
                "response_index": i,
            }
            judgment = await self.make_judgment(
                subject=response,
                criteria=[
                    JudgmentDimension.QUALITY,
                    JudgmentDimension.RELEVANCE,
                    JudgmentDimension.CONSISTENCY,
                ],
                context=eval_context,
            )
            evaluations.append(
                {
                    "response": response,
                    "agent_type": agent_type,
                    "evaluation": judgment,
                    "index": i,
                }
            )
        return evaluations

    def _select_consensus_response(
        self, evaluations: List[Dict[str, Any]], consensus_method: str
    ) -> Dict[str, Any]:
        """Select consensus response based on method.

        Issue #665: Extracted from coordinate_agent_consensus to reduce function length.
        """
        if consensus_method == "weighted_voting":
            return self._weighted_voting_consensus(evaluations)
        elif consensus_method == "highest_quality":
            return self._highest_quality_consensus(evaluations)
        elif consensus_method == "agreement_threshold":
            return self._agreement_threshold_consensus(evaluations)
        return self._simple_majority_consensus(evaluations)

    async def coordinate_agent_consensus(
        self,
        user_request: Dict[str, Any],
        agent_responses: List[Dict[str, Any]],
        agent_types: List[str],
        context: Dict[str, Any],
        consensus_method: str = "weighted_voting",
    ) -> Dict[str, Any]:
        """Coordinate agents to reach consensus. Issue #665: Refactored with helpers."""
        try:
            evaluations = await self._evaluate_responses_for_consensus(
                user_request, agent_responses, agent_types, context, consensus_method
            )
            consensus_response = self._select_consensus_response(
                evaluations, consensus_method
            )
            consensus_confidence = self._calculate_consensus_confidence(evaluations)

            return {
                "consensus_response": consensus_response["response"],
                "selected_agent": consensus_response["agent_type"],
                "consensus_confidence": consensus_confidence,
                "consensus_method": consensus_method,
                "evaluation_summary": {
                    "total_responses": len(evaluations),
                    "average_quality": sum(
                        e["evaluation"].overall_score for e in evaluations
                    )
                    / len(evaluations),
                    "agreement_level": consensus_confidence,
                },
                "detailed_evaluations": evaluations,
            }
        except Exception as e:
            logger.error("Error coordinating agent consensus: %s", e)
            return {
                "consensus_response": None,
                "error": str(e),
                "consensus_confidence": 0.0,
            }

    def _build_response_sections(
        self,
        responses: List[Dict[str, Any]],
        agent_types: List[str],
    ) -> str:
        """
        Build formatted response sections for arbitration prompt.

        Issue #620.
        """
        response_sections = [
            f"RESPONSE {i+1} - {agent_type.upper()} AGENT:\n{json.dumps(response, indent=2)}"
            for i, (response, agent_type) in enumerate(zip(responses, agent_types), 1)
        ]
        return "\n" + "\n\n".join(response_sections) + "\n\n"

    def _build_arbitration_footer(self, context: Dict[str, Any]) -> str:
        """
        Build the footer section of the arbitration prompt with weights and instructions.

        Issue #620.
        """
        weights = context.get("weights", {})
        return f"""
CONFLICT RESOLUTION STRATEGY: {context.get('conflict_resolution_strategy', 'quality_first')}

DECISION WEIGHTS:
- Quality Weight: {weights.get('quality', 0.4)}
- Relevance Weight: {weights.get('relevance', 0.3)}
- Consistency Weight: {weights.get('consistency', 0.3)}

Please provide your arbitration in the required JSON format with:
- Clear recommendation for which response is best
- Detailed reasoning comparing all responses
- Identification of conflicts or agreements between agents
- Specific evidence supporting your decision
- Improvement suggestions for multi-agent coordination
- Analysis of each agent's strengths for this request type

Focus on selecting the response that provides the most value to the user while maintaining accuracy and appropriateness.
"""

    async def _prepare_judgment_prompt(
        self,
        subject: Any,
        criteria: List[JudgmentDimension],
        context: Dict[str, Any],
        alternatives: Optional[List[Any]] = None,
        **kwargs,
    ) -> str:
        """Prepare the prompt for multi-agent arbitration. Issue #620: Refactored with helpers."""
        combined_data = subject
        responses = combined_data.get("responses", [])
        agent_types = combined_data.get("agent_types", [])
        user_request = context.get("user_request", {})
        arbitration_context = context.get("context", {})
        analysis_type = context.get("analysis_type", "arbitration")

        if analysis_type == "conflict_detection":
            return self._prepare_conflict_detection_prompt(
                responses, agent_types, context
            )

        user_request_json = json.dumps(user_request, indent=2)
        arbitration_context_json = json.dumps(arbitration_context, indent=2)

        prompt = f"""
Please arbitrate between multiple agent responses to determine the best response for the user:

USER REQUEST:
{user_request_json}

AGENT RESPONSES TO EVALUATE:
"""
        prompt += self._build_response_sections(responses, agent_types)
        prompt += f"""
ARBITRATION CONTEXT:
{arbitration_context_json}
{_ARBITRATION_CRITERIA_TEMPLATE}"""
        prompt += self._build_arbitration_footer(context)

        return prompt.strip()

    def _prepare_conflict_detection_prompt(
        self,
        responses: List[Dict[str, Any]],
        agent_types: List[str],
        context: Dict[str, Any],
    ) -> str:
        """Prepare prompt specifically for conflict detection. Issue #620."""
        prompt = self._build_conflict_detection_header()
        prompt += self._build_conflict_response_sections(responses, agent_types)
        prompt += _CONFLICT_ANALYSIS_TEMPLATE
        return prompt.strip()

    def _build_conflict_detection_header(self) -> str:
        """Build the header section for conflict detection prompt. Issue #620."""
        return """
Please analyze the following agent responses for conflicts, contradictions, and inconsistencies:

AGENT RESPONSES:
"""

    def _build_conflict_response_sections(
        self,
        responses: List[Dict[str, Any]],
        agent_types: List[str],
    ) -> str:
        """Build formatted response sections for conflict detection. Issue #620."""
        # Build response sections using list + join (O(n)) instead of += (O(n^2))
        response_sections = [
            f"RESPONSE {i+1} - {agent_type.upper()} AGENT:\n{json.dumps(response, indent=2)}"
            for i, (response, agent_type) in enumerate(zip(responses, agent_types), 1)
        ]
        return "\n" + "\n\n".join(response_sections) + "\n\n"

    def _identify_conflicting_areas(self, judgment: JudgmentResult) -> List[str]:
        """Extract conflicting areas from judgment reasoning"""
        conflicting_areas = []

        # Look for consistency issues in criterion scores
        consistency_score = next(
            (
                s
                for s in judgment.criterion_scores
                if s.dimension == JudgmentDimension.CONSISTENCY
            ),
            None,
        )

        if consistency_score and consistency_score.evidence:
            conflicting_areas.extend(consistency_score.evidence)

        # Extract from reasoning if available
        reasoning_lower = judgment.reasoning.lower()
        if "contradict" in reasoning_lower:
            conflicting_areas.append("Direct contradictions identified")
        if "disagree" in reasoning_lower:
            conflicting_areas.append("Agent disagreements detected")
        if "conflict" in reasoning_lower:
            conflicting_areas.append("Conflicting recommendations")

        return conflicting_areas

    def _weighted_voting_consensus(self, evaluations: List[Dict]) -> Dict[str, Any]:
        """Build consensus using weighted voting based on quality scores"""
        # Weight by overall quality score
        best_evaluation = max(evaluations, key=lambda x: x["evaluation"].overall_score)
        return {
            "response": best_evaluation["response"],
            "agent_type": best_evaluation["agent_type"],
            "method": "weighted_voting",
            "winning_score": best_evaluation["evaluation"].overall_score,
        }

    def _highest_quality_consensus(self, evaluations: List[Dict]) -> Dict[str, Any]:
        """Select response with highest quality score"""
        quality_scores = []
        for eval_data in evaluations:
            quality_score = next(
                (
                    s.score
                    for s in eval_data["evaluation"].criterion_scores
                    if s.dimension == JudgmentDimension.QUALITY
                ),
                0.0,
            )
            quality_scores.append((eval_data, quality_score))

        best_evaluation, best_score = max(quality_scores, key=lambda x: x[1])
        return {
            "response": best_evaluation["response"],
            "agent_type": best_evaluation["agent_type"],
            "method": "highest_quality",
            "winning_score": best_score,
        }

    def _agreement_threshold_consensus(self, evaluations: List[Dict]) -> Dict[str, Any]:
        """Build consensus requiring agreement above threshold"""
        # Find response with highest consistency across agents
        consistency_scores = []
        for eval_data in evaluations:
            consistency_score = next(
                (
                    s.score
                    for s in eval_data["evaluation"].criterion_scores
                    if s.dimension == JudgmentDimension.CONSISTENCY
                ),
                0.0,
            )
            consistency_scores.append((eval_data, consistency_score))

        # If no response meets threshold, fall back to highest quality
        threshold_met = [
            e for e, s in consistency_scores if s >= self.consensus_threshold
        ]
        if threshold_met:
            best_evaluation = max(
                threshold_met, key=lambda x: x["evaluation"].overall_score
            )
        else:
            best_evaluation = max(
                evaluations, key=lambda x: x["evaluation"].overall_score
            )

        return {
            "response": best_evaluation["response"],
            "agent_type": best_evaluation["agent_type"],
            "method": "agreement_threshold",
            "threshold_met": bool(threshold_met),
        }

    def _simple_majority_consensus(self, evaluations: List[Dict]) -> Dict[str, Any]:
        """Simple majority based on recommendation approvals"""
        approved_responses = [
            e
            for e in evaluations
            if e["evaluation"].recommendation in _APPROVAL_RECOMMENDATIONS
        ]

        if approved_responses:
            best_evaluation = max(
                approved_responses, key=lambda x: x["evaluation"].overall_score
            )
        else:
            best_evaluation = max(
                evaluations, key=lambda x: x["evaluation"].overall_score
            )

        return {
            "response": best_evaluation["response"],
            "agent_type": best_evaluation["agent_type"],
            "method": "simple_majority",
            "approved_count": len(approved_responses),
        }

    def _calculate_consensus_confidence(self, evaluations: List[Dict]) -> float:
        """Calculate confidence in consensus decision"""
        if not evaluations:
            return 0.0

        scores = [e["evaluation"].overall_score for e in evaluations]

        # High confidence if scores are close together (low variance)
        if len(scores) == 1:
            return scores[0]

        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)

        # Normalize confidence: low variance = high confidence
        confidence = max(0.0, min(1.0, mean_score * (1.0 - min(variance, 1.0))))

        return confidence

    def _get_system_prompt(self) -> str:
        """Get specialized system prompt for multi-agent arbitration"""
        return """You are an expert AI arbitrator specializing in multi-agent coordination and conflict resolution. Your role is to evaluate multiple agent responses, detect conflicts, and select the best overall response for users.

Your expertise includes:
- Multi-agent system coordination
- Conflict detection and resolution
- Response quality assessment across different agent types
- Consensus building and decision arbitration
- Agent performance evaluation and optimization

Arbitration Guidelines:
1. USER-FIRST: Always prioritize user value and satisfaction
2. OBJECTIVE EVALUATION: Base decisions on measurable criteria
3. CONFLICT AWARENESS: Identify and address contradictions between agents
4. AGENT STRENGTHS: Recognize each agent's domain expertise
5. CONSENSUS BUILDING: Seek agreement while maintaining quality
6. TRANSPARENCY: Provide clear reasoning for arbitration decisions

Key Evaluation Areas:
- Which response best addresses the user's actual need?
- Are there conflicts or contradictions between responses?
- Which agent demonstrates the most relevant expertise?
- How can multi-agent coordination be improved?
- What is the overall quality and reliability of each response?

Agent Type Considerations:
- Chat agents: Focus on helpfulness, engagement, user experience
- Research agents: Emphasize accuracy, comprehensiveness, source quality
- Security agents: Prioritize safety, compliance, risk assessment
- Code agents: Evaluate correctness, efficiency, best practices
- Task agents: Assess goal achievement, step clarity, feasibility

Arbitration Strategies:
- Quality First: Select highest quality response regardless of agent type
- Domain Expertise: Prefer agents with relevant domain knowledge
- Consensus Building: Find common ground between agent responses
- Conflict Resolution: Address contradictions and inconsistencies
- User Context: Consider user's specific needs and experience level

Response Format Requirements:
Always respond with valid JSON containing all required fields:
- overall_score: float between 0.0 and 1.0 (representing consensus quality)
- recommendation: exactly one of "APPROVE", "REJECT", "CONDITIONAL", "REVISE"
- confidence: exactly one of "very_low", "low", "medium", "high", "very_high"
- reasoning: detailed explanation of arbitration decision
- criterion_scores: array with all requested criteria evaluated
- improvement_suggestions: specific recommendations for multi-agent coordination
- alternatives_analysis: detailed comparison of all agent responses

Be thorough, fair, and focused on selecting the response that provides the most value to the user while maintaining accuracy and consistency."""
