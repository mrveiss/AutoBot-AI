# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

from autobot_shared.env_utils import env_flag
from autobot_shared.logging_manager import get_logger
from llm_shared.json_utils import extract_json_object as _extract_json_object  # Issue #11520
from llm_shared.types import LLMType
from llm_shared.validated_llm import Completer, complete_validated, validate_against

logger = get_logger(__name__)


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


#: When true, a decision whose judgment could not be read is HELD rather than
#: approved (#17307). Fail-open stays the default -- #1464 chose it so an
#: unavailable LLM does not stall every workflow -- but it is a named policy
#: now, read by every gate that acts on ``llm_model_used == "error"``
#: (``workflow_automation/step_evaluator.py``, ``workflow_step_judge.py``),
#: instead of each one hard-coding approval.
JUDGE_FAIL_CLOSED: bool = env_flag("AUTOBOT_JUDGE_FAIL_CLOSED", False)

#: Sentinel ``llm_model_used`` value an error judgment carries. The gates
#: branch on this string, so it is defined once beside the policy.
ERROR_MODEL_SENTINEL = "error"

#: Reason codes a degraded evaluation result carries so a consumer can tell an
#: approval from a default: no judgment was read, or the evaluator itself
#: failed before judging.
DEGRADATION_JUDGE_UNAVAILABLE = "judge_unavailable"
DEGRADATION_EVALUATION_ERROR = "evaluation_error"


#: Recommendations a judgment may return. ``step_evaluator.APPROVAL_RECOMMENDATIONS``
#: reads these values, so the enum in the schema is what keeps a judge from
#: inventing a fifth one that the gate would silently treat as "not approved".
RECOMMENDATIONS = ("APPROVE", "REJECT", "CONDITIONAL", "REVISE")

#: JSON Schema every judgment reply must satisfy (#17307).
#: Before this, ``_parse_llm_response`` indexed ``overall_score``,
#: ``recommendation`` and ``confidence`` straight out of a single-shot reply --
#: any key or enum drift raised, became an error judgment, and
#: ``workflow_automation/step_evaluator.py:208`` turned that into approval of
#: the step the judge was asked to gate. The schema is now sent to the
#: provider (native schema mode, #17305) *and* validated here, with a retry
#: that feeds the validation error back to the model before anything fails.
JUDGMENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "recommendation": {"type": "string", "enum": list(RECOMMENDATIONS)},
        "confidence": {"type": "string", "enum": [c.value for c in JudgmentConfidence]},
        "reasoning": {"type": "string"},
        "criterion_scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string", "enum": [d.value for d in JudgmentDimension]},
                    "score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "confidence": {"type": "string", "enum": [c.value for c in JudgmentConfidence]},
                    "reasoning": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["dimension", "score", "confidence", "reasoning"],
            },
        },
        "improvement_suggestions": {"type": "array", "items": {"type": "string"}},
        "alternatives_analysis": {"type": "array", "items": {"type": "object"}},
    },
    "required": ["overall_score", "recommendation", "confidence", "reasoning"],
}


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


