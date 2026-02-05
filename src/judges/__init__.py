# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
LLM-as-Judge Framework for AutoBot

This module provides the core framework for implementing LLM-based decision making,
quality assessment, and arbitration throughout the AutoBot system.

Key Principles:
- Transparent reasoning with confidence scores
- Multi-criteria evaluation with structured outputs
- Context-aware decision making
- Explainable AI for trust and debugging
- Feedback loops for continuous improvement
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class JudgmentConfidence(Enum):
    """Confidence levels for LLM judgments"""

    VERY_LOW = "very_low"  # 0-20%
    LOW = "low"  # 21-40%
    MEDIUM = "medium"  # 41-60%
    HIGH = "high"  # 61-80%
    VERY_HIGH = "very_high"  # 81-100%


class JudgmentDimension(Enum):
    """Dimensions for multi-criteria evaluation"""

    QUALITY = "quality"
    SAFETY = "safety"
    RELEVANCE = "relevance"
    COMPLETENESS = "completeness"
    ACCURACY = "accuracy"
    EFFICIENCY = "efficiency"
    SECURITY = "security"
    CONSISTENCY = "consistency"
    FEASIBILITY = "feasibility"
    COMPLIANCE = "compliance"


@dataclass
class CriterionScore:
    """Score for a specific evaluation criterion"""

    dimension: JudgmentDimension
    score: float  # 0.0 to 1.0
    confidence: JudgmentConfidence
    reasoning: str
    evidence: List[str]


@dataclass
class JudgmentResult:
    """Complete judgment result with reasoning and metadata"""

    subject_id: str
    judge_type: str
    timestamp: datetime

    # Overall judgment
    overall_score: float  # 0.0 to 1.0
    recommendation: str  # APPROVE, REJECT, CONDITIONAL, REVISE
    confidence: JudgmentConfidence

    # Detailed evaluation
    criterion_scores: List[CriterionScore]
    reasoning: str
    alternatives_considered: List[Dict[str, Any]]
    improvement_suggestions: List[str]

    # Metadata
    context_used: Dict[str, Any]
    processing_time_ms: float
    llm_model_used: str


