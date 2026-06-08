# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Self-Evaluation Quality Gate

Issue #4687: Lightweight self-evaluation pass that runs after agent output is
produced, before a task transitions to COMPLETED.  Scores the response for
confidence and completeness; if the score falls below a configurable threshold
the result is a FAILED transition with an eval_reason in metadata.

References:
    AI Scientist v2 (Sakana AI / Nature 2026) — automated reviewer achieves
    69% balanced accuracy vs. human reviewers using a similar confidence pass.
"""

from dataclasses import dataclass
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Default confidence threshold (0.0 – 1.0).  Tasks whose score falls below
# this value are marked FAILED instead of COMPLETED.
DEFAULT_EVAL_THRESHOLD: float = 0.6

# Signals that hint the agent could not answer the question.
_UNCERTAINTY_PHRASES = frozenset(
    {
        "i don't know",
        "i do not know",
        "i'm not sure",
        "i am not sure",
        "i cannot",
        "i can't",
        "unable to",
        "not able to",
        "no information",
        "i have no",
        "unclear",
        "uncertain",
        "sorry, i",
        "apologies, i",
    }
)

# Very short responses (character count) are treated as incomplete.
_MIN_RESPONSE_CHARS = 20


@dataclass
class EvalResult:
    """Outcome of a self-evaluation pass."""

    passed: bool
    confidence: float  # 0.0 – 1.0
    eval_reason: str


def _score_response(response_text: str, input_text: str) -> float:
    """Return a heuristic confidence score in [0.0, 1.0].

    The heuristic is intentionally cheap (no LLM call) so it adds negligible
    latency to the task lifecycle.  It penalises:
      - Very short responses (likely empty / error dumps)
      - Uncertainty phrase matches in the response
      - Responses shorter than the input (input ignored, essentially)
    """
    text = response_text.strip()

    # Hard floor: near-empty response
    if len(text) < _MIN_RESPONSE_CHARS:
        return 0.0

    score = 1.0

    # Penalise each distinct uncertainty phrase found in the lower-cased text
    lower = text.lower()
    penalty_per_phrase = 0.2
    for phrase in _UNCERTAINTY_PHRASES:
        if phrase in lower:
            score -= penalty_per_phrase
            if score <= 0.0:
                return 0.0

    # Mild penalty when response is shorter than the input (often a sign the
    # agent side-stepped the question rather than addressing it).
    if len(text) < len(input_text):
        score -= 0.1

    return max(0.0, min(1.0, round(score, 4)))


async def evaluate_task_output(
    input_text: str,
    response_text: str,
    metadata: Dict[str, Any],
    threshold: float = DEFAULT_EVAL_THRESHOLD,
) -> EvalResult:
    """Run the self-evaluation quality gate.

    Args:
        input_text: Original task input submitted by the caller.
        response_text: Primary text artifact produced by the agent.
        metadata: Routing/execution metadata dict (may be empty).
        threshold: Minimum confidence required for COMPLETED.

    Returns:
        EvalResult with passed=True when confidence >= threshold.
    """
    confidence = _score_response(response_text, input_text)

    if confidence >= threshold:
        logger.debug("Self-eval PASSED (confidence=%.4f, threshold=%.4f)", confidence, threshold)
        return EvalResult(
            passed=True,
            confidence=confidence,
            eval_reason="",
        )

    reason = (
        f"Self-evaluation failed: confidence {confidence:.4f} below threshold "
        f"{threshold:.4f}. Response may be incomplete or uncertain."
    )
    logger.warning(
        "Self-eval FAILED (confidence=%.4f, threshold=%.4f): %s",
        confidence,
        threshold,
        reason,
    )
    return EvalResult(passed=False, confidence=confidence, eval_reason=reason)