def _response_text(llm_response: Any) -> str:
    """Return the text of an LLMResponse, a plain str, or a legacy dict reply."""
    if hasattr(llm_response, "content"):
        return llm_response.content or ""
    if isinstance(llm_response, str):
        return llm_response
    return str(llm_response.get("content", ""))


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
        alternatives: List[Any] | None = None,
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
        start_time = datetime.now(tz=timezone.utc)

        try:
            judgment_prompt = await self._prepare_judgment_prompt(subject, criteria, context, alternatives, **kwargs)
            # #17307: one retry-and-validate loop, shared with structured_ops
            # and the decision seam. A reply that does not satisfy
            # JUDGMENT_SCHEMA is corrected against the schema and only then
            # allowed to fail -- it is never indexed and never guessed at.
            payload = await complete_validated(
                self._get_system_prompt(),
                judgment_prompt,
                JUDGMENT_SCHEMA,
                completer=self._judgment_completer(JUDGMENT_SCHEMA),
                label=f"judges.{self.judge_type}",
            )
            judgment_result = self._judgment_from_payload(
                payload if isinstance(payload, dict) else payload.model_dump(),
                subject,
                context,
            )
            return await self._finalize_judgment_result(judgment_result, start_time)

        except Exception as e:
            logger.error("Error in %s judgment: %s", self.judge_type, e)
            # Surface the underlying error so operators can diagnose the failure
            # rather than swallowing it behind a generic message (#1464, #10681).
            return await self._create_error_judgment(subject, f"Judgment evaluation failed: {e}")

    async def _finalize_judgment_result(self, judgment_result: JudgmentResult, start_time: datetime) -> JudgmentResult:
        """Add metadata, store in history, and log the judgment result. Issue #620."""
        judgment_result.judge_type = self.judge_type
        judgment_result.timestamp = start_time
        judgment_result.processing_time_ms = (datetime.now(tz=timezone.utc) - start_time).total_seconds() * 1000

        self.judgment_history.append(judgment_result)
        await self._log_judgment(judgment_result)

        return judgment_result

    async def _prepare_judgment_prompt(
        self,
        subject: Any,
        criteria: List[JudgmentDimension],
        context: Dict[str, Any],
        alternatives: List[Any] | None = None,
        **kwargs,
    ) -> str:
        """Prepare the prompt for LLM evaluation"""
        raise NotImplementedError("Subclasses must implement _prepare_judgment_prompt")

    def _judgment_completer(self, schema: Dict[str, Any]) -> Completer:
        """Return the completer the validated loop calls for this judge (#17307).

        The transport stays ``_get_llm_evaluation`` -- subclasses and the
        #10672 structured-output assertion both address that method -- so this
        only adapts it to the (system, user) -> text shape the loop wants.
        """

        async def _complete(system_prompt: str, user_prompt: str) -> str:
            response = await self._get_llm_evaluation(user_prompt, system_prompt=system_prompt, json_schema=schema)
            return _response_text(response)

        return _complete

    async def _get_llm_evaluation(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        json_schema: Dict[str, Any] | None = None,
    ) -> Any:
        """Get structured evaluation from LLM.

        #17307: ``json_schema`` is forwarded so a provider with a native
        schema mode constrains the reply (#17305) instead of the retry loop
        having to correct it afterwards.
        """
        if not self.llm_interface:
            from services.llm_service import get_llm_service  # Phase 2D #3185

            self.llm_interface = get_llm_service()

        try:
            chat_kwargs: Dict[str, Any] = {
                "llm_type": LLMType.ANALYSIS,
                "temperature": 0.1,  # Low temperature for consistent judgments
                "structured_output": True,  # #10672: force valid JSON so judgments aren't dropped
            }
            if json_schema is not None:
                chat_kwargs["json_schema"] = json_schema
            response = await self.llm_interface.chat(
                [
                    {"role": "system", "content": system_prompt or self._get_system_prompt()},
                    {"role": "user", "content": prompt},
                ],
                **chat_kwargs,
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

    def _judgment_from_payload(
        self,
        payload: Dict[str, Any],
        subject: Any,
        context: Dict[str, Any],
    ) -> JudgmentResult:
        """Build a JudgmentResult from a schema-valid judgment payload (#17307).

        Every key read here is either required by ``JUDGMENT_SCHEMA`` or
        defaulted, so this method cannot raise on key drift -- the drift is
        caught, retried and reported by the validated loop instead of arriving
        as a ``KeyError`` that the gate reads as approval.
        """
        criterion_scores = [
            CriterionScore(
                dimension=JudgmentDimension(item["dimension"]),
                score=float(item["score"]),
                confidence=JudgmentConfidence(item["confidence"]),
                reasoning=item["reasoning"],
                evidence=item.get("evidence", []),
            )
            for item in payload.get("criterion_scores", [])
        ]
        return JudgmentResult(
            subject_id=str(hash(str(subject))),
            judge_type=self.judge_type,
            timestamp=datetime.now(tz=timezone.utc),
            overall_score=float(payload["overall_score"]),
            recommendation=payload["recommendation"],
            confidence=JudgmentConfidence(payload["confidence"]),
            criterion_scores=criterion_scores,
            reasoning=payload["reasoning"],
            alternatives_considered=payload.get("alternatives_analysis", []),
            improvement_suggestions=payload.get("improvement_suggestions", []),
            context_used=context,
            processing_time_ms=0.0,  # Will be set by caller
            llm_model_used=getattr(self.llm_interface, "current_model", "unknown"),
        )

    async def _parse_llm_response(
        self,
        llm_response: Any,
        subject: Any,
        criteria: List[JudgmentDimension],
        context: Dict[str, Any],
        alternatives: List[Any] | None = None,
    ) -> JudgmentResult:
        """Validate a raw judge reply against JUDGMENT_SCHEMA, then convert it.

        Kept for callers holding a response object of their own; ``make_judgment``
        goes through the validated loop, which retries a bad reply before this
        point is ever reached. *criteria* and *alternatives* are part of the
        original signature and are not read -- the reply carries its own
        dimensions.
        """
        payload = validate_against(_extract_json_object(_response_text(llm_response)), JUDGMENT_SCHEMA)
        return self._judgment_from_payload(
            payload if isinstance(payload, dict) else payload.model_dump(), subject, context
        )

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

    async def _create_error_judgment(self, subject: Any, error_message: str) -> JudgmentResult:
        """Create a judgment result for error cases"""
        return JudgmentResult(
            subject_id=str(hash(str(subject))),
            judge_type=self.judge_type,
            timestamp=datetime.now(tz=timezone.utc),
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

    def get_judgment_history(self, limit: int | None = None) -> List[JudgmentResult]:
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
        avg_processing_time = sum(j.processing_time_ms for j in self.judgment_history) / total

        recommendations = [j.recommendation for j in self.judgment_history]
        recommendation_distribution = {rec: recommendations.count(rec) for rec in set(recommendations)}

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

        avg_value = sum(confidence_values[j.confidence] for j in self.judgment_history) / len(self.judgment_history)

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
