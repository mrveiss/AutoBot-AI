# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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


class ReflectionVerdict(Enum):
    """Outcome of a self-reflection evaluation."""

    ACCEPT = auto()  # Response is good enough — proceed
    REFINE = auto()  # Response needs improvement — recurse
    FAIL = auto()  # Unable to evaluate — fall through


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
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for event stream / logging."""
        return {
            "verdict": self.verdict.name,
            "quality_score": self.quality_score,
            "critique": self.critique,
            "refinement_hint": self.refinement_hint,
            "iteration": self.iteration,
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
    quality_threshold: float = 0.7
    complexity_gate: float = 0.7
    model: str = "llama3.2:latest"
    temperature: float = 0.2
    max_eval_tokens: int = 512
    timeout_ms: int = 10000
