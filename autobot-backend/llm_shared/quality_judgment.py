# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
The one seam through which an LLM scores quality (#16133).

"Ask an LLM for a 0.0-1.0 score and a critique, compare it with a
threshold" was written twice: the RLM ``ResponseQualityEvaluator`` and the
``BaseLLMJudge`` family each called ``complete_validated`` and then
unwrapped the reply with their own copy of the same line. They answer
different questions and keep their own prompts, schemas, scales and
thresholds; what they share lives here:

* :func:`judge_validated` -- the single call that returns a schema-valid
  reply as a plain dict.
* :class:`QualityAssessment` -- the common (score, critique, hint, threshold
  outcome) view both result types project onto. It is a *view*: the serialized
  ``ReflectionResult`` / ``JudgmentResult`` shapes are unchanged.
* :func:`clamp_score` / :func:`meets_threshold` -- the score arithmetic.
"""

from dataclasses import dataclass
from typing import Any, Dict

from llm_shared.validated_llm import Completer, Schema, complete_validated


async def judge_validated(
    system_prompt: str,
    user_prompt: str,
    schema: Schema,
    *,
    completer: Completer,
    label: str,
) -> Dict[str, Any]:
    """Return a schema-valid judge reply as a dict, or raise ``ValidatedLLMError``."""
    payload = await complete_validated(system_prompt, user_prompt, schema, completer=completer, label=label)
    return payload if isinstance(payload, dict) else payload.model_dump()


def clamp_score(score: float) -> float:
    """Clamp a judge-supplied score into 0.0-1.0."""
    return max(0.0, min(1.0, float(score)))


def meets_threshold(score: float, threshold: float) -> bool:
    """True when *score* is at or above *threshold* (inclusive, as RLM always was)."""
    return score >= threshold


@dataclass(frozen=True)
class QualityAssessment:
    """Common view of an LLM quality judgment: score, critique, threshold outcome."""

    score: float
    critique: str = ""
    hint: str = ""
    threshold: float | None = None

    @property
    def passed(self) -> bool | None:
        """Threshold outcome, or ``None`` when no threshold applies to this judgment."""
        if self.threshold is None:
            return None
        return meets_threshold(self.score, self.threshold)
