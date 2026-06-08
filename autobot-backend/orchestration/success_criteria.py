# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Success Criteria Evaluation for Workflow Orchestrator

Issue #3293: Custom success criteria definitions.
Replaces binary pass/fail with typed, weighted criteria that produce
partial/full/failed evaluation outcomes.
"""

import asyncio
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class SuccessCriteriaType(Enum):
    """Supported success-criteria types."""

    EXIT_CODE = "exit_code"
    OUTPUT_PATTERN = "output_pattern"
    RESOURCE_EXISTS = "resource_exists"
    CUSTOM = "custom"


@dataclass
class SuccessCriteria:
    """A single success criterion attached to a workflow definition.

    Attributes:
        criteria_type: Which kind of check to perform.
        parameters: Type-specific check parameters (see evaluator for keys).
        weight: Relative weight when computing overall score (default 1.0).
        required: When True a failure here forces overall status to ``failed``
            regardless of score (default True).
        description: Human-readable label surfaced in completion data.
    """

    criteria_type: SuccessCriteriaType
    parameters: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    required: bool = True
    description: str = ""


@dataclass
class CriteriaResult:
    """Evaluation outcome for a single criterion."""

    criteria: SuccessCriteria
    passed: bool
    detail: str = ""


@dataclass
class EvaluationResult:
    """Aggregate outcome after evaluating all criteria for a workflow.

    Attributes:
        overall: ``"full"``, ``"partial"``, or ``"failed"``.
        score: Weighted fraction of criteria passed (0.0–1.0).
        results: Per-criterion results.
    """

    overall: str  # "full" | "partial" | "failed"
    score: float
    results: List[CriteriaResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for inclusion in workflow completion data."""
        return {
            "overall": self.overall,
            "score": round(self.score, 4),
            "results": [
                {
                    "type": r.criteria.criteria_type.value,
                    "description": r.criteria.description,
                    "passed": r.passed,
                    "required": r.criteria.required,
                    "weight": r.criteria.weight,
                    "detail": r.detail,
                }
                for r in self.results
            ],
        }


class SuccessCriteriaEvaluator:
    """Evaluates a list of :class:`SuccessCriteria` against workflow results.

    Usage::

        evaluator = SuccessCriteriaEvaluator()
        result = await evaluator.evaluate(plan.structured_criteria, results)
    """

    async def evaluate(
        self,
        criteria_list: List[SuccessCriteria],
        workflow_result: Dict[str, Any],
    ) -> EvaluationResult:
        """Evaluate all criteria and return an :class:`EvaluationResult`.

        Args:
            criteria_list: Criteria attached to the workflow plan.
            workflow_result: Dict produced by the orchestrator after execution.

        Returns:
            :class:`EvaluationResult` with overall status, score, and per-item
            results.
        """
        if not criteria_list:
            return EvaluationResult(overall="full", score=1.0, results=[])

        per_result = list(await asyncio.gather(*[self._evaluate_one(c, workflow_result) for c in criteria_list]))
        return self._aggregate(per_result)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _evaluate_one(
        self,
        criterion: SuccessCriteria,
        workflow_result: Dict[str, Any],
    ) -> CriteriaResult:
        """Dispatch to the appropriate check method."""
        handler = self._handler_for(criterion.criteria_type)
        try:
            passed, detail = await handler(criterion.parameters, workflow_result)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Criteria evaluation raised unexpectedly (type=%s): %s",
                criterion.criteria_type.value,
                exc,
            )
            passed, detail = False, f"Evaluation error: {exc}"
        return CriteriaResult(criteria=criterion, passed=passed, detail=detail)

    def _handler_for(self, criteria_type: SuccessCriteriaType) -> Callable:
        """Return the async check method for a given type."""
        return {
            SuccessCriteriaType.EXIT_CODE: self._check_exit_code,
            SuccessCriteriaType.OUTPUT_PATTERN: self._check_output_pattern,
            SuccessCriteriaType.RESOURCE_EXISTS: self._check_resource_exists,
            SuccessCriteriaType.CUSTOM: self._check_custom,
        }[criteria_type]

    @staticmethod
    async def _check_exit_code(params: Dict[str, Any], result: Dict[str, Any]) -> tuple[bool, str]:
        """Check exit_code == params['expected'] (default 0)."""
        expected = params.get("expected", 0)
        actual = result.get("exit_code")
        if actual is None:
            return False, "exit_code not present in workflow result"
        passed = int(actual) == int(expected)
        return passed, f"exit_code={actual} (expected {expected})"

    @staticmethod
    async def _check_output_pattern(params: Dict[str, Any], result: Dict[str, Any]) -> tuple[bool, str]:
        """Check that params['pattern'] matches result output string."""
        pattern = params.get("pattern", "")
        output = str(result.get("output", ""))
        if not pattern:
            return False, "No pattern specified"
        matched = bool(re.search(pattern, output))
        return matched, f"Pattern '{pattern}' {'matched' if matched else 'not found'}"

    @staticmethod
    async def _check_resource_exists(params: Dict[str, Any], result: Dict[str, Any]) -> tuple[bool, str]:
        """Check that params['key'] is present (and truthy) in result."""
        key = params.get("key", "")
        if not key:
            return False, "No key specified for resource_exists check"
        resources = result.get("resources", result)
        exists = bool(resources.get(key))
        return exists, f"Resource key '{key}' {'found' if exists else 'missing'}"

    @staticmethod
    async def _check_custom(params: Dict[str, Any], result: Dict[str, Any]) -> tuple[bool, str]:
        """Invoke params['fn'](result) -> bool if provided."""
        fn: Callable | None = params.get("fn")
        if fn is None:
            return False, "No callable 'fn' supplied in custom criterion parameters"
        if asyncio.iscoroutinefunction(fn):
            passed = bool(await fn(result))
        else:
            passed = bool(fn(result))
        return passed, "Custom function returned " + str(passed)

    @staticmethod
    def _aggregate(per_result: List[CriteriaResult]) -> EvaluationResult:
        """Compute weighted score and overall status from per-criterion results."""
        total_weight = sum(r.criteria.weight for r in per_result)
        if total_weight == 0:
            return EvaluationResult(overall="full", score=1.0, results=per_result)

        passed_weight = sum(r.criteria.weight for r in per_result if r.passed)
        score = passed_weight / total_weight

        required_failed = any(not r.passed and r.criteria.required for r in per_result)

        if required_failed or score == 0.0:
            overall = "failed"
        elif score >= 1.0:
            overall = "full"
        else:
            overall = "partial"

        return EvaluationResult(overall=overall, score=score, results=per_result)
