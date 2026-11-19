# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Recursive Language Model (RLM) Types

Type definitions for the RLM subsystem. RLMs allow a language model to
recursively call itself to evaluate and refine its own responses,
improving quality on complex queries.

Issue #1373: Initial RLM prototype.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Any, Dict

from autobot_shared.ssot_config import DEFAULT_LLM_MODEL
from autobot_shared.ssot_constants import AgentThresholds
from autobot_shared.time_utils import now_utc
from llm_shared.quality_judgment import QualityAssessment


class ReflectionVerdict(Enum):
    """Outcome of a self-reflection evaluation."""

    ACCEPT = auto()  # Response is good enough — proceed
    REFINE = auto()  # Response needs improvement — recurse
    FAIL = auto()  # Hard failure (unused; retained for backwards-compat).
    # #6697: evaluator infrastructure error (LLM down, parse error, etc.).
    # Callers can distinguish "evaluator broke" from "response was bad"; the graph
    # does NOT score it -- a result with ``evaluator_failed`` is evaluated once more, then the reply
    # is kept unverified (#21845, ``chat_workflow/reflection_gate.py``).
    INDETERMINATE = auto()


#: The judges' ``recommendation`` string for each reflection verdict (#16133):
#: one vocabulary, two spellings. ``INDETERMINATE`` has no recommendation --
#: nothing was judged -- and the judges' error judgment is a REJECT with zero
#: confidence, which is deliberately not the same thing.
VERDICT_RECOMMENDATION: Dict[ReflectionVerdict, str] = {
    ReflectionVerdict.ACCEPT: "APPROVE",
    ReflectionVerdict.REFINE: "REVISE",
    ReflectionVerdict.FAIL: "REJECT",
}


@dataclass
class ReflectionResult:
    """Result of one self-reflection pass.

    Attributes:
        verdict: Whether to accept, refine, or fail through.
        quality_score: 0.0–1.0 estimate of response quality.
        critique: Free-text explanation of what's lacking.
        refinement_hint: Suggested focus for the next LLM pass.
        iteration: Which reflection pass produced this (1-based).
    """

    verdict: ReflectionVerdict
    quality_score: float
    critique: str = ""
    refinement_hint: str = ""
    iteration: int = 1
    timestamp: datetime = field(default_factory=now_utc)
    #: The evaluator broke (transport, timeout, unreadable reply): there is NO reading of the response (#21845).
    evaluator_failed: bool = False

    def assessment(self, threshold: float | None = None) -> QualityAssessment:
        """Project onto the shared quality view (#16133)."""
        return QualityAssessment(
            score=self.quality_score,
            critique=self.critique,
            hint=self.refinement_hint,
            threshold=threshold,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for event stream / logging."""
        return {
            "verdict": self.verdict.name,
            "quality_score": self.quality_score,
            "critique": self.critique,
            "refinement_hint": self.refinement_hint,
            "iteration": self.iteration,
            "evaluator_failed": self.evaluator_failed,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class RLMConfig:
    """Configuration for the RLM subsystem.

    Attributes:
        enabled: Master switch — when False the graph skips reflection.
        max_reflections: Hard ceiling on recursive refinement passes.
        quality_threshold: Minimum quality_score to accept a response.
        complexity_gate: Minimum query complexity to trigger reflection
            (avoids overhead on trivial queries).
        model: Ollama model used for the evaluator LLM call.
        temperature: Sampling temperature for the evaluator.
        max_eval_tokens: Token budget for the evaluator response.
        timeout_ms: Per-call timeout for the evaluator LLM request.
    """

    enabled: bool = True
    max_reflections: int = 3
    quality_threshold: float = AgentThresholds.QUALITY_THRESHOLD  # #19730
    complexity_gate: float = 0.7
    model: str = DEFAULT_LLM_MODEL
    temperature: float = 0.2
    max_eval_tokens: int = 512
    timeout_ms: int = 10000