class BaseLLMJudge:
    """Base class for all LLM-based judges in AutoBot"""

    def __init__(self, judge_type: str, llm_interface=None):
        """Initialize base judge with type identifier and optional LLM interface."""
        self.judge_type = judge_type
        self.llm_interface = llm_interface
        self.judgment_history: List[JudgmentResult] = []

    async def make_judgment(
        self,
        subject: Any,
        criteria: List[JudgmentDimension],
        context: Dict[str, Any],
        alternatives: Optional[List[Any]] = None,
        **kwargs,
    ) -> JudgmentResult:
        """Make a structured judgment with multi-criteria evaluation. Issue #620.

        Args:
            subject: The item being judged
            criteria: List of dimensions to evaluate
            context: Relevant context for decision making
            alternatives: Alternative options to compare against
            **kwargs: Additional judge-specific parameters

        Returns:
            JudgmentResult with detailed evaluation and reasoning
        """
        start_time = datetime.now()

        try:
            judgment_prompt = await self._prepare_judgment_prompt(
                subject, criteria, context, alternatives, **kwargs
            )
            llm_response = await self._get_llm_evaluation(judgment_prompt)
            judgment_result = await self._parse_llm_response(
                llm_response, subject, criteria, context, alternatives
            )
            return await self._finalize_judgment_result(judgment_result, start_time)

        except Exception as e:
            logger.error("Error in %s judgment: %s", self.judge_type, e)
            return await self._create_error_judgment(subject, str(e))

    async def _finalize_judgment_result(
        self, judgment_result: JudgmentResult, start_time: datetime
    ) -> JudgmentResult:
        """Add metadata, store in history, and log the judgment result. Issue #620."""
        judgment_result.judge_type = self.judge_type
        judgment_result.timestamp = start_time
        judgment_result.processing_time_ms = (
            datetime.now() - start_time
        ).total_seconds() * 1000

        self.judgment_history.append(judgment_result)
        await self._log_judgment(judgment_result)

        return judgment_result

    async def _prepare_judgment_prompt(
        self,
        subject: Any,
        criteria: List[JudgmentDimension],
        context: Dict[str, Any],
        alternatives: Optional[List[Any]] = None,
        **kwargs,
    ) -> str:
        """Prepare the prompt for LLM evaluation"""
        raise NotImplementedError("Subclasses must implement _prepare_judgment_prompt")

    async def _get_llm_evaluation(self, prompt: str) -> Dict[str, Any]:
        """Get structured evaluation from LLM"""
        if not self.llm_interface:
            from src.llm_interface import LLMInterface

            self.llm_interface = LLMInterface()

        try:
            response = await self.llm_interface.chat_completion_async(
                messages=[
                    {"role": "system", "content": self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                structured_output=True,
                temperature=0.1,  # Low temperature for consistent judgments
            )

            return response

        except Exception as e:
            logger.error("LLM evaluation failed: %s", e)
            raise

    def _get_system_prompt(self) -> str:
        """Get the system prompt for this judge type"""
        return f"""You are an expert AI judge for the {self.judge_type} domain. Your role is to provide structured, objective evaluations with clear reasoning.

Evaluation Guidelines:
1. Be thorough and analytical in your assessment
2. Provide specific evidence for your scores
3. Consider multiple perspectives and potential risks
4. Give actionable improvement suggestions
5. Be consistent in your evaluation criteria
6. Acknowledge limitations and uncertainties

Response Format:
Always respond with a structured JSON containing:
- overall_score: float (0.0 to 1.0)
- recommendation: string (APPROVE/REJECT/CONDITIONAL/REVISE)
- confidence: string (very_low/low/medium/high/very_high)
- reasoning: string (detailed explanation)
- criterion_scores: array of {{dimension, score, confidence, reasoning, evidence}}
- improvement_suggestions: array of strings
- alternatives_analysis: array of evaluated alternatives

Be precise, objective, and helpful in your judgments."""

    async def _parse_llm_response(
        self,
        llm_response: Dict[str, Any],
        subject: Any,
        criteria: List[JudgmentDimension],
        context: Dict[str, Any],
        alternatives: Optional[List[Any]] = None,
    ) -> JudgmentResult:
        """Parse LLM response into structured JudgmentResult"""
        try:
            # Extract or parse JSON from response
            if isinstance(llm_response, str):
                evaluation = json.loads(llm_response)
            else:
                evaluation = llm_response.get("content", llm_response)

            # Parse criterion scores
            criterion_scores = []
            for criterion_data in evaluation.get("criterion_scores", []):
                criterion_scores.append(
                    CriterionScore(
                        dimension=JudgmentDimension(criterion_data["dimension"]),
                        score=float(criterion_data["score"]),
                        confidence=JudgmentConfidence(criterion_data["confidence"]),
                        reasoning=criterion_data["reasoning"],
                        evidence=criterion_data.get("evidence", []),
                    )
                )

            # Create judgment result
            return JudgmentResult(
                subject_id=str(hash(str(subject))),
                judge_type=self.judge_type,
                timestamp=datetime.now(),
                overall_score=float(evaluation["overall_score"]),
                recommendation=evaluation["recommendation"],
                confidence=JudgmentConfidence(evaluation["confidence"]),
                criterion_scores=criterion_scores,
                reasoning=evaluation["reasoning"],
                alternatives_considered=evaluation.get("alternatives_analysis", []),
                improvement_suggestions=evaluation.get("improvement_suggestions", []),
                context_used=context,
                processing_time_ms=0.0,  # Will be set by caller
                llm_model_used=getattr(self.llm_interface, "current_model", "unknown"),
            )

        except Exception as e:
            logger.error("Failed to parse LLM response: %s", e)
            raise

    async def _log_judgment(self, judgment: JudgmentResult):
        """Log judgment for transparency and auditing"""
        logger.info(
            f"{self.judge_type} Judgment: {judgment.recommendation} "
            f"(score: {judgment.overall_score:.2f}, "
            f"confidence: {judgment.confidence.value})"
        )

        # Log detailed reasoning in debug mode
        logger.debug("Judgment reasoning: %s", judgment.reasoning)
        logger.debug("Improvement suggestions: %s", judgment.improvement_suggestions)

    async def _create_error_judgment(
        self, subject: Any, error_message: str
    ) -> JudgmentResult:
        """Create a judgment result for error cases"""
        return JudgmentResult(
            subject_id=str(hash(str(subject))),
            judge_type=self.judge_type,
            timestamp=datetime.now(),
            overall_score=0.0,
            recommendation="REJECT",
            confidence=JudgmentConfidence.VERY_LOW,
            criterion_scores=[],
            reasoning=f"Error during judgment: {error_message}",
            alternatives_considered=[],
            improvement_suggestions=["Resolve underlying error and retry judgment"],
            context_used={},
            processing_time_ms=0.0,
            llm_model_used="error",
        )

    def get_judgment_history(self, limit: Optional[int] = None) -> List[JudgmentResult]:
        """Get judgment history for analysis and improvement"""
        if limit:
            return self.judgment_history[-limit:]
        return self.judgment_history

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics for this judge"""
        if not self.judgment_history:
            return {"total_judgments": 0}

        total = len(self.judgment_history)
        avg_score = sum(j.overall_score for j in self.judgment_history) / total
        avg_confidence = self._average_confidence()
        avg_processing_time = (
            sum(j.processing_time_ms for j in self.judgment_history) / total
        )

        recommendations = [j.recommendation for j in self.judgment_history]
        recommendation_distribution = {
            rec: recommendations.count(rec) for rec in set(recommendations)
        }

        return {
            "total_judgments": total,
            "average_score": avg_score,
            "average_confidence": avg_confidence,
            "average_processing_time_ms": avg_processing_time,
            "recommendation_distribution": recommendation_distribution,
        }

    def _average_confidence(self) -> str:
        """Calculate average confidence level"""
        confidence_values = {
            JudgmentConfidence.VERY_LOW: 1,
            JudgmentConfidence.LOW: 2,
            JudgmentConfidence.MEDIUM: 3,
            JudgmentConfidence.HIGH: 4,
            JudgmentConfidence.VERY_HIGH: 5,
        }

        avg_value = sum(
            confidence_values[j.confidence] for j in self.judgment_history
        ) / len(self.judgment_history)

        # Convert back to confidence level
        if avg_value <= 1.5:
            return JudgmentConfidence.VERY_LOW.value
        elif avg_value <= 2.5:
            return JudgmentConfidence.LOW.value
        elif avg_value <= 3.5:
            return JudgmentConfidence.MEDIUM.value
        elif avg_value <= 4.5:
            return JudgmentConfidence.HIGH.value
        else:
            return JudgmentConfidence.VERY_HIGH.value
